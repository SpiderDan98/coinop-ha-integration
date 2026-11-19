import js from "@eslint/js";
import lit from "eslint-plugin-lit";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules"] },
  js.configs.recommended,
  tseslint.configs.strict,
  lit.configs["flat/recommended"],
  { files: ["build.js"], languageOptions: { globals: { process: "readonly" } } },
);
