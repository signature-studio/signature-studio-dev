# G python-mcp — CPython wasm + flapi/MCP 解析 + ブリッジ設計 (2026-10-10)

## 結論 (先出し)

1. **CPython 3.12.1 (FL 同梱版と完全一致) の emscripten/wasm ビルド成功**。パッチ無し、emsdk 6.0.12 でクリーンビルド 3m19s。node で `print(1+1)`=2、struct/json/zlib/hashlib/decimal/re/datetime/inspect 等が動作。`flpy.wasm` **5.92MB** (gzip 2.07MB) + `flpy.data` (stdlib zip) 3.20MB。
2. **FL の組込 Python API 面を実測**: 公開 12 module **426 関数** + FL 内部 `ilmcp` 9 = **435 関数** (公開 stubs 旧版 392 に対し +34 が 26.1.7 新規)。他に `flpianoroll`(64 メンバ)/`flcpt`/`flrack`/`fl`、MIDI script callback **27**。
3. **MCPTools.pyc = 48 tools** (「50」ではない)。逆アセンブルは同一 3.12.1 の marshal/dis。**外部通信は pyc 内に 0 件** (import は stdlib 10 + FL module 12 のみ)。分類 **A local-flapi 38 / B local-ilmcp 8 / U Gopher-UI 付随 2 / X 対象外 0**。LLM ゲートウェイ (Gopher WebView `window.flHelper`) は pyc の外で、対象外。
4. **PoC 成功**: wasm Python を Web Worker で起動し、SAB 同期 RPC で flapi モック (FLEngine 模擬) に接続、**FL 同梱 `MCPTools.pyc` を FL と同じく `__main__` として実行して 48/48 tools が成功** (例外なし・エラー文言なしの意味。モックの戻り値のため FL 実機と同一動作の保証ではない。37,424 flapi 呼出し)。Python→ホスト callable 呼戻し・MIDI callback 経路・MCP JSON-RPC (tools/list, tools/call) も確認。**headless Chrome (cross-origin isolated, module Worker) でも成功**。
5. 1 コマンド E2E: `bash tools/python/run_all.sh` (incremental 19 秒 / 初回 ~4 分)。

## 1. CPython 3.12.1 wasm ビルド

| 項目 | 実測 |
|---|---|
| ソース | python.org Python-3.12.1.tgz (FL: `Python.framework` Info.plist=3.12.1, `/Users/sysadmin/build/v3.12.1`; win は python312.dll=3.12.1 と win REPORT 記載) |
| ツール | emsdk 6.0.12 (clang-24), native build-python 3.12.1 (cross 用 + dis 用) |
| 方式 | `--host=wasm32-unknown-emscripten --with-emscripten-target=browser`、全 ext module を **静的リンク** (動的リンク無し)。`libpython3.12.a` を自前 `flpy.c` と ES module (`-sMODULARIZE -sEXPORT_ES6`) にリンク |
| 成果物 | `flpy.wasm` 5,920,419B (gzip -9 で 2,071,492) / `flpy.data` 3,199,615B (stdlib 400 pyc の zip + `/fl/Lib`) / `flpy.js` 120,194B (gzip 32,209)。stock `python.js` ビルドは wasm 5,927,165B |
| 時間 | wasm 側クリーン build+link 3m19s (16 core)、flpy 再 link 4 秒 |
| 起動 | Worker 生成〜Python init〜MCPTools 読込前まで node 約 100ms / Chrome 150〜860ms |
| 検証 | `tests/smoke_direct.mjs`: `print(1+1)`、struct/json/math/zlib/hashlib/re/decimal/collections/itertools/inspect/ast/dis/typing、FL スクリプトが実際に使う stdlib 22 module 全 import 可、再帰 900 |

詰まり所と回避 (CPython へのパッチは不要):
- `xxlimited*` の共有 module が `-fPIC` 要求で link 失敗 → configure 時 `py_cv_module_xxlimited=n/a` 等で無効化。`_sqlite3`(port 取得を避ける)・CJK codec 7 本も無効化 (wasm 7.93→5.93MB)。
- 既定 emscripten STACK_SIZE=64KB は CPython 再帰に不足 → `-sSTACK_SIZE=5MB`。
- 隔離 `PyConfig` のままだと stdio が ascii → `Py_PreInitialize(utf8_mode=1)`。
- ルート `package.json` が `"type":"module"` のため stock python.js(CJS) は node で `require is not defined` → ES module 出力に統一。
- `-sUSE_ZLIB/-sUSE_BZIP2` は emsdk 6.0.12 で動作 (port 自動取得、INFO ログのみ)。`-sWASM_BIGINT` は deprecated 警告のみ。

