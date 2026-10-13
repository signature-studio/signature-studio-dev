// lift 済み wasm (rv.wasm) を node で実行。cases.bin (native_ref.c と同一形式) を読み、同形式の res_wasm.bin を書く。
// usage: node run_wasm.mjs <workdir>
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2];
const NL = 14, PTR0 = 0xbc;
const mod = await WebAssembly.compile(readFileSync(`${W}/rv.wasm`));
const inst = await WebAssembly.instantiate(mod, {});
const ex = inst.exports;
const cases = readFileSync(`${W}/cases.bin`);
const dv0 = new DataView(cases.buffer, cases.byteOffset, cases.byteLength);
let p = 0; const rd = () => { const v = dv0.getUint32(p, true); p += 4; return v; };
const ncase = rd(); const outs = [];
for (let c = 0; c < ncase; c++) {
  const fn = rd(), n = rd(), aux = rd(), S = rd();
  const sz = [], cap = [];
  for (let i = 0; i < NL; i++) sz.push(rd());
  for (let i = 0; i < NL; i++) cap.push(rd());
  const mem = new Uint8Array(ex.memory.buffer), dv = new DataView(ex.memory.buffer);
  let sp = 4 * 1024 * 1024; const alloc = (b) => { const a = sp; sp += (b + 15) & ~15; return a; };
  const st = alloc(S); mem.set(cases.subarray(p, p + S), st); p += S;
  const bufs = [];
  for (let i = 0; i < NL; i++) { const a = alloc(cap[i] * 4); mem.set(cases.subarray(p, p + cap[i] * 4), a); p += cap[i] * 4; bufs.push(a); dv.setBigUint64(st + PTR0 + 8 * i, BigInt(a), true); }
  const inp = alloc(4 * (n + 1)); if (n) { mem.set(cases.subarray(p, p + 4 * n), inp); p += 4 * n; }
  const out = alloc(8 * (n + 1)), ax = alloc(8 * (n + 1));
  mem.fill(0xA5, out, out + 8 * (n + 1)); mem.fill(0xA5, ax, ax + 8 * (n + 1));
  try {
    if (fn === 0) ex.function_180001240(BigInt(st), BigInt(inp), BigInt(out), BigInt(n));
    else ex.function_180001ba0(BigInt(st), BigInt(inp), BigInt(out), BigInt(aux ? ax : 0), n);
  } catch (e) { outs.push(Buffer.from("TRAP:" + e.message)); continue; }
  for (let i = 0; i < NL; i++) mem.fill(0, st + PTR0 + 8 * i, st + PTR0 + 8 * i + 8);
  const parts = [mem.slice(st, st + S)];
  for (let i = 0; i < NL; i++) parts.push(mem.slice(bufs[i], bufs[i] + cap[i] * 4));
  parts.push(mem.slice(out, out + 8 * n)); if (aux) parts.push(mem.slice(ax, ax + 8 * n));
  outs.push(Buffer.concat(parts));
}
// 形式: [u32 len][bytes] の列 (TRAP は len 先頭に 0xFFFFFFFF を付けず "TRAP:" 文字列で識別)
const chunks = [];
for (const o of outs) { const h = Buffer.alloc(4); h.writeUInt32LE(o.length); chunks.push(h, o); }
writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(chunks));
