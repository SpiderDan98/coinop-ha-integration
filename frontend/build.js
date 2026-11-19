// Bundles the panel into the integration package; `--watch` rebuilds on change.
import * as esbuild from "esbuild";

const options = {
  entryPoints: ["src/wattbill-panel.ts"],
  outfile: "../custom_components/wattbill/frontend/wattbill-panel.js",
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
  sourcemap: false,
  legalComments: "eof",
  logLevel: "info",
};

if (process.argv.includes("--watch")) {
  await (await esbuild.context({ ...options, minify: false })).watch();
} else {
  await esbuild.build(options);
}
