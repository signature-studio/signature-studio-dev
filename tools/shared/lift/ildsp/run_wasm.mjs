// lift 済み wasm (fn.wasm) を node で実行。cases.bin (native_ref.c と同一形式) を読み、同形式の res_wasm.bin を書く。
// usage: node run_wasm.mjs <workdir> <export 名>
import { readFileSync, writeFileSync } from "node:fs";
const W = process.argv[2], FN = process.argv[3];
const INNER = 0x2f8, NB = 5, BUFN = 64, PTR = [0x10, 0x18, 0x20, 0x258, 0x260];
const REC = 4 + INNER + 16 + NB * BUFN * 4;
const inst = await WebAssembly.instantiate(await WebAssembly.compile(readFileSync(`${W}/fn.wasm`)), {});
const f = inst.exports[FN];
const cases = readFileSync(`${W}/cases.bin`);
const ncase = cases.readUInt32LE(0);
let p = 4; const outs = [];
for (let c = 0; c < ncase; c++) {
  const inner0 = cases.subarray(p, p + INNER); p += INNER;
  const bufs0 = [];
  for (let i = 0; i < NB; i++) { bufs0.push(cases.subarray(p, p + BUFN * 4)); p += BUFN * 4; }
  const wrap0 = cases.subarray(p, p + 16); p += 16;
  const mem = new Uint8Array(inst.exports.memory.buffer), dv = new DataView(inst.exports.memory.buffer);
  let sp = 4 * 1024 * 1024;
  const alloc = (b) => { const a = sp; sp += (b + 15) & ~15; return a; };
  const inner = alloc(INNER), wrap = alloc(16);
  const bufs = bufs0.map(() => alloc(BUFN * 4));
  mem.set(inner0, inner); mem.set(wrap0, wrap);
  bufs.forEach((a, i) => { mem.set(bufs0[i], a); dv.setBigUint64(inner + PTR[i], BigInt(a), true); });
  dv.setBigUint64(wrap + 8, BigInt(inner), true);
  try {
    f(BigInt(wrap), 0n, 0n, 0n);
  } catch (e) {
    const t = Buffer.alloc(REC); t.writeUInt32LE(1, 0); outs.push(t); continue;
  }
  for (let i = 0; i < NB; i++) dv.setBigUint64(inner + PTR[i], 0n, true);
  dv.setBigUint64(wrap + 8, 0n, true);
  const h = Buffer.alloc(4);
  outs.push(Buffer.concat([h, mem.slice(inner, inner + INNER), mem.slice(wrap, wrap + 16), ...bufs.map((a) => mem.slice(a, a + BUFN * 4))]));
}
writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(outs));
