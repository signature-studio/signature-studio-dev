# REPORT_1274 付録 — 5i (#2131)

## 5i. ON-only override の disp 除外による切り分け (#2131、測定 commit `c15a2907` = origin/main、ov.o 作り直し)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`m11_gen_ir2.sh` rc=0 (34 s、ldfix=applied、F1=902、errors=0)。ON・OFF の build rc=0。
- 基準 (`SV_RAW=1`、全 942 unit): ON `ok 869 / oob 15 / abort 2 / halt0 7 / miss 47 / noproc 1 / other 1`、OFF `ok 870 / oob 16 / halt0 7 / miss 47 / noproc 1 / other 1`。§5 と一致。
- 変種 (`trap_triage/ablate_2131.py`、各変種で `ov.o` を作り直し、測定後に `m11_ov.c` を復元):

| 変種 (ON のまま外すもの) | ok / oob / halt0 | unit 190 |
|---|---|---|
| `41c130` の disp entry | 866 / 15 / 7 | oob |
| `9b4b00` の disp entry | 868 / 15 / 7 | oob |
| 両方 | 865 / 15 / 7 | oob |
| `413060` の C override (gate を `M11_OV_413060` のみに) | 868 / 16 / 6 | oob |

- 読み: 41c130・9b4b00 の disp、413060 の override は、単独でも両方でも unit 190 の oob を消さない。したがって ON で `407a50` の `[arg-8]` 参照先を変える書込元は、これら 3 つの override の中には無い。
- 未確定: 各変種は 1 回測定 (n=1)。残る候補は ON の build で変わる他の lift 本体 (`407a50` の呼出し先の書込み) と、ov.o 以外の gate。書込元の特定は未達 (受入条件 1・2 は未達、#2131 の次 run)。

## 5j. origin/main での再現 (測定 commit `e082c4f1` = origin/main、#1274 再 run)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開 (`FL_WIN64_DIR` = fl-win64 の展開先 `$RUNNER_TEMP/fl-win64`、`extracted/..` 形式は使わない)。`m11_gen_ir2.sh` rc=0 (F1=902、errors=0)。
- build: ON・OFF とも rc=0。ON は `ov.o` を作り直してから build、OFF も同様。
- survey: `SV_RAW=1 node survey_units.mjs` (全 942 unit)。JSON は `work/probe1274/{on,off}.json` (work/ 配下・commit 対象外)。

| build | ok / oob / abort / halt0 / miss / noproc / other |
|---|---|
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 / 47 / 1 / 1 |
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 / 47 / 1 / 1 |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。kind 変化は 190 (ok→oob)・304・555 (oob→abort, #1275)。§2 と一致。
- 読み: 現 main で再現性は確認した。ただし本 run は trap 源の特定 (受入条件 1)・DEFECTS 類型への分類 (受入条件 2) には進めていない。ON の ok 退行 0 (受入条件 3) も未達 (unit 190 が残る)。
- 未達: 受入条件 1〜3 は未達のまま。起票先: #1642 (親 #1274)。