## 2. FL 同梱 Python の実測 (`python_inventory.json`, `scripts_inventory.json` — repo 外の解析出力。入力素材は `docs/REFERENCES.md` `[MAC]`)

- **mac**: `Python.framework` 64.75MB。`Python` 本体 15.99MB (universal2)、stdlib `.py` 737 本、`lib-dynload` 77 本 (非 test 65)、`site-packages` は README のみ、`test/` 無し。同梱 dylib: libssl/libcrypto/ncursesw/form/menu/panel。**FL 固有の C 拡張は lib-dynload に 0 件 — FL 独自 module は全て FLEngine_x64.dylib(Delphi/Python4Delphi) 内**。
- **win**: python312.dll + 26 .pyd (win REPORT)。`MCPTools.pyc` は mac と **byte 一致** (100,674B, magic `cb0d0d0a`=3.12)。
- 追加 Lib: `Shared/Python/Lib/midi.py` (770 行, 定数のみ), `utils.py` (213 行, 純 Python)。
- 静的リンクした wasm の builtin module 66 本。FL の非 test lib-dynload 65 中 **35 を提供**。欠落 30 は `_ctypes _curses* _dbm _hashlib _ssl _lzma _uuid _tkinter _sqlite3 _codecs_{cn,hk,iso2022,jp,kr,tw} _multibytecodec _multiprocessing _posixshmem _posixsubprocess _xxsubinterpreters _xxinterpchannels fcntl grp nis readline resource syslog termios _scproxy`。FL 同梱スクリプトの import 実測では不要 (下記)。
- **FL 同梱 Python スクリプト 65 本**: pyscript (Audio scripts 12 / Remote Scripts 5 / Piano roll 5)、device .py 1、Chord progression 41 (pyc 39 + pyscript 2)、MCPTools.pyc 1、(Hardware specific の `.scr` 95 本は旧形式で Python ではない)。import する stdlib は **22 module のみ** (`__future__ abc ast collections copy enum functools inspect itertools json math operator os pathlib random re sys time traceback types typing zlib`) — wasm で全て解決済。FL module は 17 (`enveditor flpianoroll flcpt flrack` を含む)。
- FL の Python 組込み方: Python.framework は **dlopen/dlsym で後付け** (LC_LOAD_DYLIB に無い)。C API 関数名は rodata に平文で残らず**未抽出**。Delphi 型名から `PyInterpreterConfig`(サブインタプリタ示唆)・`PythonSession`/`TMCPPythonSession`・`pycb*` callback 表・`fl.FLTextOutput`(stdout 差替)・`_ilmeta` を確認。

## 3. FL 組込 API 面 (本 repo 側の生成物は `python/analysis/flapi/FLAPI.md`)

FLEngine rodata の `name\0doc\0…<module>` 並びから機械抽出 (`flapi_extract.py`)。mac x86_64 と arm64 は **完全一致**、win PE は同一 (名前,doc) ペアが 388/399 (97%) で一致 (差は doc 末尾空白・コード連結)。公開 stubs (IL-Group/FL-Studio-API-Stubs, LGPL, 参照のみ) の署名で補完。

| module | 関数 | 旧 stubs に無い新規 | | module | 関数 | 新規 |
|---|---|---|---|---|---|---|
| channels | 54 | 6 (swing, LoopStarter reroll, fillEachNSteps) | | ui | 72 | 1 (showPicker) |
| mixer | 75 | 8 (PluginMixLevel/MuteState, RouteToLevel, getTrackCount, setCurrentTempo) | | device | 37 | 3 |
| patterns | 31 | 6 (clear/move/duplicate…) | | playlist | 42 | 1 (selectTool) |
| general | 30 | 6 (project title/author/genre, set*Numerator…) | | arrangement | 12 | 3 |
| transport | 20 | 0 | | screen / launchMapPages / plugins | 28 / 12 / 13 | 0 |
| **ilmcp (内部)** | **9** | 9 | | **合計** | **435** | **43** |

