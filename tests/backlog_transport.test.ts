/**
 * ZYS-9556: every backlog-review fetch, lookup and mark write shares the parent
 * cancellation and one absolute deadline, bounds header and body consumption,
 * and reports a named failed stage with no later mutation.
 *
 * Transports are injected. A real network is never opened, and no test waits
 * on the wall clock: stalled transports resolve only when the shared signal
 * aborts, which is the event the test awaits.
 */
import { describe, expect, it } from "bun:test";
import { homedir } from "node:os";
import { join } from "node:path";

const tool = await import(join(homedir(), ".omp/agent/tools/manage_linear_backlog.js"));
const { boundBacklogReview, onTransportEvent } = tool;
interface BacklogResponse {
  ok: boolean;
  status: number;
  text(): Promise<string>;
}
type TransportStage = "issue_fetch" | "comment_lookup" | "supersession_lookup" | "list_lookup" | "mark_write";
type BacklogTransport = (request: {
  stage: TransportStage;
  signal: AbortSignal;
  deadline: number;
  variables: Record<string, unknown>;
}, report: (phase: "headers" | "body" | "aborted") => void) => Promise<BacklogResponse>;

const TICKET = "ZYS-9556";
const ISSUE_UUID = "11111111-1111-4111-8111-111111111111";
const NOW = Date.parse("2026-11-17T17:00:00.000Z");

interface Recorded {
  stage: TransportStage;
  signal: AbortSignal;
  deadline: number;
}

function issueNode(description = "body") {
  return {
    id: ISSUE_UUID,
    identifier: TICKET,
    title: "Bound transport",
    url: `https://linear.app/zysys/issue/${TICKET}`,
    description,
    updatedAt: "2026-11-17T16:00:00.000Z",
    createdAt: "2026-11-17T15:00:00.000Z",
    state: { name: "Unreviewed", type: "backlog" },
    project: { name: "AI Tooling" },
  };
}

function graphql(data: unknown): string {
  return JSON.stringify({ data });
}

function stallError(phase: "headers" | "body"): Error {
  return Object.assign(new Error(`${phase} never finished`), { name: "StallError", phase });
}

/** Resolves on the next microtask turn, after a started request has recorded itself. */
function yielded(): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  queueMicrotask(resolve);
  return promise;
}

/** A transport that answers every read immediately and records every write. */
function quickTransport(writes: string[]): BacklogTransport {
  return async (request) => {
    if (request.stage === "mark_write") {
      const description = String(
        (request.variables.input as { description?: string } | undefined)?.description ?? "",
      );
      writes.push(description);
      return {
        ok: true,
        status: 200,
        text: async () => graphql({ issueUpdate: { issue: issueNode(description) } }),
      };
    }
    if (request.stage === "comment_lookup") {
      return {
        ok: true,
        status: 200,
        text: async () => graphql({ issue: { comments: { nodes: [{ createdAt: "2026-11-17T16:30:00.000Z" }] } } }),
      };
    }
    if (request.stage === "supersession_lookup") {
      return { ok: true, status: 200, text: async () => graphql({ issues: { nodes: [] } }) };
    }
    return { ok: true, status: 200, text: async () => graphql({ issue: issueNode() }) };
  };
}

/**
 * A transport that has accepted the request and then stalls. `entered` resolves
 * once the request is in flight, which is the only signal the test waits on.
 */
function stall(kind: "headers" | "body", entered: PromiseWithResolvers<AbortSignal>): BacklogTransport {
  return (request, report) => {
    entered.resolve(request.signal);
    if (kind === "headers") {
      const { promise, reject } = Promise.withResolvers<BacklogResponse>();
      request.signal.addEventListener(
        "abort",
        () => {
          report("headers");
          reject(stallError("headers"));
        },
        { once: true },
      );
      return promise;
    }
    const body = Promise.withResolvers<string>();
    request.signal.addEventListener(
      "abort",
      () => {
        report("body");
        body.reject(stallError("body"));
      },
      { once: true },
    );
    return Promise.resolve({ ok: true, status: 200, text: () => body.promise });
  };
}

/** The review's rejection, so a test can assert on the error instead of letting it escape. */
function settled(pending: Promise<unknown>): Promise<Error> {
  const { promise, resolve, reject } = Promise.withResolvers<Error>();
  pending.then(
    () => reject(new Error("review resolved")),
    (error: Error) => resolve(error),
  );
  return promise;
}

const deps = {
  exec: (() => {
    throw new Error("exec must not run");
  }) as never,
  now: () => NOW,
};

