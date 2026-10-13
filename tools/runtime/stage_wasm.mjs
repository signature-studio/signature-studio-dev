#!/usr/bin/env node
// 既存 PoC wasm (M1/M6/M10/M11) を work/wasm/ にハッシュ名でステージし manifest.json を生成する。
// 使い方: node tools/runtime/stage_wasm.mjs [--extra file.wasm:id:program ...] [--max-file=<bytes>] [--part-size=<bytes>]
// 無い成果物はスキップ (M1 のみ m1.sh で自動生成を試みる)。
// max-file (既定 24MiB; Static Assets 上限 25MiB) を超える wasm は <file>.parts/ に分割し、entry.file は
// <file>.parts/index.json (descriptor) を指す。形式は deploy/scripts/05-stage.mjs と同一 (fetchCompile の chunked 分岐が読む)。
import { createHash } from "node:crypto";
import { brotliCompressSync, constants as zc } from "node:zlib";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { wasmInfo } from "./lib/wasminfo.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const out = process.env.RUNTIME_WASM_DIR ?? path.join(here, "work/wasm");
mkdirSync(out, { recursive: true });
const MiB = 1024 * 1024;
const opt = (n, d) => process.argv.find((a) => a.startsWith(`--${n}=`))?.slice(n.length + 3) ?? d;
const maxFile = Number(opt("max-file", 24 * MiB));
const partSize = Number(opt("part-size", 16 * MiB));
if (partSize > 25 * MiB || maxFile > 25 * MiB) throw new Error("--part-size / --max-file は 25MiB 以下");

/** wasm を partSize ごとに <file>.parts/NNNN.<sha12>.part へ分割し、index.json (descriptor) を書く (05-stage.mjs と同形式) */
function splitParts(buf, file, contentType = "application/wasm") {
  const dir = path.join(out, `${file}.parts`);
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
  writeFileSync(path.join(dir, "index.json"), JSON.stringify({ v: 1, path: file, size: buf.length, sha256, contentType, partSize, parts }));
  return parts.length;
}

/** `<file>.br` (brotli q11) を隣に書き、圧縮後バイト数を返す。配信側が Content-Encoding: br で返す */
function brotliFile(file) {
  const z = brotliCompressSync(readFileSync(file), { params: { [zc.BROTLI_PARAM_QUALITY]: 11, [zc.BROTLI_PARAM_SIZE_HINT]: statSync(file).size } });
  writeFileSync(file + ".br", z);
  return z.length;
}

const SOURCES = [
  { id: "m1-hello", label: "M1 PoC (hello, PE→wasm)", rel: "tools/m1/build/wasm_elf.wasm", program: "m1-hello", gen: ["bash", ["tools/m1/m1.sh"]] },
  { id: "m6-ott", label: "M6 OTT DSP closure (lifted)", rel: "tools/m6/work/ott_test.cjs.wasm", program: "ott-t1" },
  { id: "m10-ott", label: "M10 OTT DSP closure (band coeff fix)", rel: "tools/m10/work/ott_m10.cjs.wasm", program: "ott-t1" },
  { id: "m11-boot", label: "M11 FLEngine DllMain boot closure (lifted)", rel: "tools/m11/work/m11_boot.cjs.wasm", program: "m11-boot" },
];
// RT-2 本番 pthread ビルド (tools/runtime/prod/build_pthread.sh の成果物)。glue (.mjs) 同梱。
SOURCES.push({ id: "mt-boot", label: "RT-2 production pthread build (shim MT + emcc glue)", rel: "tools/runtime/work/prod/fl-mt.wasm", glueRel: "tools/runtime/work/prod/fl-mt.mjs", program: "mt-boot", brotli: true });
const extra = process.argv.flatMap((a, i, v) => (a === "--extra" ? [v[i + 1]] : []));
for (const e of extra) { const [file, id, program] = e.split(":"); SOURCES.push({ id, label: id, abs: path.resolve(file), program }); }

