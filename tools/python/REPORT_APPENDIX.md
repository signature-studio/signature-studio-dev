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

## PY-13 (#588): `build_flpy.sh` の flapi_table 再生成を環境変数化

既知類型との関係 (DEFECTS.md): 該当なし (lift ではなくビルド入力の扱い。「入力が無いのに緑」型の gate 欠陥の予防)。

| 入力 | 環境変数 | 既定 (従来どおり) | 欠落時 |
|---|---|---|---|
| win PE | `FL_WIN_PE` または `FL_WIN64_DIR` | `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`tools/shared/env.sh`) | exit 2 (旧: 空 bytes 扱いで `win_pair_verified` 全 false の表を出力) |
| stubs clone | `FL_STUBS_DIR` | `tools/python/work/fl-stubs` (`fetch_inputs.sh` が clone) | exit 2 (旧: 例外) |
| mac dylib | `FL_ENGINE_DYLIB` | `$FL_MAC_DIR/.../FLEngine_x64.dylib` | WARN + 出力先の既存 `flapi_table.json` の `midi_script_callbacks_in_binary` を引き継ぐ。引き継ぎ元も無ければ exit 2 (旧: 空配列で上書き) |
| 出力先 | `FLAPI_OUT_DIR` | `analysis/flapi` | — |
| emsdk | `EMSDK_DIR` | `/opt/emsdk` | exit 2 (link 段のみ) |

- PE 照合が 1 件も一致しない (別ファイル・破損) 場合も exit 2。`FLPY_TABLE_ONLY=1 bash build_flpy.sh` は table / ids / `FLAPI.md` の再生成だけで終了 (emsdk・CPython wasm 不要)。
- 副次: 旧 `flapi_table.py` は `FLAPI.md` 先頭の「自動生成・人手編集禁止」ヘッダを出力せず、再生成で追跡中のファイルが差分になっていた。生成側に移した。
- 検証: `FL_WIN64_DIR=<fl-win64 展開先> bash tests/flapi_table_check.sh` (出力先は一時ディレクトリ。追跡中のファイルは書き換えない)。判定: 再生成 3 ファイルが追跡中とバイト一致 + `win_pair_verified=true` > 0 + ネガコン 6 本が全て exit 非 0 + 理由表示 + 出力不変。前提入力が無ければ exit 3 (NOT VERIFIED)。
- 実測 (Actions runner、oc_artifacts: fl-win64 toolchain-emsdk、直列、n=3): 3 回とも exit 0・wall 2.20 / 2.20 / 2.20 秒・load average 0.13〜0.20。正常系 3 / 3 ファイル一致 (差分 0)、`win_pair_verified=true` 388 件 (REPORT §3 の 388/399 と一致)。ネガコン 6 本 (PE 無し / PE 空 / PE が別物 / stubs 無し / emsdk 無し / dylib も既存 table も無し) は全て exit=2 + 理由表示。
- gate 自体のネガコン: 入力 PE を乱数 1 MB に差し替えると `flapi_table_check.sh` は exit 1、PE 無しは exit 3 (どちらも緑にならない)。範囲外: `build_flpy.sh` の emcc link 段 (CPython wasm の事前ビルド `build_cpython_wasm.sh` が必要で未実施。emsdk の実在 `/opt/emsdk/emsdk_env.sh` のみ確認)、`fetch_inputs.sh` / `run_all.sh` の `/home/ubuntu` 固定パス (run_all.sh の `FL_MAC` / `FL_WIN`)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `run_all.sh` が `FL_MAC` / `FL_WIN` を `/home/ubuntu/...` に固定している | Actions で `run_all.sh` 全体を回せない | #630 (PY-15) |
| mac dylib が無い環境では `midi_script_callbacks_in_binary` を既存値から引き継ぐだけで再抽出できない | 26.1.7 以外の版で更新漏れの恐れ (WARN は出る) | #588 コメントに記載 |

## 12. kwargs シグネチャの静的復元 (PY-9 b, #81)
方式・入力: §7 の kwargs 項目参照。再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi_kwargs.py` (要 capstone, pefile。出力は commit 済み JSON とバイト一致) の後 `python3 tests/kwsig_check.py` (wasm 不要)。