describe("backlog transport bounds", () => {
  it("shares one signal and one absolute deadline, and reports the stage", async () => {
    const seen: Recorded[] = [];
    const writes: string[] = [];
    const parent = new AbortController();
    const deadline = NOW + 5_000;
    const transport: BacklogTransport = async (request) => {
      seen.push({ stage: request.stage, signal: request.signal, deadline: request.deadline });
      return quickTransport(writes)(request);
    };
    const row = await boundBacklogReview(TICKET, { ...deps, signal: parent.signal, deadline, transport });
    expect(row.ticket).toBe(TICKET);
    expect(seen.length).toBeGreaterThan(0);
    expect(new Set(seen.map((entry) => entry.signal)).size).toBe(1);
    expect(seen.every((entry) => entry.deadline === deadline)).toBe(true);
    expect(seen.map((entry) => entry.stage)).toContain("issue_fetch");
    expect(writes).toHaveLength(1);
    parent.abort();
    expect(seen[0]?.signal.aborted).toBe(true);
  });

  it("names the stage and writes nothing when headers never arrive", async () => {
    const entered = Promise.withResolvers<AbortSignal>();
    const writes: string[] = [];
    const parent = new AbortController();
    const failed = settled(
      boundBacklogReview(TICKET, {
        ...deps,
        signal: parent.signal,
        deadline: NOW + 5_000,
        transport: (request, report) => {
          if (request.stage === "mark_write") writes.push(request.stage);
          return stall("headers", entered)(request, report);
        },
      }),
    );
    await yielded();
    const signal = await entered.promise;
    expect(signal.aborted).toBe(false);
    parent.abort();
    const error = await failed;
    expect(error.message).toContain("issue_fetch");
    expect(error.message.toLowerCase()).toContain("header");
    expect(writes).toEqual([]);
  });

  it("names the stage and writes nothing when the body never finishes", async () => {
    const entered = Promise.withResolvers<AbortSignal>();
    const writes: string[] = [];
    const parent = new AbortController();
    const failed = settled(
      boundBacklogReview(TICKET, {
        ...deps,
        signal: parent.signal,
        deadline: NOW + 5_000,
        transport: (request, report) => {
          if (request.stage === "mark_write") writes.push(request.stage);
          return stall("body", entered)(request, report);
        },
      }),
    );
    await yielded();
    await entered.promise;
    parent.abort();
    const error = await failed;
    expect(error.message).toContain("issue_fetch");
    expect(error.message.toLowerCase()).toContain("body");
    expect(writes).toEqual([]);
  });

  it("stops at the deadline with no later write", async () => {
    const entered = Promise.withResolvers<AbortSignal>();
    const writes: string[] = [];
    let clock = NOW;
    // Production arms its deadline through `schedule` instead of setTimeout.
    // Holding the fire callback lets the test reach the deadline with no wait.
    let fire: (() => void) | undefined;
    const failed = settled(
      boundBacklogReview(TICKET, {
        ...deps,
        now: () => clock,
        deadline: NOW + 60,
        schedule: (at: number, run: () => void) => {
          expect(at).toBe(NOW + 60);
          fire = () => {
            clock = at;
            run();
          };
        },
        transport: (request, report) => {
          if (request.stage === "mark_write") writes.push(request.stage);
          return stall("headers", entered)(request, report);
        },
      }),
    );
    const signal = await entered.promise;
    expect(signal.aborted).toBe(false);
    expect(fire).toBeDefined();
    fire?.();
    const error = await failed;
    expect(signal.aborted).toBe(true);
    expect(error.message).toContain("issue_fetch");
    expect(writes).toEqual([]);
  });

  it("emits a fetch start and a terminal error without credentials", async () => {
    const events: { stage: string; phase: string; error?: string }[] = [];
    const stop = onTransportEvent((event) => events.push(event));
    const entered = Promise.withResolvers<AbortSignal>();
    const parent = new AbortController();
    const failed = settled(
      boundBacklogReview(TICKET, {
        ...deps,
        signal: parent.signal,
        deadline: NOW + 5_000,
        transport: (request, report) => stall("headers", entered)(request, report),
      }),
    );
    await yielded();
    await entered.promise;
    parent.abort();
    await failed;
    stop();
    expect(events.some((event) => event.phase === "start" && event.stage === "issue_fetch")).toBe(true);
    expect(events.some((event) => event.phase === "headers" && event.error?.includes("issue_fetch"))).toBe(true);
    expect(JSON.stringify(events)).not.toContain("Bearer");
    expect(JSON.stringify(events)).not.toContain("lin_api_");
  });

  it("keeps the quick successful read and survives one failed comment lookup", async () => {
    const writes: string[] = [];
    let comments = 0;
    const transport: BacklogTransport = async (request) => {
      if (request.stage === "comment_lookup") {
        comments += 1;
        if (comments === 1) throw new Error("comment transport down");
      }
      return quickTransport(writes)(request);
    };
    const row = await boundBacklogReview(TICKET, { ...deps, deadline: NOW + 5_000, transport });
    expect(row.verdict).toBe("current");
    expect(row.should_do).toBe(true);
    expect(writes).toHaveLength(1);
    expect(writes[0]).toContain("linear-backlog-review");
  });
});
