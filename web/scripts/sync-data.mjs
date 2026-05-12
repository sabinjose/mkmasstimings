#!/usr/bin/env node
// Copies the extractor's output into Astro's public dir so the build picks it
// up at `/data/latest.json`. Runs automatically before `npm run dev` and
// `npm run build`. Source is the repo-root data/latest.json (written by
// `uv run main.py`); destination is gitignored (generated artifact).
import { copyFileSync, mkdirSync, existsSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const repoRoot = resolve(webRoot, "..");

const src = resolve(repoRoot, "data", "latest.json");
const dst = resolve(webRoot, "public", "data", "latest.json");

if (!existsSync(src)) {
  console.error(
    `sync-data: source missing at ${src}\n` +
      `Run \`uv run main.py --pretty --out data/latest.json\` from the repo root first.`,
  );
  process.exit(1);
}

mkdirSync(dirname(dst), { recursive: true });
copyFileSync(src, dst);

const kb = (statSync(dst).size / 1024).toFixed(1);
console.log(`sync-data: ${kb} KB -> web/public/data/latest.json`);
