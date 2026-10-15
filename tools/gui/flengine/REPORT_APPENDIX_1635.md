# REPORT_APPENDIX_1635 (GUI-22 #1635)

#1442 (GUI-21) の S1 (soft) FAIL の切り分け。`REPORT.md` / `REPORT_APPENDIX.md` §6i の 101/291/296 の記録は、現 IR では再現しなかった。差分 unit は **304 と 555** (順序依存と確認)。

測定 commit: **`7f54678a7`** (コード変更の最後の commit。`run.mjs` / `e2e.sh` / `judge.py` / `gen_api.py` と再生成された `results/`)。以降の commit は文書のみ。

## 1. 結論

| 項目 | 結果 |
|---|---|
| 原因 (304/555) | survey は unit を chained に流し、正常終了した unit の後で image を戻さない。前 unit の副作用で結果が変わる。base と soft は前 unit の振る舞いが違うため (shim の有無)、同じ unit の結果が入れ替わる |
| 101/291/296 | 現 IR では base と soft で同一 (chain・reset・単独の全条件で `halt0->longjmp` の両側 trap)。差は無い |
| 隔離条件の統一 | `GF_SURVEY_RESET=1` を base / ff / soft の全 survey に適用。各 unit を boot 直後の全メモリ状態から始める |
| 判定式 | 変更なし (S1 は `ok/noproc/miss/trap/clobber` の一致。R2 の floor 19 も不変) |
| R2 (到達 floor) | 隔離版では到達が 12 件 (< 19) に減る。到達は従来の chain 実行 `survey_soft_chain.json` で見る (33 件・missing 0) |

## 2. 実測

### 2-1. e2e (測定 commit `7f54678a7`・foreground・1 回)

| rc | 所要 (done 行) | load (開始 → 終了) | judge | S1 | R2 | native selftest | ネガコン |
|---|---|---|---|---|---|---|---|
| **0** | 504 s | 0.41 → 1.06 | **14/14 PASS** | soft `764/1/46/131/0` = base `764/1/46/131/0` | reached 33 ≥ 19 (`missing=[]`) | 512 passed / 0 failed | N1〜N9 期待どおり FAIL (9/9) |

他の gate: L1 (ff・soft とも `0/0/0`)・A1 (193/193/173/20)・B1 (units_run 109 = base 109)・R1 (`LoadStringW` ×3 IMPL)・S2 (ff/soft の fail-fast 無し)・P1〜P5・W1 (WNDCLASS 11 / fn WNDPROC 8) すべて PASS。`__pe_image` parity・pe_image e2e PASS。

### 2-2. 修正前 (chain・基点 `f46330b13` の `tools/gui` に、base の unit 別出力だけを追加した版)

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

単独では base と soft が一致する。chain の 304/555 の差は前 unit の状態による (順序依存)。

### 2-4. 全メモリ reset 実行 (`GF_SURVEY_RESET=1`・survey 単体)

| 実行 | ok/noproc/miss/trap/clobber | unit 別の差 |
|---|---|---|
| base | `764/1/46/131/0` | **0 件** (942 unit 全件一致) |
| soft | `764/1/46/131/0` | |
| soft の到達 (unit 別 dump を合算) | 12 件 (名前の集合) | chain は 33 件 |

reset で ok が 871 → 764 に下がる。多くの unit が前 unit の初期化結果を前提にしているため、chain の値は「隔離された個別結果」ではない。判定の基準を chain から reset に移すのは、base/soft を同じ条件にそろえるための変更であり、判定式は変えていない。

## 3. 変更点

| ファイル | 変更 |
|---|---|
| `tools/gui/flengine/run.mjs` | `GF_SURVEY_RESET=1` (各 unit の前に boot 直後の全メモリを戻す。戻す前に `gui_reach_dump` で到達を退避)。`GF_SURVEY_ONLY=<unit,...>` (単独再測用) |
| `tools/gui/flengine/e2e.sh` | `export GF_SURVEY_RESET=1` (survey の全実行)。base の unit 別出力 `baseline_units.json` を取る。chain の `survey_soft_chain.json` を追加 (R2 用) |
| `tools/gui/flengine/judge.py` | R2 の到達を `--survey-soft-chain` (既定 `survey_soft_chain.json`) から読む。判定式は変えていない |
| `tools/gui/gen_api.py` | IMPORTS の「実到達」列の参照を `survey_soft_chain.json` に変更 (従来の chain 値と同じ意味を保つ) |
| `tools/gui/flengine/results/` | e2e が再生成した値 (`survey_soft_chain.json` は新規) |

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chain で 304/555 の結果を変える前 unit の特定 (どの状態が base の abort を作るか) | survey の chain 値 (旧 S1 の基準) の意味。隔離版では影響しない | #1426 (`[M11-N91]`・304/555/923 の OOB 実値採取) |
| `tools/m11/m11_survey.mjs` (m11 側の survey) は chained のまま | m11 の baseline 数値は従来の protocol で取られる (本 PR は gui/flengine 側のみ) | m11 survey 隔離の件 (REPORT.md §7 の「survey の順序依存」と同件) |
| 隔離版の到達が 12 件 (chain 33 件) | R2 の意味は chain 実行に依存する | 本 PR の範囲 (R2 は chain で判定) |
