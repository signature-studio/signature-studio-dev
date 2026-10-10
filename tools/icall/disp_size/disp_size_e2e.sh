#!/usr/bin/env bash
# CAB-229 capstone disp_size 監査 — 1 コマンド再現
#   bash tools/icall/disp_size/disp_size_e2e.sh [--quick|--full]
#     既定/--quick : [1]単体 [2]prefix matrix(全組合せ+objdump照合) [3]closure 5 sample の census [4]棚卸し  (約 1 分)
#     --full       : + 全 .pdata census (FLEngine/Serum2/Delphi133/mac) + impact_hash + p0c 回帰 (約 25 分, 14 core)
# 判定: exit 0 = dispfix の補正が matrix で 0 不一致、かつ census で mem.disp 値/imm_offset 不整合が 0。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"; mkdir -p results work
MODE="${1:---quick}"
RC=0
echo "== [1/4] dispfix 単体テスト"
python3 tests/test_dispfix.py | grep -E "^(FAIL|INFO|RESULT)" || true
python3 tests/test_dispfix.py > /dev/null || RC=1
echo "== [2/4] prefix × opcode map × modrm 形式の全組合せ (capstone 誤報告の再現 + dispfix 検証 + objdump 長さ照合)"
python3 prefix_matrix.py --jobs 14 --objdump 100000 --json results/prefix_matrix.json | tee work/matrix.log | sed -n '1,12p;/objdump/p;/dispfix/p'
grep -q "dispfix 不一致 合計: 0" work/matrix.log || RC=1
echo "== [3/4] 実バイナリ census"
if [ "$MODE" = "--full" ]; then
  CJSON=results/census.json
  python3 census.py --jobs 14 --json "$CJSON" | tee work/census.log
else
  CJSON=work/census_quick.json      # quick は一部 sample のみなので results/census.json (全 sample) を上書きしない
  python3 census.py --jobs 14 --json "$CJSON" --only "OTT F (icall,Balance closure,Fresh Air SlateCore closure,KH HeartCore gain,FLEngine M11 closure" | tee work/census.log
fi
CJSON="$CJSON" python3 - <<'PY' || RC=1
import json, os, sys
r = json.load(open(os.environ['CJSON']))
bad = {k: (v['counts'].get('rip_val_mismatch', 0), v['counts'].get('imm_offset_mismatch', 0)) for k, v in r.items()}
bad = {k: v for k, v in bad.items() if v != (0, 0)}
print('census 値/imm 不整合のある sample:', bad or 'なし')
sys.exit(1 if bad else 0)
PY
echo "== [4/4] capstone disp 依存コード棚卸し"
python3 consumers.py
if [ "$MODE" = "--full" ]; then
  echo "== [5] impact_hash (fw_overlap / win_funcs 規約の legacy 再現 + fixed 差分)"
  python3 impact_hash.py --jobs 14 | tee work/impact.log
  echo "== [6] p0c kernel 表 hash 突合の回帰 (修正後 kernel_matrix.py)"
  python3 p0c_regress.py --jobs 12 | tee work/p0c_regress.log || RC=1
fi
[ "$RC" = "0" ] && echo "[disp_size_e2e] PASS" || echo "[disp_size_e2e] FAIL"
exit $RC
