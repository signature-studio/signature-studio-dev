#!/usr/bin/env bash
# ld115_e2e.sh — #2447 (LD-115) / #2527 (LD-117) 1 コマンド再現。666a60 のループの修復 (fix_ld115.py) が
# 本番の IR 生成経路 (m11_gen_ir2.sh → m11_build.sh) に組み込まれていることを検証する。
#   1/6 IR 生成: M11_FIX_LD115=0 (修復前) と既定 (修復後 = 本番) の m11_gen_ir2.sh。ir_conditions と m11_cond --check、IR の diff (差は function_666a60 の 1 関数だけ)
#   2/6 MID IR (negctl): 修復前 IR に fix_ld115.py --only count (回数初期値だけ直す。ループ内 store の欠陥を単独で示す)
#   3/6 wasm build (m11_build.sh)。修復前と MID は M11_ALLOW_LD115_DISABLED=1、修復後は通常の build
#   4/6 666a60 を 3 版の wasm で直接呼ぶ (dyn_ld115.mjs。期待: 修復前は trap、MID は slot.f16 のみ FAIL、修復後は全 PASS)
#   5/6 survey 942 unit を修復前 / 修復後で測り、unit ごとに突合 (ok 退行 0 であること)
#   6/6 ネガティブコントロール (fix_ld115 の assert・m11_cond の指紋・m11_build の ld115 記録拒否)
# 前提: tools/m11/work に work-m11 の展開 (boot0..4.lift.ll / m11_image.bin / boot*.drc.config.json ほか)、
#       FL_WIN64_DIR (fl-win64 の展開先 = extracted/block00031_PE.bin が入る)、[EMSDK] (docs/REFERENCES.md)、
#       Python の capstone・pefile。boot_final.ll は本スクリプトが m11_gen_ir2.sh で作り直す (snapshot の boot_final.ll は使わない)。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ld115_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
export FL_WIN64_DIR
OUT="${RUNNER_TEMP:-/tmp}/ld115_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/pre" "$OUT/mid" "$OUT/post"
PY="${PY:-python3}"
FAIL=0
step() { echo "[ld115_e2e] $*"; }
chk() { # chk <名前> <rc 0 なら PASS>
  if [ "$2" = 0 ]; then echo "[ld115_e2e] PASS $1"; else echo "[ld115_e2e] FAIL $1"; FAIL=$((FAIL + 1)); fi
}
step "環境: node $(node --version) / python $($PY --version 2>&1 | cut -d' ' -f2) / nproc $(nproc) / MemAvailable $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) MiB / load $(cut -d' ' -f1-3 /proc/loadavg)"
# 元の IR (work/) を退避し、終了時に必ず戻す (本スクリプトは work/boot_final*.ll と ir_conditions.json を書き換える)
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"; cp "$W/boot_final3.ll" "$OUT/orig_boot_final3.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"; cp "$OUT/orig_boot_final3.ll" "$W/boot_final3.ll"
  if [ -f "$OUT/orig_ir_conditions.json" ]; then cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"; else rm -f "$W/ir_conditions.json"; fi
}
trap restore EXIT
cd "$M11" || exit 1

