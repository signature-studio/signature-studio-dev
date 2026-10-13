# python REPORT 付録

> 正本: `tools/python/REPORT.md`。行数上限 (250 行, `docs/DOC_MAP.md` §1) のため、§PY-13 (#588) と §12・§13 (#81 PY-9 b) の全文をここに無変更で分割移動した。内容は削除していない (Git 履歴に残る)。

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
- 範囲外: **実機 FL の出力との一致** (未確認。下記 ASSUMPTION)、HUD の実フォーム UI (#10)、Chrome 上での pyscript 実行 (node のみ)、`loadScoreFromFile`、`flcpt`/`flrack`/`enveditor` (T7)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `Note` の既定値のうち number=60 / length=PPQ は docs に記載なく推定 | 新規 Note の既定が実機と違う可能性 | #79 コメント (実機確認待ち) |
| `clearNotes(False)` は selected のみ消す (docs の文言通り)。選択ゼロ時に実機が全消去するかは未確認 | Arpeggiator の「全選択無し」挙動 | #79 コメント |
| ScriptDialog の範囲外値を clamp しない (警告のみ)。実機の clamp 有無は未確認 | 範囲外入力時の結果 | #79 コメント |
| Remote Scripts が `channels` を import 無しで参照 → 実機が同名を注入していると推定 | ローダの注入名 (flapi 12 module) | #79 コメント |
| `ScriptDialog.Execute()` は headless で常に True | 対話キャンセルの再現不可 | #10 (HUD) |
| Audio scripts 12 本に `enveditor` 実装が必要 (Edison の波形操作 13 メンバ + Editor 選択) | Audio scripts 0/12 | 新規子チケット案 `[PY-6] enveditor module` (T7 を分割) |
| flpianoroll は #79 の 64 メンバのうち **62/64 実装**。stub 1 = `Score.loadScoreFromFile` (`NotImplementedError`)、未実装 1 = `ScriptDialog.DialogParams` (`src/flpianoroll.py` に無い) | #79 の受入「64 メンバ」は未充足。`loadScoreFromFile` は .fst/.fsc 読込を使うスクリプトに影響。`DialogParams` は HUD (#10) の実フォーム連携と合わせて実装 | #79 コメント (本 PR の fix で投稿) |
| Chrome 上の pyscript 実行未検証 | node のみ | 新規子チケット案 (browser_check に追加) |

### 14-b. main 競合解消後の再検証 (merge commit `647c9c1`、node v22.23.3、uptime load average 1 分値 2.52 / 2.52 / 2.96)

| 項目 | 結果 |
|---|---|
| `tests/pyscript_e2e.mjs` (n=3) | 43/43 PASS・exit 0。wall 1.64 / 0.80 / 0.78 秒 (1 回目は初回読込) |
| `build_cpython_wasm.sh` | exit 0、real 3m33.880s (native + wasm、本 run の初回ビルド) |
| `build_flpy.sh` | exit 0、real 5.680s |
| 回帰 (同 HEAD) | `smoke_direct` exit 0 / `midi_script.mjs` 23 checks OK・`--neg` exit 1 (検出) / `all_tools` 48/48 ok (host_calls 37,425) / `poc_mcp` POC OK |
| 比較 (同手順で再実行、一時展開) | 旧 head `57326b1`: host_calls 37,424 / `origin/main` `b6311f3`: 37,425 (`get_plugin_parameter_value` に `plugins.getParamValueString` 呼出しが 1 件増)。merge 後 HEAD は main と同値。差は main 側に既存。保存スナップショット `analysis/mcp/tool_coverage.json` (37,424) は現行コードより古い (自動生成物のため本 PR では更新しない) |
| 素材 | `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)、`toolchain-emsdk` は [EMSDK] (`docs/REFERENCES.md`) の位置に展開。mac dylib なし (flapi_table は既存表 27 件を引継ぎ) |
| 範囲 | node + mock engine。Chrome 上の pyscript 実行は未検証 (従来どおり) |
