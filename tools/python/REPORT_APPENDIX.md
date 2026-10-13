# tools/python REPORT 付録 (REPORT.md から分割移動)

> **正本**: `tools/python/REPORT.md`。本書は行数上限 (250 行、`docs/DOC_MAP.md` §1) 超過分の**分割移動**で、内容は削除していない。

## A. §7b-2 (PY-1 レビュー指摘の修正: `ilmcp.getBrowserNames` の固定バッファ) — 全文

### 7b-2. レビュー指摘 (d2706e1) の修正: `ilmcp.getBrowserNames` の固定バッファ

原因: `b[2048]` へ `w += snprintf(w, 残量, ...)` で連結していたため、切り詰められた出力でも snprintf の戻り値 (= 切り詰めなければ書いた長さ) が `w` に加わり、`w` が `b + sizeof b` を越えると次の `(size_t)(b + sizeof b - w)` が巨大な値になって境界なしに書いた。`q[512]` / `full[288]` / `e[576]` と `json_str` も黙って切り詰めていた。修正 (`provider/fl_engine.c`): `json_str` と `buf_add` が残量 (`size_t`) を持ち、`n >= remaining` なら何も書かず失敗 → ハンドラは `Range error` (code 4) を返す。`full` も `snprintf` の戻り値 `>= sizeof full` で失敗にする。

| 項目 | 実測 (HEAD b2225e1, GitHub Actions runner, node 22.23.3, emsdk 6.0.12, load average 0.53〜1.84) |
|---|---|
| 回帰ケース | `tests/provider_check.mjs` 節 2b: 収まる 7 + 溢れる 5 = **12 ケース**。収まる: `""` / `"db"` / 引用符・バックスラッシュ / 制御文字 4 / 日本語 90 字 (270B) / `a`×273 (full 287B ちょうど) / 制御文字×80 + `a`×17 (b[2048] に 2047B ちょうど)。溢れる: `a`×274 (full 288B) / 制御文字×80 + `a`×18 (q・full・e は収まり b だけ溢れる、2051B) / 制御文字×85 (q) / 制御文字×100 (reviewer 再現) / `a`×100000。溢れた後に `getBrowserNames("db")` が正常応答することも各ケースで確認。b の長さ = 59 + 4X (X = エスケープ後の名前長) |
| 旧コード (d2706e1) × 新テスト | **FAIL**: 溢れる 5 ケース中 5 つ。`a`×274 と `a`×100000 は黙って切り詰めた ok (`…/Fruity Slice`)、他 3 つは不正 JSON (`position 2047` の SyntaxError / `Unexpected end of JSON input`)。収まる 7 ケースは旧コードでも一致 (= 正常系の挙動は不変) |
| 修正後 × 新テスト | **PASS**: `provider_check` 0.31 / 0.29 / 0.28 秒 (3 回)。節 1〜3 全体 (Python 側の型・例外写像を含む) |
| メモリ安全 (ASan) | `emcc -fsanitize=address` で旧・新を同テスト (節 1〜2b) 実行: 旧 = **`stack-buffer-overflow` WRITE of size 1**、新 = 検出 0 件で PASS |
| 回帰なし | `FL_ENGINE=wasm node tests/all_tools.mjs` **48/48 ok**、soft_error 0・raised 0、host_calls 37,424、callback 往復 true、1.59 / 1.61 / 1.61 秒 (3 回)。`tool_coverage.wasm.json` と追跡中の `tool_coverage.json` の tool 別差 **0/48**。`poc_mcp` (mock) POC OK 1.06 秒 |
| ネガティブコントロール | `full` の判定 `>=` → `>` : 溢れる `a`×274 で FAIL。`buf_add` が溢れても 0 を返す: `98 文字` で FAIL (`",]}"` の不正 JSON)。生き残り 2 件 (等価変異): q の `json_str` 失敗を無視 / `json_str` の残量判定を 2B 緩める — q・e の境界は API 経由では b[2048] (4X) が先に律速して到達できないため (いずれも b が先に失敗するので出力は同じ)。これらの個別境界は `json_str` 単体の C テスト無しでは検出できない |

検証範囲: 上記は mac pkg 無しで `fetch_inputs.sh` の win64 DATA block 経路から配置した MCPTools.pyc / midi.py / utils.py で実行した (b76d221 時点の自己申告値 host_calls 37,424・48/48 と同値)。範囲外: `run_all.sh` 全体・headless Chrome (`browser_check`) は未実施。

## B. §12 / §12b (Piano roll scripting #79 / Chrome 検証 #466) — 全文

