#!/usr/bin/env bash
# landing_e2e.sh — CAB-227 landing pad 抽出 + IR 化 + native/wasm 差分検証 の 1 コマンド再現.
#   bash tools/icall/landing/landing_e2e.sh            # フル (FLEngine 879 断片 + 検証 1479 case + OTT 抽出, 約 5 分)
#   bash tools/icall/landing/landing_e2e.sh --quick    # 検証 20 pad サンプル (約 1 分)
# 前提: python3 (pefile, capstone), emsdk 6.0.12, node, /usr/bin/llvm-as
# 判定 (exit 0 = PASS):
#   ① gap site 879 / dtor_pad 493 の再現 (tools/icall REPORT §2 の監査数と一致)
#   ② scope table 抽出 10,837 関数 / 16,940 entry (range 妥当性 invalid=0)
#   ③ IR lift 879/879 + llvm-as 通過
#   ④ native vs wasm 差分検証: 493 pad × 3 pattern = 1479 case 全て equal
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PE=/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin
OTT=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
FUNCS=/home/ubuntu/work/webstudio/tools/icall/work/fle_F.txt
W="$HERE/work"
QUICK="${1:-}"
RC=0

echo "[1/6] gap site 再現 + 断片化 (audit_icall の gap sweep を再利用)"
python3 "$HERE/gap_fragments.py" --pe "$PE" --funcs "$FUNCS" --json "$W/fle_fragments.json" --label FLEngine | sed 's/^/      /' || RC=1

echo "[2/6] scope table 抽出 (.pdata/.xdata 全数)"
python3 "$HERE/xdata_scope.py" --pe "$PE" --json "$W/fle_xdata.json" --handler-json "$W/fle_scopes.json" --label FLEngine | sed 's/^/      /' || RC=1

echo "[3/6] landing pad → LLVM IR (verify 形 + lib 形) + メタデータ"
python3 "$HERE/lift_pad.py" --fragments "$W/fle_fragments.json" --scopes "$W/fle_scopes.json" \
  --verify-out "$W/pads_verify.ll" --lib-out "$W/pads_lib.ll" --meta-out "$W/pads_meta.json" | sed 's/^/      /' || RC=1
llvm-as "$W/pads_verify.ll" -o "$W/pads_verify.bc" || RC=1
llvm-as "$W/pads_lib.ll" -o "$W/pads_lib.bc" || RC=1
echo "      llvm-as: pads_verify.ll / pads_lib.ll OK"

echo "[4/6] native vs wasm 差分検証 (liftdiff 共有コア + FORMAT.md 準拠)"
MAXFLAG=""
[ "$QUICK" = "--quick" ] && MAXFLAG="--max 20"
python3 "$HERE/verify_pads.py" --pe "$PE" --fragments "$W/fle_fragments.json" --meta "$W/pads_meta.json" \
  --ir "$W/pads_verify.ll" --out "$W/verify" $MAXFLAG | sed 's/^/      /' || RC=1

echo "[5/6] OTT (MSVC) funclet 抽出 + 静的 lift (検証母数)"
python3 "$HERE/ott_extract.py" --pe "$OTT" --json "$W/ott_fragments.json" | sed 's/^/      /' || RC=1
python3 "$HERE/lift_pad.py" --fragments "$W/ott_fragments.json" --verify-out "$W/ott_verify.ll" \
  --lib-out "$W/ott_lib.ll" --meta-out "$W/ott_meta.json" --exec-kinds none --label ott | sed 's/^/      /' || true

echo "[6/6] 判定"
python3 - <<'PY' || RC=1
import json, sys
W = '/home/ubuntu/work/webstudio/tools/icall/landing/work'
fr = json.load(open(W + '/fle_fragments.json'))
sc = json.load(open(W + '/fle_scopes.json'))
xs = json.load(open(W + '/fle_xdata.json'))
mt = json.load(open(W + '/pads_meta.json'))
su = json.load(open(W + '/verify/summary.json'))
nf = [json.loads(l)['verdict'] for l in open(W + '/verify/verdicts_fn.jsonl')]
kc = fr['kind_counts']
ok = True
def chk(name, cond, detail):
    global ok
    print('      %-58s %s  (%s)' % (name, 'PASS' if cond else 'FAIL', detail))
    ok = ok and cond
chk('gap site = 879', fr['n_gap_sites'] == 879, str(fr['n_gap_sites']))
chk('dtor_pad = 493', kc.get('dtor_pad') == 493, str(kc.get('dtor_pad')))
chk('gap call site [rbx-0x20] = 493',
    sum(1 for f in fr['fragments'] for s in f['sites'] if s['mn'] == 'call' and s.get('base') == 'rbx' and s['disp'] == -32) == 493, '')
chk('scope 関数 = 10,837 / entry = 16,940', xs['summary']['n_with_scopes'] == 10837 and xs['summary']['n_scope_entries'] == 16940,
    '%d / %d' % (xs['summary']['n_with_scopes'], xs['summary']['n_scope_entries']))
chk('scope 妥当性 invalid = 0', sum(xs['summary']['invalid'].values()) == 0, str(xs['summary']['invalid']))
chk('IR lift 879/879', mt['lift_ok'] == 879 and mt['lift_fail'] == 0, '%d/%d' % (mt['lift_ok'], mt['lift_ok'] + mt['lift_fail']))
chk('検証 case 全 equal', su['verdicts'].get('equal') == 1479, str(su['verdicts']))
chk('検証 pad 全 match', nf.count('match') == 493, str(nf.count('match')))
print('      == landing_e2e %s ==' % ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY

[ "$RC" = "0" ] && echo "[landing_e2e] PASS" || echo "[landing_e2e] FAIL"
exit $RC
