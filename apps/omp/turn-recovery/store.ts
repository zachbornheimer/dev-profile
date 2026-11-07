// Neon-backed turn registry for ZYS-8563. Neon is the only source of truth: nothing here caches
// state locally. Every write is fenced on (turn_id, owner_id, generation) and refuses terminal rows,
// so a late hook or a stale owner cannot overwrite a newer state. All timestamps are Neon's clock.
import { SQL } from "bun";
import { LEASE_MS, TERMINAL_STATES, type PendingTool, type TurnRow, type TurnState } from "./recovery.ts";

export const SCHEMA = `
CREATE TABLE IF NOT EXISTS herder_turns (
  turn_id text PRIMARY KEY,
  session_id text NOT NULL,
  pane_id text,
  owner_id text NOT NULL,
  owner_host text,
  generation bigint NOT NULL,
  seq bigint NOT NULL DEFAULT 0,
  state text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  heartbeat_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  recovery_attempts int NOT NULL DEFAULT 0,
  recovery_sent_at timestamptz,
  recovery_acked_at timestamptz,
  pending_tools jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS herder_turns_session_idx ON herder_turns (session_id, started_at DESC);
CREATE TABLE IF NOT EXISTS herder_turn_events (
  id bigserial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  session_id text NOT NULL,
  turn_id text,
  actor text NOT NULL,
  decision text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS herder_turn_events_session_idx ON herder_turn_events (session_id, id DESC);
`;

const TERMINAL_SQL = TERMINAL_STATES.map((state) => `'${state}'`).join(",");
const LIVE_SQL = "'running','awaiting_input','recovering'";

/** Columns every read returns, with Neon's own clock beside the heartbeat. */
const COLUMNS = `turn_id, session_id, pane_id, owner_id, owner_host, generation, seq, state,
  (extract(epoch from heartbeat_at) * 1000)::float8 AS heartbeat_ms,
  (extract(epoch from started_at) * 1000)::float8 AS started_ms,
  (extract(epoch from clock_timestamp()) * 1000)::float8 AS now_ms,
  recovery_attempts,
  (extract(epoch from recovery_sent_at) * 1000)::float8 AS sent_ms,
  (extract(epoch from recovery_acked_at) * 1000)::float8 AS acked_ms,
  pending_tools`;

export interface StoredTurn extends TurnRow {
  startedMs: number;
  seq: number;
}

export interface Fence {
  turnId: string;
  ownerId: string;
  generation: number;
}

export interface AuditEvent {
  at: string;
  actor: string;
  decision: string;
  turnId: string | null;
  detail: unknown;
}

function toRow(raw: Record<string, unknown>): StoredTurn {
  const pending = raw.pending_tools;
  return {
    turnId: String(raw.turn_id),
    sessionId: String(raw.session_id),
    paneId: raw.pane_id === null ? null : String(raw.pane_id),
    ownerId: String(raw.owner_id),
    ownerHost: raw.owner_host === null ? null : String(raw.owner_host),
    generation: Number(raw.generation),
    seq: Number(raw.seq),
    state: String(raw.state) as TurnState,
    heartbeatMs: Number(raw.heartbeat_ms),
    startedMs: Number(raw.started_ms),
    nowMs: Number(raw.now_ms),
    recoveryAttempts: Number(raw.recovery_attempts),
    recoverySentMs: raw.sent_ms === null ? null : Number(raw.sent_ms),
    recoveryAckedMs: raw.acked_ms === null ? null : Number(raw.acked_ms),
    pendingTools: Array.isArray(pending) ? pending : [],
  };
}

export class TurnStore {
  readonly #sql: SQL;

  constructor(url: string) {
    this.#sql = new SQL(url, { connectionTimeout: 5, idleTimeout: 30 });
  }

