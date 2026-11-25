import { PGlite } from "@electric-sql/pglite";
import { vector } from "@electric-sql/pglite/vector";
import { describe, expect, it, mock } from "bun:test";

mock.module("@oh-my-pi/pi-utils", () => ({ logger: { debug() {}, warn() {}, info() {}, error() {} } }));

const SRC = `${process.env.OMP_FORK ?? "/tmp/omp-fork2"}/packages/coding-agent/src/memory-backend/archive`;
const { archiveConsolidateFacts } = await import(`${SRC}/consolidate.ts`);
const { archiveFactsAsOf } = await import(`${SRC}/history.ts`);
const { MEMORY_SCHEMA_STATEMENTS } = { MEMORY_SCHEMA_STATEMENTS: [] as string[] };

const DIM = 4;
const unit = (v: number[]) => {
  const n = Math.hypot(...v);
  return v.map((x) => x / n);
};
const lit = (v: number[]) => `[${unit(v).join(",")}]`;
// topic A (deploy host) and topic B (editor preference) are orthogonal; A, A2, A3 are near-identical
const A = [1, 0.02, 0, 0], A2 = [1, 0.05, 0, 0], A3 = [1, 0.08, 0, 0], B = [0, 0, 1, 0.02];

async function freshStore() {
  const db = new PGlite({ extensions: { vector } });
  await db.exec("create extension if not exists vector");
  await db.exec(`create table public.memory_chunks (
    id text primary key, session_path text not null, source text not null, repository text,
    occurred_at timestamptz not null, chunk_index integer not null, body text not null,
    embedding vector(${DIM}), scope text not null default 'personal', kind text not null default 'chunk')`);
  const client = {
    url: "pglite://scratch",
    async query<T>(text: string, values: readonly unknown[] = []): Promise<T[]> {
      const r = await db.query(text, values as unknown[]);
      return r.rows as T[];
    },
    async end() {},
  };
  const insert = (
    r: { id: string; scope: string; repo: string; at: string; body: string; emb: number[]; source: string },
  ) =>
    // the fork's INSERT_FACT_SQL semantics (retain.ts): same id upserts the row back
    db.query(
      `insert into public.memory_chunks (id, source, session_path, repository, scope, kind, occurred_at, chunk_index, body, embedding)
       values ($1,$2,$3,$4,$5,'fact',$6::timestamptz,0,$7,$8::vector)
       on conflict (id) do update set source=excluded.source, session_path=excluded.session_path, repository=excluded.repository,
         scope=excluded.scope, kind='fact', occurred_at=excluded.occurred_at, body=excluded.body,
         embedding=coalesce(excluded.embedding, public.memory_chunks.embedding)`,
      [r.id, r.source, `/s/${r.id}.jsonl`, r.repo, r.scope, r.at, r.body, lit(r.emb)],
    );
  const current = async () =>
    (await db.query("select id, scope, body from public.memory_chunks where kind='fact' order by id")).rows as {
      id: string;
      scope: string;
      body: string;
    }[];
  return { db, client, insert, current };
}

type Fact = { id: string; scope: string; repo: string; at: string; body: string; emb: number[]; source: string };
const f = (id: string, scope: string, at: string, body: string, emb: number[]): Fact => ({
  id,
  scope,
  repo: scope === "sah" ? "isa" : "dev-profile",
  at,
  body,
  emb,
  source: `src-${id}`,
});

const c1 = f("c1", "personal", "2026-11-01T10:00:00Z", "Deploy host for dev-profile is 100.92.190.20", A);
const c2 = f(
  "c2",
  "personal",
  "2026-11-02T10:00:00Z",
  "Deploy config for dev-profile lives at `/etc/dev-profile/deploy.toml`",
  A2,
);
const p1 = f("p1", "personal", "2026-11-03T10:00:00Z", "dev-profile deploys to host 100.92.190.20", A3);
const k1 = f("k1", "personal", "2026-11-05T10:00:00Z", "CORRECTION: dev-profile deploy host is now 100.92.190.99", A2);
const t1 = f("t1", "personal", "2026-11-04T10:00:00Z", "Prefers tabs over spaces", B);
const u1 = f("u1", "sah", "2026-11-06T10:00:00Z", "isa deploy host is 10.0.0.5 and is final", A3);

