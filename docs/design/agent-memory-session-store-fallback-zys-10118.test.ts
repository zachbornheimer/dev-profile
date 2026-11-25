import { expect, mock, spyOn, test } from "bun:test";

// Run from packages/coding-agent of zachbornheimer/oh-my-pi at chore/fork-upstream-compat-4530cba (ff636221), after `bun install`:
//   OMP_COMPAT=<checkout> bun test <this file>
// The module's native-dependent imports are replaced, so only the fallback logic under test runs.
const ROOT = process.env.OMP_COMPAT ?? "/tmp/omp-compat";
const SESSION_DIR = `${ROOT}/packages/coding-agent/src/session`;

mock.module("@oh-my-pi/pi-utils", () => ({ logger: { debug() {}, warn() {}, info() {}, error() {} } }));
class FileSessionStorage {
  readonly kind = "file";
}
mock.module(`${SESSION_DIR}/session-storage.ts`, () => ({ FileSessionStorage }));
mock.module(`${SESSION_DIR}/sql-session-storage.ts`, () => ({
  SqlSessionStorage: {
    create: async ({ client }: { client: { unsafe: (query: string) => Promise<unknown> } }) => {
      await client.unsafe("select 1");
      return { kind: "sql" };
    },
  },
}));
mock.module(`${SESSION_DIR}/session-path-alias.ts`, () => ({ parseSessionPathPrefixAlias: () => undefined }));

const env = await import(`${SESSION_DIR}/session-storage-env.ts`);

test(
  "unreachable SESSIONS_DB_URL degrades to FileSessionStorage and writes one stderr notice (ZYS-10146, #95/#98)",
  async () => {
    env.resetSessionStorageForTesting({ sleep: async () => {} });
    process.env.SESSIONS_DB_URL = "postgresql://u:p@127.0.0.1:1/x";
    const stderr = spyOn(process.stderr, "write").mockImplementation(() => true);
    try {
      const first = await env.resolveSessionStorage();
      const second = await env.resolveSessionStorage();
      expect(first.kind).toBe("file");
      expect(second.kind).toBe("file");
      const notices = stderr.mock.calls.filter(([chunk]) => String(chunk).includes("Session store unreachable"));
      expect(notices.length).toBe(1);
    } finally {
      stderr.mockRestore();
      delete process.env.SESSIONS_DB_URL;
    }
  },
  30_000,
);

test("unset SESSIONS_DB_URL keeps FileSessionStorage with no notice", async () => {
  env.resetSessionStorageForTesting({ sleep: async () => {} });
  delete process.env.SESSIONS_DB_URL;
  const stderr = spyOn(process.stderr, "write").mockImplementation(() => true);
  try {
    expect((await env.resolveSessionStorage()).kind).toBe("file");
    expect(stderr.mock.calls.length).toBe(0);
  } finally {
    stderr.mockRestore();
  }
});
