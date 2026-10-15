# REPORT_3608 — 本番順の survey 残 trap の段別 A/B・r8b を含む本番順の判定・F3c 33→43 の出所 (#3608 項目 2・3・4、項目 1 は部分)

既知類型との関係: 53・87・138 の消失は qstore (DEFECTS.md の D17。REPORT_942_QSTORE)、56 は guard699 (D19。REPORT_942_PRODORDER §3)、17 は alloca 縮退 (REPORT_942_ALLOCA)。158 は qstore と alloca の組合せで消え、類型は未判定。新規類型は判定しない。DEFECTS.md は変更しない。

## 0. 結論

- **項目 2 (段別 A/B・達成)**: 元の 9 件のうち 53・87・138 は **qstore だけで消える** (ldfix の後に qstore だけを足すと 9→6)。158 は **qstore と alloca の両方が要る** (qstore だけ (c4) も、qstore を外した prod fix (l_no_qstore・alloca あり) も残る)。17 は alloca、56 は guard699 で消える。**ld108・ld115・src412770 は 9 件の集合も本番順の 22 件の集合も変えない** (累積 A/B と leave-one-out の両方で確認。unit 番号の照合は §1-3)。
- **項目 3 (r8b を含む本番順の判定・達成)**: r8b (`fix_r8b815050.py`・main の `m11_gen_ir2.sh` の既定) を含めても、件数 (survey ok/miss/trap) は r8b 無しと同じ。fix・base とも 872/47/22。fix と base の差は unit 895 (OOB → halt0) の 1 件だけ。r8b は unit 280・659 の trap を消さない (最内 frame は同じ callee `function_6cefb0`。呼出し位置の offset だけが変わる)。
- **項目 4 (F3c 33→43 の出所・達成)**: commit `f63b5953d` (`fix(ldfix): repair first-deref-not-entry uses dominated by the deref block (refs #1325)`) で F3c 関数が 33 → 43 に増えた。同じ入力 `boot_final3.ll` で、親 (`f63b5953d^`) は 33、この commit は 43 (§4)。
- **項目 1 (trap 144・149・114 の引き金・未達)**: unit 別の最内 frame と段ごとの変化までを記録した。引き金 (最内 IR 関数の入力値・書込み元) は未特定。PR は部分達成 (`Refs #3608`)。残りは #3608 で続行。

## 1. 測定 (測定 commit `40d3a788d`・以後の差分は §6)

測定コマンド (すべて `export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP`。各 run 後の load average は 1.9 以下 (4 コア・uptime 実測)。各変種は単独で完走)。

| 変種 | 入力 | 追加した段 (適用順は main の `m11_gen_ir2.sh` → `m11_build.sh` に固定) | units_run | threw | survey ok / miss / trap (OOB・halt0) |
|---|---|---|--:|---|---|
| c0 | `ldfix_fixed.ll` | (なし) | 17 | OOB | 136 / 14 / 9 (8・1) |
| c1 | 同 | ld108 | 17 | OOB | 136 / 14 / 9 (8・1) |
| c2 | 同 | ld108・ld115 | 17 | OOB | 136 / 14 / 9 (8・1) |
| c3 | 同 | ld108・ld115・src412770 | 17 | OOB | 136 / 14 / 9 (8・1) |
| c4 | 同 | 〜・qstore | 17 | OOB | 139 / 14 / 6 (4・2) |
| c5 | 同 | 〜・alloca | 52 | OOB | 871 / 47 / 23 (15・8) |
| c6 | 同 | 〜・guard699 | 109 | なし | 872 / 47 / 22 (14・8) |
| **prod fix (= h_nor8b)** | 同 | 〜・guard4fa210 | 109 | なし | 872 / 47 / 22 (14・8) |
| l\_no\_ld108 | 同 | prod fix から ld108 を外す | 109 | なし | 872 / 47 / 22 (14・8) |
| l\_no\_ld115 | 同 | prod fix から ld115 を外す | 109 | なし | 872 / 47 / 22 (14・8) |
| l\_no\_src412770 | 同 | prod fix から src412770 を外す | 109 | なし | 872 / 47 / 22 (14・8) |
| l\_no\_qstore | 同 | prod fix から qstore を外す | 83 | OOB | 869 / 47 / 25 (17・8) |
| **full\_r8b (本番順・r8b 含む fix)** | 同 | ld108・ld115・src412770・**r8b**・qstore・alloca・guard699・guard4fa210 | 109 | なし | 872 / 47 / 22 (14・8) |
| **base\_r8b (本番順・r8b 含む base)** | `boot_final3.ll` | **r8b**・qstore・alloca・guard699・guard4fa210 | 109 | なし | 872 / 47 / 22 (15・7) |

