// cpi_reach.mjs: lift 済み Fruity Wrapper (wasm) で CreatePlugInstance (VA 0x86ab10) への入場を確認する (#829 受入 2)。
// usage: node cpi_reach.mjs <cpi.cjs> <image.bin> <ImageBase 16進> <entry VA 16進> [a0 16進] [a1 16進]
// 判定は JSON で出す (null, 1 で整形するため複数行): entered = 入場ログ "[cpi] enter <entry VA>" を受けたか。false なら err_tail の末尾が最初に失敗した地点。
// a0/a1 省略時は 0 (NULL)。ゼロ埋めの guest 領域 (例 0x30000000) を渡すと、NULL の逆参照で落ちる地点を越えられるかを見る。
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const [cjs, imgPath, baseHex, vaHex, a0Hex = '0x0', a1Hex = '0x0'] = process.argv.slice(2);
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

// CreatePlugInstance(host, tag): 既定は host = NULL。host 実体は無いため、失敗地点の特定が目的。
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
console.log(JSON.stringify({
  entered,
  ret: ret === null ? null : String(ret),
  trap,
  trap_stack: trapStack,
  insn_count: n,
  last_insn: last,
  err_tail: err.slice(-6),
  out_tail: out.slice(-3),
}, null, 1));
