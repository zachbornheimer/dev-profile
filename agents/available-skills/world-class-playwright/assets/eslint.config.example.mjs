// eslint.config.mjs
//
// The enforcement layer for the Playwright standard. Every rule here maps to a
// rule in SKILL.md; the mapping is deliberate, so a rule cannot be added to the
// document without someone asking how it will be enforced.
//
// Verify eslint-plugin-playwright rule names against your installed version —
// they change across majors.

import playwright from 'eslint-plugin-playwright';
import tseslint from 'typescript-eslint';

/** Boolean-blind assertion: every failure reads "expected true, received false". */
const BOOLEAN_ASSERTION = {
  selector: "CallExpression[callee.property.name='toBe'][arguments.0.value=true]",
  message:
    'Assert the value, not a boolean. expect(delta).toBeLessThanOrEqual(3) reports the number; ' +
    'expect(delta <= 3).toBe(true) forces you to hand-write a compensating message.',
};

/** Sleeps no Playwright rule catches. */
const HAND_ROLLED_SLEEP = {
  selector: "CallExpression[callee.name='setTimeout']",
  message:
    'Hand-rolled sleep. Use a web-first assertion, an event wait, or a domain wait primitive. ' +
    'For asserting the ABSENCE of a signal, use the one sanctioned bounded-wait module in support/.',
};

const SWALLOWED_ERRORS = [
  {
    selector: 'CatchClause[body.body.length=0]',
    message: 'Empty catch. A swallowed error turns a test that cannot fail into a test that cannot protect.',
  },
  {
    selector: "CallExpression[callee.property.name='catch'] > ArrowFunctionExpression",
    message:
      'Inline .catch() converts an unknown failure into a value. Probe optional state explicitly ' +
      '(isVisible/count/isChecked) and let real failures throw.',
  },
];

const TIMEOUT_POLICY = {
  selector: "CallExpression[callee.object.name='test'][callee.property.name='setTimeout']",
  message: 'Timeouts are policy. Use a category from timeouts.ts, or an escape hatch with a ticket.',
};

const SHARED_STATE = [
  {
    selector: "Program > VariableDeclaration[kind='let']",
    message: 'Module-level mutable state contaminates tests across a file. Use a fixture.',
  },
  {
    selector: 'Literal[value=/^(test|qa|admin)[-_.@]/i]',
    message: 'Fixed identity collides under parallelism. Take identity from the `unique` or `tenant` fixture.',
  },
];


const SERIAL_SUITE = {
  selector:
    "CallExpression[callee.object.object.name='test'][callee.object.property.name='describe'][callee.property.name='serial']",
  message:
    'Serial suites hide shared-state design and disable parallelism. Prefer independent setup or one journey test; use a documented escape hatch only for a real external constraint.',
};

const XPATH = {
  selector: "CallExpression[callee.property.name='locator'] > Literal[value=/^(\\/\\/|xpath=)/]",
  message: 'XPath binds to document structure, which changes for reasons unrelated to product behaviour.',
};

export default [
  { ignores: ['node_modules/**', 'test-results/**', 'playwright-report/**'] },

  // --- Specs: tightest ruleset -------------------------------------------
  {
    files: ['tests/specs/**/*.spec.ts'],
    plugins: { playwright },
    rules: {
      ...playwright.configs['flat/recommended'].rules,

      // The structural rule. Specs cannot reach Playwright directly, so every
      // spec necessarily comes through the base fixture.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@playwright/test',
              message: 'Import { test, expect } from fixtures/base instead.',
            },
          ],
        },
      ],

      'no-restricted-syntax': [
        'error',
        BOOLEAN_ASSERTION,
        HAND_ROLLED_SLEEP,
        TIMEOUT_POLICY,
        SERIAL_SUITE,
        XPATH,
        ...SWALLOWED_ERRORS,
        ...SHARED_STATE,
        {
          selector: "CallExpression[callee.property.name='locator'] > Literal[value=/^\\s*[.#]/]",
          message: 'Raw CSS in a spec. Put the selector in a page or component object.',
        },
      ],

      'playwright/no-wait-for-timeout': 'error',
      'playwright/no-networkidle': 'error',
      'playwright/no-wait-for-selector': 'error',
      'playwright/no-element-handle': 'error',
      'playwright/no-eval': 'error',
      'playwright/no-force-option': 'error',
      'playwright/no-nth-methods': 'error',
      'playwright/no-raw-locators': 'error',
      'playwright/no-conditional-in-test': 'error',
      'playwright/no-conditional-expect': 'error',
      'playwright/no-skipped-test': 'error',
      'playwright/no-focused-test': 'error',
      'playwright/expect-expect': 'error',
      'playwright/prefer-web-first-assertions': 'error',

      // An unawaited assertion silently makes a test unable to fail, and it is
      // invisible in review because the line looks correct.
      '@typescript-eslint/no-floating-promises': 'error',
    },
  },

  // --- Page objects, components, workflows -------------------------------
  // May hold CSS selectors (that is their job) but not sleeps or shared state.
  {
    files: ['tests/pages/**/*.ts', 'tests/components/**/*.ts', 'tests/workflows/**/*.ts'],
    rules: {
      'no-restricted-syntax': ['error', BOOLEAN_ASSERTION, HAND_ROLLED_SLEEP, XPATH, ...SWALLOWED_ERRORS, ...SHARED_STATE],
    },
  },

  // --- Dumping grounds ---------------------------------------------------
  {
    files: ['tests/**/{helpers,utils,common}.ts'],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: 'Program', message: 'helpers/utils/common are ownership vacuums. Put this in pages/, workflows/, api/, builders/ or assertions/.' },
      ],
    },
  },

  // --- The single sanctioned home for a bounded wait ---------------------
  {
    files: ['tests/support/wait.ts'],
    rules: { 'no-restricted-syntax': 'off', 'playwright/no-wait-for-timeout': 'off' },
  },

  ...tseslint.configs.recommendedTypeChecked.map((c) => ({
    ...c,
    files: ['tests/**/*.ts'],
    languageOptions: { ...c.languageOptions, parserOptions: { projectService: true } },
  })),
];
