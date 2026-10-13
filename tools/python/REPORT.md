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

| 項目 | 実測 (HEAD b76d221, GitHub Actions runner, node 22.23.3, load average 0.08〜0.46) |
|---|---|
| 実装ハンドラ | **60** = MCPTools 静的参照の全て (公開 52: channels 18 / mixer 18 / plugins 7 / playlist 4 / ui 3 / transport 2 + ilmcp 8)。残り 375 は未実装 (`tests/provider_check.mjs` が 60/375 を assert) |
| `tests/all_tools.mjs` (`FL_ENGINE=wasm`) | **48/48 ok**、soft_error 0・raised 0、host_calls 37,424、callback 往復 true。所要 2.08 / 2.11 / 2.25 秒 (3 回、b76d221 クリーン再ビルド後。mock 2.06 秒)。`provider_check` 0.33 秒、`poc_mcp` (mock) 1.21 秒 POC OK で回帰なし。tool 別の結果文字列・api_calls は mock と **48/48 完全一致** (`tool_coverage.json` との差 0 件) |
| `tests/provider_check.mjs` | PASS: 戻り型 (C 側: float=`D`/int=`I`/bool/str/None/JSON) が Python 型で float/int/bool/str/dict、kwargs 経由、code 4 → `IndexError`、code 5 → `TypeError`、未実装 → `RuntimeError` |
| wasm | `flprov.wasm` 43,225B (`-O2`、provider 単体、b2225e1。b76d221〜d2706e1 は 42,953B)。CPython と同一 wasm にはまだ入れていない (T2) |
| ネガティブコントロール | `mixer.getTrackName` ハンドラを削除して再ビルド → all_tools **33/48 ok・soft_error 15・host_calls 1,079**、provider_check は「MCP 使用 mixer.getTrackName が未実装」で失敗 (= テストが実際に C 実装を踏んでいる) |

mock との差で見つかったもの: mock は引数の個数/型を検査しないため通っていた呼出しを C 側が拒否した (`ilmcp.showHighlight` の `whenDone` 内の 3 引数呼出し → 個数 3〜5 を許可に修正)。`getChannelName` 等は署名の引数数 (index, useGlobalIndex) を超えると code 5。

エラー code の割当 (`provider/fl_api.h`): FLEngine PE の文言 9 種 (Invalid value / Unspecified error / Operation unsafe at current time / Range error / Index out of range / Wrong number of function parameters or wrong parameter type / Linked device not assigned / Device not assigned / Plugin not valid) を 1〜8 に割当 (`Range error` と `Index out of range` は 4 に束ねた)。provider が実際に返すのは 2 / 4 / 5 のみで、1 (Invalid value)・3 (unsafe)・6〜8 は定義だけ (実エンジンの発生条件が未解明)。**数値は Python 側 `fl_api._ERR` の写像と整合させた暫定値で、実エンジンの数値は未確認**。

再現: `bash provider/build.sh && node tests/provider_check.mjs && FL_ENGINE=wasm node tests/all_tools.mjs` (前提: `build_flpy.sh` 済み。runner では `EMSDK_ENV=<emsdk>/emsdk_env.sh`、`FL_WIN64_DIR`)。
入力の用意 (mac pkg 無しの Actions): `oc_artifacts: fl-win64 toolchain-emsdk` + `FL_WIN64_DIR=<fl-win64 展開先> bash fetch_inputs.sh` (パスは `tools/shared/env.sh` 経由。`$FL_MAC_DIR` に mac pkg が無ければ win64 の `block25159_DATA.bin` = MCPTools.pyc、`block24429_DATA.bin` = midi.py (770 行)、`block24430_DATA.bin` = utils.py (213 行) を `work/` に置く)。続けて `build_cpython_wasm.sh` → `build_flpy.sh` (注: `build_flpy.sh` は先頭で `analysis/flapi_table.py` を再実行し、mac dylib / win PE が無い環境では追跡中の `flapi_table.json` / `FLAPI.md` を書き換える。commit しないこと)。

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

## 10. MCP JSON-RPC をアプリ UI / devtools に公開 (PY-4, #77)

既知類型との関係: 該当なし (lift / 逆アセではない。flapi は引き続き `fl_mock.mjs` = FLEngine 模擬)。

- 公開面: `window.flMcp` (`start(files)` `rpc(req)` `list()` `call(name,args)` `stop()`) + `/?mcp=1` の UI パネル。実装 `src/runtime/mcp_panel.ts`、配信 `vite.config.ts` `pyAssets` (`/py/` = host/・dist/flpy.{js,wasm,data}・flapi_ids.json の許可リストのみ)。設計は `BRIDGE.md` §3。
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
| ilmcp B 群 8 tools は最小の偽実装 | UI から呼べるが FL 本来の挙動ではない | 親 #35 の T3 (ilmcp 実装) |
| `/?mcp=1` のパネルは最小 UI (整形・履歴・複数行 arguments 編集なし)。`pnpm build` 成果物 (`dist/`) は `/py/` を持たないため dev / preview 専用 | 本番配信での公開は未対応 | 親 #35 に提案 (配信設計は #62 H 系と調整) |
| `build_flpy.sh` が `flapi_table.json` / `FLAPI.md` を再生成する。runner には win PE が無く `win_pair_verified` が false になる | 本 PR では当該 2 ファイルをコミットしていない | #74 の PR (provider) と同じ `/home/ubuntu` 固定パス問題。`fetch_inputs.sh` / `run_all.sh` の env 化を別 issue で提案 |

## 11. Piano roll scripting (`flpianoroll` + `.pyscript` ローダ) — #79 (PY-5)

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
| ~~Chrome 上の pyscript 実行未検証~~ | 下記 §11b で解消 (#466) | — |

### 11b. Chrome (agent-browser) 上の pyscript 実行検証 — #466 (PY-11)

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
