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

## 5k. ON-only override の 4 要素同時除外と 410360 戻り値の切り分け (#2131 次 run)

- 測定 commit: `016cc403` (= origin/main)。変種の build・survey はこの commit のソースに変種の差し替えを足して行った (`ov.o` 作り直し、測定後に `m11_ov.c` を復元し `git status` で差分 0 を確認)。
- 素材 (測定時): fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開。`m11_gen_ir2.sh` rc=0 (41 s、F1=902、errors=0)。本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` しか無く、toolchain-retdec・toolchain-emsdk・work-m11 は無いため、本 run では再測定できない。
- 基準 ON (`SV_RAW=1`、全 942 unit) の再測定は未実施。前 run の値 (`ok 869 / oob 15 / abort 2 / halt0 7`) は測定元が `a1d55799` 作業ツリーで、clean だった証跡が無く出所は未検証のため、本節の比較には使わない。`git diff a1d55799 016cc403 -- tools/m11` はビルド入力のコードに差分が無い (`REPORT_1676.md`・`REPORT_SHX-T27.md`・`store_watch_2217.sh` の 3 ファイル)。

| 変種 (ON のまま外すもの) | 測定 commit | ok / oob / abort / halt0 | unit 190 |
|---|---|---|---|
| `all_off`: 41c130 disp・9b4b00 disp・413060 gate・410360 vcall (`M11_NOVCALL=1`) を同時に外す | `016cc403` | 869 / 16 / 2 / 6 | oob |
| `ret0_410360`: 410360 の C 版の戻り値だけ 0 にする | `016cc403` | 未測定 (survey が 400 s で timeout) | 未測定 |

- 読み (all_off): 上の 4 要素を同時に外しても unit 190 は oob のまま (n=1)。つまり ON-only の C 転記のうち、この 4 要素の範囲には原因が無い。all_off の結果では abort 2 が残る。
- 基準 ON との unit 別比較は未実施。`ablate_2131.py` は変種ごとの JSON を引数で渡された出力先 (`OUT`) に書くが、all_off の JSON は repo・`work/` のどちらにも保存されておらず、`survey_diff` で比較できない。よって「halt0 から oob に移った 1 unit」の記述は採らず、移った unit の番号は未特定。unit 190 の結論 (oob のまま) には影響しない。
- `ret0_410360` は survey が 400 s で timeout した。通常時の所要時間は本 run で測っていないため、比較の根拠は無い。410360 の戻り値を 0 にすると、呼出し側が hang する可能性がある (推定。未検証)。原因は未切り分け。
- 測定に使った一時変更 (`all_off`・`ret0_410360` の define 差し替え) は本 PR の script にのみ残し、`m11_ov.c` は変更していない。
- 未達 (受入条件 1・2): ON の `407a50` の `[arg-8]` 参照先を変える書込元は未特定。次の候補は、ON の build で変わる `407a50` の呼出し先 (481790・412d60・4133f0) の書込み、または 410360 の戻り値 (呼出し側の観測) の扱い。

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
