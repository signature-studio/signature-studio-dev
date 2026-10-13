// src/runtime/memory_budget.ts を型除去して work/gen/memory_budget.js に出力 (node/ブラウザ両用・依存なし)。
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
export const genDir = path.join(here, "work", "gen");
export function transpile() {
  const src = readFileSync(path.join(here, "../../../src/runtime/memory_budget.ts"), "utf8");
  mkdirSync(genDir, { recursive: true });
  const out = path.join(genDir, "memory_budget.js");
  writeFileSync(out, stripTypeScriptTypes(src, { mode: "strip" }));
  return out;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) console.log(transpile());