| 項目 | 実測 |
|---|---|
| メソッド表から 435 関数全件に対応付け | 435/435 (13 module)。メソッド表に載るが本 table の module 外の 8 表 (flpianoroll/flcpt/ScriptDialog 等のクラスメソッド) は対象外 |
| 書式文字列を復元 (flags=1/3 + 引数あり) | 303 関数 (flags=1: 200 / flags=3: 103。flags 全体は 1=205, 3=105, 4=125)。flags=4 (NOARGS) 125 件は書式無し。初版の「309 (flags=4: 6)」は `ret` を越えて隣の関数の `lea` を拾った誤検出で、`ret`/`int3` 打切りと NOARGS 除外で修正 (変化は 6 関数のみ。flags=1/3 の 303 件は全て最初の `ret`/`int3` より前に間接 call があり、再生成の前後で不変) |
| **kwlist (引数名) を復元** (flags=3 = VARARGS\|KEYWORDS) | **103 関数**。全件で `len(kwlist) == 書式の最大引数数`。flags=3 で未復元は 2 (`device.flrMidiNote`, `flrMidiCC`: lea の並びが他と異なる) |
| flags=1 (VARARGS のみ、実 FL は kwargs を受けない可能性) | 205 (うち書式あり 200)。**位置引数のみ**。ただし MCPTools が `channels.channelCount(globalCount=)` を kw 呼出しするため kwargs 拒否にはしていない |
| 新規 43 関数のうち | 書式あり 32 / kwlist あり 9 (`fillEachNSteps` `rerollLoopStarter*` `setPluginMixLevel` `setPluginMuteState` `setLoopStarterRootNote` `releaseCC` `selectionSet` 等)。残りは flags=1 (位置引数のみ)/4 (引数なし) |