- `ilmcp`: showHighlight, forwardTutorialEvent, storePRScript, runPRScript, addChannel, removeChannel, getBrowserNames, getHighlightNames, addEffect (MCPTools は forwardTutorialEvent 以外の 8 を使用)。
- piano roll: `flpianoroll` = Note 17 / Marker 7 / score 22 / Utils 3 / ScriptDialog 15 メンバ (`Execute AddInput* GetInputValue SetText addGroup endGroup restoreFormValues` 等)、エントリは `createDialog()` / `apply(form)`。
- MIDI scripting: callback は rodata の `pycb*` 表で **27** (公開 26 + 新規 `OnInitAll`)、event 型 `flmidimsg` 23 フィールド。
- 詳細表: `FLAPI.md`、全関数 (doc/署名/MCP 使用): `flapi_table.json`、fn_id 正本: `flapi_ids.json`。

## 4. MCPTools.pyc 48 tools (本 repo 側は `python/analysis/mcp/MCP_TOOLS.md`, `mcp_classification.json`)

- 構造: `@mcp_tool`(= `_is_mcp_tool=True`) 付き関数を `get_mcp_tools_json()` が `sys.modules['__main__']` から走査して name/description/inputSchema(型は Annotated から生成) を JSON 化。FLEngine 側 `TMCPServer`/`TMCPPythonSession`/`TMCPSyncCall` が JSON-RPC 2.0 応答 (`result.content[{type:text}], isError`) を組立て、結果は WebView の `window.flHelper.onMCPTools/onRunJson` へ渡る (rodata の JS 呼出し文字列からの推定)。
- 使う FL API は **8 module / 61 参照** (channels 18, mixer 18, ilmcp 8, plugins 7, playlist 4, ui 3, transport 2, midi 定数 1)。静的 61 参照 = flapi 関数 60 (公開 52 + ilmcp 8) + `midi.PIM_None` 定数 1。実行実測で 55 を踏み (`mcp_classification.json` の `api_arity_observed` も 55)、未実行 6 は分岐違いで静的閉包に含まれるもの (isChannelSelected, mixer.focusEditor, mixer.isTrackSelected, plugins.getParamValueString, ui.hideWindow, midi.PIM_None)。**実行時に呼ばれた API は静的閉包の部分集合** (不一致 0)。

| 分類 | 数 | tools |
|---|---|---|
| A local-flapi (公開 flapi のみ) | 38 | get_session_context show_or_hide_window play stop get/set_tempo / channel 系 13 (list_channel_names select/rename/mute/solo_channels route_channels_to_mixer get_channel_volumes set_channels_volume(_db)/pan/colour set_step_sequencer_step/pattern) / mixer 系 11 (tracks pan/volume(_db/_percent)/rename/colour/mute/solo, get/set/reset_mixer_routing) / open_piano_roll_for_channel quantize_channel / playlist 3 / plugin param 3 |
| B local-ilmcp (FLEngine 内部機能が必要) | 8 | get_browser_names add_channel remove_channels add_effect remove_effect reset_mixer_tracks save_piano_roll_script run_piano_roll_script |
| U Gopher UI 付随 (ローカル完結・低優先) | 2 | get_highlight_names show_highlight (Python callable `whenDone` を FL へ渡す実測) |
| X 対象外 (外部通信) | 0 | pyc 内に無し。クラウド/LLM は Gopher WebView + FL Cloud 側で本プロジェクト対象外 |

## 5. ブリッジ設計と PoC (詳細: `BRIDGE.md`)

`main ⇄ Worker B(flpy.wasm: CPython+_flhost+fl_api+fl_rt) ⇄ SAB mailbox(Atomics.wait / waitAsync) ⇄ FLEngine 側 provider`。`_flhost.call(fn_id, args)` が唯一の境界 (16B tagged slot ABI、構造値は JSON、callable は `{__cb:id}`)。FL module は `flapi_table.json` から**データ駆動で生成**する薄ラッパで Python 側に FL ロジック無し。

