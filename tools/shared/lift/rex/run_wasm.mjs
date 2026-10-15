// lift 済み rex.wasm で cases.bin を実行し、native_ref.c と同一形式の res_wasm.bin を書く。
// usage: node run_wasm.mjs <workdir>      env REX_NEG=ctx で wasm 側だけ ctx 大域を 0 にする (ネガティブコントロール)
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2];
const NEG = process.env.REX_NEG || "";
const L = JSON.parse(readFileSync(`${W}/layout.json`, "utf8"));
const BASE = L.base, ARENA = L.arena, ARENA_SZ = L.arena_sz, CTX = BASE + L.ctx_rva;
const DATA = BASE + L.data_rva, DATA_SZ = L.data_sz;
const EXP = [BASE + L.exp_creator_rva, BASE + L.exp_info_rva];
const img = readFileSync(`${W}/image_wasm.bin`);
const cases = readFileSync(`${W}/cases.bin`);
// WASI 呼出 (libc の stdio 等) は使わない想定。念のため未実装の import は 0 を返す (値は比較に影響しない)。
const wasi = new Proxy({}, { get: () => () => 0 });
const inst = await WebAssembly.instantiate(await WebAssembly.compile(readFileSync(`${W}/rex.wasm`)), { wasi_snapshot_preview1: wasi, env: wasi });
const ex = inst.exports;
const nat = readFileSync(`${W}/res_native.bin`);
const REC = 16 + ARENA_SZ + DATA_SZ;
const dv = new DataView(cases.buffer, cases.byteOffset, cases.byteLength);
let p = 0;
const ncase = dv.getUint32(p, true); p += 4;
const chunks = [];
let traps = 0;
for (let c = 0; c < ncase; c++) {
  const fn = dv.getUint32(p, true); p += 8;
  const natMark = nat.readBigUInt64LE(c * REC) === 0xC2A5C2A5C2A5C2A5n;
  const a0 = dv.getBigUint64(p, true), a1 = dv.getBigUint64(p + 8, true);
  const a2 = dv.getBigUint64(p + 16, true), a3 = dv.getBigUint64(p + 24, true);
  p += 32;
  const ctx = dv.getBigUint64(p, true); p += 8;
  const arena = cases.subarray(p, p + ARENA_SZ); p += ARENA_SZ;
  const mem = new Uint8Array(ex.memory.buffer);
  const mdv = new DataView(ex.memory.buffer);
  mem.set(img, BASE);
  mem.set(arena, ARENA);
  mdv.setBigUint64(CTX, NEG === "ctx" ? 0n : ctx, true);
  if (natMark) { chunks.push(nat.subarray(c * REC, (c + 1) * REC)); continue; }   // 元の機械語が落ちた case は実行しない (比較対象外)
  ex.rex_reset();
  let rax, hits;
  try {
    rax = ex.rex_run(EXP[fn], a0, a1, a2, a3);
    hits = ex.rex_hits_get();
  } catch (e) {
    traps++;
    rax = 0xdeadn; hits = 0xdeadn;
  }
  const head = Buffer.alloc(16);
  head.writeBigUInt64LE(BigInt(rax), 0);
  head.writeBigUInt64LE(BigInt(hits), 8);
  const m2 = new Uint8Array(ex.memory.buffer);
  chunks.push(head, Buffer.from(m2.slice(ARENA, ARENA + ARENA_SZ)), Buffer.from(m2.slice(DATA, DATA + DATA_SZ)));
}
writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(chunks));
console.log(`[run_wasm] cases=${ncase} traps=${traps} neg=${NEG || "none"}`);