- 再現スクリプト: `tools/m11/ldfix/prod_order_3608.sh NAME (fix|raw) STAGES` (段は `ld108,ld115,src412770,r8b,qstore,alloca,guard699,guard4fa210` から選ぶ)。比較用の既存測定 `prod_order_942.sh` は実測 fix 53.6 秒・base 52.4 秒 (`time`)。
- 検算: prod fix (h_nor8b) は `prod_order_942.sh fix` (REPORT_942_PRODORDER §1 の prod fix 872/47/22 (14・8)) と一致。ldfix_e2e (base 136/14/9・fix 136/14/9・judge PASS) も §1 と一致。
- ハーネス: prod_order_3608.sh は prod_order_942.sh と同じ unweak/reweak と CF (fix のみ `-DM11_OV_NO_450560`) を使う。
- 本 fix (差し戻し対応・commit `87208313b`) で上表の 14 変種を全て再実行し、ok / miss / trap の件数は上表と全て一致した。trap の unit 番号は §1-3。load は本 fix の再測定では記録していない (上表の load の主張は 40d3a788d 時点の値)。
- 母集団 (survey の ok + miss + trap) は c0〜c4 が 159、c5 以降が 941。段が進むと boot が unit 17 を越えて進み (c5 の units_run は 52、c6 以降は 109)、survey 対象が増えるため、c4 と c5 は同じ母集団ではない。c5 の trap 23 件のうち 19 件 (245・275・279・280・314・368・477・484・492・509・513・520・647・659・745・830・880・895・923) は c0 の 9 件に無い (§1-3)。

### 1-1 unit 別の trap 一覧 (c0 の 9 件)

| unit | c0 (ldfix のみ) | 段で消える・変わる |
|---|---|---|
| 17 | OOB | alloca で消える (c4 まで残る・c5 で消える) |
| 53 | OOB | **qstore で消える** (c3 → c4) |
| 56 | OOB | guard699 で消える (c5 → c6) |
| 87 | OOB | **qstore で消える** (c3 → c4)。qstore を外すと再出現 (l_no_qstore) |
| 114 | halt0 | 変化なし (全変種で halt0) |
| 138 | OOB | **qstore で消える** (c3 → c4) |
| 144 | OOB | qstore で halt0 になる (c4)。alloca で OOB に戻る (c5)。prod では OOB |
| 149 | OOB | 変化なし (全変種で OOB) |
| 158 | OOB | **qstore と alloca の両方で消える**。qstore だけ (c4) も、qstore を外した prod fix (l_no_qstore・alloca あり) も残る |

### 1-2 段別 A/B の読み (項目 2)

- ld108・ld115・src412770 は、累積 (c0 → c1 → c2 → c3) でも leave-one-out (prod fix から 1 段ずつ外す) でも、trap 集合・survey 件数を変えない。よって 53・138・158 の消失の寄与はこの 3 段には無い。
- 53・87・138 の寄与は qstore。c3 → c4 で 9 → 6 (消えたのは 53・87・138)。
- 158 は qstore と alloca の組合せ (c4 残る・c5 消える・l_no_qstore 残る)。
- 17 は alloca (c4 残る → c5 消える)。56 は guard699 (c5 残る → c6 消える)。guard4fa210 は trap 集合を変えない (c6 と prod fix が同じ)。

### 1-3 trap unit 集合の照合 (本 fix で再測定)

`prod_order_3608.sh` で上表の変種を再実行し、`work/p3608/NAME/trap_units.json` (gitignore) の unit 番号と種別 (OOB / halt0) を比べた。件数は §1 と全変種で一致。

**9 件版 (units_run 17・母集団 159)**。S9 = 17・53・56・87・138・144・149・158 (OOB)、114 (halt0)。

| 変種 | 段 | trap 件数 | trap 集合 |
|---|---|--:|---|
| c0 (ldfix のみ) | (なし) | 9 | S9 |
| c1 | + ld108 | 9 | S9 と同じ |
| c2 | + ld115 | 9 | S9 と同じ |
| c3 | + src412770 | 9 | S9 と同じ |
| c4 | + qstore | 6 | 17・56・149・158 (OOB)、114・144 (halt0)。S9 から 53・87・138 が消える |

**本番順 (units_run 109・母集団 941)**。S22 = 114・245・279・314・368・509・647・895 (halt0)、144・149・275・280・477・484・492・513・520・659・745・830・880・923 (OOB)。