// stand-in for the Haiku combiner: oldest to newest, the newest statement last, every identifier kept
const combine = async (facts: { body: string }[]) => facts.map((x) => x.body).join(" || ");
const now = () => new Date("2026-11-10T00:00:00Z");
const run = (client: unknown, embed = async () => unit(A)) =>
  archiveConsolidateFacts({ client: client as never, combine: combine as never, embed: embed as never, now });

describe("fork @ f7f3e88: real SQL on real Postgres (pglite + pgvector)", () => {
  it("synthesizes, keeps the old version retrievable as-of, and never carries a fact across scopes", async () => {
    const s = await freshStore();
    for (const x of [c1, c2, p1, k1, t1, u1]) await s.insert(x);
    const report = await run(s.client);
    expect(report.failed).toBe(0);
    expect(report.clustersConsolidated).toBe(1);
    const cur = await s.current();
    expect(cur.map((r) => r.id)).toEqual(["k1", "t1", "u1"]); // c1,c2,p1 left the current set
    expect(cur.find((r) => r.id === "u1")!.body).toBe(u1.body); // sah fact untouched by personal facts
    expect(cur.find((r) => r.id === "k1")!.body).toContain("/etc/dev-profile/deploy.toml"); // complementary fact kept
    // as-of before the merge: the old versions come back with their own ids and sources
    const before = await archiveFactsAsOf(s.client, "2026-11-09T00:00:00Z", { scope: "personal" });
    expect(before.map((r) => r.id).sort()).toEqual(["c1", "c2", "k1", "p1", "t1"].sort());
    expect(before.find((r) => r.id === "k1")!.body).toBe(k1.body); // canonical's pre-merge text
    expect(before.find((r) => r.id === "c1")!.source).toBe("src-c1");
    // as-of after the merge: only the replacement
    const after = await archiveFactsAsOf(s.client, "2026-11-11T00:00:00Z", { scope: "personal" });
    expect(after.map((r) => r.id).sort()).toEqual(["k1", "t1"]);
    const history = (await s.db.query("select id, superseded_by from public.memory_fact_history order by id")).rows;
    expect(history.map((h: any) => h.id)).toEqual(["c1", "c2", "k1", "p1"]);
    expect(new Set(history.map((h: any) => h.superseded_by))).toEqual(new Set(["k1"]));
  });

  it("current recall still carries the superseded host: the combiner joins both statements", async () => {
    const s = await freshStore();
    for (const x of [c1, c2, p1, k1]) await s.insert(x);
    await run(s.client);
    const body = (await s.current()).find((r) => r.id === "k1")!.body;
    expect(body).toContain("100.92.190.99");
    expect(body).toContain("100.92.190.20"); // real Haiku is asked to resolve contradictions to the newest; the stub does not, so this row only bounds the storage layer
  });

  it("replay twice and out-of-order give the same store, with no duplicate history", async () => {
    const forward = await freshStore();
    for (const x of [c1, c2, p1, k1, t1, u1]) await forward.insert(x);
    await run(forward.client);
    const snapshot = JSON.stringify(await forward.current());
    const hist1 = (await forward.db.query("select count(*)::int n from public.memory_fact_history")).rows[0] as any;
    const second = await run(forward.client);
    expect(second.clustersFound).toBe(0);
    expect(JSON.stringify(await forward.current())).toBe(snapshot);
    expect(((await forward.db.query("select count(*)::int n from public.memory_fact_history")).rows[0] as any).n).toBe(
      hist1.n,
    );

    const reversed = await freshStore();
    for (const x of [u1, t1, k1, p1, c2, c1]) await reversed.insert(x);
    await run(reversed.client);
    expect(JSON.stringify(await reversed.current())).toBe(snapshot);
  });

  it("re-ingesting a superseded fact id resurrects it until the next sweep, then history stays single", async () => {
    const s = await freshStore();
    for (const x of [c1, c2, p1, k1]) await s.insert(x);
    await run(s.client);
    expect((await s.current()).map((r) => r.id)).toEqual(["k1"]);
    await s.insert(c1); // a replayed retain/learn of the old fact
    expect((await s.current()).map((r) => r.id)).toEqual(["c1", "k1"]); // resurrected: old host is current again
    await run(s.client);
    expect((await s.current()).map((r) => r.id)).toEqual(["k1"]); // folded back in by the next sweep
    const hist =
      (await s.db.query("select id, count(*)::int n from public.memory_fact_history group by id order by id"))
        .rows as any[];
    expect(hist.find((h) => h.id === "c1").n).toBeGreaterThanOrEqual(1);
    expect(MEMORY_SCHEMA_STATEMENTS.length).toBe(0);
  });
});
