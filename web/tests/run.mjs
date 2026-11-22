// Bundles the TypeScript tests with Vite (no extra dependencies), then runs them with node:test.
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { build } from "vite";

const outDir = "node_modules/.tmp/tests";
const entries = readdirSync("tests").filter((f) => f.endsWith(".test.ts"));
for (const entry of entries) {
  await build({
    configFile: false,
    logLevel: "error",
    build: {
      ssr: `tests/${entry}`,
      outDir,
      emptyOutDir: false,
      copyPublicDir: false,
      rollupOptions: { output: { entryFileNames: "[name].mjs" } },
    },
  });
}
const files = entries.map((e) => resolve(outDir, e.replace(/\.ts$/, ".mjs")));
const run = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
process.exit(run.status ?? 1);
