// Bundles the extension with esbuild and copies static assets into dist/.
// Usage: `node build.mjs` (extension) or `node build.mjs --test` (test bundle).
import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

const isTest = process.argv.includes("--test");

if (isTest) {
  await mkdir("dist-test", { recursive: true });
  await build({
    entryPoints: ["test/redaction.test.ts"],
    bundle: true,
    platform: "node",
    format: "cjs",
    outfile: "dist-test/redaction.test.cjs",
    logLevel: "info",
  });
  console.log("built test bundle");
  process.exit(0);
}

await mkdir("dist", { recursive: true });

// Background runs as an ES module service worker.
await build({
  entryPoints: ["src/background.ts"],
  bundle: true,
  format: "esm",
  target: "es2020",
  outfile: "dist/background.js",
  logLevel: "info",
});

// Content and options run as classic scripts → IIFE, no module imports.
await build({
  entryPoints: ["src/content.ts"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: "dist/content.js",
  logLevel: "info",
});

await build({
  entryPoints: ["src/options.ts"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: "dist/options.js",
  logLevel: "info",
});

await copyFile("manifest.json", "dist/manifest.json");
await copyFile("options.html", "dist/options.html");

console.log("extension built → dist/");
