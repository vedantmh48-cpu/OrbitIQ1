/** Bundles the smoke harness, aliasing only the bare "zustand" specifier. */
import esbuild from "esbuild";
import path from "node:path";
import process from "node:process";

const shim = path.resolve(".smoke/zustand-shim.mjs");

await esbuild.build({
  entryPoints: [".smoke/harness.mjs"],
  bundle: true,
  platform: "node",
  format: "esm",
  jsx: "automatic",
  packages: "external",
  define: { "import.meta.env": "{}" },
  outfile: ".smoke/harness.bundle.mjs",
  logLevel: "warning",
  plugins: [
    {
      name: "zustand-test-shim",
      setup(build) {
        build.onResolve({ filter: /^zustand$/ }, () => ({ path: shim }));
      },
    },
  ],
});
console.log("bundled");
process.exit(0);