| 変種 | 段 | units_run | trap 件数 | S22 との関係 |
|---|---|--:|--:|---|
| prod fix (h_nor8b) | ld108・ld115・src412770・qstore・alloca・guard699・guard4fa210 | 109 | 22 | S22 (基準) |
| full\_r8b | prod fix + r8b | 109 | 22 | S22 と同じ (種別も同じ) |
| l\_no\_ld108 | prod fix − ld108 | 109 | 22 | S22 と同じ |
| l\_no\_ld115 | prod fix − ld115 | 109 | 22 | S22 と同じ |
| l\_no\_src412770 | prod fix − src412770 | 109 | 22 | S22 と同じ |
| c6 | prod fix − guard4fa210 | 109 | 22 | S22 と同じ |
| base\_r8b (raw) | r8b・qstore・alloca・guard699・guard4fa210 | 109 | 22 | S22 と同じ。895 だけ OOB (fix は halt0) |
| c5 | prod fix − guard699 − guard4fa210 | 52 | 23 | S22 + 56 |
| l\_no\_qstore | prod fix − qstore | 83 | 25 | S22 + 87・158・898 |

- ld108・ld115・src412770 は、9 件版 (c0〜c3) でも本番順 (prod fix と各 leave-one-out) でも trap 集合を変えない。
- 53・87・138 は qstore で消える (S9 → c4)。158 は qstore と alloca の両方が要る (c4 は残る・c5 は消える・l_no_qstore は残る)。
- r8b は集合を変えない。fix と base の差は unit 895 の種別だけ (§2)。

## 2. 項目 3: r8b を含む本番順の判定 (ldfix の件数反映)

- 本番順 (r8b 含む) の fix と base: 両方 872 / 47 / 22。stage4 は両方 units 109・init 111・icall_ok 435・dllmain_done True・threw なし。
- fix と base の差は **unit 895 のみ** (fix = halt0、base = OOB)。r8b を入れても同じ (base_r8b の 895 は OOB、full_r8b の 895 は halt0)。
- 件数の反映: ldfix の修復 (F3a 2 関数・F3c 43 関数 (§4)) のうち、survey の件数に反映されたのは unit 895 の 1 件 (OOB → halt0) だけ。他の修復が件数に反映されない理由は未特定 (§3 の 144 の注を参照。未検証)。
- r8b の効果: 件数は変えない (h_nor8b と full_r8b、base と base_r8b は同じ 22 件・同じ 872)。unit 280・659 は r8b を入れても OOB のまま (最内 `function_6cefb0` ← `function_815050`。呼出し元 frame の offset が 0x25f6f0 → 0x25f6ed に変わるだけ)。REPORT_942_PRODORDER の注 (r8b で 280・659 の判定が変わり得る) は、件数では変わらないと判定する。

## 3. 項目 1: 残る trap の unit 別 frame (部分・引き金は未特定)

最内 frame (wasm 関数 index @ 位置) と呼出し元 (`prod fix` = h_nor8b・`full_r8b` の値)。IR 名は REPORT_942_PRODORDER §4 の対応 (測定 commit の位置。現 HEAD では wasm 位置が数 byte ずれる)。

| unit | 種別 | 最内 frame (IR 名は REPORT_942_PRODORDER §4) | 呼出し元 | 段による変化 |
|---|---|---|---|---|
| 114 | halt0 | — | — | 変化なし |
| 144 | OOB | 2761 @0x1746ae (`function_44aeb0`) | 683 @0xad284 (`function_44f040`) ← 3903 @0x1c2f9e (`function_653660`) | qstore で halt0 (c4)・alloca で OOB に戻る (c5)。c0 は別の frame (1878 @0x13cf02) |
| 149 | OOB | 77 @0x6b6cd (`function_412e40`) | 3903 @0x1c32b6 (`function_653660`) ← 3904 @0x1c330f (`function_6539e0`) | 全変種で同じ呼出し鎖 (offset だけ変化) |

- 149 は、ldfix 以降のどの段を足しても・外しても、最内は `function_412e40`、呼出しは `function_653660` ← `function_6539e0` のまま。段の修復の対象外。
- 144 の呼出し元 `function_44f040` は、`f63b5953d` で新たに F3c 修復の対象になった 10 関数の 1 つ (§4)。修復後も 144 は OOB のまま (最内は `function_44aeb0` の位置 0x1746ae)。修復が 144 の入力に効かなかったことを示す。ただし入力値・書込み元の確認は未実施。
- 項目 1 の残り: 144 (最内 `function_44aeb0` の入力値と書込み元) と 149 (`function_412e40` の入力値) の unit 単位の入力・書込み元の特定は未実施。114 (halt0) は Halt 呼出し元の特定が未実施。`trap56_probe_942.mjs` 相当の引数採取を 144・149 に当てる作業が要る (未着手)。

