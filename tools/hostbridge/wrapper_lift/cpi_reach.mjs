// cpi_reach.mjs: lift 済み Fruity Wrapper (wasm) で CreatePlugInstance への入場と完走を確認する (#829 受入 2・#2653)。
// usage: node cpi_reach.mjs <cpi.cjs> <image.bin> <ImageBase 16進> <entry VA 16進> [a0 16進] [a1 16進]
// 判定は JSON で出す (null, 1 で整形するため複数行): entered = 入場ログ "[cpi] enter <entry VA>" を受けたか。
// ret は戻り値 (rax)。trap があれば最初に失敗した地点は last_insn の末尾 (命令 VA)。
// host_calls = host の vtable 呼び (cpi_miss) と未 lift import (cpi_miss_imp) の記録件数。host_log は先頭 40 件。
// a0 は host object の guest アドレス (cpi_host.c の CPI_HOST = 0xA00000)。a0 = 0 (NULL) なら host は無い。
// host 領域が PE イメージ [ImageBase, ImageBase+SizeOfImage) と交差したら cpi_host_setup が 0 を返し、停止する (exit 3)。
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const [cjs, imgPath, baseHex, vaHex, a0Hex = '0xa00000', a1Hex = '0x0'] = process.argv.slice(2);
const base = Number(baseHex);
const va = Number(vaHex);
const out = [];
const err = [];

// PE ヘッダの section 表と SizeOfImage (optional header の offset 56。PE32 / PE32+ 共通)。
const pe = readFileSync(imgPath);
const peOff = pe.readUInt32LE(0x3c);
if (pe.toString('latin1', peOff, peOff + 4) !== 'PE\0\0') throw new Error('not a PE image: ' + imgPath);
const sizeOfImage = pe.readUInt32LE(peOff + 24 + 56);
const nSec = pe.readUInt16LE(peOff + 6);
const secOff = peOff + 24 + pe.readUInt16LE(peOff + 20);
const sections = [];
for (let i = 0; i < nSec; i++) {
  const s = secOff + 40 * i;
  const name = pe.toString('latin1', s, s + 8).replace(/\0.*$/, '');
  const va0 = base + pe.readUInt32LE(s + 12);
  sections.push(`${name} 0x${va0.toString(16)}-0x${(va0 + pe.readUInt32LE(s + 8)).toString(16)}`);
}

const createModule = require(resolve(cjs));
const m = await createModule({
  print: (s) => out.push(s),
  printErr: (s) => err.push(s),
});
m.HEAPU8.set(pe, base);
const hostOk = m._cpi_host_setup(BigInt(base), BigInt(base + sizeOfImage));
if (hostOk !== 1) {
  console.log(JSON.stringify({
    guard: 'host_overlaps_pe_image',
    pe_image: `0x${base.toString(16)}-0x${(base + sizeOfImage).toString(16)}`,
    sections,
  }, null, 1));
  process.exit(3);
}

let ret = null;
let trap = null;
let trapStack = null;
try {
  ret = m._ott_run(va, BigInt(a0Hex), BigInt(a1Hex), 0n, 0n, 0n, 0n, 0n, 0n);
} catch (e) {
  trap = String((e && e.message) || e);
  trapStack = String((e && e.stack) || '').split('\n').slice(0, 4);
}
// 直近の命令 VA (古い順, 最大 16 件)。trap 後も wasm メモリは残るため ring を読める。
const n = m._cpi_count();
const ringBase = m._cpi_ring_addr() >>> 0;
const last = [];
for (let i = Math.max(0, n - 16); i < n; i++) {
  const slot = ringBase + 8 * (i & 255);
  last.push('0x' + m.HEAPU32[slot >>> 2].toString(16));
}
const enterTag = `[cpi] enter 0x${va.toString(16)}`;
const entered = err.some((l) => l.includes(enterTag));
const hostLog = err.filter((l) => l.startsWith('[cpi] host') || l.startsWith('[cpi] import'));
console.log(JSON.stringify({
  pe_image: `0x${base.toString(16)}-0x${(base + sizeOfImage).toString(16)}`,
  sections,
  entered,
  ret: ret === null ? null : String(ret),
  trap,
  trap_stack: trapStack,
  insn_count: n,
  last_insn: last,
  host_calls: hostLog.length,
  host_log: hostLog.slice(0, 40),
  err_tail: err.slice(-6),
  out_tail: out.slice(-3),
}, null, 1));
