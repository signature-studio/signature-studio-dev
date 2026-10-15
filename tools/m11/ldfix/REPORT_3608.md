# REPORT_3608 — 本番順の survey 残 trap の段別 A/B・r8b を含む本番順の判定・F3c 33→43 の出所 (#3608 項目 2・3・4、項目 1 は部分)

既知類型との関係: 53・87・138 の消失は qstore (DEFECTS.md の D17。REPORT_942_QSTORE)、56 は guard699 (D19。REPORT_942_PRODORDER §3)、17 は alloca 縮退 (REPORT_942_ALLOCA)。158 は qstore と alloca の組合せで消え、類型は未判定。新規類型は判定しない。DEFECTS.md は変更しない。

## 0. 結論

- **項目 2 (段別 A/B・達成)**: 元の 9 件のうち 53・87・138 は **qstore だけで消える** (ldfix の後に qstore だけを足すと 9→6)。158 は **qstore と alloca の両方が要る** (qstore だけ・alloca だけでは残る)。17 は alloca、56 は guard699 で消える。**ld108・ld115・src412770 は 9 件の集合も本番順の 22 件の集合も変えない** (累積 A/B と leave-one-out の両方で確認)。
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
| 158 | OOB | **qstore と alloca の両方で消える**。qstore だけ (c4) も alloca だけ (l_no_qstore) も残る |

### 1-2 段別 A/B の読み (項目 2)

- ld108・ld115・src412770 は、累積 (c0 → c1 → c2 → c3) でも leave-one-out (prod fix から 1 段ずつ外す) でも、trap 集合・survey 件数を変えない。よって 53・138・158 の消失の寄与はこの 3 段には無い。
- 53・87・138 の寄与は qstore。c3 → c4 で 9 → 6 (消えたのは 53・87・138)。
- 158 は qstore と alloca の組合せ (c4 残る・c5 消える・l_no_qstore 残る)。
- 17 は alloca (c4 残る → c5 消える)。56 は guard699 (c5 残る → c6 消える)。guard4fa210 は trap 集合を変えない (c6 と prod fix が同じ)。

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

| commit | F3c | f3c_use_replaced | f3c_fn_stores | f3c_use_dom / not_dom |
|---|--:|--:|--:|---|
| `f63b5953d^` (親) | 33 | 66 | 10 | — / — |
| `f63b5953d` | **43** | **80** | 9 | 11 / 7 |

- 増えた 10 関数 (親の F3c 集合に無く、`f63b5953d` で入った): `40fe90`・`41b8d0`・`41b970`・`449550`・`44f040`・`44fb40`・`47ad70`・`784ed0`・`c40420`・`f552a0`。削除された関数は 0。
- `f3c_use_replaced` の +14 は、REPORT_1325 §6 の記載どおり、§3 の 11 組の置換数の和 (1+1+1+1+2+2+1+1+1+1+2 = 14)。`f3c_fn_stores` 10 → 9 は、`806740` の store 形 1 site が use 形へ移った分 (REPORT_1325 §6)。
- 由来: `f63b5953d` は REPORT_1325 (#1325) の修復 (支配関係つき first-deref-not-entry)。F3c 件数の増加は、その修復の意図した効果 (修復対象の拡大)。REPORT_942_PRODORDER の 33 は、この commit より前の値。
- 現 HEAD (`40d3a788d` 時点) の F3c = 43 (`ldfix_e2e` の出力行 `F3a=2 F3c=43`)。REPORT_942_PRODORDER §7 の「現 43 の出所」はこの §4 で解消。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| trap 144 (最内 `function_44aeb0` の入力値・書込み元)・149 (`function_412e40`)・114 (Halt 呼出し元) の unit 単位の引き金 | 項目 1 (受入 1 の残り) | #3608 (open のまま・部分達成) |
| ldfix の F3a 2・F3c 43 のうち件数に反映されなかった修復 (反映は unit 895 の 1 件) の理由 | 項目 3 の理由 | #3608 |

## 6. 測定 commit と差分 (`docs/WORKFLOW.md` §6)

- 測定 commit: `40d3a788d` (手元 HEAD。測定は作業ツリーの `prod_order_3608.sh` で行い、その内容は本 PR の commit と同一)。
- 測定経路 (`git diff 40d3a788d origin/main -- <path>` の出力は §6-1 のとおり、差分 0):

```
git diff 40d3a788d origin/main -- tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_ld108.py tools/m11/ldfix/fix_ld115.py tools/m11/ldfix/fix_src412770.py tools/m11/ldfix/fix_r8b815050.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/ldframe.py tools/m11/ldfix/stage4.sh tools/m11/ldfix/run_stage4.mjs tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/trap_units.mjs tools/m11/ldfix/prod_order_942.sh tools/m11/ldfix/ldfix_e2e.sh tools/m11/m11_build.sh tools/m11/m11_gen_ir2.sh tools/m11/alloca tools/m11/guard699 tools/m11/guard4fa210 tools/m11/qstore tools/m11/lb_base.py tools/shared/env.sh
```

- 上の範囲の差分は 0 行 (`... | wc -l` → 0)。よって `origin/main` 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。
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

- 出力は `tools/m11/ldfix/work/p3608/NAME/summary.txt` と `trap_units.json` (gitignore)。
- F3c 33/43 の確認: `git archive f63b5953d^ tools/m11/ldfix tools/m11/lb_base.py` と `git archive f63b5953d ...` を展開し、各 `ldfix.py` を同じ入力で実行 (本 REPORT §4 の表)。
