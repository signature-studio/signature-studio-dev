// LD-185 (#3988): x64c 計装 wasm (-DOTT_INSNTRACE) で 1801c5e84 を vm0 / u16 の入力 1 回ずつ実行し、命令 VA 列を取る。
// 使い方: node ld185_trace.mjs <ottl_insn.cjs> <out.json>
// arena 配置は tools/liftdiff/ldlib/cases.py (make_blob_vm / make_blob_u16) と同じ。ptr 引数 = arena+0x1000、2 番目の引数 = small (3)。
import fs from 'node:fs';
import path from 'node:path';
import { load } from '../../../ott/diff/api.mjs';

const cjs = process.argv[2];
const out = process.argv[3];
const api = await load(path.resolve(cjs));
const mod = api.mod;
const INS = 0x35a00000;          // ott_cpu.c の OTT_INSN_BUF
const CAP = 0x40000;
const ARENA = 0x30400000;        // guest 領域と非衝突 (cases.py の arena 相当)
const TARGET = 0x1801c5e84;
function blobFor(name) {
  const buf = new Uint8Array(0x40000);
  const dv = new DataView(buf.buffer);
  if (name === 'vm0') {
    // this の先頭 = VMT (arena+0x2000) への fixup ptr。ARENA の guest アドレスは実行時に足す。
    dv.setBigUint64(0x1000, BigInt(0x2000), true);
  } else {
    const text = 'FL Studio 26.1.7 ABC';
    dv.setInt32(0x1000, 1, true);
    dv.setInt32(0x1004, text.length, true);
    for (let i = 0; i < text.length; i++) { buf[0x1008 + 2 * i] = text.charCodeAt(i); buf[0x1008 + 2 * i + 1] = 0; }
  }
  return buf;
}

function runOne(name) {
  const u8 = mod.HEAPU8;
  u8.fill(0, ARENA, ARENA + 0x40000);
  const blob = blobFor(name);
  u8.set(blob, ARENA);
  const dv = new DataView(u8.buffer);
  if (name === 'vm0') dv.setBigUint64(ARENA + 0x1000, BigInt(ARENA + 0x2000), true);
  const p = ARENA + 0x1000;
  mod.HEAPU32[INS / 4] = 0; mod.HEAPU32[INS / 4 + 1] = CAP;
  const rv = api.run(TARGET, [p, 3]);
  const n = mod.HEAPU32[INS / 4];
  const vas = [];
  for (let i = 0; i < n && i < CAP; i++) vas.push(mod.HEAPU32[INS / 4 + 2 + i].toString(16));
  return { pattern: name, ret: rv.toString(16), count: n, vas };
}

const res = { target: '1801c5e84', cases: [runOne('vm0'), runOne('u16')] };
fs.writeFileSync(out, JSON.stringify(res, null, 1));
console.log(JSON.stringify(res.cases.map(c => ({ pattern: c.pattern, ret: c.ret, count: c.count }))));
