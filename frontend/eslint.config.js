// ESLint flat config. Rule sets: @eslint/js recommended, typescript-eslint recommended
// (not type-aware) and eslint-plugin-react-hooks recommended. Nothing else is enabled;
// a rule is turned off only with a comment saying why.
import { createRequire } from "node:module";
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";

// typescript-eslint 8.71 supports TypeScript up to 6.0 and refuses to start when it finds
// the project's TypeScript 7 (which is what `tsc`, `npm run typecheck` and `npm run build`
// use, and has no JavaScript API). The owner's decision: keep TypeScript 7 and give
// typescript-eslint the TypeScript 6 API from `@typescript/typescript6`. typescript-eslint
// does `require("typescript")`, so that CommonJS cache entry is pointed at TypeScript 6
// before typescript-eslint is loaded. Only this ESLint process is affected. Remove this
// block when typescript-eslint supports TypeScript 7.
const require = createRequire(import.meta.url);
const typescriptEntry = require.resolve("typescript");
require.cache[typescriptEntry] = {
  id: typescriptEntry,
  filename: typescriptEntry,
  loaded: true,
  exports: require("@typescript/typescript6"),
};
const { default: tseslint } = await import("typescript-eslint");

export default defineConfig([
  globalIgnores(["dist", "test-results", "playwright-report"]),
  js.configs.recommended,
  tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
]);
