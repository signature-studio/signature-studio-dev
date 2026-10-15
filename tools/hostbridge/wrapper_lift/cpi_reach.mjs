// cpi_reach.mjs: lift 済み Fruity Wrapper (wasm) で CreatePlugInstance への入場と完走を確認する (#829 受入 2・#2653)。
// usage: node cpi_reach.mjs <cpi.cjs> <image.bin> <ImageBase 16進> <entry VA 16進> [a0 16進] [a1 16進]
// 判定は JSON で出す (null, 1 で整形するため複数行): entered = 入場ログ "[cpi] enter <entry VA>" を受けたか。
// ret は戻り値 (rax)。trap があれば最初に失敗した地点は last_insn の末尾 (命令 VA)。
// host_calls = host の vtable 呼び (cpi_miss) と未 lift import (cpi_miss_imp) の記録件数。host_log は先頭 40 件。
// a0 は host object の guest アドレス (cpi_host.c の CPI_HOST = 0x600000)。a0 = 0 (NULL) なら host は無い。
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const [cjs, imgPath, baseHex, vaHex, a0Hex = '0x600000', a1Hex = '0x0'] = process.argv.slice(2);
const base = Number(baseHex);
const va = Number(vaHex);
const out = [];
const err = [];
const createModule = require(resolve(cjs));
const m = await createModule({
  print: (s) => out.push(s),
  printErr: (s) => err.push(s),
});
m.HEAPU8.set(readFileSync(imgPath), base);
m._cpi_host_setup();

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
