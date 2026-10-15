# REPORT_APPENDIX_1635 (GUI-22 #1635)

#1442 (GUI-21) の S1 (soft) FAIL の切り分け。`REPORT.md` / `REPORT_APPENDIX.md` §6i の 101/291/296 の記録は、現 IR では再現しなかった。差分 unit は **304 と 555** (順序依存と確認)。

測定の状態: **§2 の実測値はすべて測定 commit `7f54678a7` (B1 修正前のコード) の値**。`7f54678a7` 以降の変更 (B1: 線形メモリの伸長領域のゼロ埋め・伸長 unit 数の出力 / B2: unit 別出力の保存と judge の S3 / m4) は **未測定**。この変更を入れた HEAD の e2e は、素材 (emcc・retdec・mingw・`tools/m11/work/`) が無かったため実行していない。本付録の S1・S3 は、この HEAD では値を持たない。`results/` は `7f54678a7` の値のまま (再測定で書き直す)。

## 1. 結論

| 項目 | 結果 |
|---|---|
| 原因 (304/555) | **測定済み**: survey は unit を chained に流し、正常終了した unit の後で線形メモリを戻さない。単独実行 (§2-3) では base と soft がともに `halt0->longjmp` で一致し、chain 実行でだけ差が出る (順序依存)。**未解明**: どの前 unit のどの状態が base の abort を作るか (#1426)。base と soft の前 unit の振る舞いが違う理由が shim の有無かどうか: **推定で、未測定** |
| 101/291/296 | 現 IR では base/soft とも同じ結果 (§2-2 の unit 別比較で差は 304/555 の 2 件のみ)。差は無い |
| 隔離条件の統一 | `GF_SURVEY_RESET=1` を base / ff / soft の全 survey に適用。各 unit の開始時に wasm 線形メモリを boot 直後の内容へ戻す。boot 後に伸びた領域 (`ALLOW_MEMORY_GROWTH=1`) はゼロ埋めする (B1 修正・**未測定**)。**範囲は wasm 線形メモリだけ**。JS 側の状態 (`errs` の蓄積・`perUnit`・`kinds` などの JS 変数) と wasm 外の状態は reset の対象外 |
| 判定式 | S1 (totals の一致) は変更なし。S3 (unit 単位の base/soft 一致) を追加 (B2 対応・**未測定**)。R2 の floor 19 は不変 |
| S1 の判定条件 (範囲) | 隔離版の到達は **12 種** (trap 131)。chain の soft は **33 種** (trap 21)。S1 は GUI API の 12/33 しか通らない条件で判定される。既定にしてよいかは **PM agent の判断待ち** (§4) |
| R2 (到達 floor) | 入力は chain 実行 `survey_soft_chain.json` (873/21・到達 33 種)。pre-PR の `survey_soft.json` (`git show f46330b13:tools/gui/flengine/results/survey_soft.json`) と、survey 全体・reach 名の集合・`reach_summary` が一致する。R2 の意味は変わっていない |

## 2. 実測 (測定 commit `7f54678a7`・B1 修正前)

### 2-1. e2e (`7f54678a7`・foreground・1 回)

| rc | 所要 (done 行) | load (開始 → 終了) | judge | S1 | R2 | native selftest | ネガコン |
|---|---|---|---|---|---|---|---|
| **0** | 504 s | 0.41 → 1.06 | **14/14 PASS** | soft `764/1/46/131/0` = base `764/1/46/131/0` | reached 33 ≥ 19 (`missing=[]`) | 512 passed / 0 failed | N1〜N9 期待どおり FAIL (9/9) |

他の gate: L1 (ff・soft とも `0/0/0`)・A1 (193/193/173/20)・B1 (units_run 109 = base 109)・R1 (`LoadStringW` ×3 IMPL)・S2 (ff/soft の fail-fast 無し)・P1〜P5・W1 (WNDCLASS 11 / fn WNDPROC 8) すべて PASS。`__pe_image` parity・pe_image e2e PASS。

### 2-2. 修正前 (chain・基点 `f46330b13` の `tools/gui` に、base の unit 別出力だけを追加した版)

| 実行 | 結果 |
|---|---|
| e2e (chain) | rc 1 / 489 s / judge 13/14 (S1 のみ FAIL)。S1 soft `873/1/47/21/0` vs base `871/1/47/23/0` |
| 差分 unit (survey 配列の突き合わせ・942 件) | **304 と 555 の 2 件のみ**。base `Aborted(native code called abort())` → soft `ok`。101/291/296 は差なし |

この unit 別の出力 (`baseline_units.json` / `survey_soft_units.json`) は当時 `$W/res` にだけ残り、repo には入らなかった。本 HEAD から `results/` へ保存する (B2)。

### 2-3. 単独実行 (boot 直後に当該 unit だけ実行。`GF_SURVEY_ONLY`)

| unit | base | soft |
|---|---|---|
| 304 | `halt0->longjmp` | `halt0->longjmp` |
| 555 | `halt0->longjmp` | `halt0->longjmp` |
| 101 | `halt0->longjmp` | `halt0->longjmp` |
| 291 | `halt0->longjmp` | `halt0->longjmp` |
| 296 | `halt0->longjmp` | `halt0->longjmp` |

単独では base と soft が一致する。chain の 304/555 の差は前 unit の状態による (順序依存)。**どの前 unit のどの状態が効くかは未解明** (#1426)。「base と soft は前 unit の振る舞いが違う (shim の有無による)」は測定していない推定であり、結論には含めない。

### 2-4. 全メモリ reset 実行 (`GF_SURVEY_RESET=1`・survey 単体・`7f54678a7`)

| 実行 | ok/noproc/miss/trap/clobber | 到達 |
|---|---|---|
| base | `764/1/46/131/0` | — |
| soft | `764/1/46/131/0` | 12 種 (名前の集合) |
| soft (chain・`GF_SURVEY_RESET=0`) | `873/1/47/21/0` | 33 種 |

reset で ok が 871 → 764 に下がる。多くの unit が前 unit の初期化結果を前提にしているため、chain の値は「隔離された個別結果」ではない。判定の基準を chain から reset に移すのは、base/soft を同じ条件にそろえるための変更であり、判定式は変えていない。

**unit 単位の一致 (旧記述の訂正)**: 旧版は「base 942 unit 全件一致」と書いたが、その根拠になる unit 別出力は repo に無く、検証できない (review B2)。合計 (`ok/noproc/miss/trap/clobber`) の一致は unit 単位の一致を示さない。本 HEAD で `e2e.sh` が `baseline_units.json` と `survey_soft_units.json` を `results/` へ保存し、judge の **S3** が unit 単位で突き合わせる。unit 差の件数は、本 HEAD の測定で記録する (**未測定**)。再現: `bash tools/gui/flengine/e2e.sh` (素材が必要)。

### 2-5. 本 HEAD で追加した出力 (B1・未測定)

`survey` オブジェクトに次を出す: `mem_boot_bytes` (boot 直後の線形メモリの長さ)・`mem_end_bytes` (最後の unit の後)・`mem_grown_units` (実行の前後で線形メモリの長さが増えた unit 数)。`survey_ff.json` / `survey_soft.json` に入る。値は本 HEAD の測定で記録する (**未測定**)。

### 2-6. reset 後の集計値の意味 (review m2)

`GF_SURVEY_RESET=1` のとき、次の値は **最後の unit の値** であり、全 unit の集計ではない (wasm 内カウンタは unit ごとに戻るため): `survey_ff.json` / `survey_soft.json` の `reach_summary` (`reached=1`)・`gui_icall_calls`・`probes`・`va_calls`・`init_count`。judge はこれらを参照しない。`reach` (errs 由来) は各 unit 開始時の dump の連結で、名前の集合は 12 種。judge の INFO 行 (natural reach) は isolated survey の `reach` を使うため 12 種の集計になる。到達の全体 (33 種) は `survey_soft_chain.json` を見る。

## 3. 変更点

| ファイル | 変更 |
|---|---|
| `tools/gui/flengine/run.mjs` | `GF_SURVEY_RESET=1`: 各 unit の前に、前 unit の到達を errs へ退避し、線形メモリを boot 直後の内容へ戻す。boot 後に伸びた領域はゼロ埋め (B1)。伸長 unit 数 `mem_grown_units` と `mem_boot_bytes` / `mem_end_bytes` を survey に出す (B1)。`GF_SURVEY_ONLY=<unit,...>` (単独再測用) |
| `tools/gui/flengine/e2e.sh` | survey 全実行に `GF_SURVEY_RESET=1` を適用。base の unit 別出力 `baseline_units.json`。R2 用の chain 実行 `survey_soft_chain.json`。unit 別出力 2 件を `results/` へ保存 (B2)。存在チェックに `survey_soft_chain` と unit 別出力 2 件を追加 (m4・B2)。ネガコン N10 (soft の 1 unit を ok→trap に壊し S3 が FAIL すること) を追加 (B2) |
| `tools/gui/flengine/judge.py` | S3 (unit 単位の base/soft 突き合わせ・942 件・差 0 を要求) を追加 (B2)。`--base-units` / `--soft-units`。R2 の到達は chain 実行から読む (floor 19 は不変)。S1 の判定式は変更なし |
| `tools/gui/gen_api.py` | IMPORTS の「実到達」列は chain 実行の値で生成 (従来の chain 値と同じ意味を保つ) |
| `tools/gui/flengine/results/` | `7f54678a7` の e2e が生成した値 (`survey_soft_chain.json` は新規)。本 HEAD の再測定まで書き直さない |
| `tools/gui/flengine/REPORT_APPENDIX.md` | §6i の 1 文に「#1442 時点の記述」と明記 (m1) |
| `docs/DOC_MAP.md` | 本付録の行数を実数に合わせた (m3) |

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **PM agent の判断待ち**: S1 を隔離条件のまま既定にしてよいか。既定案: 現行 (S1 は隔離、R2 は chain 実行) | S1 は GUI API の到達 12/33 しか通らない条件で判定される | PM agent の判断 (本 PR の未解決表) |
| 本 HEAD (B1・B2・m4 の修正後) の e2e 再測定。`results/`・§2-4・§2-5 の書き直し | 本 HEAD の S1・S3・`mem_grown_units` は未測定。S3 は初回実行で FAIL する可能性がある | 本 PR の次の review run (`oc_artifacts` を本文に追加済み。素材が取得されない場合は次の run で再依頼) |
| chain で 304/555 の結果を変える前 unit の特定。base の abort を作る状態 | 順序依存の原因。隔離版の判定には影響しない | #1426 (`[M11-N91]`・304/555/923 の OOB 実値採取) |
| base と soft の前 unit の振る舞いの違いが shim の有無によるか (推定・未測定) | 結論に含めていない | #1426 (同上) |
| reset の範囲は wasm 線形メモリだけ。JS 側の状態は対象外 | JS 側の状態が前 unit の結果に効いていれば、隔離は完全ではない | #1426 (隔離の範囲を同じ調査で扱う) |
| `tools/m11/m11_survey.mjs` (m11 側の survey) は従来の chained protocol のまま | m11 の baseline 数値は従来どおり (本 PR は `tools/gui/flengine` 側の判定のみ) | m11 survey 隔離の件 (REPORT.md §7 の「survey の順序依存」と同件) |
