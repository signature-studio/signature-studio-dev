# REPORT_APPENDIX_1635 (GUI-22 #1635)

#1442 (GUI-21) の S1 (soft) FAIL の切り分け。`REPORT.md` / `REPORT_APPENDIX.md` §6i の 101/291/296 の記録は、現 IR では再現しなかった。差分 unit は **304 と 555** (順序依存と確認)。

測定の状態: **§2-0 の実測値は HEAD `33585cb01` の e2e 1 回の値** (B1・B2・m4 の修正を含む)。測定 commit は `33585cb01` (コードを変えた最後の commit。鮮度は §2-0)。`results/` はこの測定の出力。過去の測定 (`7f54678a7`・B1 修正前) は §2-1〜§2-3 に残す。

## 1. 結論

| 項目 | 結果 |
|---|---|
| 原因 (304/555) | **測定済み**: survey は unit を chained に流し、正常終了した unit の後で線形メモリを戻さない。単独実行 (§2-3) では base と soft がともに `halt0->longjmp` で一致し、chain 実行でだけ差が出る (順序依存)。**未解明**: どの前 unit のどの状態が base の abort を作るか (#1426)。base と soft の前 unit の振る舞いの違いが shim の有無によるかは **推定で、未測定** |
| 101/291/296 | 現 IR では base/soft とも同じ結果。unit 単位の比較 (§2-4) で差は 304/555 の 2 件のみ |
| 隔離条件の統一 | `GF_SURVEY_RESET=1` を base / ff / soft の全 survey に適用。各 unit の開始時に wasm 線形メモリを boot 直後の内容へ戻し、boot 後に伸びた領域はゼロ埋めする (§2-5)。**範囲は wasm 線形メモリだけ**。JS 側の状態 (`errs` の蓄積・`perUnit`・`kinds` などの JS 変数) と wasm 外の状態は対象外 |
| 判定式 | S1 (totals の一致) は変更なし。S3 (unit 単位の base/soft 一致・942 件) を追加し、HEAD で PASS (§2-4)。R2 の floor 19 は不変 |
| S1 の判定条件 (範囲) | 隔離版の到達は **12 種** (trap 131)。chain の soft は **33 種** (trap 21)。S1 は GUI API の 12/33 しか通らない条件で判定される。既定にしてよいかは **PM agent の判断待ち** (§4) |
| R2 (到達 floor) | 入力は chain 実行 `survey_soft_chain.json` (873/21・到達 33 種)。pre-PR の `survey_soft.json` (`git show f46330b13:tools/gui/flengine/results/survey_soft.json`) と、`ok/noproc/miss/trap/clobber`・`kinds`・`failfast_units`・reach 名の集合 (33 種)・`reach_summary` が一致する (§2-6)。survey 辞書の全体比較は、新キー `mem_boot_bytes`・`mem_grown_units`・`mem_end_bytes` の 3 件が増えたため一致しない。R2 の意味は変わっていない |
| 本 HEAD の e2e | rc 0・510 s・judge 15/15 PASS・S1 soft = base `764/1/46/131/0`・S3 942/942 units 差 0 件・ネガコン N1〜N10 すべて期待どおり FAIL (§2-0) |

## 2. 実測

### 2-0. 本 HEAD (`33585cb01`) の e2e (foreground・1 回)

| 項目 | 値 |
|---|---|
| 測定 commit | `33585cb01`。測定時の作業ツリーはこの commit と同一 (e2e の出力 `tools/gui/work/`・`tools/m11/work/` は gitignore) |
| 日時・所要 | 2026-10-15 05:19:21 → 05:27:51 UTC (`date`)。e2e の done 行で 510 s |
| load | 0.35 0.34 0.16 → 1.10 1.01 0.59 (nproc 4) |
| 素材 | `fl-win64` (`extracted/` のみ展開)・`toolchain-emsdk` (`/opt/emsdk`)・`toolchain-retdec` (`/opt/retdec`)・`work-m11` (`tools/m11/work/`)。`x86_64-w64-mingw32-gcc` は runner 導入済み |

| rc | judge | S1 soft | S3 | R2 | native selftest | ネガコン |
|---|---|---|---|---|---|---|
| **0** | **15/15 PASS** | `764/1/46/131/0` = base `764/1/46/131/0` | **942/942 units・差 0 件** | reached 33 ≥ 19 (`missing=[]`) | 512 passed / 0 failed | **N1〜N10 すべて期待どおり FAIL** |

他の gate (PASS): L1 (ff・soft とも `0/0/0`)・A1 (declare 193 = adapter 193・impl 174・stub 19)・B1 (units_run 109 = base 109・GetMem 761・FreeMem 24・icall_miss 7)・R1 (最初の API `LoadStringW` ×3 IMPL・boot の到達 24 件 (名前も 24 種))・S2・P1〜P5・W1 (WNDCLASS 11・fn WNDPROC 8・最終 IR 外 0)。`__pe_image` の parity と e2e も PASS。

ネガコン (期待どおり FAIL): N1 R1 (plain) / N2 B1 (期待 23) / N3 R2 (`NoSuchGuiApi` 追加) / N4 S1 (ok→trap) / N5 selftest (`GetDC(NULL)` を fail-fast に戻した shim・rc 134) / N6 W1 走査 (`--check`) / N7 W1 (judge) / N8 走査 floor +1 / N9 P5 (hwnd NULL) / N10 S3 (soft の 1 unit を ok→trap)。

鮮度 (測定 commit から HEAD までのコード差分。`*.md` と生成結果 `results/` は除く):

```
git diff 33585cb01 HEAD -- tools/gui tools/m11 tools/shim tools/shared ':!*.md' ':!tools/gui/flengine/results'
```

出力: 0 行 (本 commit は本 REPORT・`results/`・PR 本文の修正だけ)。

### 2-1. 過去の e2e (`7f54678a7`・B1 修正前・foreground・1 回)

| rc | 所要 (done 行) | load (開始 → 終了) | judge | S1 | R2 | native selftest | ネガコン |
|---|---|---|---|---|---|---|---|
| **0** | 504 s | 0.41 → 1.06 | **14/14 PASS** | soft `764/1/46/131/0` = base `764/1/46/131/0` | reached 33 ≥ 19 (`missing=[]`) | 512 passed / 0 failed | N1〜N9 期待どおり FAIL (9/9) |

### 2-2. 修正前の chain 実行 (`f46330b13` の `tools/gui` に base の unit 別出力だけを足した版)

| 実行 | 結果 |
|---|---|
| e2e (chain) | rc 1 / 489 s / judge 13/14 (S1 のみ FAIL)。S1 soft `873/1/47/21/0` vs base `871/1/47/23/0` |
| 差分 unit (survey 配列の突き合わせ・942 件) | **304 と 555 の 2 件のみ**。base `Aborted(native code called abort())` → soft `ok`。101/291/296 は差なし |

### 2-3. 単独実行 (boot 直後に当該 unit だけ実行。`GF_SURVEY_ONLY`)

| unit | base | soft |
|---|---|---|
| 304 | `halt0->longjmp` | `halt0->longjmp` |
| 555 | `halt0->longjmp` | `halt0->longjmp` |
| 101 | `halt0->longjmp` | `halt0->longjmp` |
| 291 | `halt0->longjmp` | `halt0->longjmp` |
| 296 | `halt0->longjmp` | `halt0->longjmp` |

単独では base と soft が一致する。chain の 304/555 の差は前 unit の状態による (順序依存)。**どの前 unit のどの状態が効くかは未解明** (#1426)。「base と soft は前 unit の振る舞いが違う (shim の有無による)」は測定しておらず、結論に含めない。

### 2-4. unit 単位の一致 (本 HEAD・S3)

| 出力 | units | ok | noproc | miss | trap | clobber |
|---|---|---|---|---|---|---|
| base (`results/baseline_units.json`) | 942 | 764 | 1 | 46 | 131 | 0 |
| soft (`results/survey_soft_units.json`) | 942 | 764 | 1 | 46 | 131 | 0 |

unit 差 (unit ごとの `[status, kind]` の組の比較): **0 件** (judge の S3 PASS)。trap の kind も unit 単位で一致する (内訳は `results/baseline_survey.json` の `kinds`: `memory access out of bounds` 122 / `halt0->longjmp` 9)。

`e2e.sh` が 2 件を `results/` へ保存し、judge の S3 が突き合わせる。旧版の「942 unit 全件一致」は根拠の無い記述だった (review B2)。本節の値が、その根拠に置き換わる。

### 2-5. reset の伸長領域 (本 HEAD・B1)

| 実行 | `mem_boot_bytes` | `mem_grown_units` | `mem_end_bytes` |
|---|---|---|---|
| base (`baseline_survey.json`) | 301989888 | 1 | 362414080 |
| ff (`survey_ff.json`) | 301989888 | 1 | 362414080 |
| soft 隔離 (`survey_soft.json`) | 301989888 | 1 | 362414080 |
| soft chain (`survey_soft_chain.json`・`GF_SURVEY_RESET=0`) | 301989888 | 9 | 1578237952 |

`mem_grown_units` は、実行の前後で線形メモリの長さが増えた unit 数。隔離実行では 1 件 (伸ばした領域は縮まないため、以後の unit では増えない)。boot 時には存在しない領域は `mem_end − mem_boot` = 60424192 bytes (57.6 MiB) で、reset のたびにゼロ埋めされる。**B1 の修正前後で S1 は変わらなかった** (修正前 `7f54678a7` の S1 = 本 HEAD の S1 = `764/1/46/131/0`)。この測定では伸長による結果の差は出ていない。

### 2-6. reset 後の集計値の意味 (review m2・本 HEAD で確認)

`survey_ff.json` / `survey_soft.json` の `reach_summary` (`reached=1 impl=1 stub=0`)・`gui_icall_calls` (0)・`va_calls` (0)・`init_count` (0) は **最後の unit の値** で、全 unit の集計ではない。reset なしの `survey_soft_chain.json` では `reached=33 impl=33`・`gui_icall_calls` 7・`va_calls` 28・`init_count` 895。`reach` は各 unit 開始時の dump の連結で、`survey_soft.json` では 18 件・名前の集合は 12 種。judge の INFO 行 (natural reach) は隔離 survey の `reach` を使うため 12 種の集計になる。judge はこれらの最後の unit の値を参照しない。

R2 の一致 (`f46330b13` の `survey_soft.json` と `survey_soft_chain.json`): `ok/noproc/miss/trap/clobber` = 873/1/47/21/0 で一致、`kinds`・`failfast_units` 一致、reach 名の集合 33 種 一致、`reach_summary` 一致。survey 辞書の全体は新キー 3 件 (`mem_*`) のみ差がある。

### 2-7. IR 指紋と wasm_size の run 間変動 (review m-a)

`results/ir_sha256.txt` の `after_m11_build` (m11_build 後の IR の sha256 の先頭 8 桁):

| 測定 | boot_final.ll | boot_final3.ll | `baseline_boot` の wasm_size |
|---|---|---|---|
| `f46330b13` (PR 前の results) | `39373add…` | `61b3a477…` | 6917638 |
| `7f54678a7` (B1 修正前) | `42b63536…` | `45dc73b2…` | 6917845 |
| `33585cb01` (本 HEAD・§2-0) | `42b63536…` | `45dc73b2…` | 6917845 |
| 検収側の再現 (同 commit・別 run・review コメント) | `4cd3e6cc…` | `d4c36a2e…` | (未報告) |

素材そのままの IR (`material` 行) の指紋は全測定で同じ。同じ commit `33585cb01` の 2 回 (本 HEAD と検収側) で指紋が変わるため、IR の生成結果は run ごとに変わる。**原因 (環境差か非決定性か) は未切り分け**。生成された IR に作業ツリーの絶対パス (`ws-…`・`/home/runner`) は含まれていない (grep 0 件)。isolated S1 は 3 回 (`7f54678a7`・`33585cb01`・検収側) とも `764/1/46/131/0` で、指紋の変動は S1 に効いていない。

## 3. 変更点

| ファイル | 変更 |
|---|---|
| `tools/gui/flengine/run.mjs` | `GF_SURVEY_RESET=1`: 各 unit の前に、前 unit の到達を errs へ退避し、線形メモリを boot 直後の内容へ戻す。boot 後に伸びた領域はゼロ埋め (B1)。伸長 unit 数 `mem_grown_units` と `mem_boot_bytes` / `mem_end_bytes` を survey に出す (B1)。`GF_SURVEY_ONLY=<unit,...>` (単独再測用) |
| `tools/gui/flengine/e2e.sh` | survey 全実行に `GF_SURVEY_RESET=1` を適用。base の unit 別出力 `baseline_units.json`。R2 用の chain 実行 `survey_soft_chain.json`。unit 別出力 2 件を `results/` へ保存 (B2)。存在チェックに `survey_soft_chain` と unit 別出力 2 件を追加 (m4・B2)。ネガコン N10 (soft の 1 unit を ok→trap に壊し S3 が FAIL すること) を追加 (B2) |
| `tools/gui/flengine/judge.py` | S3 (unit 単位の base/soft 突き合わせ・942 件・差 0 を要求) を追加 (B2)。`--base-units` / `--soft-units`。R2 の到達は chain 実行から読む (floor 19 は不変)。S1 の判定式は変更なし |
| `tools/gui/flengine/results/` | 本 HEAD の e2e の出力 (§2-0)。`baseline_units.json`・`survey_soft_units.json` を追加し、`mem_*` の 3 キーを survey に加えた。`survey_soft_chain.json` は `7f54678a7` で追加 |
| `tools/gui/flengine/REPORT_APPENDIX.md` | §6i の 1 文に「#1442 時点の記述」と明記 (m1) |
| `docs/DOC_MAP.md` | 本付録の行数を実数に合わせ、測定の参照先を §2-0 にした (m3) |

`tools/gui/gen_api.py` (1 行・`7f54678a7`): IMPORTS の「実到達」列の survey 入力を `survey_soft.json` (隔離版) から `survey_soft_chain.json` (chain 実行) に変えた。隔離版の到達は 12 種で、列の意味 (従来の chain 値) を保つため。`e2e.sh` が実行する `gen_api.py` の出力 (IMPORTS.md) は、この測定で変わらなかった (git status に差分なし)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **PM agent の判断待ち**: S1 を隔離条件のまま既定にしてよいか。既定案: 現行 (S1 は隔離、R2 は chain 実行) | S1 は GUI API の到達 12/33 しか通らない条件で判定される (§1) | PM agent の判断 (本 PR の未解決表) |
| **PM 判断**: 受入条件 3 は本 HEAD の e2e で PASS (§2-0)。`Closes #1635` へ戻すかどうか | 戻すまでは issue #1635 が open のまま残る | PM agent の判断 |
| `tools/startup/boot_metric.py` の `m11-gui-survey` 記録は `GUI_SURVEY` = `results/survey_soft.json` を出典にする。本 PR で同ファイルは隔離版 (`ok/trap` 873/21 → 764/131・到達 33 → 12) に変わる。generator は `tools/m11/REPORT.md` の `de50ffa` 行が無いため停止する (origin/main でも同じ・既存の不具合) | `boot_metric.json` の該当 record は本 PR の後も旧値のまま。generator を直すまで再生成できない。出典を `survey_soft_chain.json` に向けるかは PM の判断 | PM agent の判断 + generator の修復。追跡のみの子は規約 (AGENTS §1 の規範 11) により本 PR では起票しない。PM が整理時に起票 |
| `tools/m11/work/` (work-m11) は `docs/WORKFLOW.md` §11 で「survey の基準には使わない」(#680)。本 e2e の IR 素材もこれに当たる | 本 e2e の前提 (既存の e2e と同じ素材)。素材の扱いの判断が要る | PM agent の判断 |
| IR 指紋の run 間変動 (§2-7) の原因 (環境差か非決定性か) | 指紋を素材の provenance に使えない。S1・S3 には効いていない | 追跡のみ (未起票)。PM が要否を判断 |
| `e2e.sh` 24 行目のコメントの「全メモリ状態」は範囲の記述として古い (実態は wasm 線形メモリ・§1)。コメントだけの修正は、測定後のコード差分になるため本 round では行わない | 挙動には影響しない | 次の修正 commit (コメントのみ) |
| 304/555 の真因 (どの前 unit のどの状態が base の abort を作るか) | 順序依存の原因。隔離版の判定には影響しない | #1426 (`[M11-N91]`・304/555/923 の OOB 実値採取) |
| base と soft の前 unit の振る舞いの違いが shim の有無によるか (推定・未測定) | 結論に含めていない | #1426 (同上) |
| reset の範囲は wasm 線形メモリだけ。JS 側の状態は対象外 | JS 側の状態が前 unit の結果に効いていれば、隔離は完全ではない | #1426 (隔離の範囲を同じ調査で扱う) |
| `tools/m11/m11_survey.mjs` (m11 側の survey) は従来の chained protocol のまま | m11 の baseline 数値は従来どおり (本 PR は `tools/gui/flengine` 側の判定のみ) | m11 survey 隔離の件 (REPORT.md §7 の「survey の順序依存」と同件) |
