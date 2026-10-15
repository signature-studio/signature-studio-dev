# G python-mcp — CPython wasm + flapi/MCP 解析 + ブリッジ設計 (2026-10-10)

> 行数上限 (250 行) のため、§7c (#82)・§9 (T1〜T9 表)・§PY-13 (#588)・§12・§13 (#81) の全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md)、§15 (#654) の全文は [REPORT_PY16.md](REPORT_PY16.md) に分割移動 (本体は要約のみ)。channels 7 関数の PE 解析 (PY-39, #1527) は [REPORT_PY39.md](REPORT_PY39.md)。

## 結論 (先出し)

1. **CPython 3.12.1 (FL 同梱版と完全一致) の emscripten/wasm ビルド成功**。パッチ無し、emsdk 6.0.12 でクリーンビルド 3m19s。node で `print(1+1)`=2、struct/json/zlib/hashlib/decimal/re/datetime/inspect 等が動作。`flpy.wasm` **5.92MB** (gzip 2.07MB) + `flpy.data` (stdlib zip) 3.20MB。
2. **FL の組込 Python API 面を実測**: 公開 12 module **426 関数** + FL 内部 `ilmcp` 9 = **435 関数** (公開 stubs 旧版 392 に対し +34 が 26.1.7 新規)。他に `flpianoroll`(64 メンバ)/`flcpt`/`flrack`/`fl`、MIDI script callback **27**。
3. **MCPTools.pyc = 48 tools** (「50」ではない)。逆アセンブルは同一 3.12.1 の marshal/dis。**外部通信は pyc 内に 0 件** (import は stdlib 10 + FL module 12 のみ)。分類 **A local-flapi 38 / B local-ilmcp 8 / U Gopher-UI 付随 2 / X 対象外 0**。LLM ゲートウェイ (Gopher WebView `window.flHelper`) は pyc の外で、対象外。
4. **PoC 成功**: wasm Python を Web Worker で起動し、SAB 同期 RPC で flapi モック (FLEngine 模擬) に接続、**FL 同梱 `MCPTools.pyc` を FL と同じく `__main__` として実行して 48/48 tools が成功** (例外なし・エラー文言なしの意味。モックの戻り値のため FL 実機と同一動作の保証ではない。37,425 flapi 呼出し。HEAD e9f46a0 の実測。内訳は REPORT_APPENDIX §7c 検証 2)。Python→ホスト callable 呼戻し・MIDI callback 経路・MCP JSON-RPC (tools/list, tools/call) も確認。**headless Chrome (cross-origin isolated, module Worker) でも成功**。
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

- **FL 側 Python C API 呼出し面は抽出済み (§7d で訂正: 名前は UTF-16LE で PE 内にあり 110 件抽出済み)。以前の記述: dlsym 先の関数名が平文で無い。サブインタプリタ運用 (`PyInterpreterConfig` 型の存在から示唆のみ) の実態は不明。wasm で `Py_NewInterpreterFromConfig` が動くかも未検証 (→ §11 で検証: 動く。`_flhost` は PY-12 #587 で対応済み = PY-12 節)。
- `mixer.getCurrentTempo(1)`/`setCurrentTempo(bpm,1)` の第 2 引数の意味 (MCPTools は素の BPM 扱い、公式 docs は ×1000) は**実機で未確認**。モックは MCPTools 側に合わせた。
- FLEngine 側 flapi 実装は**モック(27 API を実装、他は None)**。実エンジンとの意味差 (引数省略時の既定値、-1 の意味) は実機/lift 後に検証が必要。
- **kwargs 署名の静的復元 (PY-9 b, #81) 済み**: rodata の並び順ではなく、FLEngine (win PE) の `.data` 内メソッド表 (name/fn/flags/doc, 32B 刻み) と各ラッパー冒頭の `lea [rip+x]` から `PyArg_ParseTupleAndKeywords` の書式と kwlist を復元 (`analysis/flapi_kwargs.py` → `analysis/flapi/flapi_kwargs.json`、`flapi_table.json` の各関数に `kwsig` を追記)。結果は §12。
- 旧 stubs (LGPL) は**参照入力のみ**でリポジトリ非同梱 (`fetch_inputs.sh` が clone)。FL 由来 pyc/py も非同梱 — 利用者の FL から実行時供給。EULA 判断は行わない (事実整理のみ)。
- 呼出しコストは node/Chrome headless の mock 実測。実 FLEngine(wasm) 結合時に再計測要。
- **MCPTools 内のテンポ規約が不整合に見える**: `get_session_context` は `mixer.getCurrentTempo()` (引数なし) を `/1000` して BPM 化、`get_tempo` は `getCurrentTempo(1)` を素の BPM として表示、`set_tempo` は `setCurrentTempo(bpm, 1)`。モックは後者に合わせたため `get_session_context` が `tempo_bpm: 0.13` を返す (`mcp_classification.json` 側の解析メモ)。どちらが実 FL の挙動かは未確認。
- flapi 435 関数のうち doc 無し 36 (ui 27 + ilmcp 9): ui の 27 は stubs の関数名辞書と rodata 窓内トークンの一致で補完 (`flapi_extract.py`)。doc 無しの *新規* 関数は stubs 辞書に無いため抽出漏れの可能性がある (doc 付きの新規 34 は rodata から直接抽出)。
- 「LGPL stubs 非同梱」はファイルとしての話: stubs 由来の署名 (引数名/型/既定値、394 関数・535 引数) と callback 名 26 が `flapi_table.json` に取り込み済み (docstring 本文は無し)。`flapi_table.json` の doc 欄 (≤66 字) と `raw_*.json` は FLEngine rodata の抽出文字列、`mcp_tools.json` / `MCP_TOOLS.md` の description は MCPTools.pyc の先頭 160 字。
- 再ビルドで成果物バイト数は ±0.2% 程度変動 (クリーン再ビルドで wasm 5,921,416 / data 3,204,697 / js 120,269、検収時)。

## 7b. PY-1 flapi provider (C `fl_api_call`, #74 — 2026-10-13)

`provider/` = `fl_api_call(fn_id, const fl_slot* argv, int argc, fl_slot* ret)` (16B スロット ABI は §5 / BRIDGE.md §2 と同一)。`gen_provider.py` が `flapi_table.json` + `flapi_ids.json` から `provider/gen/fl_table.c` (fn_id 順の記述子 435 行: 戻り型・引数数・型列) を生成し、`fl_dispatch.c` が個数/型検査・戻り型・エラー code を担う。ハンドラ (`fl_engine.c`) は `FL_H(module, name)` を weak 参照するだけなので、未実装は表に NULL で入り "Unspecified error (not implemented: …)" (code 2) を返す。`host/fl_provider.mjs` が `createMockEngine()` と同じ `engine.call(name,args)` で包む (Worker/SAB RPC は無変更)。

| 項目 | 実測 (HEAD b76d221, GitHub Actions runner, node 22.23.3, load average 0.08〜0.46) |
|---|---|
| 実装ハンドラ | **60** = MCPTools 静的参照の全て (公開 52: channels 18 / mixer 18 / plugins 7 / playlist 4 / ui 3 / transport 2 + ilmcp 8)。残りは未実装 (`tests/provider_check.mjs` が期待集合 `tests/provider_expect/` から件数を導出して assert。件数の実測は REPORT_PY280.md) |
| `tests/all_tools.mjs` (`FL_ENGINE=wasm`) | **48/48 ok**、soft_error 0・raised 0、host_calls 37,424、callback 往復 true。所要 2.08 / 2.11 / 2.25 秒 (3 回、b76d221 クリーン再ビルド後。mock 2.06 秒)。`provider_check` 0.33 秒、`poc_mcp` (mock) 1.21 秒 POC OK で回帰なし。tool 別の結果文字列・api_calls は mock と **48/48 完全一致** (`tool_coverage.json` との差 0 件) |
| `tests/provider_check.mjs` | PASS: 戻り型 (C 側: float=`D`/int=`I`/bool/str/None/JSON) が Python 型で float/int/bool/str/dict、kwargs 経由、code 4 → `IndexError`、code 5 → `TypeError`、未実装 → `RuntimeError` |
| wasm | `flprov.wasm` 43,225B (`-O2`、provider 単体、b2225e1。b76d221〜d2706e1 は 42,953B)。CPython と同一 wasm にはまだ入れていない (T2) |
| ネガティブコントロール | `mixer.getTrackName` ハンドラを削除して再ビルド → all_tools **33/48 ok・soft_error 15・host_calls 1,079**、provider_check は「MCP 使用 mixer.getTrackName が未実装」で失敗 (= テストが実際に C 実装を踏んでいる) |

mock との差で見つかったもの: mock は引数の個数/型を検査しないため通っていた呼出しを C 側が拒否した (`ilmcp.showHighlight` の `whenDone` 内の 3 引数呼出し → 個数 3〜5 を許可に修正)。`getChannelName` 等は署名の引数数 (index, useGlobalIndex) を超えると code 5。

エラー code の割当 (`provider/fl_api.h`): FLEngine PE の文言 9 種 (Invalid value / Unspecified error / Operation unsafe at current time / Range error / Index out of range / Wrong number of function parameters or wrong parameter type / Linked device not assigned / Device not assigned / Plugin not valid) を 1〜8 に割当 (`Range error` と `Index out of range` は 4 に束ねた)。provider が実際に返すのは 2 / 4 / 5 のみで、1 (Invalid value)・3 (unsafe)・6〜8 は定義だけ (実エンジンの発生条件が未解明)。**数値は Python 側 `fl_api._ERR` の写像と整合させた暫定値で、実エンジンの数値は未確認**。

再現: `bash provider/build.sh && node tests/provider_check.mjs && FL_ENGINE=wasm node tests/all_tools.mjs` (前提: `build_flpy.sh` 済み。runner では `EMSDK_ENV=<emsdk>/emsdk_env.sh`、`FL_WIN64_DIR`)。
入力の用意 (mac pkg 無しの Actions): `oc_artifacts: fl-win64 toolchain-emsdk` + `FL_WIN64_DIR=<fl-win64 展開先> bash fetch_inputs.sh` (パスは `tools/shared/env.sh` 経由。`$FL_MAC_DIR` に mac pkg が無ければ win64 の `block25159_DATA.bin` = MCPTools.pyc、`block24429_DATA.bin` = midi.py (770 行)、`block24430_DATA.bin` = utils.py (213 行) を `work/` に置く)。続けて `build_cpython_wasm.sh` → `build_flpy.sh` (`build_flpy.sh` は先頭で `analysis/flapi_table.py` を再実行する。入力は環境変数 `FL_WIN64_DIR`/`FL_WIN_PE`・`FL_STUBS_DIR`・`FL_ENGINE_DYLIB`・`FLAPI_OUT_DIR`・`EMSDK_DIR` で指定でき、win PE / stubs 欠落・PE 照合 0 件は exit 2 + 理由表示で止まる。詳細は §PY-13)。

### 7b-2. レビュー指摘 (d2706e1) の修正: `ilmcp.getBrowserNames` の固定バッファ

原因 (`snprintf` 連結の戻り値で境界を越えて書いた) と修正 (`json_str`/`buf_add` の残量判定・code 4)・ASan と NC の全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §7b-2。
現況 (8674fa6): 固定バッファは消滅 (`json_str`/`buf_add` 削除、結果は malloc して `fl_ret_json` でコピー)。このため `provider_check.mjs` 節 2b の溢れ 5 ケースを削除し、長大入力 (`\x01`×100000 → code 1) の検査に置換した。

### 7b-4. device 5 関数 (MIDI scripting 用) を C 実装 (#74)

mock と差分 0 の device 5 関数を C 側に実装。結論・実測は [REPORT_PY74.md](REPORT_PY74.md) §7b-4。
### 7b-3. ilmcp 8 ハンドラを `host/ilmcp.mjs` の意味論に合わせる (#74, PR #763 / 8674fa6)

getBrowserNames (木・不明パス code 1)・getHighlightNames (21 件)・addChannel/addEffect/storePRScript の検証を JS ホストと一致させた。データは `gen_provider.py` が `analysis/ilmcp/*.json` から `provider/gen/ilmcp_data.h` を生成 (dir 28 / plugin 141 / highlight 21)。`tests/ilmcp_diff.mjs` (新規): 呼出し 32 + 状態 9、diffs 0。ネガティブコントロール (addEffect の plugin 名検証を外す) で 2 件差分。実測・検証表は [REPORT_PY74.md](REPORT_PY74.md) §7b-3。

## 7d. CPython を provider と同一 wasm に静的リンク (PY-2, #83 / #115) — 全文は `REPORT_PY2.md`

結論: `build_flpy_static.sh` で CPython + flapi provider を 1 つの wasm (`flpy_static.wasm`) にリンクし、`_flhost.call` を同一 wasm 内 C 呼出しにした。48/48 tool が SAB+provider 版・モック版と tool 別差 0/48、Python 込み往復は median 0.34µs (Worker+SAB 版 25〜27µs)。FL の `Py_*` 動的束縛 110 名を PE (`0xc395a0`) から機械抽出し (§7 の「未抽出」を訂正)、109 件が `libpython3.12.a` に存在・1 件は Py_REF_DEBUG 限定。実 FLEngine wasm へのリンクは未実施。1 コマンド: `node tests/static_check.mjs` (前提 `build_flpy_static.sh`)。

## 8. ユーザ依頼事項

特になし (全て既存素材で完結)。任意: 実機 FL で `mixer.getCurrentTempo(1)` の戻り値 (130 か 130000 か) を確認できれば §7 の 2 点目が解消。

## 7c. ilmcp 9 関数の実装 (PY-3 / #82) — `host/ilmcp.mjs`

**結論**: `ilmcp` 9 関数を JS ホスト (`host/ilmcp.mjs`) に実装し、実 `MCPTools.pyc` 上の class B 8 tool を FLEngine 側状態検査で確認 (`tests/ilmcp_e2e.mjs` 25/25)。**受入条件「実エンジン上で動作」は未達** (PR は `Refs #82`)。引数規約・データ・検証表・仮定・未解決の全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) (§7c を 250 行上限のため分割移動)。

## 9. 下流チケット案

T1〜T9 の表は 250 行上限のため [REPORT_APPENDIX.md](REPORT_APPENDIX.md) に分割移動した。T3 = PY-3 (本 §7c)・T4 = PY-4 (§10)・T6 = PY-6 (§11) は着手済み。

## 10. MCP JSON-RPC をアプリ UI / devtools に公開 (PY-4, #77)

既知類型との関係: 該当なし (lift / 逆アセではない。flapi は引き続き `fl_mock.mjs` = FLEngine 模擬)。

- 公開面: `window.flMcp` (`start(files)` `rpc(req)` `list()` `call(name,args)` `stop()`) + `/?mcp=1` の UI パネル。実装 `src/runtime/mcp_panel.ts`、配信 `vite.config.ts` `pyAssets` (`/py/` = host/・dist/flpy.{js,wasm,data}・flapi_ids.json・ilmcp の 2 JSON の許可リストのみ)。設計は `BRIDGE.md` §3。
- `mcp_rpc.mjs` 変更: `tools/call` は `tools/list` に出る name だけ受理 (未知 / 非 tool は isError=true。変更前は `__main__` の任意属性を呼べた)、不正 JSON は -32700。`flpython.mjs` は呼出し側が Worker を渡せる `worker` 引数を追加 (既存呼出しは無変更)。
- MCPTools.pyc / midi.py / utils.py は**配信しない**: 利用者が UI のファイル選択 (または `flMcp.start({...})`) で供給する。未供給の `start()` は「供給が必要」で reject。

| 受入条件 | 結果 | 検証 (`node tools/python/tests/mcp_ui_check.mjs`) |
|---|---|---|
| アプリ内から tools/list = 48、tools/call 実行 | 達成 (UI・devtools 両方) | UI で状態表示 `tools/list = 48`・`get_tempo` 実行 `Current tempo is 130 BPM.`。devtools で `flMcp.rpc` の tools/list = 48 (inputSchema あり・id エコー)、`set_tempo(140)` → `get_tempo` = 140 |
| MCPTools.pyc は実行時供給 (非同梱) | 達成 | `/py/work/MCPTools.pyc` `/py/work/midi.py` `/py/src/fl_rt.py` は 404、未供給 `start()` は reject。リポジトリ内に FL 由来ファイル無し (`work/` は gitignore) |
| 未知 tool は isError=true | 達成 | `no_such_tool` と非 tool 属性 `get_mcp_tools_json` が isError=true、既知 tool に不正引数も isError=true |

検証環境: Actions runner (4 core, node 22.23.3, Chrome 154.0.8037.97)。入力は `fl-win64` 素材の `extracted/block25159_DATA.bin` (MCPTools.pyc, 100,674B, magic cb0d0d0a) / `block24429_DATA.bin` (midi.py) / `block24430_DATA.bin` (utils.py) を `work/` へコピー。CPython wasm は本 run でクリーンビルド (3m13.8s)。
実測 (コミット 281784f の HEAD、n=3): `mcp_ui_check.mjs` 全 14 check PASS、スクリプト内計測 1.261 / 1.362 / 1.308 秒 (wall 1.39 / 1.49 / 1.44 秒、load average 0.18〜0.57、直列 1 本)。同 HEAD で `pnpm typecheck` / `pnpm build` 成功、既存 `poc_mcp.mjs` POC OK・`all_tools.mjs` 48/48 ok (host_calls 37,424)・`browser_check.mjs` BROWSER OK。範囲外: `run_all.sh` 全体 (runner に win PE が無く analysis 再生成が走らないため未実施)。
ネガティブコントロール: MCPTools.pyc の先頭 1 バイトを壊す (`--neg`) → `UI: tools/list = 48` が FAIL し、原因が `pyc magic mismatch` として UI に出る (ハングしない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| flapi の提供側がモック (`fl_mock.mjs`) のまま。実 FLEngine wasm の `fl_api_call` に差替え未了 | tool の結果はモック値で、実 FL と同一動作の保証なし | #74 (PY-1, PR #459) 以降 / 親 #35 |
| ilmcp B 群 8 tools は JS ホスト・C provider とも状態機械の模擬 (実 FLEngine 未接続) | 戻り値・code の FL 実機一致は未検証。意味論は `host/ilmcp.mjs` と `tests/ilmcp_diff.mjs` で一致 (§7b-3) | #74 (実 FLEngine 上の 38 tool 成功が受入条件) |
| 非 ASCII 空白の扱い: JS `norm` (trim) と C `browser_key` (isspace) が不一致 | ASCII 入力では差分 0。`\u00a0` 付きパスで JS 成功・C code 1 | #74 の子チケット (REPORT_PY74.md 未解決) |
| `/?mcp=1` のパネルは最小 UI (整形・履歴・複数行 arguments 編集なし)。`pnpm build` 成果物 (`dist/`) は `/py/` を持たないため dev / preview 専用 | 本番配信での公開は未対応 | 親 #35 に提案 (配信設計は #62 H 系と調整) |
| (解消) `build_flpy.sh` の `flapi_table.json` 再生成が win PE / stubs 無しで黙って劣化する | #588 (PY-13) で env 化・入力欠落は exit 2 | §PY-13。`fetch_inputs.sh` / `run_all.sh` の `/home/ubuntu` 固定パスは別途 (下の未解決表) |

## 11. MIDI scripting ホスト (PY-6, #76)

既知類型との関係: 該当なし (lift / 逆アセではない。flapi は引き続き `fl_mock.mjs` = FLEngine 模擬)。検証起点 commit `3e25620`。

**結論**: 受入条件 2 件 (callback 27 個の配送表・同梱 device script (Forward CCs to current plugin Port 10) の動作) は**達成** (後者は fl-win64 付き再実行 = 下記「同梱 device script」で確定。flapi は `fl_mock.mjs` の模擬上で、実 FLEngine 上ではない)。サブインタプリタは **wasm で動く** が、現行 `_flhost` は未対応で、device script 配送には**不要**と判断 (下記)。

- **device script ローダ** (`src/fl_rt.py`): `load_device_script(name, source|path, port)` が script ごとに独立した module namespace で実行 (`# name=` 等のヘッダも解釈)。例外は FL と同様 stderr に traceback を出して続行し、`errors` に記録 (他 script の配送は継続)。
- **配送表** (`fl_rt.CALLBACKS`): 27 個 = lifecycle 3 (OnInit/OnInitAll/OnDeInit)・受信 MIDI 10・MIDI Out 1・host 通知 13。引数の個数が表と違う呼出しは reject。順序と停止は公開 stubs 文書 (callbacks / FlMidiMsg.handled) に従う: OnMidiIn → OnMidiMsg → 型別 (OnNoteOn…、sysex は OnSysEx)、各 callback が返った時点で `handled` なら以降を呼ばない (PoC は OnMidiIn の handled を無視していたため是正)。`flmidimsg` の note/velocity/controlNum… は data1/data2 の別名 (書込み双方向)、midiId/midiChan は文書上「常に 0」に合わせた (PoC は midiChan=status&0xF)。
- **Web MIDI 結線** (`host/midi_host.mjs` `MidiScriptHost.attachWebMidi`): 全入力の `onmidimessage` → `midiIn` (直列キューで到着順を保存)。port は `portMap[id|name]` か接続順の連番、script 側は `port` 一致 (port 無指定は全ポート) だけに配送。アプリ側 `src/runtime/midi_script.ts` が `window.flMidi` (devtools) と `/?midi=1` の UI パネルを公開。device script は利用者が実行時に供給 (配信物に非同梱、`/py/` の許可リスト方式は PY-4 のまま)。

### 検証 (Actions runner 4 core, node 22.23.3, Chrome 154.0.8037.97, emsdk 6.0.12。load average 0.72〜0.84、直列 1 本)

| 受入条件 / 項目 | 結果 | 検証 (`tools/python/` から) |
|---|---|---|
| callback 27 個の配送 | 達成 | `node tests/midi_script.mjs`: 23 check PASS。表 27 = FLEngine rodata 27 (`midi_script_callbacks_in_binary`)、引数 26 = stubs 署名。合成 recorder (27 全定義) へ全 callback を想定引数で 1 回ずつ配送、受信 MIDI 8 種 (0x80〜0xE0・sysex) が OnMidiIn→OnMidiMsg→型別の順 |
| handled / port / 例外 | 達成 | handled で停止 (OnMidiIn・OnMidiMsg 各)・0xF8 は型別なし・port 不一致は非配送・例外の隔離と stderr traceback・未知 callback / 個数不一致 / 不正バイトは reject |
| Web MIDI → dispatch 結線 | **偽 MIDIAccess で達成**・実デバイス未検証 | node 偽 access: 200 件連投が到着順、portMap・後から接続した入力・detach。Chrome (`node tests/midi_ui_check.mjs`, ルートから): UI でファイル供給→起動→OnInit→60 件連投・port 別配送・devtools から注入、14 check PASS。**実 Chrome の `requestMIDIAccess` はこの runner で `InvalidStateError: Platform dependent initialization failed`** (MIDI backend なし) |
| 同梱 device script の動作 | **達成** (実ファイル・mock flapi 上) | `node tests/midi_bundled_device.mjs`: 9 check PASS。詳細は下記「同梱 device script」 |
| サブインタプリタ | 下記 | `node tests/subinterp_probe.mjs`: 12 check PASS |

実測 (n=3): `midi_script.mjs` wall 0.59〜0.60 秒。MIDI 1 件のフル配送 (Worker + SAB RPC、OnMidiIn+OnMidiMsg+OnNoteOn の 3 callback) は逐次 137〜143 µs・パイプライン 129〜137 µs (1000 件当り)。`midi_ui_check.mjs` スクリプト内 1.292 / 1.322 / 1.541 秒。`subinterp_probe.mjs` wall 5.09〜5.10 秒。`pnpm typecheck` / `pnpm build` 成功。`flpy.wasm` 5,923,783B / `flpy.data` 3,214,338B / `flpy.js` 120,351B (本 run のリンク。§1 の 5,920,419B との差は同表記の再ビルド変動の範囲で、因果は未切り分け)。CPython クリーンビルド (tgz 取得+native+wasm+記録) 210 秒 (4 core, ログの開始/終了時刻差)。

ネガティブコントロール (終了コード 1 = 検出): `midi_script.mjs --neg` (recorder から OnDirtyChannel を消す → 「27 全配送」だけが FAIL、26/27 と欠落名を表示)・`midi_ui_check.mjs --neg` (構文エラー入り script → 「2 script 読込」だけが FAIL、UI に SyntaxError)・`subinterp_probe.mjs --neg` (拒否 builtin の期待を 1 本欠く → その check だけ FAIL)・`midi_bundled_device.mjs --neg` (midi.py 無し → 読込 check が FAIL)。通常実行の FAIL は exit 2、入力欠落は exit 3 (緑にならない)。

### 同梱 device script (fl-win64 26.1.7.5653 で実測)

結論: 同梱 device script (Forward CCs to current plugin Port 10) は mock flapi 上で 9 check PASS ×3・ネガコン 2 種が検出 (検証 commit `f40fac7`)。入力の所在・挙動・再測定・ネガコン・限界の全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §11b。**#601 (load 失敗の巻き戻し)** の全文も同じく §11b。

### サブインタプリタ (`flpy_subinterp_run` = 検証用 export)

| 項目 | 実測 |
|---|---|
| `Py_NewInterpreterFromConfig` | **3 構成とも成功** (isolated+OWN_GIL / isolated+SHARED_GIL / legacy)。スレッド無しの wasm でも OWN_GIL が成立。破棄後に main は継続 |
| stdlib | FL 同梱スクリプトが使う 22 module は isolated で全て import 可 |
| builtin 66 本 | isolated で拒否 5 本 (`_elementtree _flhost _lsprof faulthandler pyexpat`、"does not support loading in subinterpreters")。legacy は 0 本 |
| 隔離 | isolated は main の `__main__` 変数・`sys.modules` を共有しない |
| コスト | 作成+`import json, re`+実行+破棄 = 26.74〜28.21 ms/個 (50 個ずつの平均を 1 run 3 batch、3 run)。150 回後も線形メモリ 33,554,432B のまま (増加なし) |
| **`_flhost`** (PY-6 時点・PY-12 #587 で解消 → PY-12 節) | isolated では import 不可 (`Py_mod_multiple_interpreters` 未宣言。3.12.1 の既定は非対応)。**legacy では import できるが、`flhost_exec` が static 変数 (`json_loads`/`HostError`/`g_cbs`) を上書きし、サブインタプリタ破棄後に main の `_flhost.call` が壊れる** (trap `memory access out of bounds` / `NameError: isinstance` 等、症状は不定) |

判断 (推定を含む): device script の配送は script ごとの module namespace で足りるため、サブインタプリタは**採用しない**。違いは `sys.modules` を共有する点 (script 間で `utils` 等が共有される)。FL が script ごとにインタプリタを分けているかは `PyInterpreterConfig` 型名の存在以外に証拠が無く未確認。将来必要になれば `_flhost` を module state 化 + `Py_mod_multiple_interpreters` 宣言する改修が前提 (下表)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実ブラウザ / 実 MIDI デバイスでの Web MIDI 受信が未検証 | 結線は偽 MIDIAccess のみ | #37 (AU-14) にコメント。手元ブラウザでの `flMidi.connectWebMidi()` 実行を依頼 |
| host 通知 13 個と OnMidiOutMsg の**発火元** (OnIdle の 20ms 周期・OnRefresh フラグ・OnUpdateMeters の `device.setHasMeters` ゲート等) は FLEngine 側の責務で、本実装は配送面のみ。OnInitAll の意味 (全 script の OnInit 後に 1 回) は名前からの推定 | エンジン結合時に発火条件を別途実装・実機確認 | 親 #35 に提案 (FLEngine 結線チケット) |
| 文書 (公開 stubs) 由来の仕様 (handled 伝播・midiId/midiChan=0・timestamp=0) は 26.1.7 実機で未確認 | 他の同梱 script が midiChan 等に依存すると差が出る | 同梱 script (Forward CCs) は midiChan/midiId を使わないため差は出ない。他の同梱 script・`event.status` の ch 含有は実機があれば #35 |
| mock の `device.*` は forwardMIDICC / midiOutMsg の記録と 3 関数のみ。実エンジン未接続 | 同梱 script が他の device API を使うと None が返る (`midi_bundled_device.mjs` は未実装 API 呼出しを FAIL にする) | #74 (PY-1) 以降 / 親 #35 |
| PY-4 の `poc_mcp.mjs` / `all_tools.mjs` / `mcp_ui_check.mjs` は MCPTools.pyc が無く再実行不可 (本 run で `dispatch_midi` の PoC 区間のみ `midi_script.mjs` に複製して同結果を確認) | `fl_rt.py` / `fl_mock.mjs` の変更の回帰を全体では未確認 | 本 run (fl-win64 付き) で `midi_script` / `poc_mcp` / `all_tools` / `midi_ui_check` を個別に再実行し PASS (上記「回帰」)。`run_all.sh` 全体 (FL バイナリ抽出の step 4 など win PE / mac dylib 要) は未実行 |
| `_flhost` の per-module state 化 + `Py_mod_multiple_interpreters` 宣言 | 解消 | #587 (PY-12) で実装 → PY-12 節 |
| (解消) `build_flpy.sh` の `flapi_table.json` 再生成 | #588 (PY-13) で env 化 | §PY-13 (`REPORT_APPENDIX.md`) |

## PY-12 (#587): `_flhost` の per-module state 化 — 実測・全文は `REPORT_PY12.md`

**結論**: 受入条件 3 件とも達成 (`_flhost` を module state 化し `Py_mod_multiple_interpreters` 宣言、isolated で import 可・破棄後も main 無傷、採用判断材料あり)。**採用判断: 採用しない** (隔離の代償が module namespace 分離の数百倍)。

## PY-7 (#78): Chord progression 41 本の import / 実行 (mock 条件つき)
結論: 41/41 import・実行 (wasm, mock 値あり・根拠なし)。ネガコン 7 FAIL exit 1。全文・mock 表: [REPORT_PY7.md](REPORT_PY7.md)。

## PY-13 (#588): `build_flpy.sh` の flapi_table 再生成を環境変数化
入力 (win PE / stubs / mac dylib / 出力先 / emsdk) を環境変数化し、欠落時は exit 2 (旧: 空入力で緑)。検証 `tests/flapi_table_check.sh` (3 回とも exit 0・2.20 秒・正常系 3/3 一致・ネガコン 6 本 exit 2)。全文・未解決 (#630 PY-15 ほか): [REPORT_APPENDIX.md](REPORT_APPENDIX.md)

## 12. kwargs シグネチャの静的復元 (PY-9 b, #81)
FLEngine の PyMethodDef 表から 435/435 関数を対応付け、書式 303 関数・kwlist 103 関数を復元 (flags=4 の 125 件は書式無し)。`fl_api.bind` は kwlist 名を stubs 名より優先し、既定値が静的に不明な引数の省略後は後続の既定値を足さない (`getGridBit(index=1)` → `(1,)`)。stubs 名とは 66 一致 / 28 不一致 (バイナリを正とする)。再現: `FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi_kwargs.py` の後 `python3 tests/kwsig_check.py` (0.03〜0.04 秒)。wasm 回帰 (`all_tools.mjs` 48/48 ほか)・stubs 照合の例・`arrangement.selectionSet` の kwlist 重複の CPython 実測: [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §12。

## 13. 未解決 (#81)
(a) 実機 FL での `mixer.getCurrentTempo(1)` 確認 (#81 のブロッカー)、`device.flrMidiNote` / `flrMidiCC` の書式未復元は未解決。省略引数の渡し方は #653 (PY-15) で解決 (全文 [REPORT_PY15.md](REPORT_PY15.md))、`midi.*` の NameError は §15 (#654) で解消。詳細: [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §13。

## 14. Piano roll scripting (`flpianoroll` + `.pyscript` ローダ) — #79 (PY-5)

結論: 同梱 Piano roll scripts 5/5 を wasm 上で回帰テスト化 (`tests/pyscript_e2e.mjs`)。Remote Scripts 5/5・Audio scripts 12/12 (`enveditor` 実装後、PY-23 #1054)。flpianoroll は 64 メンバ全て実装 (PY-19 #792 で `loadScoreFromFile` = 仮想 FS の JSON 読込、`DialogParams` = MOCK)。全文・実測・未解決は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §14 と [REPORT_PY19.md](REPORT_PY19.md)。Chrome (headless) 上の同梱 Piano roll 5/5 実行と node との出力一致 (#466) は [REPORT_CHROME.md](REPORT_CHROME.md) §14b。

## 15. stubs 既定値 `midi.*` の評価 (PY-16, #654)
結論: `fl_api.bind` の `eval` を、許可した式だけを評価する `_default_value` に置換した。`midi.*` の既定値 **20 関数・21 引数・名前 10 種** は利用者の `midi` から実行時に解決し、repo には値を置かない (`docs/LEGAL.md`)。検証起点 `8d883c3`、修正 commit `4b3cbe2`。`kwsig_check` PASS (wall 43〜45 ms)、旧コード + 新テストは `NameError` で FAIL、実物 midi.py で 21/21 一致。wasm 回帰は all_tools 48/48 (wasm・mock とも)、provider・poc・midi_script・subinterp PASS。追跡の `tool_coverage.json` は旧 NameError で欠けていた 1 tool の出力を新結果に更新。全数列挙・検証の詳細は [REPORT_PY16.md](REPORT_PY16.md)。
