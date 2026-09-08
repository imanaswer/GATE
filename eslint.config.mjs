import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Not source. The Python virtualenv is gitignored but ESLint does not read
    // .gitignore, and packages like playwright vendor multi-megabyte bundled JS
    // into it — enough to crash the formatter outright.
    ".venv/**",
    "graphify-out/**",
  ]),
]);

export default eslintConfig;
