// lift 済み wc.wasm で cases.bin を実行し、wc_native_ref.c と同一形式の res_wasm.bin を書く (T-SH-52 / #3216)。
// usage: node wc_run_wasm.mjs <workdir>      env WC_NEG=arena で wasm 結果の heap 先頭 1 バイトを反転 (ネガティブコントロール)
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2];
const NEG = process.env.WC_NEG || "";
const COV = process.env.WC_COV === "1";
const HEAPLOG = process.env.WC_HEAP_LOG === "1";
const covChunks = [];
const L = JSON.parse(readFileSync(`${W}/layout.json`, "utf8"));
const BASE = L.base, ARENA = L.arena, ARENA_SZ = L.arena_sz, DATA = BASE + L.data_rva, DATA_SZ = L.data_sz;
const ENTRY = BASE + L.entry_rva;
const img = readFileSync(`${W}/image_wasm.bin`);
const cases = readFileSync(`${W}/cases.bin`);
// wasm の import は全て throw させる (0 を返して黙殺すると、呼出しが比較を誤って一致させうる)。
// 呼ばれた場合は下の catch で trap として数え、差分は FAIL になる。
const mod = await WebAssembly.compile(readFileSync(`${W}/wc.wasm`));
const imports = {};
for (const { module, name } of WebAssembly.Module.imports(mod)) {
  (imports[module] ??= {})[name] = () => { throw new Error(`unknown import ${module}.${name}`); };
}
// 診断用 (WC_LOG_FD=1): fd_write の文字列 (runtime の fprintf(stderr) の内容) を出して続行する。既定は上の throw のまま。
if (process.env.WC_LOG_FD === "1") {
  imports.wasi_snapshot_preview1 ??= {};
  imports.wasi_snapshot_preview1.fd_write = (fd, iovs, n, nw) => {
    const dv = new DataView(inst.exports.memory.buffer), bytes = new Uint8Array(inst.exports.memory.buffer);
    let total = 0, s = "";
    for (let i = 0; i < n; i++) {
      const p = dv.getUint32(iovs + i * 8, true), l = dv.getUint32(iovs + i * 8 + 4, true);
      s += Buffer.from(bytes.subarray(p, p + l)).toString("utf8"); total += l;
    }
    dv.setUint32(nw, total, true);
    console.log(`[fd_write fd=${fd}] ${s.trimEnd()}`);
    return 0;
  };
}
console.log(`[run_wasm] imports: ${WebAssembly.Module.imports(mod).map((i) => `${i.module}.${i.name}`).join(" ") || "(none)"}`);
const inst = await WebAssembly.instantiate(mod, imports);
const ex = inst.exports;
const nat = readFileSync(`${W}/res_native.bin`);
const REC = 16 + ARENA_SZ + DATA_SZ;
const ncase = cases.readUInt32LE(0);
let p = 4;
const chunks = [];
let traps = 0, skipped = 0;
for (let c = 0; c < ncase; c++) {
  const data = cases.subarray(p, p + DATA_SZ); p += DATA_SZ;
  // native が落ちた case (hits 欄 = CRASH_MARK) は定義された結果が無いので、native の記録をそのまま使い比較から外す
  if (nat.readBigUInt64LE(c * REC + 8) === 0xC2A5C2A5C2A5C2A5n) { chunks.push(nat.subarray(c * REC, (c + 1) * REC)); skipped++; continue; }
  const mem = new Uint8Array(ex.memory.buffer);
  mem.set(img, BASE);
  mem.set(data, DATA);
  mem.fill(0, ARENA, ARENA + ARENA_SZ);
  ex.wc_reset();
  const heapLog = HEAPLOG && c === 0;
  let rax, hits;
  try {
    // (init) → CreateInstance → vtable の slot を順に呼ぶ (wc_native_ref.c と同一の順序・引数・式)
    if (heapLog) ex.wc_log_set(1, 0);
    if (L.init_rva) ex.wc_run(BASE + L.init_rva, 0n, 0n, 0n, 0n);
    if (process.env.WC_TRACE === "1") console.error(`[run_wasm] trace case=${c} stage=init-done`);
    if (heapLog) ex.wc_log_set(1, 1);
    const obj = ex.wc_run(ENTRY, 0n, 0n, 0n, 0n);
    if (process.env.WC_TRACE === "1") console.error(`[run_wasm] trace case=${c} stage=create-done obj=${obj.toString(16)}`);
    let acc = obj;
    for (const [k, s] of L.slots.slice(0, L.call_slots).entries()) {
      const [a1, a2, a3, a4] = L.call_args[k].map((v) => BigInt(v));
      if (process.env.WC_TRACE === "1") console.error(`[run_wasm] trace case=${c} slot=${k} rva=${s.toString(16)} args=${[obj, a1, a2, a3, a4].map((v) => v.toString(16)).join(",")}`);
      if (heapLog) ex.wc_log_set(1, 2 + k);
      const r = ex.wc_run5(BASE + s, obj, a1, a2, a3, a4);
      if (process.env.WC_TRACE === "1") console.error(`[run_wasm] trace case=${c} slot=${k} done rax=${r.toString(16)}`);
      if ((L.ret_mask >> k) & 1) acc = BigInt.asUintN(64, acc * 31n + r);
    }
    rax = acc;
    hits = ex.wc_hits_get();
  } catch (e) {
    if (traps === 0) console.error(`[run_wasm] first trap case=${c}: ${e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e}`);
    traps++;
    rax = 0xdeadn; hits = 0xdeadn;
  }
  const head = Buffer.alloc(16);
  head.writeBigUInt64LE(BigInt(rax), 0);
  head.writeBigUInt64LE(BigInt(hits), 8);
  const m2 = new Uint8Array(ex.memory.buffer);
  const arena = Buffer.from(m2.slice(ARENA, ARENA + ARENA_SZ));
  if (NEG === "arena") arena[0] ^= 0x01;
  chunks.push(head, arena, Buffer.from(m2.slice(DATA, DATA + DATA_SZ)));
  if (COV) {
    const cov = new Uint8Array(512);
    for (let i = 0; i < 512; i++) cov[i] = ex.wc_cov_get(i);
    covChunks.push(Buffer.from(cov));
  }
}
writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(chunks));
if (COV) writeFileSync(`${W}/res_cov_wasm.bin`, Buffer.concat(covChunks));
console.log(`[run_wasm] cases=${ncase} traps=${traps} native_excluded=${skipped} neg=${NEG || "none"}`);
