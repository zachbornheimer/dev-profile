#!/usr/bin/env node
/**
 * Reject temporary characterization tests from mergeable branches.
 *
 * Characterization tests intentionally assert known-wrong behavior during the
 * first phase of characterize → falsify → fix. They are useful locally but must
 * never survive interruption as apparently permanent contracts.
 *
 * Usage:
 *   node scripts/reject-characterization-tests.mjs [testsDir]
 */
import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative, resolve } from 'node:path';

const MARKER = '@characterization-only';
const TEST_EXTENSIONS = new Set(['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts']);
const root = resolve(process.argv[2] ?? 'tests');

/** Return executable test-source files below `dir`, excluding generated artifacts. */
async function collectTestFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === 'test-results' || entry.name === 'playwright-report') {
      continue;
    }

    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectTestFiles(path));
    } else if (entry.isFile() && TEST_EXTENSIONS.has(extname(entry.name))) {
      files.push(path);
    }
  }

  return files;
}

let files;
try {
  files = await collectTestFiles(root);
} catch (error) {
  console.error(`Could not scan test directory ${root}:`, error);
  process.exit(2);
}

const violations = [];
for (const file of files) {
  const source = await readFile(file, 'utf8');
  const lines = source.split(/\r?\n/u);

  lines.forEach((line, index) => {
    if (line.includes(MARKER)) {
      violations.push(`${relative(process.cwd(), file)}:${index + 1}: ${line.trim()}`);
    }
  });
}

if (violations.length > 0) {
  console.error(
    `Temporary characterization tests cannot merge. Convert them to the desired contract and remove ${MARKER}:\n` +
    violations.map((violation) => `  ${violation}`).join('\n'),
  );
  process.exit(1);
}
