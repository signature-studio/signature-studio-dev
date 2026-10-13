# tools/python REPORT 付録

> 正本: `tools/python/REPORT.md`。行数上限 (250 行, `docs/DOC_MAP.md` §1) のため、§7c (ilmcp, PY-3 #82)・§9 (下流チケット T1〜T9 表)・§PY-13 (#588)・§12・§13 (#81 PY-9 b) の全文をここに分割移動した。内容は削除していない (Git 履歴に残る)。

## 7c. ilmcp 9 関数の実装 (PY-3 / #82) — `host/ilmcp.mjs`

既知類型との関係: 該当なし (lift ではなく JS ホスト実装。DEFECTS.md の対象外)。検証起点 commit は PR 本文参照。

**結論**: `ilmcp` 9 関数を `host/ilmcp.mjs` に実装し `fl_mock.mjs` から差し替えた (旧: 戻り値固定の偽実装)。class B 8 tool + U 2 tool を wasm CPython 上の実 `MCPTools.pyc` で実行し、**FLEngine 側状態** (チャンネル・ミキサースロット・PRScript・highlight) を検査する e2e `tests/ilmcp_e2e.mjs` が 25/25 PASS。
**ただし受入条件「実エンジン上で動作」は未達**: FLEngine は未完成 (`tools/flelift/boot` は InitUnits まで)。本実装は JS ホストの状態機械で、実 FL との戻り値・例外の一致は未検証。

| 関数 | 引数規約 (MCPTools 逆アセンブル実測) | 実装 |
|---|---|---|
| getBrowserNames(name, recursive) | name = `Plugin database[/…]`、recursive = int(0/1) | カタログ木の直下 / 全子孫を `["Effects/", …, "Drum/Kick"]` の list で返す。不明パスは ValueError |
| addChannel(plugin) | 拡張子・パスは MCPTools 側で除去済み | generator のみ受理。戻り = 0 起点 index。effect 名・未知名は ValueError |
| removeChannel(idx) | 0 起点。MCPTools が降順に呼ぶ | 範囲外は IndexError (code 4) |
| addEffect(plugin, track, slot) | slot は 0 起点 (visual−1)。**plugin="" = スロット消去** (remove_effect / reset_mixer_tracks が使う) | effect のみ受理。track 0..126・slot 0..9 |
| storePRScript(name, source) | name は拡張子なし | `/ \ :` を含む名前は拒否 (保存先は FL の Piano roll scripts dir 想定) |
| runPRScript(source) | `ui.showWindow(piano roll)` の後に呼ばれる | ソースを保持し `st.prRunner` があれば委譲。**実行本体は PY-5 (#79) の flpianoroll 待ち** |
| getHighlightNames() / showHighlight(item,name,caption,whenDone,flag) | whenDone は Python callable (`{__cb:id}`) | 名前は FLEngine win64 rodata 実測 21 件 (旧モックは 4 件・大文字小文字も違った: `Piano roll` ≠ 実機 `Piano Roll`) |
| forwardTutorialEvent | MCPTools 未使用・arity 不明 | 呼出を記録して None |

データ: `analysis/ilmcp/plugin_catalog.json` = native 136 (fst_manifest の `Data/Patches/Plugin database`: Generators 57 / Effects 79) + installed 5 (`hostbridge/nfo/specs/wasm_plugins.json`)。`analysis/ilmcp/highlight_names.json` = rodata の UnicodeString リテラル 21 件。生成 = `FL_WIN64_DIR=… python3 analysis/ilmcp_catalog.py`。
`/py/` の配信許可 (`vite.config.ts` `pyAssets`) は ilmcp.mjs が import する 2 JSON を個別に列挙している。import 一覧からの自動生成は、許可リストを意図的に固定する設計 (PY-4) を崩すため不採用。取りこぼしは `mcp_ui_check.mjs` (run_all step 11) が検出する。
カタログは**名前とカテゴリのみ** (FL 由来のバイト列は含まない)。FL 同梱プラグイン名・UI 文字列 21 件をリポジトリに置くことの可否は `docs/LEGAL.md` に照らして未確認 → PM 判断事項 (下記未解決)。

### 検証 (runner, node 22.23.3, 4 core。検証起点 = クリーン worktree の commit 828d245。環境: `work/` に MCPTools.pyc・midi.py・utils.py・fl-stubs、`dist/` に `build_flpy.sh` 産の flpy.*)
| コマンド | 結果 |
|---|---|
| `node tests/ilmcp_e2e.mjs` (n=3) | **25/25 PASS** × 3。wall 0.23 / 0.23 / 0.24 s (チェック本体 43 / 44 / 47 ms)、load average 0.14 |
| `node tests/all_tools.mjs` | 48/48 ok、host_calls 37,424 (828d245 時点の値。main の PY-9b (3d1646f) 取込後の HEAD では 37,425 → 検証 2)、callback_roundtrip true、1.05 秒 |
| `node tests/poc_mcp.mjs` | POC OK、0.60 秒 |
| `node tests/browser_check.mjs` (headless Chrome) | BROWSER OK (crossOriginIsolated, 48 tools)、12.5 秒 |
| ネガティブコントロール `--negative <fn>` (その関数を「何もしない / 空」に差替え) | 8 関数すべて検出: getBrowserNames 5 / addChannel 4 / removeChannel 1 / addEffect 3 / storePRScript 2 / runPRScript 1 / getHighlightNames 4 / showHighlight 3 件 FAIL (`NEGATIVE-CONTROL OK`) |

### 検証 2 (PR #470 head での再実測。runner, node 22.23.3, 4 core。素材 fl-win64 から `fetch_inputs.sh`、`build_cpython_wasm.sh` + `build_flpy.sh` = 253 秒。main (bd67740) merge 後の競合解消 `fl_mock.mjs` / `run_all.sh` を含む)
| コマンド | 結果 |
|---|---|
| `node tests/ilmcp_e2e.mjs` (n=3) | 25/25 PASS × 3。wall 0.44 / 0.42 / 0.41 s、load average 3.49 (ビルド直後) |
| `node tests/all_tools.mjs` / `FL_ENGINE=wasm node tests/all_tools.mjs` | どちらも 48/48 ok、host_calls 37,424 |
| `node tests/poc_mcp.mjs` / `node tests/browser_check.mjs` | POC OK 1.27 s / BROWSER OK 1.52 s |
| `node tests/provider_check.mjs` (run_all 9b) | PASS (implemented 60 / mcp_static 60) |
| **`node tools/python/tests/mcp_ui_check.mjs`** (run_all step 11) | **MCP UI OK**、exit 0、8.53 s (UI で tools/list = 48・get_tempo = 130 BPM、devtools で set_tempo(140) → 140)。`--neg` は NEG-CONTROL DETECTED |
| 同上、`vite.config.ts` の ilmcp JSON 許可を**外した**状態 | **FAIL** (`Failed to fetch dynamically imported module: …/py/host/fl_mock.mjs`)、exit 2 → 修正 (`pyAssets` の `allowed` に `analysis/ilmcp/(plugin_catalog\|highlight_names).json`) の検出力を確認。許可を戻した状態で再 OK |
| run_all step 12 / 13 / 14 | midi_script OK (23 checks、`--neg` exit 1)、subinterp OK (12 checks)、midi_ui_check OK。`midi_bundled_device.mjs` は NOT VERIFIED (exit 3): fl-win64 素材から同梱 device script を取れない (`fetch_inputs.sh` の win64 経路が配置しない)。本 PR 範囲外 |

`run_all.sh` 全体は `/home/ubuntu` 固定 (#630) のため一括実行できず、上記は step ごとの個別実行。

`all_tools.mjs` の 48/48 は「エラー文言が無い」判定なので、旧モックでも通っていた (get_browser_names の戻りが `[object Object]` だった点は `tool_coverage.json` の差分に現れる)。状態検査は `ilmcp_e2e.mjs` が担う。

### 仮定 (実機未確認)
- getBrowserNames の戻り形: 旧モックは `{name, items}` dict、本実装は文字列 list。MCPTools は `data` をそのまま返すだけで形を検査しないため静的解析では確定できない。実機の形は PY-9 (#81) で確認。
- フォルダ末尾 `/` の表記・`recursive` の深さ・エラー時が例外か空 list か。
- addEffect の既知プラグイン検査: 実機が未知名に例外を返すか黙って無視するかは未確認 (MCPTools は例外を捕捉して "Failed to add effect" を返す実装なので、どちらでも tool 側は破綻しない)。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine 上での動作 (受入条件 1) | PY-3 を Closes にできない | #74 (PY-1) の実エンジン結線後に再検証 |
| C provider (`fl_api_call`, PR #459) の ilmcp ハンドラは旧モック意味論のまま | provider 経由 (`FL_ENGINE=wasm`) では本実装と挙動が乖離 | #459 (MERGED) にコメント済み。`fl_engine.c` を本実装と同じ意味論に更新するチケットは PM 起票待ち |
| runPRScript の実行 (flpianoroll) | run_piano_roll_script はソース受領までで、スクリプトは走らない | #79 (PY-5) |
| 実機の戻り形・例外の確認 | 上記「仮定」 | #81 (PY-9) |
| `run_all.sh` が `/home/ubuntu` 固定のまま | CI で一括実行できない (本 run は手動で work/ 配置) | #630 (PY-15) にコメント済み (親 #294) |
| カタログ (プラグイン名 141 件) と highlight 名 21 件の commit 可否 | FL 由来の名称文字列をリポジトリに含める | #569 (LGL-7)。`docs/LEGAL.md` 照合は未実施。不可なら実行時に利用者の FL から生成する形へ変更 |

## 9. 下流チケット案

| # | 内容 | 規模 |
|---|---|---|
| T1 | **(MCP 60 関数は §7b で完了。残り MIDI 経路 → 426 関数は未着手)** FLEngine wasm に flapi provider (`fl_api_call(fn_id,slots)`) を実装: まず MCP が使う 60 (公開 52 + ilmcp 8) + MIDI 経路 (device/transport/mixer/channels) 優先 → 426 関数。`flapi_table.json` から C 雛形を生成 | L |
| T2 | CPython を FLEngine wasm へ静的リンク (JS 往復撤廃)。`flpy.c` 再利用、スレッド/GIL 方針確定 | M |
| T3 | `ilmcp` 9 関数の実装 (PluginDB/Browser 列挙、addChannel/addEffect、PRScript store/run) → MCP B 群 8 tools | L |
| T4 | MCP JSON-RPC をアプリ内 UI/devtools に公開 (`mcp_rpc.mjs` を FLEngine UI に接続、外部 LLM 無し) | S |
| T5 | piano roll scripting: `flpianoroll`(Note/Marker/score/ScriptDialog) + `.pyscript` ローダ、同梱 5 本 (Euclidean/Humanize/Arpeggiator…) を回帰試験に。ScriptDialog は HUD フォーム連携 | L |
| T6 | MIDI scripting ホスト: device script(.py) ローダ、27 callback 配送、Web MIDI 入力→`dispatch_midi`。サブインタプリタ可否の wasm 検証 | M |
| T7 | Edison `enveditor` / `flcpt` / `flrack` module と Chord progression ツール (pyc 39 + pyscript 2) の動作検証 | M |
| T8 | 性能: 構造値の binary ABI、バッチ API、MIDI 1 イベント当り呼出し数の計測 | S |
| T9 | 実機 FL でのモック意味差検証 (ユーザ環境があれば。**kwargs 復元は #81 で完了**、残りは実機確認のみ) | S |

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
