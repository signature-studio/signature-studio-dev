#!/usr/bin/env bash
# icall_e2e.sh — 間接 call 落ち監査 + 復元 pass の 1 コマンド検証 (OTT を native 実機械語と bit 比較)
#   bash tools/icall/icall_e2e.sh            OTT: unit → 監査(before/after) → RetDec route build → matrix 89 scenario (約 1 分)
#   bash tools/icall/icall_e2e.sh --small    + Fruity Balance / Fresh Air / Kilohearts の before/after 監査 (約 +3 分)
#   bash tools/icall/icall_e2e.sh --full     + FLEngine_x64.dll 7,421 関数の before/after 監査 (RetDec 4 並列, 約 +10 分)
# 前提: tools/ott/work/{libottnative.so,lift/lift_meta.json} (= bash tools/ott/ott_e2e.sh を 1 回実行済み), tools/m6/work/ott_ranges.txt (無ければ `mkdir -p tools/m6/work && python3 tools/m6/m6_scan.py`),
#       python3 (capstone, pefile), emsdk 6.0.12, /opt/retdec, node(emsdk 同梱可), setarch
# 判定 (exit 0 = PASS): ① unit 全 PASS ② OTT F の非 IAT 間接 call 落ち before >= 60 → after <= 8 (jump table 未解決分の許容) かつ tail jmp 落ち 0
#                       ③ matrix: 89 scenario 中 failed 0, 全 cell が native と bit 一致 (max_ulp 0), state diff 0
#                       ④ CRT 関数単位 gate (diff/crt_fn_gate.sh): SSE2 経路の 6 関数が native と xmm0 全一致 (各 600 点)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/.."
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
NODE_BIN="$(command -v node || true)"; [ -n "$NODE_BIN" ] || NODE_BIN="$(ls /opt/emsdk/node/*/bin/node 2>/dev/null | head -1)"
export NODE="$NODE_BIN" PATH="$(dirname "$NODE_BIN"):$PATH"
MODE="${1:-}"
RC=0
source "$T/shared/env.sh"
OTT_DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
[ -f "$OTT_DLL" ] || { echo "[icall_e2e] $OTT_DLL 無し" >&2; exit 2; }
[ -f "$T/ott/work/lift/lift_meta.json" ] && [ -f "$T/ott/work/libottnative.so" ] || { echo "[icall_e2e] 先に bash tools/ott/ott_e2e.sh を実行してください (native 参照と coverage が必要)" >&2; exit 2; }

mkdir -p "$HERE/work"
echo "[1/4] route build (closure → rewrite → RetDec → restore → flatten → emcc)"
bash "$HERE/ott_route.sh" > "$HERE/work/route_build.log" 2>&1 || { tail -20 "$HERE/work/route_build.log"; echo "[icall_e2e] FAIL: route build"; exit 1; }
tail -1 "$HERE/work/route_build.log"
echo "[2/4] unit / rewriter 回帰"
python3 "$HERE/tests/test_icall.py" | tail -3 || RC=1

echo "[3/4] 監査 (OTT closure F: 元 PE を RetDec decode した IR vs 書換え→復元後 IR)"
bash "$HERE/roundtrip.sh" "$OTT_DLL" "$HERE/work/route/F.txt" ott-F "$HERE/work/rt_ott-F" > "$HERE/work/rt_ott.log" 2>&1 || RC=1
python3 - "$HERE/work/rt_ott-F" <<'PY' || RC=1
import json, sys
d = sys.argv[1]
b = json.load(open(d + '/audit_before.json')); a = json.load(open(d + '/audit_after.json'))
f = lambda r: (r['call_non_iat'], r['call_lost_non_iat'], r['jmp_tail_sites'], r['jmp_tail_lost'], r['jmptable_sites'], r['jmptable_dropped'])
mp = json.load(open(d + '/map.json'))
print('      OTT F  非IAT間接call %d: 落ち %d -> %d | tail-jmp %d: 落ち %d -> %d | jump table %d: RetDec 未解決 %d -> cmp/je 列へ %d 展開' % (
    b['call_non_iat'], b['call_lost_non_iat'], a['call_lost_non_iat'], b['jmp_tail_sites'], b['jmp_tail_lost'], a['jmp_tail_lost'],
    b['jmptable_sites'], b['jmptable_dropped'], mp['njt']))
ok = b['call_lost_non_iat'] >= 60 and a['call_lost_non_iat'] <= 8 and a['jmp_tail_lost'] == 0
print('      監査判定', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
PY

echo "[4/4] matrix: route build (RetDec + 復元 pass) vs native 実機械語 (89 scenario / 出力 cell + 最終 heap/obj state)"
( cd "$T/ott" && python3 diff/matrix.py "$HERE/work/route/ott_route.cjs" > "$HERE/work/matrix_route.log" 2>&1 ); MRC=$?
grep -E '"name": "(std|std_f248_0)"' "$HERE/work/matrix_route.log" | python3 -c "
import sys, json
for l in sys.stdin:
    r = json.loads(l); c = r['census']
    print('      %-11s ok=%s cells=%d bit-equal=%d max_ulp=%d census: zero %d / normal %d / junkHi %d / junkTiny %d / nan %d / |max| %.4g' % (r['name'], r['ok'], r['cells'], r['bit_equal'], r['max_ulp'], c['zero'], c['normal'], c['junkHi'], c['junkTiny'], c['nan'], r['absmax']))"
tail -1 "$HERE/work/matrix_route.log"
[ "$MRC" = "0" ] || RC=1
echo "[+] CRT 関数単位 native 差分 gate (diff/crt_fn_gate.sh)"
bash "$HERE/diff/crt_fn_gate.sh" > "$HERE/work/crt_fn_gate.log" 2>&1 || RC=1
tail -16 "$HERE/work/crt_fn_gate.log"

if [ "$MODE" = "--small" ] || [ "$MODE" = "--full" ]; then
  echo "[+] 小規模 target の監査 (before/after)"
  bash "$HERE/roundtrip.sh" "$FL_WIN64_DIR/extracted/block18983_PE.bin" "$HERE/work/bal_ranges.txt" fruity-balance > /dev/null 2>&1 || echo "      (balance 失敗)"
  bash "$HERE/roundtrip.sh" "$T/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" "$HERE/work/fa_ranges.txt" freshair-core > /dev/null 2>&1 || echo "      (freshair 失敗)"
  bash "$HERE/roundtrip.sh" "$T/targets/kilohearts/work/winpkg/HeartCore.core_64" "$HERE/work/kh_gain_ranges.txt" kilohearts-gain > /dev/null 2>&1 || echo "      (kilohearts 失敗)"
fi
if [ "$MODE" = "--full" ]; then
  echo "[+] FLEngine_x64.dll (M11 closure 7,421 関数)"
  CHUNKS=4 bash "$HERE/roundtrip.sh" "$FL_WIN64_DIR/extracted/block00031_PE.bin" "$HERE/work/fle_F.txt" flengine > "$HERE/work/rt_flengine.log" 2>&1 || echo "      (flengine 失敗)"
fi
python3 "$HERE/audit_table.py" 2>/dev/null || true
[ "$RC" = "0" ] && echo "[icall_e2e] PASS" || echo "[icall_e2e] FAIL"
exit $RC
