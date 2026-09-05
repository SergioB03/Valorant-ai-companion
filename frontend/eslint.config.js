// Flat ESLint config — deliberately minimal: core recommended JS rules plus
// the react-hooks rules. No style/formatting rules (no Prettier bikeshed),
// no TS. The goal is the undefined-name-in-error-path bug class.
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist/", "node_modules/"] },
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      ...js.configs.recommended.rules,
      // Components referenced only from JSX aren't visible to core
      // no-unused-vars — same convention as the official Vite React template.
      "no-unused-vars": ["error", { varsIgnorePattern: "^[A-Z_]" }],
      // ESLint 10's recommended set added preserve-caught-error, which wants
      // `cause:` threaded onto rethrown errors. That is an app-behavior
      // change, not lint glue — keep the pre-10 posture for the toolchain
      // bump and adopt the rule deliberately later if wanted.
      "preserve-caught-error": "off",
    },
  },
  {
    files: ["**/*.jsx"],
    plugins: { "react-hooks": reactHooks },
    // eslint-plugin-react-hooks 7's `recommended` preset also turns on the
    // React Compiler-powered rules (purity, set-state-in-effect, …), which
    // flag existing app code. Pin the two classic rules at their
    // long-standing levels; adopting the compiler rules is an app-code
    // migration to do deliberately, not inside a toolchain bump.
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    // Node contexts: the asset pipeline scripts and the Vite/Vitest configs.
    files: ["scripts/**/*.mjs", "vite.config.js", "eslint.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // Vitest specs run in Node (or jsdom via pragma); APIs are imported
    // explicitly from "vitest", so only the Node globals are needed here.
    files: ["src/**/*.spec.js"],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
];
