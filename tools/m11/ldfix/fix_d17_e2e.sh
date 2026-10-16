#!/usr/bin/env bash
# fix_d17_e2e.sh — #968 (LD-21) D17 修復 pass の 1 コマンド再現。PE 無しで work-m11 だけで走る。
#   1/6 audit_lsf_ssa.py (修復前) → 2/6 fix_d17.py で修復 → 3/6 audit_lsf_ssa.py (修復後)
#   → 4/6 spill 宛 CELL_COLLAPSED 37 site の判定対応 (#1169・spill37_1169.py)
#   → 5/6 spill 宛 TRUE_DROP の修復 pass (#2794・#2910・fix_spill_2794.py) + 修復後 audit + 突合 (check_spill_2794.py) + ネガコン
#   → 6/6 emcc 構文検証 (修復 IR = 5/6 の出力)
# 使い方: bash tools/m11/ldfix/fix_d17_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
OUT="${RUNNER_TEMP:-/tmp}/fix_d17_e2e"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[fix_d17_e2e] $*"; }

step "1/6 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1
step "2/6 fix_d17.py"
"$PY" "$HERE/fix_d17.py" "$IR" "$OUT/ssa_base.json" "$OUT/boot_d17.ll" --report "$OUT/d17_report.json" || exit 1
step "3/6 audit (修復後)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_d17.ll" "$IMG" "$CFG" --json "$OUT/ssa_fix.json" | head -1
step "4/6 spill 宛 CELL_COLLAPSED の判定対応 (#1169)"
"$PY" "$HERE/spill37_1169.py" "$OUT/spill37_1169.tsv" "$OUT/ssa_base.json" "$OUT/ssa_fix.json" || exit 1
cmp "$OUT/spill37_1169.tsv" "$HERE/results/spill37_1169.tsv" || { echo "[fix_d17_e2e] FAIL: spill37_1169.tsv が results と不一致" >&2; exit 1; }
step "5/6 spill 宛 TRUE_DROP の修復 pass (#2794): 1 対 1 のゲート付き・修復後 audit・突合"
spillout="$("$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --report "$OUT/spill_2794.json")" || exit 1
echo "$spillout" | head -1
echo "$spillout" | grep -q '^cmp fixed=3 skipped=25$' || { echo "[fix_d17_e2e] FAIL: icmp 根拠 (cmp) の修復件数が 3 件・見送り 25 件にならない" >&2; exit 1; }
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_spill.ll" "$IMG" "$CFG" --json "$OUT/ssa_spill.json" | head -1
"$PY" "$HERE/check_spill_2794.py" "$OUT/ssa_base.json" "$OUT/ssa_spill.json" "$OUT/spill_2794.json" "$HERE/results/spill37_1169.tsv" "$OUT/spill_repair_2794.tsv" || exit 1
cmp "$OUT/spill_repair_2794.tsv" "$HERE/results/spill_repair_2794.tsv" || { echo "[fix_d17_e2e] FAIL: spill_repair_2794.tsv が results と不一致" >&2; exit 1; }
"$PY" "$HERE/check_spill_2794.py" "$OUT/ssa_base.json" "$OUT/ssa_fix.json" "$OUT/spill_2794.json" "$HERE/results/spill37_1169.tsv" /dev/null > /dev/null
if [ $? -eq 0 ]; then echo "[fix_d17_e2e] FAIL: ネガコン (修復を外した audit) が PASS した" >&2; exit 1; fi
echo "[fix_d17_e2e] ネガコン: 修復を外した audit では突合が FAIL (期待どおり)"
nogate="$("$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill_nogate.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --gate none)" || exit 1
echo "$nogate" | head -1
echo "$nogate" | head -1 | grep -q '^spill fixed=30 skipped=0 ' || { echo "[fix_d17_e2e] FAIL: ネガコン 2 (--gate none) が 30 件を書き換えない" >&2; exit 1; }
gate1="$("$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill_1to1.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --gate 1to1)" || exit 1
echo "$gate1" | head -1
echo "$gate1" | head -1 | grep -q '^spill fixed=9 skipped=21 ' || { echo "[fix_d17_e2e] FAIL: ネガコン 3 (--gate 1to1 = #2794 の根拠だけ) が 9 件にならない" >&2; exit 1; }
argi5_py="$OUT/fix_spill_2794_argi5.py"
sed 's/argi = 4 + /argi = 5 + /' "$HERE/fix_spill_2794.py" > "$argi5_py"
grep -q 'argi = 5 + ' "$argi5_py" || { echo "[fix_d17_e2e] FAIL: ネガコン 4 のコピーで argi を書き換えられない" >&2; exit 1; }
argi5="$(PYTHONPATH="$HERE:$REPO/tools/m11" "$PY" "$argi5_py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill_argi5.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --gate both)" || exit 1
echo "$argi5" | head -1
echo "$argi5" | head -1 | grep -q '^spill fixed=9 skipped=21 ' || { echo "[fix_d17_e2e] FAIL: ネガコン 4 (argi を 1 つずらす) が 9 件・見送り 21 件にならない" >&2; exit 1; }
echo "$argi5" | grep -c ' callarg_ir_matches=0$' | grep -qx '4' || { echo "[fix_d17_e2e] FAIL: ネガコン 4 で callarg の 4 site が callarg_ir_matches=0 にならない" >&2; exit 1; }
echo "[fix_d17_e2e] ネガコン 4: 引数位置を 1 つずらすと callarg の 4 site が見送られる (期待どおり)"
cmpnc="$("$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill_cmpoff.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --gate both --cmp off)" || exit 1
echo "$cmpnc" | grep -q '^cmp fixed=0 skipped=0$' || { echo "[fix_d17_e2e] FAIL: ネガコン 5 (cmp gate を外す) で cmp 修復が 0 件にならない" >&2; exit 1; }
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_spill_cmpoff.ll" "$IMG" "$CFG" --json "$OUT/ssa_spill_cmpoff.json" > /dev/null || exit 1
off_n="$("$PY" -c 'import json,sys; a=json.load(open(sys.argv[1])); print(sum(1 for v in a["functions"].values() for s in v["sites"] if s.get("frame") and (s.get("cell") or {}).get("verdict")=="CELL_COLLAPSED"))' "$OUT/ssa_spill_cmpoff.json")"
on_n="$("$PY" -c 'import json,sys; a=json.load(open(sys.argv[1])); print(sum(1 for v in a["functions"].values() for s in v["sites"] if s.get("frame") and (s.get("cell") or {}).get("verdict")=="CELL_COLLAPSED"))' "$OUT/ssa_spill.json")"
[ "$off_n" = 28 ] && [ "$on_n" = 25 ] || { echo "[fix_d17_e2e] FAIL: ネガコン 5 で cmp gate の有無による spill 宛 CELL_COLLAPSED の差が 3 件 (off=28 on=25) にならない: off=$off_n on=$on_n" >&2; exit 1; }
echo "[fix_d17_e2e] ネガコン 5: icmp 根拠 (cmp) の gate を外すと spill 宛 CELL_COLLAPSED が 28 件のまま、入れると 25 件 (3 件差。突合の C2 は両方 PASS)"
step "5b/6 site 単位の判定 (#4556・非既定。既定の 37→25 assert は変えない) + ネガコン"
sg="$("$PY" "$HERE/site_gran_4556.py" "$IR" "$OUT/boot_spill.ll" "$IMG" "$CFG" "$OUT/ssa_base.json" "$OUT/ssa_spill.json" --tsv "$OUT/site_gran.tsv")" || exit 1
echo "$sg" | head -1 | grep -q '後 25 site / 16 関数 -> site 単位の後 24 site / 15 関数$' || { echo "[fix_d17_e2e] FAIL: site 単位の判定が 25 site / 16 関数 -> 24 site / 15 関数 にならない: $(echo "$sg" | head -1)" >&2; exit 1; }
sgneg="$("$PY" "$HERE/site_gran_4556.py" "$IR" "$IR" "$IMG" "$CFG" "$OUT/ssa_base.json" "$OUT/ssa_base.json" --tsv "$OUT/site_gran_neg.tsv")" || exit 1
echo "$sgneg" | head -1 | grep -q '後 37 site / 22 関数 -> site 単位の後 37 site / 22 関数$' || { echo "[fix_d17_e2e] FAIL: ネガコン (修復を外した site 単位の判定) で減少が 0 にならない: $(echo "$sgneg" | head -1)" >&2; exit 1; }
echo "[fix_d17_e2e] ネガコン 6: 修復を外すと site 単位の減少は 0 (37 site / 22 関数 のまま)"
step "6/6 emcc 構文検証 (修復 IR)"
if ! source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1 || ! command -v emcc > /dev/null 2>&1; then
  echo "[fix_d17_e2e] FAIL: emsdk が無い (/opt/emsdk/emsdk_env.sh の source か emcc の検出に失敗)" >&2
  exit 2
fi
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
emcc -c "$OUT/boot_spill.ll" -o "$OUT/boot_spill.o" -w -Wno-error=int-conversion -O0 -g1 || { echo "[fix_d17_e2e] FAIL: emcc rc!=0" >&2; exit 1; }
echo "[fix_d17_e2e] emcc rc=0"