## 4. 項目 4: F3c 33 → 43 の出所

同じ入力 (`tools/m11/work/boot_final3.ll`)・同じ PE で `ldfix.py` を commit ごとに実行 (`git archive` で一時展開。作業ツリーは未変更):

| commit | F3c |
|---|--:|
| `f63b5953d^` (親) | 33 |
| `f63b5953d` | **43** |

- 増えた 10 関数 (親の F3c 集合に無く、`f63b5953d` で入った): `40fe90`・`41b8d0`・`41b970`・`449550`・`44f040`・`44fb40`・`47ad70`・`784ed0`・`c40420`・`f552a0`。削除された関数は 0。
- `f3c_use_replaced`・`f3c_fn_stores`・use の dom / not_dom の内訳と、その増減の由来は REPORT_1325 §6 を引く (本 REPORT には書かない)。
- 由来: `f63b5953d` は REPORT_1325 (#1325) の修復 (支配関係つき first-deref-not-entry)。F3c 件数の増加は、その修復の意図した効果 (修復対象の拡大)。REPORT_942_PRODORDER の 33 は、この commit より前の値。
- 現 HEAD (`87208313b`・本 fix で再確認) の F3c = 43、F3a = 2 (`ldfix.py` の `ldfix_report.json` の `f3c_fns`・`f3a_fns`)。REPORT_942_PRODORDER §7 の「現 43 の出所」はこの §4 で解消。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| trap 144 (最内 `function_44aeb0` の入力値・書込み元)・149 (`function_412e40`)・114 (Halt 呼出し元) の unit 単位の引き金 | 項目 1 (受入 1 の残り) | #3608 (open のまま・部分達成) |
| ldfix の F3a 2・F3c 43 のうち件数に反映されなかった修復 (反映は unit 895 の 1 件) の理由 | 項目 3 の理由 | #3608 |
| §8 の引数採取 (probe144.py・read144.mjs) が未 commit で、committed HEAD から再現できない。IR 生成に RetDec 全 lift が要り、本 runner に無い | §8 の全数値の根拠 (受入 1) | #3608 (採取スクリプトの commit と IR 生成環境が要る) |

## 6. 測定 commit と差分 (`docs/WORKFLOW.md` §6)

- 測定 commit: `40d3a788d` (§1 の元の測定。手元 HEAD。測定に使った `prod_order_3608.sh` の内容は本 PR の commit `87208313b` と同一)・`87208313b` (本 fix で §1 の全変種と §1-3 を再測定した commit。以後コードは変えていない)。
- 測定経路 (`git diff 40d3a788d origin/main -- <path>` は 0 行。`fix_450560.py`〜`fix_abi_3450.py` は `ldfix_e2e.sh` の前段で使う):

```
git diff 40d3a788d origin/main -- tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py tools/m11/ldfix/fix_site_3326.py tools/m11/ldfix/fix_site_3372.py tools/m11/ldfix/fix_abi_3450.py tools/m11/ldfix/fix_ld108.py tools/m11/ldfix/fix_ld115.py tools/m11/ldfix/fix_src412770.py tools/m11/ldfix/fix_r8b815050.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/ldframe.py tools/m11/ldfix/stage4.sh tools/m11/ldfix/run_stage4.mjs tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/trap_units.mjs tools/m11/ldfix/prod_order_942.sh tools/m11/ldfix/prod_order_3608.sh tools/m11/ldfix/ldfix_e2e.sh tools/m11/m11_build.sh tools/m11/m11_gen_ir2.sh tools/m11/alloca tools/m11/guard699 tools/m11/guard4fa210 tools/m11/qstore tools/m11/lb_base.py tools/shared/env.sh
```

- 上の範囲の差分は 0 行 (`... | wc -l` → 0)。よって `origin/main` 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。
- 本 fix の再測定 (§1 の全変種・§1-3) は `87208313b` で実施。同じ経路 (上の一覧) について、`git diff 40d3a788d 87208313b` は `prod_order_3608.sh` の追加 (71 行) だけ。`git diff 87208313b HEAD` は 90 行追加 (5 ファイル: `ldfix.py`・`ldfix_e2e.sh`・`fix_site_3372.py`・`m11_build.sh`・`m11_gen_ir2.sh`。main 取り込みで入った変更。`d1759801c`・`189d9580b` ほか)。よって §1 の数値は `87208313b` 時点のコードのもので、HEAD のコードでは再測定していない。HEAD 上の測定値は未取得 (§8 と同じく本 runner に RetDec・emsdk が無い)。
- `origin/main` (`91ed96332`) と `40d3a788d` の差分は、REPORT・新規の別系統スクリプト (`ld175_site_link.py`・`trap_triage/slot653660_exp.py`)・`tools/shared/lift/rex` (x64c 系) のみ。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP   # 素材展開後
bash tools/m11/ldfix/ldfix_e2e.sh                                 # work/ldfix_fixed.ll と base/fix (判定 PASS)
bash tools/m11/ldfix/prod_order_3608.sh h_nor8b fix ld108,ld115,src412770,qstore,alloca,guard699,guard4fa210
bash tools/m11/ldfix/prod_order_3608.sh c0_ldfix fix ""
bash tools/m11/ldfix/prod_order_3608.sh c4_qstore fix ld108,ld115,src412770,qstore
bash tools/m11/ldfix/prod_order_3608.sh c5_alloca fix ld108,ld115,src412770,qstore,alloca
bash tools/m11/ldfix/prod_order_3608.sh full_r8b fix ld108,ld115,src412770,r8b,qstore,alloca,guard699,guard4fa210
bash tools/m11/ldfix/prod_order_3608.sh base_r8b raw r8b,qstore,alloca,guard699,guard4fa210
cd tools/m11 && python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe <block00031_PE.bin> --report out.json   # F3c 43 (現 HEAD)
```

- 出力は `tools/m11/ldfix/work/p3608/NAME/summary.txt` と `trap_units.json` (gitignore)。本 fix の §1-3 は、§1 の表の変種を全て同じスクリプトで再実行して照合した (`ld108,ld115,src412770` 等の段は表の列どおり。c1〜c6・l_no_*・base_r8b を含む)。
- F3c 33/43 の確認: `git archive f63b5953d^ tools/m11/ldfix tools/m11/lb_base.py` と `git archive f63b5953d ...` を展開し、各 `ldfix.py` を同じ入力で実行 (本 REPORT §4 の表)。

### 7-1 `ldfix_e2e.sh` の再現 (受入 1 の run・HEAD `d1759801c`)

- `origin/main` の `ldfix.py` は #4421・#4439 で採番が変わり、6074b0 の 1 段読みが `%ldfxu24` → `%ldfxu25` になった。`fix_site_3372.py` がその名前を決め打ちしていたため `ldfix_e2e.sh` が 1d/5 で落ちていた (AssertionError)。`d1759801c` で値名に依存しない判定に直した (機械照合・IR 編集の中身は不変)。
- `d1759801c` で `ldfix_e2e.sh` を実行: rc=0・所要 36 秒 (13:09:27Z 終了時の `uptime` load 0.82)・判定 PASS。base/fix ともに stage4 到達 4/6・survey ok 136 / miss 14 / trap 9 (§1 の c0 と一致)。
- 機械照合は 44f040 9 件・47cf10 8 件・6074b0 4 件で、いずれも従来どおり 21 件 ok。
- **受入 1 は未着手**: 144・149 の trap 時点の引数採取 (`trap56_probe_942.mjs` 相当の probe) と書込み元の追跡は本 run では行っていない。次の run で着手する。

## 8. trap 144・149・114 の引き金 (受入 1・部分) — 未再現のため測定値は撤回

- 前の run で採取した entry 引数の表 (144 の `a1`・149 の `a2` など) は撤回した。採取に使った probe (`probe144.py`・`read144.mjs`) は commit されておらず (`work/` 内・gitignore)、committed HEAD から再現できない。撤回前の本節は commit `1c0911297` の `tools/m11/ldfix/REPORT_3608.md` §8 に残る。ここには値も読みも書かない。
- `ldfix_e2e.sh`・`prod_order_3608.sh` の rc・所要時間・件数の主張も撤回した。本 run では未実行。理由: IR の生成 (`tools/m11/m11_e2e.sh`) に RetDec・emsdk・PE 素材 (`FL_WIN64_DIR`) が要り、本 runner には `/opt/retdec`・`/opt/emsdk`・PE 素材が無い。§1〜§6 の測定値は従来どおり測定 commit `40d3a788d`・`87208313b` に基づく (§6)。
- 未確定 (受入 1 の残り): 144 の `function_44aeb0` が受ける値の書込み元、149 の `function_412e40` の引数の上流、114 の Halt 呼出し元。採取は採取スクリプトを committed な場所に置き、IR 生成環境が揃ってから行う。
- 検証起点: `git diff 4e9e1d974 HEAD --numstat -- tools/m11/ldfix` の出力は `tools/m11/ldfix/REPORT_3608.md` のみで、コード差分は 0 (数値は PR 本文に書く)。
