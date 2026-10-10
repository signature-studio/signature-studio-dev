#!/usr/bin/env bash
# m10_e2e.sh (M10): 1 コマンド検収.
#   - E1 ctor/resume 完走 ([0x30c]/[0x310] = 1/1)
#   - E2 [F8] band filter 係数 = dsm register-exact 転記との bit 突合 (tools/m10/m10_coefref.py, maxdev==0)
#   - E3 .rdata 直値 (π̂ bits 等) が native PE と一致 (m6 install 検証)
#   - E4 processReplacing determinism (同一 obj+fresh module → 出力 bits 完全一致)
#   - E5 param 応答 (0.1 vs 0.5 で正常 cell が変化)
#   - E6 junk census INFO ([0x248]=0 / =1) — M9 baseline junkHi=175 継続 (整形条件は REPORT §)
#   - E7 [F3] fail-fast OOB 不発 (c69cc / c91cc, m8 設計保持)
# bit-exact 512/512 は junkHi=175>0 のため不成立 → REPORT.md の tolerance 宣言に従う。
set -euo pipefail
M10="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$M10"
export M10_DIR="$M10"

if [ "${M10_SKIP_BUILD:-0}" != "1" ]; then
  timeout 1200 bash "$M10/m10_build.sh" >/dev/null 2>&1 || { echo "[m10_e2e] build FAIL" >&2; exit 1; }
fi
[ -f work/ott_m10.cjs ] || { echo "[m10_e2e] ott_m10.cjs 無し" >&2; exit 1; }

# --- probe 1: E1/E3/E4/E5/E6 を node で 1 回実行
cat > work/e2e_check.mjs <<'EOFMJS'
const M10 = process.env.M10_DIR;
const m2 = await import(M10 + '/work/ott_m10.cjs');
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = 256;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const chk = [];
const ck = (nm, cond, extra = '') => { chk.push([nm, cond]); console.log((cond ? 'OK  ' : 'FAIL'), nm, extra); };

function fillInputs() {
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
  U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}
function setup(val) {
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  mod._function_180120800(BigInt(OBJ));
  U8[OBJ + 0x248] = 0;
  fillInputs();
}

// E1
setup(0.5);
ck('E1a ctor/resume ([0x30c]/[0x310]=1/1)',
   dv.getUint32(OBJ + 0x30c, true) === 1 && dv.getUint32(OBJ + 0x310, true) === 1);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
ck('E1b processReplacing 完走', true);

// E3 .rdata 直値: π̂ と 2π̂
const lin = (va) => 0x30000000 + (va - 0x180000000);
const bits64 = (p) => dv.getBigUint64(p, true);
ck('E3a .rdata π̂ = 0x4009249249249243',
   bits64(lin(0x1802056E8)) === 0x4009249249249243n,
   '(0x' + bits64(lin(0x1802056E8)).toString(16) + ')');
ck('E3b .rdata 2π̂ = 0x4019249249249243',
   bits64(lin(0x1802056F8)) === 0x4019249249249243n,
   '(0x' + bits64(lin(0x1802056F8)).toString(16) + ')');
ck('E3c outputs pointer 配列 intact', dv.getUint32(OU_A, true) === BUF + N * 8);

// E4 determinism: 強制確認のため OBJ 再初期化後, 2 回同一手順 → 出力 bits 一致
const snap = () => {
  const a = new Array(N * 2);
  for (let i = 0; i < N; i++) a[i] = dv.getUint32(BUF + N * 8 + i * 4, true);
  for (let i = 0; i < N; i++) a[N + i] = dv.getUint32(BUF + N * 12 + i * 4, true);
  return a;
};
setup(0.5);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const ref = snap();
setup(0.5);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const ref2 = snap();
let dsum = 0;
for (let i = 0; i < N * 2; i++) if (ref[i] !== ref2[i]) dsum++;
ck('E4 determinism (再実行で出力 bits 完全一致)', dsum === 0, '(diff cells=' + dsum + ')');

// E5 param 応答
setup(0.1);
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const cmp = snap();
let ndiff = 0;
for (let i = 0; i < N * 2; i++) if (cmp[i] !== ref[i]) ndiff++;
ck('E5 t1 出力 param 応答 (0.5 vs 0.1 bits 変化)', ndiff > 100, '(diff cells=' + ndiff + ')');

// E6 junk census ([0x248]=0)
const cens = (f248) => {
  setup(0.5); U8[OBJ + 0x248] = f248;
  mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const r = { zero: 0, normal: 0, junkHi: 0, junkTiny: 0, nan: 0, absmax: 0 };
  for (let ch = 0; ch < 2; ch++) for (let i = 0; i < N; i++) {
    const v = dv.getFloat32(BUF + N * 8 + ch * N * 4 + i * 4, true);
    const a = Math.abs(v); if (a > r.absmax) r.absmax = a;
    if (v === 0) r.zero++;
    else if (Number.isNaN(v)) r.nan++;
    else if (a >= 4) r.junkHi++;
    else if (a <= 1e-18) r.junkTiny++;
    else r.normal++;
  }
  return r;
};
const c0 = cens(0), c1 = cens(1);
console.log('[INFO] census [0x248]=0 :', JSON.stringify(c0));
console.log('[INFO] census [0x248]=1 :', JSON.stringify(c1));

const broken = chk.filter(([, c]) => !c).length;
console.log(`[m10_e2e] checks ${chk.length} / broken ${broken}`);
if (broken > 0) process.exit(1);
EOFMJS

P=0
timeout 300 node work/e2e_check.mjs || P=1

# --- probe 2: [F8] dsm register-exact 突合 (E2)
timeout 120 node m10_coefdump.mjs > work/m10_coefdump.json || P=1
PYOUT=$(timeout 60 python3 m10_coefref.py work/m10_coefdump.json) || P=1
echo "[E2] coefref: $PYOUT"
python3 - "$PYOUT" <<'PYEOF' || P=1
import json, sys
r = json.loads(sys.argv[1])
assert r['nbad'] == 0 and r['maxdev'] <= 1e-9, r
print('OK   E2 [F8] band 係数 = dsm register-exact (maxdev=%.3g, 8 states x 10 coef 全 bit 突合)' % r['maxdev'])
PYEOF

# --- probe 3: [F3] OOB 不発 (trap9 相当, 参照 tools/m9)
cat > work/e2e_trap10.mjs <<'EOFMJS2'
const M10 = process.env.M10_DIR + '/work/ott_m10.cjs';
const mk = await import(M10);
let oob = 0;
for (const n of ['function_1801c69cc', 'function_1801c91cc']) {
  const mod = await (mk.default ? mk.default() : mk());
  if (mod._m6_data_install) mod._m6_data_install();
  const obj = BigInt(mod._function_18011d400(BigInt(0x30000000 + 0x310000), 0n));
  const args = n === 'function_1801c69cc' ? [obj] :
    [0x30310000, BigInt(0), BigInt(0), BigInt(0)];
  try { mod['_' + n](...args); console.log('OK  (no trap):', n); }
  catch (e) {
    const msg = String(e.message || e);
    if (/out of bounds/i.test(msg)) { console.log('FAIL (OOB!!):', n); oob++; }
    else console.log('OK  (fail-fast missing CRT, OOB 不発):', n, '|', msg.slice(0, 60));
  }
}
process.exit(oob ? 1 : 0);
EOFMJS2
timeout 300 node work/e2e_trap10.mjs || P=1

[ "$P" = "0" ] && echo '[m10_e2e] PASS' || echo '[m10_e2e] FAIL'
exit $P
