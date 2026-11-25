import { describe, expect, it, mock } from "bun:test";

mock.module("@oh-my-pi/pi-utils", () => ({ logger: { debug() {}, warn() {}, info() {}, error() {} } }));

// Run from packages/coding-agent of zachbornheimer/oh-my-pi @ 3b7375f: OMP_FORK=<checkout> bun test <this file>
const SRC = `${process.env.OMP_FORK ?? "/tmp/omp-fork"}/packages/coding-agent/src/memory-backend/archive`;
const { archiveConsolidateFacts } = await import(`${SRC}/consolidate.ts`);

interface Row {
  id: string;
  source: string;
  session_path: string;
  repository: string;
  scope: string;
  occurred_at: string;
  body: string;
  embedding: number[] | null;
}

const norm = (v: number[]) => {
  const n = Math.hypot(...v);
  return v.map((x) => x / n);
};
// direction A = "deploy config" topic, direction B = unrelated topic
const A = norm([1, 0.02]);
const A2 = norm([1, 0.05]);
const A3 = norm([1, 0.08]);
const B = norm([0.02, 1]);

function store(rows: Row[]) {
  const t = new Map(rows.map((r) => [r.id, { ...r }]));
  const parse = (s: string) => JSON.parse(s) as number[];
  const client = {
    async query<T>(text: string, values: readonly unknown[] = []): Promise<T[]> {
      const sorted = () =>
        [...t.values()].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at) || a.id.localeCompare(b.id));
      if (text.includes("select id, body") && text.includes("embedding is null")) {
        return sorted().filter((r) => r.embedding === null).map((r) => ({ id: r.id, body: r.body })) as T[];
      }
      if (text.includes("embedding::text as embedding")) {
        return sorted().filter((r) => r.embedding).map((r) => ({
          id: r.id,
          embedding: JSON.stringify(r.embedding),
        })) as T[];
      }
      if (text.includes("id = any($1::text[])") && text.trim().startsWith("select")) {
        const ids = String(values[0]).slice(1, -1).split(",");
        return sorted().filter((r) => ids.includes(r.id)) as unknown as T[];
      }
      if (text.includes("set body = $2")) {
        const r = t.get(String(values[0]))!;
        r.body = String(values[1]);
        r.embedding = parse(String(values[2]));
        r.occurred_at = String(values[3]);
        r.source = String(values[4]);
        return [] as T[];
      }
      if (text.startsWith("delete from public.memory_chunks")) {
        for (const id of String(values[0]).slice(1, -1).split(",")) t.delete(id);
        return [] as T[];
      }
      throw new Error("unhandled sql: " + text.slice(0, 60));
    },
    async end() {},
  };
  const ingest = (r: Row) => {
    t.set(r.id, { ...r });
  }; // INSERT_FACT_SQL is `on conflict (id) do update`: same id => upsert, deleted id => recreated
  return { t, client, ingest, current: () => [...t.values()].map((r) => r.id).sort() };
}

// a stand-in for the Haiku combiner: newest statement wins, all identifiers kept
const combine = async (facts: { id: string; body: string }[]) => facts.map((f) => f.body).join(" || ");
const embed = async () => A;
const run = (client: unknown) =>
  archiveConsolidateFacts({ client: client as never, combine: combine as never, embed: embed as never });

const row = (id: string, scope: string, at: string, body: string, embedding: number[], source = `src-${id}`): Row => ({
  id,
  source,
  session_path: `/s/${id}.jsonl`,
  repository: scope === "sah" ? "isa" : "dev-profile",
  scope,
  occurred_at: at,
  body,
  embedding,
});

describe("supersession on a scratch store (real consolidate.ts, in-memory SQL)", () => {
  const complementary = [
    row("c1", "personal", "2026-11-01T10:00:00Z", "Deploy host for dev-profile is 100.92.190.20", A),
    row(
      "c2",
      "personal",
      "2026-11-02T10:00:00Z",
      "Deploy config for dev-profile lives at /etc/dev-profile/deploy.toml",
      A2,
    ),
  ];
  const paraphrase = row("p1", "personal", "2026-11-03T10:00:00Z", "dev-profile deploys to host 100.92.190.20", A3);
  const correction = row(
    "k1",
    "personal",
    "2026-11-05T10:00:00Z",
    "CORRECTION: dev-profile deploy host is now 100.92.190.99",
    A2,
  );
  const unrelatedScopeNewer = row("u1", "sah", "2026-11-06T10:00:00Z", "isa deploy host is 10.0.0.5 and is final", A3);
  const unrelatedTopic = row("t1", "personal", "2026-11-04T10:00:00Z", "Prefers tabs over spaces", B);

  it("complementary + paraphrase + correction: synthesized, but only the newest row id survives", async () => {
    const s = store([...complementary, paraphrase, correction, unrelatedTopic]);
    const report = await run(s.client);
    expect(report.clustersConsolidated).toBe(1);
    const merged = s.t.get("k1")!;
    expect(merged.body).toContain("/etc/dev-profile/deploy.toml");
    expect(merged.body).toContain("100.92.190.99");
    expect(s.current()).toEqual(["k1", "t1"]); // c1, c2, p1 deleted
    expect(s.t.has("c1")).toBe(false); // as-of / history read of the old version: impossible
    expect(merged.source).toBe("src-k1"); // source ids of c1,c2,p1 are not recorded anywhere
    // current recall still contains the superseded value (no supersession-aware filtering: Haiku joined both)
    expect(merged.body).toContain("100.92.190.20");
  });

  it("an unrelated-scope newer statement with a similar embedding merges across scopes", async () => {
    const s = store([...complementary, unrelatedScopeNewer]);
    await run(s.client);
    const survivor = s.t.get("u1")!;
    expect(survivor.scope).toBe("sah"); // personal facts folded into an sah row
    expect(survivor.body).toContain("100.92.190.20"); // personal text now readable under sah scope
    expect(s.t.has("c1") || s.t.has("c2")).toBe(false);
  });

  it("replay twice is a no-op", async () => {
    const s = store([...complementary, paraphrase, correction]);
    await run(s.client);
    const afterFirst = JSON.stringify([...s.t.values()]);
    const second = await run(s.client);
    expect(second.clustersFound).toBe(0);
    expect(JSON.stringify([...s.t.values()])).toBe(afterFirst);
  });

  it("out-of-order insertion yields the same result", async () => {
    const a = store([correction, paraphrase, ...complementary].reverse());
    const b = store([...complementary, paraphrase, correction]);
    await run(a.client);
    await run(b.client);
    expect(JSON.stringify([...a.t.values()])).toBe(JSON.stringify([...b.t.values()]));
  });

  it("re-ingesting a superseded fact resurrects it (same id upserts the deleted row back)", async () => {
    const s = store([...complementary, paraphrase, correction]);
    await run(s.client);
    expect(s.t.has("c1")).toBe(false);
    s.ingest(complementary[0]!); // a replayed transcript / retain of the old fact
    expect(s.t.has("c1")).toBe(true); // old value is current again until the next sweep
    await run(s.client);
    expect(s.t.has("c1")).toBe(false); // a later sweep re-merges it; the window in between is the resurrection
  });
});