| PoC 実測 | 値 |
|---|---|
| MCPTools.pyc を wasm Python 上で `__main__` 実行、`get_mcp_tools_json()` | 48 tools (FL と同一出力形) |
| 全 48 tools 実行 (モック) | **48/48 ok**、flapi 呼出し 37,424 (tool 別合計は 37,423)、全体 2.2 秒 (検収再実行 約 4 秒、負荷依存) |
| flapi 往復 (Worker↔main, JSON RPC) | **bimodal: 約 15µs (速い時) 〜 約 100〜130µs (遅い時)**。検収再計測 (`tests/rtt_bench.mjs`, 20k 回×3 を 5 試行) は大半が 86〜110µs で 16〜17µs は 2/15 回。コールド (最初の 500〜2,000 回) 65〜134µs。15µs は常時値ではない |
| MCP JSON-RPC (`host/mcp_rpc.mjs`) | tools/list=48、tools/call 成功、未知 tool は isError=true |
| MIDI 経路 (`fl_rt.dispatch_midi`) | OnMidiIn→OnMidiMsg→OnNoteOn の FL 順、`handled` 反映 |
| headless Chrome | crossOriginIsolated=true、module Worker + SAB RPC で同 PoC 成功 |

方針: **現行 = 別 Worker + SAB RPC (provider だけ差替で FLEngine wasm の C ABI `fl_api_call` に接続)**、**最終形 = CPython を FLEngine wasm に静的リンク** (JS 往復 0、FL と同じ同一スレッド callback)。

## 6. 再現 / ファイル

`bash tools/python/run_all.sh` が下記を順に実行 (全て PASS で `== ALL OK`)。
`fetch_inputs.sh`(FL 由来 pyc/py を `work/` へ。**git 非管理**) → `build_cpython_wasm.sh` → `analysis/{mcp_extract,flapi_extract,flapi_table,scripts_inventory}` → `build_flpy.sh` → `tests/{smoke_direct,poc_mcp,all_tools,browser_check}` → `mcp_classify`/`py_inventory`。
`src/`=flpy.c, flhost_lib.js, fl_api.py, fl_rt.py / `host/`=flpython, py_worker, rpc, fl_mock, mcp_rpc / 成果物は `dist/`(gitignore)。`tests/rtt_bench.mjs` は検収で追加した往復コスト計測 (run_all.sh 対象外)。

## 7. 未解決・ブロッカー・留意

- **FL 側 Python C API 呼出し面は未抽出**: dlsym 先の関数名が平文で無い。サブインタプリタ運用 (`PyInterpreterConfig` 型の存在から示唆のみ) の実態は不明。wasm で `Py_NewInterpreterFromConfig` が動くかも未検証。
- `mixer.getCurrentTempo(1)`/`setCurrentTempo(bpm,1)` の第 2 引数の意味 (MCPTools は素の BPM 扱い、公式 docs は ×1000) は**実機で未確認**。モックは MCPTools 側に合わせた。
- FLEngine 側 flapi 実装は**モック(27 API を実装、他は None)**。実エンジンとの意味差 (引数省略時の既定値、-1 の意味) は実機/lift 後に検証が必要。
- 引数名 (kwargs) は stubs 由来の署名がある関数のみ。新規 43 関数と ilmcp は位置引数のみ (rodata の書式文字列 `i if sdd…` は順序対応が曖昧で未採用)。
- 旧 stubs (LGPL) は**参照入力のみ**でリポジトリ非同梱 (`fetch_inputs.sh` が clone)。FL 由来 pyc/py も非同梱 — 利用者の FL から実行時供給。EULA 判断は行わない (事実整理のみ)。
- 呼出しコストは node/Chrome headless の mock 実測。実 FLEngine(wasm) 結合時に再計測要。
- **MCPTools 内のテンポ規約が不整合に見える**: `get_session_context` は `mixer.getCurrentTempo()` (引数なし) を `/1000` して BPM 化、`get_tempo` は `getCurrentTempo(1)` を素の BPM として表示、`set_tempo` は `setCurrentTempo(bpm, 1)`。モックは後者に合わせたため `get_session_context` が `tempo_bpm: 0.13` を返す (`mcp_classification.json` 側の解析メモ)。どちらが実 FL の挙動かは未確認。
- flapi 435 関数のうち doc 無し 36 (ui 27 + ilmcp 9): ui の 27 は stubs の関数名辞書と rodata 窓内トークンの一致で補完 (`flapi_extract.py`)。doc 無しの *新規* 関数は stubs 辞書に無いため抽出漏れの可能性がある (doc 付きの新規 34 は rodata から直接抽出)。
- 「LGPL stubs 非同梱」はファイルとしての話: stubs 由来の署名 (引数名/型/既定値、394 関数・535 引数) と callback 名 26 が `flapi_table.json` に取り込み済み (docstring 本文は無し)。`flapi_table.json` の doc 欄 (≤66 字) と `raw_*.json` は FLEngine rodata の抽出文字列、`mcp_tools.json` / `MCP_TOOLS.md` の description は MCPTools.pyc の先頭 160 字。
- 再ビルドで成果物バイト数は ±0.2% 程度変動 (クリーン再ビルドで wasm 5,921,416 / data 3,204,697 / js 120,269、検収時)。

