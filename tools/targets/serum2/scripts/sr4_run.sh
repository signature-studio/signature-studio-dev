#!/bin/bash
# SR-4 one-command e2e: Serum 2 DSP 段階 lift (第 1 段: WT osc -> filter -> voice) の対象表 + pilot lift + 判定 gate + ネガコン。
# usage: PY=<python+pefile,capstone,numpy> bash tools/targets/serum2/scripts/sr4_run.sh [--pilot]
#   既定  : strict gate。第 1 段 (vtable root 56 関数) が全て bit-exact でない限り exit 1 (= 現状は不合格が正しい)
#   --pilot: pilot ごとの期待 (sr4/pilots.tsv) と観測の一致だけを判定 (exit 0 = 期待通り)。ネガコンは両モードで実行し、1 つでも
#            期待通り FAIL しなければ exit 1。
# 前提: /opt/retdec (toolchain-retdec) と /opt/emsdk (toolchain-emsdk)。入力 PE は work/Serum2_win64.vst3 (無ければ installer から抽出)。
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="${PY:-python3}"; DL="${DL:-${ARTIFACTS_DIR:-$HOME/artifacts}}"
TMPR="${RUNNER_TEMP:-/tmp}"; W=work; O=out
MODE="${1:-strict}"
SHA=501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283
mkdir -p "$W" "$O"
if [ ! -f $W/Serum2_win64.vst3 ]; then
  EXE="$DL/Install_Xfer_Serum2_2.1.5.exe"
  [ -f "$EXE" ] || EXE="$TMPR/serum2/Install_Xfer_Serum2_2.1.5.exe"
  if [ ! -f "$EXE" ] && [ -f "$DL/plugins-serum2.tar.zst" ]; then mkdir -p "$TMPR/serum2" && tar --zstd -xf "$DL/plugins-serum2.tar.zst" -C "$TMPR/serum2" Install_Xfer_Serum2_2.1.5.exe; EXE="$TMPR/serum2/Install_Xfer_Serum2_2.1.5.exe"; fi
  [ -f "$EXE" ] || { echo "FAIL: installer not found (oc_artifacts: plugins-serum2)"; exit 2; }
  7z x -y -o$W/exe_extract "$EXE" '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' >/dev/null
  cp "$W/exe_extract/\$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3" $W/Serum2_win64.vst3
fi
V=$W/Serum2_win64.vst3
[ "$(sha256sum $V | cut -d' ' -f1)" = "$SHA" ] || { echo "FAIL: input sha256 mismatch"; exit 2; }
[ -x /opt/retdec/bin/retdec-decompiler ] || { echo "FAIL: /opt/retdec missing (oc_artifacts: toolchain-retdec)"; exit 2; }
[ -d /opt/emsdk ] || { echo "FAIL: /opt/emsdk missing (oc_artifacts: toolchain-emsdk)"; exit 2; }
FAILS=0
nc() {  # nc <name> <rc> <want_rc> : 期待した exit code (入力不正 rc=2 など別理由の失敗を FAIL 検出と誤認しない)
  if [ "$2" -eq "$3" ]; then echo "NC PASS: $1 (rc=$2)"; else echo "NC FAIL: $1 (rc=$2, 期待 rc=$3)"; FAILS=$((FAILS+1)); fi
}

res_of() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[0]['result'])" "$1"; }  # 別理由 (liftlib 異常 = error) の失敗を mismatch 検出と誤認しない

echo "## 1. survey (対象表 / 静的 closure)"
$PY scripts/sr4_survey.py $V $O || exit 2
SR4_REQUIRE_EXTRA=XferFilterNope $PY scripts/sr4_survey.py $V $W/sr4_nc_survey >/dev/null 2>&1; nc "survey: 存在しないクラスを必須にすると exit 2" $? 2

echo "## 2. pilot lift (RetDec -> liftlib 修復 -> emcc -> 実機機械語 vs wasm 差分)"
RUN=$TMPR/sr4_run; rm -rf "$RUN"; mkdir -p "$RUN"
$PY scripts/sr4_pilots.py $V "$RUN" $O/sr4_pilot_results.json || exit 2

echo "## 3. gate"
$PY scripts/sr4_gate.py $O/sr4_summary.json $O/sr4_pilot_results.json --pilot | tee $O/sr4_gate_pilot.txt; PRC=${PIPESTATUS[0]}
$PY scripts/sr4_gate.py $O/sr4_summary.json $O/sr4_pilot_results.json > $O/sr4_gate_strict.txt; SRC=$?
tail -2 $O/sr4_gate_strict.txt

