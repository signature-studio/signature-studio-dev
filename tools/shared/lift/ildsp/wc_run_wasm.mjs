// lift 済み wc.wasm で cases.bin を実行し、wc_native_ref.c と同一形式の res_wasm.bin を書く (T-SH-52 / #3216)。
// usage: node wc_run_wasm.mjs <workdir>      env WC_NEG=arena で wasm 結果の heap 先頭 1 バイトを反転 (ネガティブコントロール)
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2];
const NEG = process.env.WC_NEG || "";
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
  let rax, hits;
  try {
    // CreateInstance → vtable の slot を順に呼ぶ (wc_native_ref.c と同一の順序・引数・式)
    const obj = ex.wc_run(ENTRY, 0n, 0n, 0n, 0n);
    let acc = obj;
    for (const s of L.slots.slice(0, L.call_slots)) {
      const r = ex.wc_run(BASE + s, obj, BigInt(ARENA + 0x8000), 0n, 0n);
      acc = BigInt.asUintN(64, acc * 31n + r);
    }
    rax = acc;
    hits = ex.wc_hits_get();
  } catch (e) {
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
}
writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(chunks));
console.log(`[run_wasm] cases=${ncase} traps=${traps} native_excluded=${skipped} neg=${NEG || "none"}`);
