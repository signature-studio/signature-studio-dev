#!/usr/bin/env bash
# #593 (M11-N22) gate: m6_data_gen.py / liftlib dataimage.py の DIR64 補正境界 (section 末尾 8B slot) を検査する。
#   [1] 全数列挙 (grep 系 + AST 系の突合): 旧境界 0 件
#   [2] 実バイト: FL 本体 PE (block00031_PE.bin) で m6 / liftlib の生成物の補正漏れ 0 (独立算法 = pefile)
#   [3] ネガコン: 条件を旧 `<` に戻した複製で [1] が FAIL (旧境界 3 件) / [2] が補正漏れ 1 を要求
# どれか 1 つでも期待と違えば非 0 で終了する (不合格で exit 0 にならない)。
#   bash tools/liftlib/dir64_boundary_gate.sh [PE]     PE 省略時: $FL_WIN64_DIR/extracted/block00031_PE.bin
set -u
cd "$(dirname "$0")"
# shellcheck source=/dev/null
source ../shared/env.sh   # FL_WIN64_DIR (既定: $ANALYSIS_DIR/win64 = 従来の作業用 VM 既定値)
PE="${1:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
[ -f "$PE" ] || { echo "[gate] FAIL: PE 無し: $PE"; exit 2; }
python3 -c 'import pefile' 2>/dev/null || { echo "[gate] FAIL: pefile 無し"; exit 2; }
T="$(mktemp -d "${TMPDIR:-/tmp}/dir64_gate.XXXXXX")"
trap 'rm -rf "$T"' EXIT
rc=0
ok() { echo "[gate] PASS $1"; }
ng() { echo "[gate] FAIL $1"; rc=1; }

# [1] 現行ツリーの列挙
if python3 dir64_boundary_enum.py > "$T/enum.log" 2>&1; then ok "[1] 列挙: 旧境界 0 件 ($(grep -o '和集合=[0-9]*' "$T/enum.log"))"; else ng "[1] 列挙"; tail -4 "$T/enum.log"; fi

# [2] 実バイト (現行コード)
for g in m6 liftlib; do
  if python3 dir64_boundary_check.py "$PE" --gen $g --expect-missed 0 > "$T/c_$g.log" 2>&1; then ok "[2] $g 実バイト: $(grep -o '補正漏れ=[0-9]* 不正値=[0-9]* 末尾slot対象=[0-9]* 末尾slot補正=[0-9]*' "$T/c_$g.log" | head -1)"; else ng "[2] $g 実バイト"; tail -3 "$T/c_$g.log"; fi
done

# [3] ネガコン: 旧条件に戻した複製 (ツリー構造ごとコピー)
N="$T/neg"; mkdir -p "$N/m6" "$N/liftlib/liftlib/passes" "$N/liftlib/tests"
cp ../m6/m6_data_gen.py ../m6/ottlib.py "$N/m6/"
cp -r liftlib "$N/liftlib/"; cp tests/test_unit.py "$N/liftlib/tests/"
cp dir64_boundary_enum.py "$N/liftlib/"
cp -r ../hostbridge/lowbase/x64c "$N/lb_x64c" 2>/dev/null
for f in "$N/m6/m6_data_gen.py" "$N/liftlib/liftlib/passes/dataimage.py" "$N/liftlib/tests/test_unit.py"; do
  sed -i 's/lo <= r <= lo + len(sd) - 8:/lo <= r < lo + len(sd) - 8:/' "$f"
  grep -q 'lo <= r < lo + len(sd) - 8:' "$f" || { ng "[3] 旧条件への置換が効いていない: $f"; }
done
if python3 dir64_boundary_enum.py --root "$N" > "$T/neg_enum.log" 2>&1; then ng "[3] 列挙ネガコン: 旧境界を検出できず exit 0"; else
  n=$(grep -o 'OLD=[0-9]*' "$T/neg_enum.log" | tail -1)
  [ "$n" = "OLD=3" ] && ok "[3] 列挙ネガコン: 旧境界 3 件で FAIL ($n)" || { ng "[3] 列挙ネガコン: 期待 OLD=3, 実測 $n"; tail -4 "$T/neg_enum.log"; }
fi
python3 dir64_boundary_check.py "$PE" --gen m6 --m6-py "$N/m6/m6_data_gen.py" --expect-missed 1 > "$T/neg_m6.log" 2>&1 \
  && ok "[3] m6 旧条件: 補正漏れ 1 (= 検査が off-by-one を検出) $(grep -o 'MISS .*' "$T/neg_m6.log" | head -1)" || { ng "[3] m6 ネガコン"; tail -3 "$T/neg_m6.log"; }
python3 dir64_boundary_check.py "$PE" --gen liftlib --liftlib-dir "$N/liftlib" --expect-missed 1 > "$T/neg_ll.log" 2>&1 \
  && ok "[3] liftlib 旧条件: 補正漏れ 1 $(grep -o 'MISS .*' "$T/neg_ll.log" | head -1)" || { ng "[3] liftlib ネガコン"; tail -3 "$T/neg_ll.log"; }
# 期待逆転 (現行コードに --expect-missed 1 を与えると FAIL する = 検査が期待外れを落とす)
python3 dir64_boundary_check.py "$PE" --gen m6 --expect-missed 1 > /dev/null 2>&1 && ng "[3] 現行 m6 に期待 1 を与えても PASS (検査が甘い)" || ok "[3] 期待逆転: 現行 m6 + expect 1 は FAIL"
[ $rc = 0 ] && echo "[gate] ALL PASS" || echo "[gate] FAILED"
exit $rc
