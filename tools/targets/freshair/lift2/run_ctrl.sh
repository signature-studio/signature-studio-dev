#!/usr/bin/env bash
# run_ctrl.sh [Nstructured] [Nrandom] [seed] — FA-2c 制御層: native(実機機械語) vs wasm(mlift) bit-exact 比較 (fma 0/1)。
#   先頭 8 scenario = factory .epf 8 本駆動 (macro 値は .epf から抽出)。
#   既定 NS=2 NR=5 = 回帰用 (既定 seed では 1 scenario が native/wasm 両側で同一の ERR。REPORT_APPENDIX §2.5)。**既定の 200/1000 は既知限界**:
#   structured scenario が W+0x70 (カウント) / P+0x9e54 (型 enum) / C+0x5e8 (種別) など
#   「意味 field」へランダム値を注入するため、実機機械語側でも OOB 書込 → native/wasm とも失敗
#   (残骸 REPORT の ERR S1000/S2001 と同根)。epf 8 本 + 小規模 structured を検収範囲とする。
# 判定は Python の ctrl_norm.py (ポインタ値マスク + 行数/ERR 一致を含む厳密判定)。
# 判定は **非空・行数一致・mismatch 0・ERR は両側で同一 scenario のみ許容** (片側だけ ERR は不一致)。旧版は片側クラッシュで両出力 0 byte → mismatch 0 → 空 PASS する脆弱性があった。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ctrl"; [ -x "$W/native_ctrl" ] && [ -f "$W/ctrl_full.cjs" ] || { echo "ERROR: $W に native_ctrl / ctrl_full.cjs が無い (build_ctrl.sh を先に実行)" >&2; exit 2; }
cd "$W"; source "$HERE/env.sh"
NS="${1:-2}"; NR="${2:-5}"; SEED="${3:-0xFA2C0001}"
python3 "$HERE/gen_ctrl_scen.py" ctrl_scen.txt "$NS" "$NR" "$SEED" | tail -1
EXPECT=$(wc -l < ctrl_scen.txt)
[ "$EXPECT" -eq $((NS + NR + 8)) ] || { echo "ERROR: factory .epf 8 本が無い (work/win/Fresh Air/.../FACTORY Presets/Factory Bank/*.epf を展開する。REPORT §11)。生成シナリオ $EXPECT 本"; exit 2; }
tot=0; bad=0
for F in 0 1; do
  FA_DBG=1 FA_HEAP_ZERO=1 ./native_ctrl "$CORE" ctrl_scen.txt $F > ctrl_n$F.txt 2> ctrl_n$F.err
  FA_DBG=1 FA_HEAP_ZERO=1 node "$HERE/native/ctrl_harness.mjs" ./ctrl_full.cjs ctrl_scen.txt $F > ctrl_w$F.txt 2> ctrl_w$F.err
  if ! python3 "$HERE/ctrl_norm.py" ctrl_scen.txt ctrl_n$F.txt ctrl_w$F.txt $F; then bad=$((bad+1)); fi
done
if [ $bad -eq 0 ]; then echo "RESULT: ctrl BIT-EXACT $EXPECT/$EXPECT scenarios (epf 8 + structured $NS + random $NR, fma0+fma1)"; else echo "RESULT: MISMATCH in ctrl scenarios"; exit 1; fi