echo "## 4. ネガティブコントロール"
RAW=$RUN/sr4_svf_setup/sr4_svf_setup.drc.ll
# NC-a: 係数定数 (-pi/2 の double bits) の仮数を 2^34 (相対 3.8e-6) 壊した raw .ll -> 差分ハーネスが bit 不一致を検出する
#       (+1 ulp (double) では最終 float 変換で丸められ bit-exact のままだった = 初版の NC は検出力不足。実測は REPORT)
sed 's/i64 -4613618979930100456/i64 -4613618962750231272/' $RAW > $RUN/nc_const.ll
cmp -s $RAW $RUN/nc_const.ll && { echo "NC FAIL: 定数置換が効いていない"; FAILS=$((FAILS+1)); }
$PY scripts/sr4_pilots.py $V $RUN/nc_a $RUN/nc_a.json --only sr4_svf_setup --raw-ll-override sr4_svf_setup=$RUN/nc_const.ll >/dev/null
[ "$(res_of $RUN/nc_a.json)" = mismatch ] || { echo "NC FAIL: a の結果が mismatch でない ($(res_of $RUN/nc_a.json))"; FAILS=$((FAILS+1)); }
$PY scripts/sr4_gate.py $O/sr4_summary.json $RUN/nc_a.json --pilot >/dev/null; nc "a: 係数仮数 2^34 破壊 -> pilot gate が FAIL (期待 PASS の pilot が不一致)" $? 1
# NC-b: movlps の store 呼びを消した raw .ll -> 状態書込み (this+0x74) 欠落を検出する
grep -v '__asm_movlps(' $RAW > $RUN/nc_store.ll
$PY scripts/sr4_pilots.py $V $RUN/nc_b $RUN/nc_b.json --only sr4_svf_setup --raw-ll-override sr4_svf_setup=$RUN/nc_store.ll >/dev/null
[ "$(res_of $RUN/nc_b.json)" = mismatch ] || { echo "NC FAIL: b の結果が mismatch でない ($(res_of $RUN/nc_b.json))"; FAILS=$((FAILS+1)); }
$PY scripts/sr4_gate.py $O/sr4_summary.json $RUN/nc_b.json --pilot >/dev/null; nc "b: store 脱落 -> pilot gate が FAIL" $? 1
# NC-c: FP ALU の insn.addr メタデータを削った raw .ll -> 被覆検査 (fp_alu_cov<1.0) が検出する
python3 - "$RAW" "$RUN/nc_cov.ll" <<'EOF'
import re, sys
t = open(sys.argv[1]).read()
ids = re.findall(r'^(!\d+) = !\{i64 (\d+)\}$', t, re.M)
drop = {i for i, a in ids[10:20]}
open(sys.argv[2], 'w').write('\n'.join(l for l in t.split('\n') if not (re.match(r'^(!\d+) = ', l) and l.split(' = ')[0] in drop)))
EOF
CV=$($PY scripts/sr4_cov.py $V $RUN/nc_cov.ll 0x1802f7370 0x1802f74ec | python3 -c "import json,sys; print(json.load(sys.stdin)['fp_alu_cov'])")
python3 -c "import sys; sys.exit(0 if float('$CV') < 1.0 else 1)"; nc "c: insn.addr 欠落 -> fp_alu_cov=$CV < 1.0" $((1 - $?)) 1
# NC-d: gate 自体 -- 期待 fail の pilot が bit-exact + 被覆 1.0 に化けた結果 JSON は期待表の陳腐化として FAIL させる
python3 - "$O/sr4_pilot_results.json" "$RUN/nc_d.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
for d in r:
    if d['name'] == 'sr4_osc_setscale':
        d.update(result='bit-exact', mismatch=0, match=d['steps'], fp_alu_cov=1.0)
json.dump(r, open(sys.argv[2], 'w'))
EOF
$PY scripts/sr4_gate.py $O/sr4_summary.json $RUN/nc_d.json --pilot >/dev/null; nc "d: 期待 fail の pilot が PASS に化けると pilot gate が FAIL" $? 1
# NC-e: strict gate -- 56 root 中 5 のみ PASS の状態は exit 1
nc "e: strict gate は第 1 段未達 (root 5/56 < 56) で exit 1" $SRC 1

echo "## verdict"
echo "pilot gate rc=$PRC / strict gate rc=$SRC / negative-control failures=$FAILS"
if [ "$FAILS" -ne 0 ]; then echo "SR4 E2E FAIL (ネガコン不成立)"; exit 1; fi
if [ "$MODE" = "--pilot" ]; then [ "$PRC" -eq 0 ] && { echo "SR4 PILOT E2E OK"; exit 0; } || { echo "SR4 PILOT E2E FAIL"; exit 1; }; fi
[ "$SRC" -eq 0 ] && { echo "SR4 STAGE1 OK"; exit 0; } || { echo "SR4 STAGE1 NOT COMPLETE (strict gate)"; exit 1; }