for (const f of readdirSync(out)) if (/\.(wasm|mjs|br)$/.test(f) && !extra.length) rmSync(path.join(out, f));
for (const f of readdirSync(out)) if (f.endsWith(".wasm.parts") && !extra.length) rmSync(path.join(out, f), { recursive: true, force: true });
const entries = [];
for (const s of SOURCES) {
  let src = s.abs ?? path.join(root, s.rel);
  if (!existsSync(src) && s.gen) { console.error(`[stage] ${s.rel} 無し → ${s.gen[0]} ${s.gen[1].join(" ")}`); try { execFileSync(s.gen[0], s.gen[1], { cwd: root, stdio: "inherit" }); } catch (e) { console.error("[stage] gen 失敗:", e.message); } }
  if (!existsSync(src)) { console.error(`[stage] skip ${s.id}: ${src} 無し`); continue; }
  const buf = readFileSync(src);
  const sha = createHash("sha256").update(buf).digest("hex");
  const file = `${s.id}.${sha.slice(0, 12)}.wasm`;
  copyFileSync(src, path.join(out, file));
  const info = wasmInfo(buf);
  let glueFields = {};
  if (s.glueRel) {
    // emcc glue は自分自身 (pthread Worker 起動) と wasm のファイル名を決め打ちで持つ → hash 名へ置換して配置
    const gsrc = path.join(root, s.glueRel);
    if (!existsSync(gsrc)) { console.error(`[stage] skip ${s.id}: glue ${gsrc} 無し`); rmSync(path.join(out, file)); continue; }
    const base = path.basename(s.rel, ".wasm"); // fl-mt
    const gorig = readFileSync(gsrc, "utf8");
    const gfile = `${s.id}.${createHash("sha256").update(gorig).digest("hex").slice(0, 12)}.mjs`;
    const gtext = gorig.replaceAll(`${base}.mjs`, gfile).replaceAll(`${base}.wasm`, file);
    if (gtext.includes(`${base}.`)) throw new Error(`[stage] glue に未置換の ${base}. 参照が残っています`);
    writeFileSync(path.join(out, gfile), gtext);
    glueFields = { glue: gfile };
    if (s.brotli) glueFields.encodedGlue = brotliFile(path.join(out, gfile));
  }
  // 大物は元ファイルを置かず descriptor 経由で配信する (事前 br 圧縮は非対応: part は非圧縮で連結する)
  const chunked = buf.length > maxFile;
  let deliveredFile = file;
  if (chunked) {
    const nParts = splitParts(buf, file);
    rmSync(path.join(out, file));
    deliveredFile = `${file}.parts/index.json`;
    console.error(`[stage] ${s.id}: ${(buf.length / 1048576).toFixed(2)} MiB > ${(maxFile / 1048576).toFixed(0)} MiB → ${nParts} parts (descriptor ${deliveredFile})`);
  }
  const encodedWasm = s.brotli && !chunked ? brotliFile(path.join(out, file)) : undefined;
  entries.push({
    ...(s.brotli && !chunked ? { encoding: "br", encodedBytes: { wasm: encodedWasm, ...(glueFields.encodedGlue ? { glue: glueFields.encodedGlue } : {}) } } : {}),
    ...(glueFields.glue ? { glue: glueFields.glue } : {}),
    id: s.id, label: s.label, file: deliveredFile, bytes: buf.length, sha256: sha, program: s.program, source: s.abs ? s.abs : s.rel,
    memory: { imported: info.imported, exported: info.exported, shared: info.shared, memory64: info.memory64, initialPages: info.initialPages, maximumPages: info.maximumPages },
    importCount: info.importCount, exportCount: info.exportCount,
  });
  console.error(`[stage] ${s.id}: ${(buf.length / 1048576).toFixed(2)} MiB → ${file}`);
}
writeFileSync(path.join(out, "manifest.json"), JSON.stringify({ version: 1, generated: new Date().toISOString(), entries }, null, 1));
console.log(`[stage] manifest: ${entries.length} entries → ${out}/manifest.json`);
