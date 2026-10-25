#!/usr/bin/env node
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sha256Hex } from "./sha256.mjs";
import { SNAPSHOT_FILES, TOKENS_SHA_HEADER } from "./snapshot-files.mjs";

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "references", "contract");
const manifest = JSON.parse(readFileSync(path.join(DIST, "shas.json"), "utf8"));

let failed = false;
for (const name of SNAPSHOT_FILES) {
  const text = readFileSync(path.join(DIST, name), "utf8");
  const actual = sha256Hex(text);
  const expected = manifest.files[name];
  if (actual !== expected) {
    console.error(`check-snapshot: ${name} sha ${actual} != ${expected}`);
    failed = true;
  }
}

const genCss = readFileSync(path.join(DIST, "contract.gen.css"), "utf8");
const headerSha = TOKENS_SHA_HEADER.exec(genCss)?.[1];
if (headerSha !== manifest.tokensSha256) {
  console.error(
    `check-snapshot: tokens-sha256 header ${headerSha} != manifest ${manifest.tokensSha256}`,
  );
  failed = true;
}

if (failed) process.exit(1);
console.log(`check-snapshot: ok (${manifest.tokensSha256.slice(0, 12)}…)`);
