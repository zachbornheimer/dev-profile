#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "references", "contract");

const args = process.argv.slice(2);
const legacy = args.includes("--legacy");
const force = args.includes("--force");
const outDirFlag = args.indexOf("--out-dir");
const positional = args.filter((a) => !a.startsWith("--"));
const repoRoot = positional[0];
if (!repoRoot) {
  console.error(
    "usage: node scripts/install-into-repo.mjs <repo-root> [--legacy] [--out-dir styles] [--force]",
  );
  process.exit(1);
}

const outDir = path.resolve(repoRoot, outDirFlag >= 0 ? args[outDirFlag + 1] : "styles");
const contractFile = legacy ? "contract.gen.legacy.css" : "contract.gen.css";
const copies = [
  [contractFile, "contract.css"],
  ["brand.example.css", "brand.example.css"],
  ["shas.json", "contract-shas.json"],
];

mkdirSync(outDir, { recursive: true });
for (const [from, to] of copies) {
  const dest = path.join(outDir, to);
  if (!force && existsSync(dest)) {
    console.error(`install-into-repo: ${dest} exists — pass --force`);
    process.exit(1);
  }
  writeFileSync(dest, readFileSync(path.join(DIST, from)));
}
console.log(
  `install-into-repo: wrote ${copies.map(([, to]) => to).join(", ")} → ${outDir} (${legacy ? "legacy" : "layered"})`,
);
