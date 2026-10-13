# tools/python REPORT 付録: Chrome 上の pyscript 実行検証 (#466)

> 正本: `tools/python/REPORT.md` §14。本書は行数上限 (250 行、`docs/DOC_MAP.md` §1) のため、PR #619 で追加した §14b (Chrome 検証) の全文を分割移動した。

## 14b. Chrome (agent-browser) 上の pyscript 実行検証 — #466 (PY-11)

既知類型との関係 (DEFECTS.md / icall §4): 該当なし (lift ではなく wasm CPython のホスト検証)。

結論: **同梱 Piano roll scripts 5/5 は Chrome 154 (headless, agent-browser 0.39.0) 上の wasm CPython で実行でき、node (v22.23.3) と出力が全件一致した**。不一致 0 件のため原因調査対象なし。

| 項目 | 内容 |
|---|---|
| 方式 | シナリオ本体を `tests/pyscript_scenarios.mjs` に分離 (node 版 `pyscript_e2e.mjs` と Chrome 版 `browser/pyscript.html` が**同一コード**を実行 = harness の差を排除)。Chrome は `tests/pyscript_browser.mjs` が `tools/e2e` の agent-browser ドライバで起動・結果回収 (module Worker + SAB RPC、`crossOriginIsolated=true` を判定に含む) |
| スクリプト供給 | `node tests/pyscript_e2e.mjs --export-scripts work/pyscripts.json` で FL 同梱本文を `work/` (gitignore) に出力し、ページが実行時 fetch。FL 由来物は commit しない |
| 判定 | (1) 43 check が両環境で名前・ok とも一致し全 PASS、(2) `run_pyscript` 出力 19 件 (`{name, values, score, result}`) がキー順非依存の正規化 JSON で全件 bit 一致、(3) Chrome の Euclidean 2 出力を **python (`tests/pyscript_compare.py`、JS oracle とは別実装の整数算術)** で再計算し一致、(4) 実行された Piano roll script が 5 本であること |
| 再現 | `FL_WIN64_DIR=<fl-win64> bash tools/python/run_all.sh` の step 9d、または上記 3 コマンド: `node tests/pyscript_e2e.mjs --dump work/pyscript_node.json --export-scripts work/pyscripts.json` → `node tests/pyscript_browser.mjs --dump work/pyscript_chrome.json` → `python3 tests/pyscript_compare.py work/pyscript_node.json work/pyscript_chrome.json` |

実測 (コミット c61317a の内容、Actions runner 4 core、Chrome 154.0.0.0 headless、node v22.23.3、`dist/flpy.*` は本 run でクリーンビルド、n=3、直列):

| 回 | load average (1 分, 開始時) | node 43 check | Chrome 43 check (スクリプト内 / wall) | compare |
|---|---|---|---|---|
| 1 | 1.96 | 43 PASS / 0 FAIL, 1 s | 43 PASS / 0 FAIL, 1.1 s / 2.0 s | outputs 19 件中不一致 0 |
| 2 | 2.04 | 43 PASS / 0 FAIL, 1 s | 43 PASS / 0 FAIL, 1.1 s / 2.0 s | 同上 |
| 3 | 2.04 | 43 PASS / 0 FAIL, 1 s | 43 PASS / 0 FAIL, 1.1 s / 2.0 s | 同上 |

マージ後 HEAD (`cf0547f` = origin/main `e64ef6f` 取り込み後、`build_flpy.sh` 再リンク済み) でも step 9d を n=3 再実行: 3/3 とも node 43/43・Chrome 43/43・compare 不一致 0 (load average 1.04 / 1.44 / 1.44)。

再検証 (#619 レビュー対応): origin/main `f9adacd` 取り込み後の HEAD `3522e52` (コード差分なし = 競合解消 + REPORT 分割) をクリーンな worktree でビルドし直して実行 (Actions runner 4 core、node v22.23.3、Chrome 154.0.0.0 headless、agent-browser 0.39.0)。`build_cpython_wasm.sh` 202 s、`build_flpy.sh` 6 s。step 9d の 3 コマンドを n=3 直列:

| 回 | load average (1 分, 開始時) | node | Chrome (スクリプト内) | compare | 3 コマンド合計 wall |
|---|---|---|---|---|---|
| 1 | 2.79 | 43/43 PASS, exit 0 | 43/43 PASS, 0.9 s, exit 0 | outputs 19 件中不一致 0, exit 0 | 15.7 s (初回: agent-browser 初回起動を含む) |
| 2 | 2.78 | 同上 | 同上 | 同上 | 2.7 s |
| 3 | 2.80 | 同上 | 同上 | 同上 | 2.7 s |

`pyscript_compare.py --neg` は `outputs 不一致 1/19` + `Euclidean 再計算不一致` を検出して exit 1。検証コミットは `3522e52` のみ (上の c61317a / cf0547f は各時点の記録)。

(別途の先行 3 回: Chrome スクリプト内 1.1〜1.2 s / wall 1.9〜2.1 s。node のスクリプト内秒は整数丸め (`toFixed(1)` の 0.9〜1.0)。)
node 版は分離リファクタ後も 43/43 PASS (リファクタ前 #79 の check 数と同数)。

ネガティブコントロール (全て実測):

| NEG | 操作 | 結果 |
|---|---|---|
| 比較側 | Chrome 出力 1 ノートの `time` を +1 して `pyscript_compare.py --neg` | `outputs 不一致 1/19` + `Euclidean 再計算不一致` を検出し exit 1 (run_all.sh は exit 0 を異常扱い) |
| Chrome 実行側 | `work/pyscripts_mut.json` で Euclidean 本文を 1 箇所改変 (`current := int(i * slope + 0.5)`) して `pyscript_browser.mjs --scripts` | Chrome 上で `Euclidean default 41 vs 39`・`custom 46 vs 45` の 2 check が FAIL、total 43 / pass 41 / fail 2、exit 1 |
| 既存 | シナリオ内 NEG-a/b/c (Euclidean 改変・getNote clone・typo 値 KeyError) | Chrome でも 3/3 検出 (43 check に含む) |

検証範囲: 同梱 Piano roll 5 本 + Remote 5 本の flapi 列 + Audio 12 本の調査を、モック engine で Chrome headless 1 環境・agent-browser 経由で実行。範囲外: 実機 FL との一致、Firefox/Safari、headful Chrome、実 FLEngine(wasm) 結合 (本検証は mock engine)、`run_all.sh` 全体の再実行 (step 9d のみ実行)。
注意: `build_flpy.sh` は mac dylib / win PE の無い runner で追跡中の `analysis/flapi/{FLAPI.md,flapi_table.json}` を書き換える (既知)。本 PR には含めていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Firefox / Safari での pyscript 実行 | Chrome 以外は未検証 | #165 (PERF-P7 ブラウザ行列) にコメント |
| mock engine ではなく実 FLEngine(wasm) 結合時の再検証 | 出力一致は mock 上の結論 | #112 / T3 以降 |
