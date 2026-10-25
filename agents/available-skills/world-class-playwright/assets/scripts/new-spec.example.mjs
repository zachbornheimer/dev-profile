#!/usr/bin/env node
/**
 * Spec generator.
 *
 * Most drift enters a suite by copy-paste from a neighbouring file, not by
 * ignorance of the standard. A generator beats a document: file #200 starts in
 * the blessed shape instead of inheriting whatever file #199 happened to do.
 *
 * The path is a product area/scenario, never a ticket ID or PR number.
 * Usage: node scripts/new-spec.mjs checkout/guest-checkout
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const slug = process.argv[2];
if (!slug) {
  console.error('Usage: node scripts/new-spec.mjs <area>/<scenario-name>');
  process.exit(1);
}

if (/^[A-Z]+-?\d+$/i.test(slug.split('/').pop() ?? '')) {
  console.error('Use a product behavior path, not a ticket/work-item ID.');
  process.exit(1);
}

const title = slug.split('/').pop().replace(/-/g, ' ');
const target = join('tests/specs', `${slug}.spec.ts`);

const template = `import { test, expect } from '../../fixtures/base';

test.describe('${title}', () => {
  test('describes the observable product outcome', {
    tag: '@regression',
    // Issue/work-item IDs belong in annotation metadata, not in the behavior title.
    // annotation: { type: 'issue', description: 'PROJECT-123' },
  }, async ({ authedPage, tenant, unique }) => {
    await test.step('given: the required product state exists', async () => {
      // Use the cheapest reliable setup path. Assert required preconditions;
      // never make them optional with count()/isVisible()/catch-and-continue.
    });

    await test.step('when: the behavior under test occurs', async () => {
      // Use strict semantic locators. UI traversal belongs here only when it is
      // part of the behavior being validated.
    });

    await test.step('then: the scoped observable contract holds', async () => {
      // Assert the exact owning surface/value/state. Avoid body-wide searches,
      // permissive regexes, and implementation details unless they are the contract.
    });
  });
});
`

await mkdir(dirname(target), { recursive: true });
await writeFile(target, template, { flag: 'wx' });
console.log(`Created ${target}`);
