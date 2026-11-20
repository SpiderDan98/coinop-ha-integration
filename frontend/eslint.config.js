import js from "@eslint/js";
import lit from "eslint-plugin-lit";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules"] },
  js.configs.recommended,
  tseslint.configs.strict,
  lit.configs["flat/recommended"],
  { files: ["build.js"], languageOptions: { globals: { process: "readonly" } } },
  {
    files: ["src/**/*.ts"],
    // The view controls: filters, pager, selection and upload.
    ignores: [
      "src/fields.ts",
      "src/pagination.ts",
      "src/run-images.ts",
      "src/run-list.ts",
      "src/run-tile.ts",
      "src/tag-input.ts",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "TaggedTemplateExpression[tag.name='html'] TemplateElement[value.raw=/<(input|select|textarea)\\b/]",
          message:
            "Data is edited in a dialog (formDialog in src/dialog.ts) with the fields of src/fields.ts, which fill its width; pages show data read-only.",
        },
      ],
    },
  },
);