  /** Create the tables. An advisory lock serialises concurrent first starts from many machines. */
  async migrate(): Promise<void> {
    await this.#sql.begin(async (tx) => {
      await tx`SELECT pg_advisory_xact_lock(hashtext('herder_turns_schema'))`;
      await tx.unsafe(SCHEMA);
    });
  }

  async close(): Promise<void> {
    await this.#sql.close();
  }

  /**
   * Start a turn. Takes the session's next generation and, in the same transaction, closes every
   * older live turn of the session as `stopped`: only one turn per session is current.
   */
  async begin(input: { turnId: string; sessionId: string; paneId: string | null; ownerId: string; ownerHost: string }): Promise<Fence> {
    return this.#sql.begin(async (tx) => {
      await tx`SELECT pg_advisory_xact_lock(hashtext(${input.sessionId}))`;
      const [next] = await tx`SELECT coalesce(max(generation), 0) + 1 AS generation FROM herder_turns WHERE session_id = ${input.sessionId}`;
      const generation = Number(next.generation);
      await tx.unsafe(
        `UPDATE herder_turns SET state = 'stopped', ended_at = now() WHERE session_id = $1 AND state IN (${LIVE_SQL})`,
        [input.sessionId],
      );
      await tx`INSERT INTO herder_turns (turn_id, session_id, pane_id, owner_id, owner_host, generation, state)
        VALUES (${input.turnId}, ${input.sessionId}, ${input.paneId}, ${input.ownerId}, ${input.ownerHost}, ${generation}, 'running')`;
      return { turnId: input.turnId, ownerId: input.ownerId, generation };
    });
  }

  /** Newest turn of the session, with Neon's clock. Undefined when the session has none. */
  async latest(sessionId: string): Promise<StoredTurn | undefined> {
    const rows = await this.#sql.unsafe(
      `SELECT ${COLUMNS} FROM herder_turns WHERE session_id = $1 ORDER BY started_at DESC, generation DESC LIMIT 1`,
      [sessionId],
    );
    return rows[0] ? toRow(rows[0]) : undefined;
  }

  /** Renew the lease and record in-flight tools. False when the fence no longer holds. */
  async heartbeat(fence: Fence, pendingTools: PendingTool[]): Promise<boolean> {
    const rows = await this.#sql.unsafe(
      `UPDATE herder_turns SET heartbeat_at = now(), pending_tools = $4::jsonb
       WHERE turn_id = $1 AND owner_id = $2 AND generation = $3 AND state IN (${LIVE_SQL}) RETURNING turn_id`,
      [fence.turnId, fence.ownerId, fence.generation, pendingTools],
    );
    return rows.length === 1;
  }

  /**
   * Move a live turn to `state`. `seq` orders hooks: an event that is not newer than the stored one
   * is dropped, as is anything for a terminal row or a different owner or generation.
   */
  async transition(fence: Fence, state: TurnState, seq: number): Promise<boolean> {
    const terminal = TERMINAL_STATES.includes(state);
    const rows = await this.#sql.unsafe(
      `UPDATE herder_turns SET state = $4, seq = $5, heartbeat_at = now(),
         ended_at = CASE WHEN $6::boolean THEN now() ELSE ended_at END
       WHERE turn_id = $1 AND owner_id = $2 AND generation = $3 AND seq < $5
         AND state NOT IN (${TERMINAL_SQL}) RETURNING turn_id`,
      [fence.turnId, fence.ownerId, fence.generation, state, seq, terminal],
    );
    return rows.length === 1;
  }

  /**
   * Take over an abandoned turn for recovery. One statement, so of any number of simultaneous
   * reconnects exactly one gets a row back; the rest see a changed generation or a fresh lease.
   * Writes the send intent (attempt count, sent time) before the caller sends anything.
   */
  async claimRecovery(seen: StoredTurn, ownerId: string): Promise<Fence | undefined> {
    const rows = await this.#sql.unsafe(
      `UPDATE herder_turns SET state = 'recovering', owner_id = $3, generation = generation + 1,
         recovery_attempts = recovery_attempts + 1, recovery_sent_at = now(), recovery_acked_at = NULL,
         heartbeat_at = now()
       WHERE turn_id = $1 AND generation = $2 AND state IN ('running','recovering')
         AND heartbeat_at < now() - ($4::int * interval '1 millisecond')
       RETURNING generation`,
      [seen.turnId, seen.generation, ownerId, LEASE_MS],
    );
    return rows[0] ? { turnId: seen.turnId, ownerId, generation: Number(rows[0].generation) } : undefined;
  }

  /** The harness accepted the recovery message: stamp the ack and close the interrupted turn. */
  async ackRecovery(fence: Fence): Promise<boolean> {
    const rows = await this.#sql.unsafe(
      `UPDATE herder_turns SET state = 'recovered', recovery_acked_at = now(), ended_at = now()
       WHERE turn_id = $1 AND owner_id = $2 AND generation = $3 AND state = 'recovering' RETURNING turn_id`,
      [fence.turnId, fence.ownerId, fence.generation],
    );
    return rows.length === 1;
  }

  /**
   * Close an abandoned turn with a verdict that came from other evidence (the transcript shows it
   * finished, a message already landed, or retries ran out). Fenced on the generation just read.
   */
  async settle(seen: StoredTurn, state: TurnState): Promise<boolean> {
    const rows = await this.#sql.unsafe(
      `UPDATE herder_turns SET state = $3, ended_at = now(),
         recovery_acked_at = CASE WHEN $3 = 'recovered' THEN now() ELSE recovery_acked_at END
       WHERE turn_id = $1 AND generation = $2 AND state IN ('running','recovering') RETURNING turn_id`,
      [seen.turnId, seen.generation, state],
    );
    return rows.length === 1;
  }

  /** Append a decision to the audit trail. */
  async record(sessionId: string, turnId: string | null, actor: string, decision: string, detail: unknown): Promise<void> {
    await this.#sql`INSERT INTO herder_turn_events (session_id, turn_id, actor, decision, detail)
      VALUES (${sessionId}, ${turnId}, ${actor}, ${decision}, ${detail ?? {}}::jsonb)`;
  }

  async events(sessionId: string, limit = 20): Promise<AuditEvent[]> {
    const rows = await this.#sql`SELECT at, actor, decision, turn_id, detail FROM herder_turn_events
      WHERE session_id = ${sessionId} ORDER BY id DESC LIMIT ${limit}`;
    return rows.map((r: Record<string, unknown>) => ({
      at: String(r.at),
      actor: String(r.actor),
      decision: String(r.decision),
      turnId: r.turn_id === null ? null : String(r.turn_id),
      detail: r.detail,
    }));
  }
}
