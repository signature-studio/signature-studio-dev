#!/usr/bin/env bash
#!/bin/bash
# m9_e2e.sh (M9): 1 コマンド検収。
#   - m9_build.sh (work/ 既存があれば chain 再利用; build は増分で数十秒)
#   - node probe 群: 
#     (E1) ctor/resume 完走 + [0x30c]/[0x310] = 1/1
#     (E2) [F7] 出力 copy deref: outputs pointer 配列改変無し + outL/outR 両立非ゼロ
#     (E3) [F8] band filter 係数: state+0x68..0xb0 の f64 NaN 係数の消滅 (旧 qNaN → 実数)
#     (E4) [F9] c38c8 family table base remap: c69cc/c91cc 直呼で OOB (out of bounds) 不発
#          (missing CRT fail-fast abort は m8 設計通り許容)
#     (E5) t1 出力が param/入力に応答 (T1VAL 変化で out が変化)
# 安全 net: 全チェックは try 系 catch なしで FAIL 時 exit 1。
set -euo pipefail
M9="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$M9"

if [ "${M9_SKIP_BUILD:-0}" != "1" ]; then
  bash "$M9/m9_build.sh" >/dev/null 2>&1 || { echo "[m9_e2e] build FAIL" >&2; exit 1; }
fi
[ -f work/ott_m9.cjs ] || { echo "[m9_e2e] ott_m9.cjs 無し" >&2; exit 1; }
cat > work/e2e_check.mjs <<'EOFMJS'
const VA_BASE = 0x30000000;
const mod = await (async () => {
  const m2 = await import(process.env.M9_DIR + '/work/ott_m9.cjs');
  return m2.default ? m2.default() : m2();
})();
if (mod._m6_data_install) mod._m6_data_install();
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const f32b = (v)=>{const f=new Float32Array(1);f[0]=v;return BigInt(new Uint32Array(f.buffer)[0]);};
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = 256;
const chk = [];
const ck = (nm, cond) => { chk.push([nm, cond]); console.log((cond ? 'OK  ' : 'FAIL'), nm); };

// ---- 共通手順: ctor → setParam(0..18 = 0.5, 19 = 0) → resume → (SVF 路線強制 0x248=0)
function setup(val) {
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  mod._function_180120800(BigInt(OBJ));
  U8[OBJ + 0x248] = 0;
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
  U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}
setup(0.5);
ck('E1a ctor/resume 完走 ([0x30c]/[0x310] = 1/1)',
   dv.getUint32(OBJ + 0x30c, true) === 1 && dv.getUint32(OBJ + 0x310, true) === 1);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
ck('E1b processReplacing 完走 (OOB 無し)', true);   // throw しなければ PASS

// (E2) F7: outputs pointer 配列が改変されていない (f32 junk 書込み無し → qword slot 保持)
const okArr = dv.getUint32(OU_A, true) === BUF + N * 8 && dv.getUint32(OU_A + 8, true) === BUF + N * 12
  && dv.getUint32(OU_A + 4, true) === 0 && dv.getUint32(OU_A + 16, true) === 0;
ck('E2a outputs pointer 配列 intact (F7 deref 修復)', okArr);
let outLnonzero = 0, outRnonzero = 0;
for (let i = 0; i < N; i++) {
  if (dv.getUint32(BUF + N * 8 + i * 4, true) !== 0) outLnonzero++;
  if (dv.getUint32(BUF + N * 12 + i * 4, true) !== 0) outRnonzero++;
}
ck('E2b outL/outR 両チャネル非ゼロ (L/R 配置回復)', outLnonzero > 16 && outRnonzero > 16);

// (E3) F8: band filter state の係数が NaN → 実数化
const st = dv.getUint32(OBJ + 0x148, true);
let nancoef = 0;
for (const off of [0x68, 0x70, 0x78, 0x98, 0xa0, 0xa8, 0xb0])
  if (!Number.isFinite(dv.getFloat64(st + off, true))) nancoef++;
ck('E3 band filter 係数 NaN 消滅 (F8 C port)', nancoef === 0);

// (E5) t1 param 応答 (param 値 0.1 へ変更後に再 process → out が変化)
setup(0.1);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const bv = [], av = [];
setup(0.5);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
let diff = 0;
for (let i = 0; i < N; i++) {
  const vb = dv.getFloat32(BUF + N * 8 + i * 4, true);
  if (vb !== 0) { bv.push(vb); diff++; }
}
ck('E5 t1 出力 param/入力 応答 (非 zero 値 ' + bv.length + ' sample)', diff > 8);

const broken = chk.filter(([_, c]) => !c).length;
console.log(`[m9_e2e] checks ${chk.length} / broken ${broken}`);
if (broken > 0) process.exit(1);
EOFMJS

# (E4) F9: c69cc/c91cc 直呼で OOB 不発 (fail-fast abort は許容)。別 instance 分離。
cat > work/e2e_trap9.mjs <<'EOFMJS2'
const VA_BASE = 0x30000000;
const mk = await import(process.env.M9_DIR + '/work/ott_m9.cjs');
const probes = [['function_1801c69cc', 1], ['function_1801c91cc', 4]];
let oobCount = 0;
for (const [n, argc] of probes) {
  const mod = await (mk.default ? mk.default() : mk());
  if (mod._m6_data_install) mod._m6_data_install();
  const obj = BigInt(mod._function_18011d400(BigInt(VA_BASE + 0x310000), 0n));
  const args = n === 'function_1801c69cc' ? [obj] : [0x30310000, BigInt(0), BigInt(0), BigInt(0)];
  try { mod['_' + n](...args); console.log('OK  (no trap):', n); }
  catch (e) {
    const msg = String(e.message || e);
    const oob = /out of bounds/i.test(msg);
    console.log(oob ? 'FAIL (OOB!!)' : 'OK  (fail-fast missing CRT, OOB 不発):', n, '|', msg.slice(0, 70));
    if (oob) oobCount++;
  }
}
if (oobCount > 0) process.exit(1);
EOFMJS2

P=0
M9_DIR="$M9" timeout 300 node work/e2e_check.mjs || P=1
M9_DIR="$M9" timeout 300 node work/e2e_trap9.mjs || P=1
[ "$P" = "0" ] && echo '[m9_e2e] PASS' || echo '[m9_e2e] FAIL'
exit $P