step "1/6 IR 生成 (本番経路 m11_gen_ir2.sh。修復前 = M11_FIX_LD115=0、修復後 = 既定)"
M11_FIX_LD115=0 bash m11_gen_ir2.sh > "$OUT/gen_pre.log" 2>&1 || { echo "gen_ir2 (修復前) 失敗: $OUT/gen_pre.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/pre.ll"; cp "$W/ir_conditions.json" "$OUT/pre.cond.json"
python3 m11_cond.py --check "$OUT/pre.ll"; chk "m11_cond --check (修復前 IR・生成直後)" $?
bash m11_gen_ir2.sh > "$OUT/gen_post.log" 2>&1 || { echo "gen_ir2 (修復後) 失敗: $OUT/gen_post.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/post.ll"; cp "$W/ir_conditions.json" "$OUT/post.cond.json"
python3 m11_cond.py --check "$OUT/post.ll"; chk "m11_cond --check (修復後 IR・生成直後)" $?
echo "[ir_conditions pre ] $(tr -d '\n ' < "$OUT/pre.cond.json")"
echo "[ir_conditions post] $(tr -d '\n ' < "$OUT/post.cond.json")"
"$PY" - "$OUT/pre.cond.json" "$OUT/post.cond.json" <<'PYEOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
same = all(a.get(k) == b.get(k) for k in ('ldfix', 'qstore', 'ld108', 'pe'))
print('[ir_conditions] ldfix・qstore・ld108・pe は修復前後で %s。ld115: %s -> %s。ir_sha256: %s' % (
    '一致' if same else '不一致', a.get('ld115'), b.get('ld115'), '差あり' if a.get('ir_sha256') != b.get('ir_sha256') else '同一'))
sys.exit(0 if same and a.get('ld115') == 'disabled' and b.get('ld115') == 'applied' and a.get('ir_sha256') != b.get('ir_sha256') else 1)
PYEOF
chk "ir_conditions (ldfix・qstore・ld108・pe 一致、ld115 disabled -> applied、指紋は別)" $?
diff "$OUT/pre.ll" "$OUT/post.ll" > "$OUT/ir.diff"
echo "[diff pre.ll post.ll] 変更行 $(grep -c '^[<>]' "$OUT/ir.diff") 行"
"$PY" - "$OUT/pre.ll" "$OUT/post.ll" <<'PYEOF'
import re, sys
FN = re.compile(r'^define [^\n]*@([\w$.]+)\(.*?\n}\n', re.M | re.S)
def split(p):
    s = open(p, errors='replace').read()
    fns, rest, pos = {}, [], 0
    for m in FN.finditer(s):
        rest.append(s[pos:m.start()]); fns[m.group(1)] = m.group(0); pos = m.end()
    rest.append(s[pos:])
    return fns, ''.join(rest)
fa, ra = split(sys.argv[1]); fb, rb = split(sys.argv[2])
diff = sorted(n for n in set(fa) | set(fb) if fa.get(n) != fb.get(n))
print('LD115_IRDIFF 差のある関数 %d: %s / 関数外の本文 %s' % (len(diff), ' '.join(diff), '一致' if ra == rb else '不一致'))
sys.exit(0 if diff == ['function_666a60'] and ra == rb else 1)
PYEOF
chk "IR の差は function_666a60 の 1 関数だけ" $?

step "2/6 MID IR (negctl): 修復前 IR に回数初期値だけを直す (fix_ld115.py --only count)"
"$PY" "$HERE/fix_ld115.py" "$OUT/pre.ll" "$OUT/mid.ll" --only count || exit 1
diff "$OUT/pre.ll" "$OUT/mid.ll" > "$OUT/ir_mid.diff"; echo "[diff pre.ll mid.ll] 変更行 $(grep -c '^[<>]' "$OUT/ir_mid.diff") 行"

step "3/6 wasm build (修復前 → $OUT/pre, MID → $OUT/mid, 修復後 → $OUT/post)"
build() { # build <pre|mid|post> <環境変数...>
  local k="$1"; shift
  cp "$OUT/$k.ll" "$W/boot_final.ll"
  if [ "$k" = mid ]; then
    # MID は正規の生成経路を通らない negctl。修復前の記録 (ld115=disabled) を写し、指紋だけ MID の IR に合わせる (手で記録)
    cp "$OUT/pre.cond.json" "$W/ir_conditions.json"; python3 m11_cond.py --bind "$W/boot_final.ll"
  else
    cp "$OUT/$k.cond.json" "$W/ir_conditions.json"
  fi
  rm -f "$W/obj/boot.o" "$W/boot_final3.ll"
  env "$@" timeout 1500 bash m11_build.sh > "$OUT/build_$k.log" 2>&1 || { echo "build 失敗: $OUT/build_$k.log"; exit 1; }
  python3 m11_cond.py --check "$W/boot_final.ll"; chk "m11_cond --check ($k・build 後。qstore 等の書換え後に指紋が更新されている)" $?
  cp "$W/ir_conditions.json" "$OUT/$k.cond_built.json"
  cp "$W/m11_boot.cjs" "$OUT/$k/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/$k/m11_boot.cjs.wasm"
}
build pre M11_ALLOW_LD115_DISABLED=1
build mid M11_ALLOW_LD115_DISABLED=1
build post M11_ALLOW_LD115_DISABLED=0
echo "[ir_conditions post・build 後] $(tr -d '\n ' < "$OUT/post.cond_built.json")"

step "4/6 666a60 の動的確認 (dyn_ld115.mjs。通常 build の wasm を after に渡す)"
node "$HERE/dyn_ld115.mjs" "$OUT/pre/m11_boot.cjs" "$OUT/mid/m11_boot.cjs" "$OUT/post/m11_boot.cjs" "$W/m11_image.bin" | tee "$OUT/dyn.txt"
grep -q 'DYN_SUMMARY after_fail=0/1' "$OUT/dyn.txt"; chk "修復後 wasm (本番経路) の 666a60 が期待値と一致" $?
grep -q 'DYN 666a60 base: TRAP' "$OUT/dyn.txt"; chk "修復前 wasm の 666a60 は TRAP (回数初期値の欠陥)" $?
grep -qE 'DYN 666a60 mid: .*-> FAIL\(slot0\.f16\)' "$OUT/dyn.txt"; chk "MID (回数初期値のみ) は slot.f16 だけ FAIL (ループ内 store の欠陥を単独で示す)" $?

step "5/6 survey 942 unit (修復前 / 修復後)"
cp "$OUT/pre/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/pre/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_pre.json" | tail -1
cp "$OUT/post/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_post.json" | tail -1
"$PY" trap_triage/survey_diff.py "$OUT/sv_pre.json" "$OUT/sv_post.json" | tee "$OUT/survey_diff.txt" | tail -8
grep -q '^ok 退行 unit: 0 ' "$OUT/survey_diff.txt"; chk "ok 退行 0" $?
"$PY" - "$OUT/sv_pre.json" "$OUT/sv_post.json" <<'PYEOF'
import collections, json, sys
for p in sys.argv[1:]:
    c = collections.Counter(r['kind'] for r in json.load(open(p)))
    if c['miss'] > 200:
        print('SURVEY_ANOMALY', p, dict(c)); sys.exit(1)
PYEOF
chk "survey が miss 過多の異常形 (REPORT_2316 §4 の ok 136 / miss 797 型。通常は miss 47) でない" $?

step "6/6 ネガティブコントロール"
sed 's/^define i64 @function_666a60(i64 %arg1,/define i64 @function_666a60(i32 %arg1,/' "$OUT/pre.ll" > "$OUT/neg_head.ll"
cmp -s "$OUT/pre.ll" "$OUT/neg_head.ll" && { echo "negctl: sed が効いていない"; FAIL=$((FAIL + 1)); }
"$PY" "$HERE/fix_ld115.py" "$OUT/neg_head.ll" "$OUT/neg_head.out.ll" 2> "$OUT/neg_head.err"; [ $? != 0 ] && grep -q '仮引数が想定と違う' "$OUT/neg_head.err"; rc=$?
chk "NC1 仮引数が i32 の IR を fix_ld115 が拒否 ($(tail -1 "$OUT/neg_head.err"))" $rc
"$PY" "$HERE/fix_ld115.py" "$OUT/post.ll" "$OUT/neg_twice.ll" 2> "$OUT/neg_twice.err"; [ $? != 0 ] && grep -q '既に修復済み' "$OUT/neg_twice.err"; rc=$?
chk "NC2 適用済み IR への二重適用を fix_ld115 が拒否 ($(tail -1 "$OUT/neg_twice.err"))" $rc
cp "$OUT/post.ll" "$W/boot_final.ll"; cp "$OUT/post.cond.json" "$W/ir_conditions.json"
python3 m11_cond.py --check "$OUT/post.ll"; chk "NC3 対照: 記録どおりの IR は m11_cond --check が一致" $?
cp "$OUT/post.ll" "$OUT/neg_tamper.ll"; echo '; tamper' >> "$OUT/neg_tamper.ll"
python3 m11_cond.py --check "$OUT/neg_tamper.ll" 2> /dev/null; [ $? != 0 ]; rc=$?
chk "NC3 同じ IR に 1 行書き足すと m11_cond --check が不一致" $rc
cp "$OUT/pre.ll" "$W/boot_final.ll"; cp "$OUT/pre.cond.json" "$W/ir_conditions.json"
M11_ALLOW_LD115_DISABLED=0 bash m11_build.sh > "$OUT/neg_build.log" 2>&1; [ $? = 2 ] && grep -q 'ld115=applied の記録無し' "$OUT/neg_build.log"; chk "NC4 ld115=disabled の IR は opt-in 無しの m11_build.sh が拒否 (rc 2)" $?

echo "LD115_E2E_SUMMARY fail=$FAIL"
echo "[ld115_e2e] done: $OUT"
exit $((FAIL > 0))
