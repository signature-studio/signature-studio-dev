#!/usr/bin/env bash
# M11-N21 (#572) gate: m11_data_gen.py が .reloc DIR64 の全 slot (セクション末尾 8B 含む) を補正することを検査する。
#   1) 現行 m11_data_gen.py (LB=0 / 0x10000) → 補正漏れ 0 を要求
#   2) ネガコン: 補正条件を旧版 (`<`) に戻した複製 → 補正漏れ 1 (RVA 0x11e5000) を要求 (= 検査が off-by-one を検出できる)
# どれか 1 つでも期待と違えば非 0 で終了する (不合格で exit 0 にならない)。
#   bash tools/m11/m11_reloc_gate.sh [PE]     PE 省略時: $FL_WIN64_DIR/extracted/block00031_PE.bin
set -u
cd "$(dirname "$0")"
source ../shared/env.sh   # FL_WIN64_DIR (既定値は tools/shared/env.sh が正本)
PE="${1:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
[ -f "$PE" ] || { echo "[gate] FAIL: PE 無し: $PE"; exit 2; }
T="$(mktemp -d "${TMPDIR:-/tmp}/m11_reloc_gate.XXXXXX")"
trap 'rm -rf "$T"' EXIT
rc=0
chk() { # chk <label> <expect_missed> <lb> <gen.py>
  local label="$1" exp="$2" lb="$3" gen="$4"
  if ! M11_LB_BASE="$lb" M11_DATA_OUT="$T/d.c" python3 "$gen" "$PE" > "$T/gen.log" 2>&1; then
    echo "[gate] FAIL $label: generator 失敗"; tail -3 "$T/gen.log"; rc=1; return
  fi
  if python3 m11_reloc_audit.py "$PE" "$T/d.c" --lb "$lb" --expect-missed "$exp" > "$T/audit.log" 2>&1; then
    echo "[gate] PASS $label (補正漏れ == $exp)"
  else
    echo "[gate] FAIL $label"; grep -E 'MISS|FAIL' "$T/audit.log"; rc=1
  fi
}
chk "fixed LB=0x0"     0 0x0     m11_data_gen.py
chk "fixed LB=0x10000" 0 0x10000 m11_data_gen.py
# ネガコン: 現行コードの条件だけを旧版に戻した複製 (同ディレクトリに置く: lb_base を import するため)
NEG=./.m11_data_gen_negctl.py
sed 's/if lo <= r <= lo + len(sd) - 8:/if lo <= r < lo + len(sd) - 8:/' m11_data_gen.py > "$NEG"
if cmp -s m11_data_gen.py "$NEG"; then
  echo "[gate] FAIL negctl: 旧条件への置換が効いていない (m11_data_gen.py の条件が想定と違う)"; rc=1
else
  chk "negctl(旧条件 '<') LB=0x0" 1 0x0 "$NEG"
fi
rm -f "$NEG"
[ $rc = 0 ] && echo "[gate] ALL PASS" || echo "[gate] FAILED"
exit $rc