## 12. Piano roll scripting (`flpianoroll` + `.pyscript` ローダ) — #79 (PY-5)

既知類型との関係 (DEFECTS.md): 該当なし (lift ではなく純 Python 実装)。検証起点 commit: `57326b1` (クリーン worktree で再現)。

**結論**: 同梱 Piano roll scripts **5/5** が wasm CPython 上で実行でき、**43 検査 (うちネガティブコントロール 3) 全 PASS** で回帰テスト化。Remote Scripts 5 本は flapi のみで動作 (5/5)。Audio scripts 12 本は `enveditor` 依存のため flapi のみでは **0/12** (Edison 用 `enveditor` 実装が別途必要)。

| 項目 | 実装 |
|---|---|
| `flpianoroll` | `src/flpianoroll.py`。Note / Marker / Score(`score`) / TUtils(`Utils`) / ScriptDialog。score はホスト JSON と `load`/`dump` で同期。`getNote` は live 参照 (Humanize が in-place 更新するため) |
| ローダ | `fl_rt.load_pyscript(path, name)` (専用 module namespace で exec) / `fl_rt.run_pyscript(name, score, values)` (score 注入 → `createDialog()` → 値注入 → `apply(form)` → `{dialog, score, utils, warnings}`)。`call_json` 経由で呼べる |
| HUD 連携 (#10) の境界 | `ScriptDialog.describe()` がコントロール記述 (type/min/max/items/既定値) を返し、`set_values()` で値を注入。GUI 自体は #10 側 (本 PR 範囲外) |
| Remote Scripts | `channels` 等の flapi module を script グローバルに注入 (import 無しで参照するため) |

**素材**: 同梱スクリプトは `FL_WIN64_DIR/extracted/block*_DATA.bin` から**実行時に**読む (非同梱)。ブロック名は元ファイル名を持たないため、ScriptDialog の題名/関数名で特定 (各 1 件一致を要求)。

### 回帰検査の中身 (`tests/pyscript_e2e.mjs`、全て JS 側の独立 oracle と照合)

| script | oracle |
|---|---|
| Euclidean | 整数算術 `floor(i*o/p)` の遷移 + 循環シフト。既定 + 独自設定の 2 構成 |
| Selector | JS 再実装の判定式。3 構成 × 40 ノートの `selected` 全件一致 (非自明: 選択 20 / 2 / 38) |
| Repeater | 件数・時刻・長さ・色・velocity の閉形式 (既定 6→24、Repeats=2 で 18) |
| Humanize | range=0 で恒等 / offset の厳密値 / 同 seed 決定論 / 別 seed で変化 / ジッタ境界 |
| Arpeggiator | 3 和音 → Increasing `60,64,67,60`、Decreasing `60,67,64,60` を手導出、Prob=0 で全消去 |
| Remote 5 本 | `fl_mock` の呼出し記録で flapi 列を照合 (filleach / reroll×3)、flrInit の 5 関数 |

### 実測 (コミット済み `57326b1`、クリーン worktree、node v22.23.3、4 core、load average 0.80 / 0.83 / 0.69、n=3)

| 項目 | 値 |
|---|---|
| `pyscript_e2e.mjs` 所要 (wall) | 0.98–1.00 秒 (3 回、43/43 PASS) |
| `build_cpython_wasm.sh` 初回 (native + wasm) | 本 run では計時していない (§1 の 3m19s は wasm 側の既存実測。本 run の値ではない) |
| `build_flpy.sh` 再リンク | 6.4 秒 (1 回) |
| 回帰 (既存 PoC) | `smoke_direct` OK / `poc_mcp` POC OK / `all_tools` 48/48 ok・37,424 呼出し (§5 と同値) |

ネガティブコントロール (数値): (a) Euclidean の `int(i*slope)` を `int(i*slope+0.5)` に改変 → oracle 不一致を検出 (改変版のノート集合が oracle と異なる)。(b) `Score.getNote` を clone 返却に差替え → Humanize の offset が反映されず検出。(c) 存在しないコントロール名 → `KeyError` で検出。3/3 が期待通り FAIL 側に倒れた。

### Remote Scripts 5 本 / Audio scripts 12 本 の調査結果

| 群 | 本数 | flapi のみで動作 | 根拠 |
|---|---|---|---|
| Piano roll scripts | 5 | **5/5** | 上記回帰 |
| Remote Scripts | 5 | **5/5** | `filleach` `rerollLSloop/Sample/Steps` `flrInit` (channels API のみ、モックで列照合) |
| Audio scripts | 12 | **0/12** | 全て `from enveditor import *` (`EditorSample` / `Editor` / `Utils` を使用)。`enveditor` は flapi 435 関数に含まれない別 module。静的に使用メンバを集計: `EditorSample` 系 (`SetSampleAt` `GetSampleAt` `SineFromTo` `AmpFromTo` `SilenceFromTo` `PasteFromTo` `GetRegion` `RegionCount` `Length` `SampleRate` `NumChans` `MSToSamples` `NormalizeFormat`) と `Editor.SelectionStartS/EndS` |

### 検証範囲 / 範囲外

- 範囲: 同梱 5+5 本の wasm 上の動作・上記 oracle との一致。モック engine (実 FLEngine ではない)。
- 範囲外: **実機 FL の出力との一致** (未確認。下記 ASSUMPTION)、HUD の実フォーム UI (#10)、`loadScoreFromFile`、`flcpt`/`flrack`/`enveditor` (T7)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `Note` の既定値のうち number=60 / length=PPQ は docs に記載なく推定 | 新規 Note の既定が実機と違う可能性 | #79 コメント (実機確認待ち) |
| `clearNotes(False)` は selected のみ消す (docs の文言通り)。選択ゼロ時に実機が全消去するかは未確認 | Arpeggiator の「全選択無し」挙動 | #79 コメント |
| ScriptDialog の範囲外値を clamp しない (警告のみ)。実機の clamp 有無は未確認 | 範囲外入力時の結果 | #79 コメント |
| Remote Scripts が `channels` を import 無しで参照 → 実機が同名を注入していると推定 | ローダの注入名 (flapi 12 module) | #79 コメント |
| `ScriptDialog.Execute()` は headless で常に True | 対話キャンセルの再現不可 | #10 (HUD) |
| Audio scripts 12 本に `enveditor` 実装が必要 (Edison の波形操作 13 メンバ + Editor 選択) | Audio scripts 0/12 | 新規子チケット案 `[PY-6] enveditor module` (T7 を分割) |
| `loadScoreFromFile` 未実装 | .fst/.fsc 読込を使うスクリプト | #79 コメント |
| ~~Chrome 上の pyscript 実行未検証~~ | 下記 §12b で解消 (#466) | — |

### 12b. Chrome (agent-browser) 上の pyscript 実行検証 — #466 (PY-11)

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

(別途の先行 3 回: Chrome スクリプト内 1.1〜1.2 s / wall 1.9〜2.1 s。node のスクリプト内秒は整数丸め (`toFixed(1)` の 0.9〜1.0)。)
node 版は分離リファクタ後も 43/43 PASS (リファクタ前 #79 の check 数と同数)。

ネガティブコントロール (全て実測):

| NEG | 操作 | 結果 |
|---|---|---|
| 比較側 | Chrome 出力 1 ノートの `time` を +1 して `pyscript_compare.py --neg` | `outputs 不一致 1/19` + `Euclidean 再計算不一致` を検出し exit 1 (run_all.sh は exit 0 を異常扱い) |
| Chrome 実行側 | `work/pyscripts_mut.json` で Euclidean 本文を 1 箇所改変 (`current := int(i * slope + 0.5)`) して `pyscript_browser.mjs --scripts` | Chrome 上で `Euclidean default 41 vs 39`・`custom 46 vs 45` の 2 check が FAIL、total 43 / pass 41 / fail 2、exit 1 |
| 既存 | シナリオ内 NEG-a/b/c (Euclidean 改変・getNote clone・typo 値 KeyError) | Chrome でも 3/3 検出 (43 check に含む) |

検証範囲: 同梱 Piano roll 5 本 + Remote 5 本の flapi 列 + Audio 12 本の調査を、モック engine で Chrome headless 1 環境・agent-browser 経由で実行。範囲外: 実機 FL との一致、Firefox/Safari、headful Chrome、実 FLEngine(wasm) 結合 (本検証は mock engine)、`run_all.sh` 全体の再実行 (step 9d のみ実行)。
注意: `build_flpy.sh` は mac dylib / win PE の無い runner で追跡中の `analysis/flapi/{FLAPI.md,flapi_table.json}` を書き換える (既知、#79 REPORT 7b-2 記載)。本 PR には含めていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Firefox / Safari での pyscript 実行 | Chrome 以外は未検証 | #165 (PERF-P7 ブラウザ行列) にコメント |
| mock engine ではなく実 FLEngine(wasm) 結合時の再検証 | 出力一致は mock 上の結論 | #112 / T3 以降 |
