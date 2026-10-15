#!/usr/bin/env node
// stage_guest.mjs — wasm を partSize ごとに <file>.parts/NNNN.<sha12>.part へ分割し、index.json (descriptor) を書く。
// 形式は tools/runtime/stage_wasm.mjs の splitParts と同一 (deploy/client/chunked.mjs と src/runtime/loader_boot.ts が読む)。
// usage: node tools/gui/e2e/stage_guest.mjs <file.wasm> [partSize = 65536]
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const [file, partArg] = process.argv.slice(2);
if (!file) throw new Error("usage: stage_guest.mjs <file.wasm> [partSize]");
const partSize = Number(partArg ?? 65536);
const buf = readFileSync(file);
const dir = `${file}.parts`;
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });
const parts = [];
for (let off = 0, i = 0; off < buf.length; off += partSize, i++) {
  const chunk = buf.subarray(off, Math.min(off + partSize, buf.length));
  const sha = createHash("sha256").update(chunk).digest("hex");
  const name = `${String(i).padStart(4, "0")}.${sha.slice(0, 12)}.part`;
  writeFileSync(path.join(dir, name), chunk);
  parts.push({ name, size: chunk.length, sha256: sha });
}
const sha256 = createHash("sha256").update(buf).digest("hex");
writeFileSync(
  path.join(dir, "index.json"),
  JSON.stringify({ v: 1, path: path.basename(file), size: buf.length, sha256, contentType: "application/wasm", partSize, parts }),
);
console.log(`[stage-guest] ${path.basename(file)} ${buf.length} B -> ${parts.length} parts (partSize ${partSize})`);
