import { createHash, randomBytes } from "node:crypto";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SECRET_BYTES = 32;
const PRIVATE_DIRECTORY = 0o700;
const PRIVATE_FILE = 0o600;
const incarnation = randomBytes(SECRET_BYTES).toString("hex");
const processRoots = new Set<string>();
process.once("exit", () => {
  for (const root of processRoots) rmSync(root, { recursive: true, force: true });
});
export type Registration = Readonly<{ session: string }>;

/** Capabilities belong to a live process activation, never to a session name alone. */
export class Registry {
  #root: string | undefined;
  #registrations = new Map<string, Registration>();

  get root(): string {
    if (!this.#root) {
      const root = mkdtempSync(join(tmpdir(), "atask-runtime-"));
      chmodSync(root, PRIVATE_DIRECTORY);
      this.#root = root;
      processRoots.add(root);
    }
    return this.#root;
  }

  activate(session: string): Registration | undefined {
    if (this.#registrations.has(session)) return undefined;
    const registration = Object.freeze({ session });
    writeFileSync(this.#path(session), JSON.stringify({
      session,
      pid: process.pid,
      incarnation,
      capability: randomBytes(SECRET_BYTES).toString("hex"),
    }), { mode: PRIVATE_FILE, flag: "wx" });
    this.#registrations.set(session, registration);
    return registration;
  }

  revoke(registration: Registration): void {
    if (this.#registrations.get(registration.session) !== registration) return;
    rmSync(this.#path(registration.session), { force: true });
    this.#registrations.delete(registration.session);
  }

  #path(session: string): string {
    const digest = createHash("sha256").update(session).digest("hex");
    return join(this.root, `${digest}.json`);
  }
}

export const runtimeRegistry = new Registry();