## 7b. PY-1 flapi provider (C `fl_api_call`, #74 — 2026-10-13)

`provider/` = `fl_api_call(fn_id, const fl_slot* argv, int argc, fl_slot* ret)` (16B スロット ABI は §5 / BRIDGE.md §2 と同一)。`gen_provider.py` が `flapi_table.json` + `flapi_ids.json` から `provider/gen/fl_table.c` (fn_id 順の記述子 435 行: 戻り型・引数数・型列) を生成し、`fl_dispatch.c` が個数/型検査・戻り型・エラー code を担う。ハンドラ (`fl_engine.c`) は `FL_H(module, name)` を weak 参照するだけなので、未実装は表に NULL で入り "Unspecified error (not implemented: …)" (code 2) を返す。`host/fl_provider.mjs` が `createMockEngine()` と同じ `engine.call(name,args)` で包む (Worker/SAB RPC は無変更)。

| 項目 | 実測 (コミット済み HEAD, node 22, 16 core, load avg 0.3〜0.6) |
|---|---|
| 実装ハンドラ | **60** = MCPTools 静的参照の全て (公開 52: channels 18 / mixer 18 / plugins 7 / playlist 4 / ui 3 / transport 2 + ilmcp 8)。残り 375 は未実装 (`tests/provider_check.mjs` が 60/375 を assert) |
| `tests/all_tools.mjs` (`FL_ENGINE=wasm`) | **48/48 ok**、soft_error 0・raised 0、host_calls 37,424、callback 往復 true。所要 1.96〜2.04 秒 (mock 2.03 秒)。tool 別の結果文字列・api_calls は mock と **48/48 完全一致** (`tool_coverage.json` との差 0 件) |
| `tests/provider_check.mjs` | PASS: 戻り型 (C 側: float=`D`/int=`I`/bool/str/None/JSON) が Python 型で float/int/bool/str/dict、kwargs 経由、code 4 → `IndexError`、code 5 → `TypeError`、未実装 → `RuntimeError` |
| wasm | `flprov.wasm` 42,953B (`-O2`、provider 単体)。CPython と同一 wasm にはまだ入れていない (T2) |
| ネガティブコントロール | `mixer.getTrackName` ハンドラを削除して再ビルド → all_tools **33/48 ok・soft_error 15・host_calls 1,079**、provider_check は「MCP 使用 mixer.getTrackName が未実装」で失敗 (= テストが実際に C 実装を踏んでいる) |

mock との差で見つかったもの: mock は引数の個数/型を検査しないため通っていた呼出しを C 側が拒否した (`ilmcp.showHighlight` の `whenDone` 内の 3 引数呼出し → 個数 3〜5 を許可に修正)。`getChannelName` 等は署名の引数数 (index, useGlobalIndex) を超えると code 5。

エラー code の割当 (`provider/fl_api.h`): FLEngine PE の文言 9 種 (Invalid value / Unspecified error / Operation unsafe at current time / Range error / Index out of range / Wrong number of function parameters or wrong parameter type / Linked device not assigned / Device not assigned / Plugin not valid) を 1〜8 に割当 (`Range error` と `Index out of range` は 4 に束ねた)。provider が実際に返すのは 2 / 4 / 5 のみで、1 (Invalid value)・3 (unsafe)・6〜8 は定義だけ (実エンジンの発生条件が未解明)。**数値は Python 側 `fl_api._ERR` の写像と整合させた暫定値で、実エンジンの数値は未確認**。

再現: `bash provider/build.sh && node tests/provider_check.mjs && FL_ENGINE=wasm node tests/all_tools.mjs` (前提: `build_flpy.sh` 済み。runner では `EMSDK_ENV=<emsdk>/emsdk_env.sh`、`FL_WIN64_DIR`)。

## 8. ユーザ依頼事項

特になし (全て既存素材で完結)。任意: 実機 FL で `mixer.getCurrentTempo(1)` の戻り値 (130 か 130000 か) を確認できれば §7 の 2 点目が解消。

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
| T9 | 実機 FL でのモック意味差検証 (ユーザ環境があれば) と kwargs 署名の rodata 書式文字列からの自動復元 | S |