stubs (LGPL 参照) 署名との照合 (kwlist のある 103 のうち stubs 署名がある関数): 名前一致 66 / **不一致 28** (バイナリ側を正とする)。例: `channels.getChannelName` は stubs の `index` でなくバイナリの kwlist 先頭が `value`、`channels.getChannelVolume` は `mode` でなく `useDb`、`channels.setChannelPitch` は `mode` でなく `pitchUnit`、`mixer.getTrackVolume` は `mode` でなく `flag`、`plugins.setParamValue` は `value` でなく `paramValue`、`transport.globalTransport` は `command` でなく `index`、`device.forwardMIDICC` は `mode` でなく `forwardTo`、`mixer.automateEvent` は `speed` でなく `smoothSpeed`。書式の引数数 (必須/最大) は stubs 署名と 230 件一致 / 49 件不一致 (stubs の引数が欠けている・書式の `|` 位置が異なる等)。
- `fl_api.py`: kwlist があれば stubs 名より優先して kwargs を束縛。省略可能引数の既定値が C 側で静的に不明なとき、それを飛ばして後続だけ指定する呼出しは `TypeError` (推測値で埋めない)。stubs の既定値は、同名の引数のものを引き継ぎ、名前だけ変わった同位置の引数 (`mode`→`useDb` 等) のものも引き継ぐ。stubs 側の名前が kwlist の別位置にある (位置がずれた) 3 関数 `channels.soloChannel` / `plugins.getColor` / `plugins.getParamValueString` は別の引数の既定値になるため引き継がない。未知の kwarg は既定値の評価より先に `TypeError`。
- **kwlist の重複 1 件 (バイナリ由来)**: `arrangement.selectionSet` = `['selStart','selStart','selectNotes','updateSongLoop','scroll']` (kwlist 表 0x151dc00 の先頭 2 エントリが同じ文字列 0xd7890c を指す。2 つ目は `selEnd` の記載ミスと推定)。bind は最初の出現だけを kw で束縛し、2 つ目以降は位置専用 (kw では埋まらない)。実 CPython (3.14, ctypes で `PyArg_ParseTupleAndKeywords` を直接呼出し) は `selStart=5` のみ → 必須欠落 `TypeError` (mock と同じ) だが、位置 1 個 + `selStart=5` は 2 つ目に束縛されて通り、mock はこれを拒否する (誤記を kw で踏まない側に倒した差)。
- 検証 (`tests/kwsig_check.py`): 435 関数に kwsig・kwlist 103・NOARGS 書式無し・bind の 9 区分。区分 8 は PR 前 (stubs 署名のみ) の bind との新旧比較で、94 関数 (stubs 署名と kwlist の両方あり) の「位置 k 個 + kw 1 個 (kwlist の名前)」呼出しのうち旧が通った 224 件が対象、新も同結果 216 件、差 8 件 (4 関数: `getStepParam` はバイナリが 5 引数で 6 つ目を渡さない / 上記のずれた 3 関数。うち 3 件は旧が gap 後の既定値で位置ずれさせていたもの: 新は gap 以降の未指定引数を省略し `getGridBit(index=1)` は `(1,)`、`triggerLiveClip(index=1, blockNum=2)` は `(1, 2)`)。MCPTools.pyc の flapi への kw 呼出し 20 箇所 (重複除き 14 パターン; `KW_NAMES` 付き `CALL` を 3.12 `dis` で抽出。`print(..., file=)` 等は対象外) は新 bind で 14/14 通り、kwlist のある関数では全て kwlist 名と一致 (旧 main の bind は 13/14: `plugins.getParamValueString(slotIndex=, useGlobalIndex=)` が stubs 既定値 `midi.PIM_None` の `eval` で `NameError`)。
- **wasm 回帰** (検証起点 bdd2f7c を別 worktree に展開、`FL_WIN64_DIR` 設定、node 22.23.3、直列 1 本、load average 1.1。`run_all.sh` は step 4 が `/home/ubuntu` 固定 (#588) のため同じ手順を個別実行): `all_tools.mjs` 48/48 (JS mock と `FL_ENGINE=wasm` の両方、host_calls 37,425)・`provider_check.mjs` PASS・`poc_mcp.mjs` POC OK・`browser_check.mjs` (headless Chrome) OK・`midi_script.mjs` 23 check PASS (`--neg` で検出)・`subinterp_probe.mjs` 12 check PASS (各 0〜8 秒)。**`provider_check.mjs:86` が stubs 名で `getChannelName(index=)` を kw 呼出ししており、kwlist (`value`) 採用で `TypeError` になっていた** (ec9813b で FAIL を確認) ため `value=` に修正。未実行: `mcp_ui_check.mjs` / `midi_ui_check.mjs` (Vite が要る)。CPython wasm は ec9813b の run でクリーンビルド 243 秒 (その後 `work/` を別 worktree へ移したため `build_cpython_wasm.sh` の再実行は絶対パスのずれで rc=2、libpython は流用)。`build_flpy.sh` が再生成する `flapi_table.json` は `midi_script_callbacks_in_binary` を失う (§10 の既知問題) ため、`midi_script.mjs` は commit 済みの表で実行。`tests/kwsig_check.py` 0.03〜0.04 秒 (n=3、load 0.44)。`analysis/flapi_kwargs.py` の再生成は両 JSON とも commit 済みとバイト一致。

## 13. 未解決 (#81)
- (a) 実機 FL での `mixer.getCurrentTempo(1)` 等の意味差確認は実機が必要で未着手 (#81 のブロッカーのまま)。`device.flrMidiNote` / `flrMidiCC` の書式・kwlist も未復元 (2 件)。
- stubs 既定値が C 側で不明な引数を飛ばす呼出し (`channels.soloChannel(1, useGlobalIndex=True)` 等 3 関数) は `TypeError`。実 FL は C 側の既定値で通すため意味差。ホストへの「省略」の渡し方 (provider は `None`=handler 既定値、JS mock の `tog` は `undefined` のみ省略扱い) が未統一で、PM 判断待ち (PR #463 コメントに起票依頼)。
- stubs 既定値 `midi.*` 10 種 (21 引数: `PIM_None` 7、`GT_All` 5 ほか) は `eval(…, {})` で `NameError` (main 既存の問題)。PM が別 issue で追跡 (PR #463 コメントに起票依頼)。

## B. §14 / §14b (Piano roll scripting #79 / Chrome 検証 #466) — 全文

## 14. Piano roll scripting (`flpianoroll` + `.pyscript` ローダ) — #79 (PY-5)

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
| ~~Chrome 上の pyscript 実行未検証~~ | 下記 §14b で解消 (#466) | — |

### 14b. Chrome (agent-browser) 上の pyscript 実行検証 — #466 (PY-11)

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
注意: `build_flpy.sh` は mac dylib / win PE の無い runner で追跡中の `analysis/flapi/{FLAPI.md,flapi_table.json}` を書き換える (既知、#79 REPORT 7b-2 記載)。本 PR には含めていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Firefox / Safari での pyscript 実行 | Chrome 以外は未検証 | #165 (PERF-P7 ブラウザ行列) にコメント |
| mock engine ではなく実 FLEngine(wasm) 結合時の再検証 | 出力一致は mock 上の結論 | #112 / T3 以降 |
