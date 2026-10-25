#!/usr/bin/env node
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sha256Hex } from "./sha256.mjs";
import { SNAPSHOT_FILES, TOKENS_SHA_HEADER } from "./snapshot-files.mjs";

const SKILL_ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST_OUT = path.join(SKILL_ROOT, "references", "contract");

const packageRoot = process.argv[2];
if (!packageRoot) {
  console.error(
    "usage: node scripts/refresh-from-package.mjs <path/to/packages/style-contract>",
  );
  process.exit(1);
}

const srcDist = path.join(path.resolve(packageRoot), "dist");
mkdirSync(DIST_OUT, { recursive: true });

const files = {};
for (const name of SNAPSHOT_FILES) {
  const text = readFileSync(path.join(srcDist, name), "utf8");
  writeFileSync(path.join(DIST_OUT, name), text);
  files[name] = sha256Hex(text);
}

const genCss = readFileSync(path.join(DIST_OUT, "contract.gen.css"), "utf8");
const tokensSha256 = TOKENS_SHA_HEADER.exec(genCss)?.[1];
if (!tokensSha256) {
  console.error("refresh-from-package: contract.gen.css missing tokens-sha256 header");
  process.exit(1);
}

const manifest = { tokensSha256, files };
writeFileSync(path.join(DIST_OUT, "shas.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`refresh-from-package: wrote ${SNAPSHOT_FILES.length} files + shas.json (${tokensSha256.slice(0, 12)}…)`);
