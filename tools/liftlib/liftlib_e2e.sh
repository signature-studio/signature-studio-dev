#!/usr/bin/env bash
# liftlib_e2e.sh — 共通 lift 修復基盤 (tools/liftlib) の 1 コマンド回帰。
#
#   bash tools/liftlib/liftlib_e2e.sh [--quick] [--fresh]
#
#   (a) OTT   : liftlib 側だけで m10_e2e 相当を再現。既定は auto f2,f7,p1 (CAB-238: checks 7/0 + census 改善 junkHi ≤104 ゲート,
#               出力 SHA は m10 参照と分離 = 修復由来の差分は正当)。旧既定 (修復無し = m10 chain 再現 + SHA 42/42 ゲート) は
#               `python3 -m liftlib ott --auto none` で実行できる。
#               注: #3067 (p1_legacy の repmap 修正) 後は, 旧既定の SHA 42/42 ゲートは FAIL する (修正由来の期待差分。
#               基準の差し替えは PM 判断。REPORT_APPENDIX_3067.md §6)。
#   (b) FA    : Fresh Air gain::GainDsp::process を RetDec → liftlib 修復 → wasm → 実機機械語と差分 (400 シナリオ bit-exact)
#   (c) KH    : Kilohearts Gain を同様に (61 シーケンス × 6 ブロック = 366 ステップ bit-exact)
#   (d) SIMD  : 生成 helper を実機 inline asm と bit 突合 (205 mnemonic の全 form) + 被覆 before/after   [--quick で省略]
#   (e) 注入  : パターン注入による P1/F7/F2 検出器の検出力と偽陽性                                     [--quick で省略]
#   (f) leaf  : OTT leaf native spec — exp/log 等の lift を実機機械語と bit 突合 (CAB-239)             [--quick で省略]
#   --fresh : RetDec の raw .ll キャッシュ (work/*/*.drc.ll) を捨てて再 lift する (KH は約 40 秒)
#
# 前提 (読取のみ): tools/targets/{freshair,kilohearts}/work の展開物, tools/m6/work の OTT lift 成果物, /opt/{emsdk,retdec}
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
QUICK=0; FRESH=0
for a in "$@"; do case "$a" in --quick) QUICK=1;; --fresh) FRESH=1;; esac; done
export PATH="$PATH:/opt/emsdk/node/24.19.0_64bit/bin"
# emcc/gcc の中間ファイルを tmpfs (/tmp 3.7GB) から担当 dir の work へ隔離 (CAB-239)
export TMPDIR="$HERE/work/tmp"; mkdir -p "$TMPDIR"
mkdir -p work

need() { [ -e "$1" ] || { echo "[liftlib_e2e] 前提が無い: $1  ($2)" >&2; exit 2; }; }
need "$HERE/../targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" "bash tools/targets/freshair/fetch.sh"
need "$HERE/../targets/kilohearts/work/winpkg/HeartCore.core_64" "bash tools/targets/kilohearts/scripts/extract_installer.sh"
need "$HERE/../m6/work/ott.drc.ll" "bash tools/m6/m6_lift.sh (OTT RetDec lift 成果物)"
need "$HERE/../m6/work/full_t1.drc.ll" "OTT full lift 成果物 (tools/m6/work)"
need /opt/retdec/bin/retdec-decompiler "RetDec"

RC=0
echo "=== (0) ユニット/性質テスト (base==m2+m5, p1_legacy/shift/gdata==m6 鎖, helper 名前非依存 ほか)"
python3 tests/test_unit.py || RC=1
# --fresh の削除は unit テスト (T4 が work/fa_gain/fa_gain.drc.ll を読む) の後
if [ "$FRESH" = 1 ]; then
  rm -f work/fa_gain/fa_gain.drc.* work/kh_gain/kh_gain.drc.*
  echo "[liftlib_e2e] --fresh: RetDec raw .ll を再生成"
fi
echo "=== (a)(b)(c) 回帰: FA Gain / KH Gain / OTT"
python3 -m liftlib regress || RC=1
if [ "$QUICK" = 0 ]; then
  echo "=== (d) SIMD helper: 実機 inline asm vs wasm (全 form)"
  python3 -m liftlib simd test --n 200 || RC=1
  python3 -m liftlib simd report || RC=1
  echo "=== (e) パターン注入による検出力評価"
  python3 -m liftlib inject-eval || RC=1
  echo "=== (f) OTT leaf native spec (leafabi + 実機機械語オラクル bit 突合, CAB-239)"
  python3 -m liftlib leafspec targets/ott_leaf.json --n 40 || RC=1
fi
if [ "$RC" = 0 ]; then echo "[liftlib_e2e] ALL PASS"; else echo "[liftlib_e2e] FAIL (上のログ参照)" >&2; fi
exit $RC
