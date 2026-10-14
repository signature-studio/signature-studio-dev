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

- 記載上の測定 commit (出所未検証): `016cc403` (= origin/main)。
- 測定の実施: 下表の all_off・ret0_410360 の測定 run の run id と日付は記録されていない (本文書・PR・repo のどこにも残っていない)。測定時の素材の内訳も記録が無い。記録に残っている内容は「`m11_gen_ir2.sh` rc=0 (41 s、F1=902、errors=0)」のみである。
- 本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` (2.3 GB) しか実在せず、toolchain-retdec・toolchain-emsdk・work-m11 は無い。本 run では再測定していない。
- 基準 ON (`SV_RAW=1`、全 942 unit) の再測定は未実施。前 run の値 (`ok 869 / oob 15 / abort 2 / halt0 7`) は測定元が `a1d55799` 作業ツリーで、clean だった証跡が無く出所は未検証のため、本節の比較には使わない。`git diff a1d55799 016cc403 -- tools/m11` はビルド入力のコードに差分が無い (`REPORT_1676.md`・`REPORT_SHX-T27.md`・`store_watch_2217.sh` の 3 ファイル)。

| 変種 (ON のまま外すもの) | 測定 commit | ok / oob / abort / halt0 | unit 190 |
|---|---|---|---|
| `all_off`: 41c130 disp・9b4b00 disp・413060 gate・410360 vcall (`M11_NOVCALL=1`) を同時に外す | 記載の `016cc403` は出所未検証 (run id 不明) | 869 / 16 / 2 / 6 (出所未検証) | oob (出所未検証) |
| `ret0_410360`: 410360 の C 版の戻り値だけ 0 にする | 記載上 `016cc403` (出所未検証) | 未測定 (記録上の記述・未検証: survey が 400 s で timeout) | 未測定 |

- 結論: 本節の測定結果は未確定。all_off の行は run id・日付・測定ログ・JSON のいずれも残っておらず、出所を示せないため、結論には使わない。「4 要素を同時に外しても oob は消えない」とは書かない。本節で確定しているのは、切り分けスクリプト (`ablate_2131.py` の `all_off`・`ret0_410360` 変種) の追加と、その変種の置換対象が `016cc403` の `m11_ov.c` と一致することまで。
- all_off の 869 / 16 / 2 / 6 が §5g の ON+NOVCALL 行 (`5229fe5f`、同じ値) と一致する点は、偶然の一致か、同値の取り違えかを判定できない。再測定まで比較に使わない。
- 基準 ON との unit 別比較は未実施。`ablate_2131.py` は変種ごとの JSON を引数で渡された出力先 (`OUT`) に書くが、all_off の JSON は repo に commit しておらず、`work/` にも残っていない。理由: 測定時の出力先 (`OUT`) を repo へ保存する手順を取らず、その作業ディレクトリも本 run には残っていない (記録が無いため、これ以上は確定できない)。このため `survey_diff` で比較できず、「halt0 から oob に移った 1 unit」の記述は採らず、移った unit の番号は未特定。unit 190 の結論 (oob のまま) には影響しない。
- `ret0_410360` は、記録上は survey が 400 s で timeout したと記載されている (記録上の記述・未検証)。通常時の所要時間は本 run で測っていないため、比較の根拠は無い。410360 の戻り値を 0 にすると、呼出し側が hang する可能性がある (推定。未検証)。原因は未切り分け。
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

## 5k. origin/main での再現 (測定 commit `d33c763a` = origin/main、#1274 再 run・worktree ws-1274)

- 素材: fl-win64 (`FL_WIN64_DIR` = `$RUNNER_TEMP/fl-win64`)・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`m11_gen_ir2.sh` rc=0 (50 s、ldfix=applied、F1=902、errors=0)。
- 展開の注意: `work-m11` / `work-liftdiff` の tar は `tools/m11/work/` 等の相対パスを内包する。`-C tools/m11` で展開すると `tools/m11/tools/m11/work/` に二重化するため、`-C` を付けず repo 直下で展開する (本 run は誤展開後に移動して解消)。
- build: ON・OFF とも `ov.o` を作り直してから rc=0 (ON 24 s、OFF 19 s)。
- survey: 全 942 unit、`SV_RAW=1`、JSON は `work/probe1274/{on,off}.json` (work/ 配下・commit 対象外)。

| build | ok / oob / abort / halt0 / miss / noproc / other |
|---|---|
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 / 47 / 1 / 1 |
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 / 47 / 1 / 1 |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。kind 変化は 190 (ok→oob)・304・555 (oob→abort, #1275)。§5j・§2 と一致。
- 読み: 現 main でも同じ数値が再現した。書込元の切り分け (ON-only override の除外や書込マスク) は本 run では未実施。§5h・§5i で否定済みの 3 要素 (9b4b00/9b5450 の書込み、41c130・9b4b00 の disp、413060 の override) を再実施しても新しい情報は得られないため、次の切り分けは別経路 (ON build で変わる lift 本体側の書込み、ov.o 以外の gate) に絞る必要がある。
- 未達: 受入条件 1 (書込元の特定)・2 (DEFECTS 類型への分類)・3 (ON の ok 退行 0: unit 190 が残る)。起票先: #1642 (親 #1274)。
