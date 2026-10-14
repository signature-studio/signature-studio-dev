# python 付録: PY-2 静的リンク + Py_* 動的束縛の対応表 (#83 / #115)

(REPORT.md の 250 行上限のため分割移動。本体からは §7d として参照。REPORT.md の §7c (ilmcp, PY-3) と §11 (MIDI, PY-6) とは別節)

## 7d. CPython を provider と同一 wasm に静的リンク (PY-2, #83 / #115 の対応表)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。PE 側は束縛名の機械抽出のみ)。flapi の実体は §7b の provider (最小エンジン状態) で、**実 FLEngine wasm ではない** (範囲外の節参照)。

構成: `build_flpy_static.sh` が `libpython3.12.a` + `flpy.c` (`-DFLPY_STATIC`) + `provider/{fl_dispatch,fl_engine,gen/fl_table}.c` を 1 つの wasm (`dist/flpy_static.{js,wasm,data}`) にリンクする。`_flhost.call` は `flhost_call` を JS import ではなく同一 wasm 内の `fl_api_call` 直呼びにしたもの (引数・戻りの 16B スロットはそのまま、**JSON 化は構造値の戻り `J` だけ**で、これは C 内で完結)。Worker・SAB・JS import は経路に無い。

| 項目 | 実測 (HEAD は末尾の検証欄、GitHub Actions runner 4 core、node 22.23.3、emsdk 6.0.12) |
|---|---|
| wasm サイズ | `flpy_static.wasm` 5,956,381B。`flpy.wasm` 5,923,824B との差 +32,557B (HEAD f6352cd の再ビルド値。5a0b3c3 では 5,955,357B / 5,921,211B。同一ソースでもビルドごとにパス文字列分で数百 B 変わる) (provider 単体は `flprov.wasm` 43,225B) |
| JS import 排除 | `WebAssembly.Module.imports` に `flhost|fl_api|flprov|flHostCall` 一致 **0 件**。同じ検査を `flpy.wasm` に掛けると `env.flhost_call` が 1 件出る (検査が空振りしていないことのポジコン)。`fl_api_call` は export に有り |
| 48 tool 実行 | `tests/static_check.mjs`: **48/48 ok**、soft_error 0・raised 0、callback 往復 true、host_calls 37,425 (tool 別合計 37,424 + callback 1) |
| 結果の同一性 | tool 別 (status・結果文字列・api_calls・host_calls) の差: **SAB+provider 版 (`FL_ENGINE=wasm all_tools`) と 0/48、モック版 (追跡中 `tool_coverage.json`) と 0/48**。class A 38 を含む 48 全件 |
| 所要 (`e872dbb`、1 回ずつ実測、load 2.07) | `static_check.mjs` 0.356 秒 (rc=0、2 回目の実行も `STATIC CHECK OK`)。SAB 版 `FL_ENGINE=wasm all_tools` 1.067 秒 (load 0.31、9de66ea 時の実測)。f6352cd 時の `static_check` 0.277 秒と同オーダー |

### 往復コスト (`tests/static_bench.mjs`、1 trial = 20,000 回、5 trial の min / median / max、µs/呼出し)

| 経路 | 試行 1 (load 0.89) | 試行 2 (load 0.90) | 5a0b3c3 (load 0.78) | **f6352cd 5 trial (load 0.96)** |
|---|---|---|---|---|
| 静的: C から `fl_api_call` のみ (Python 無し) | 0.013 / 0.013 / 0.015 | 0.012 / 0.013 / 0.018 | 0.012 / 0.013 / 0.018 | 0.006 / 0.007 / 0.009 |
| 静的: Python `_flhost.call(fn,())` 直 (戻り int、lambda 込み) | 0.216 / 0.220 / 0.614 | 0.214 / 0.216 / 0.607 | 0.215 / 0.218 / 0.291 | 0.154 / 0.164 / 0.416 |
| 静的: Python `channels.channelCount()` (fl_api ラッパ経由 = MCPTools が通る経路) | 0.333 / 0.337 / 0.522 | 0.339 / 0.342 / 0.547 | 0.332 / 0.339 / 0.367 | 0.268 / 0.289 / 0.714 |
| 静的: 戻り str (`mixer.getTrackName`、malloc/free + decode) | 0.285 / 0.299 / 0.428 | 0.286 / 0.296 / 0.418 | 0.294 / 0.303 / 0.323 | 0.209 / 0.210 / 0.326 |
| 参考: 空の Python 関数呼出し (計測ループの下限) | 0.074 / 0.075 / 0.168 | 0.077 / 0.077 / 0.178 | 0.075 / 0.076 / 0.122 | 0.054 / 0.055 / 0.119 |
| Worker + SAB (同一 provider、`channels.channelCount()`) | 24.321 / 26.575 / 27.165 | 22.827 / 25.049 / 26.224 | 24.058 / 25.675 / 26.961 | 20.802 / 21.545 / 24.724 |

結論: 「<1µs」目標は **Python 呼出し込みで f6352cd の median 0.289µs (5 trial の min 0.268 / max 0.714)、5a0b3c3 の median 0.34µs で達成**。SAB 版との比は f6352cd で 74.5 倍 (21.545/0.289)、5a0b3c3 では 73.2〜78.9 倍。f6352cd の同一 run 内で 5 trial の median 同士は 0.289µs 対 21.545µs。§5 の過去値 (bimodal 15〜130µs) と違い、本 runner の SAB 版は 20.8〜27.2µs の単峰で、15µs 側・100µs 側は再現しなかった (環境差。比較は同一 run 内の値だけを使う)。内訳 (5a0b3c3 の median の差からの推定) は Python のラッパ (`fl_api._make.f` の `bind` + try) が約 0.12µs、`_flhost.call` の引数組立+C 呼出しが約 0.14µs、`fl_api_call` 自体が約 0.013µs。

### Py_* 動的束縛の対応表 (#115 の範囲を本 issue で処理: PM 判断)

FL は `LoadLibrary("Python312")` 後に `Py_*` を動的束縛する。`analysis/pybind_extract.py` が FLEngine PE の `0xc395a0` (InitSharedPython 配下の束縛関数) から名前を機械抽出する。§7 の「平文で無いため未抽出」は**ASCII 検索だけが原因で、名前は UTF-16LE の Delphi 文字列定数として 0x839554〜0x83a520 に連続して入っていた**ので訂正する。

| 項目 | 実測 (`analysis/pybind/pybind_map.{json,tsv}`) |
|---|---|
| 抽出方式 | `0xc395a0` から最初の epilogue までの `lea reg,[rip+rel32]` の参照先を UTF-16LE 文字列として読み、`_?Py[A-Z_]` に一致したものを採る。直後の `call 0x4235f0` (名前→アドレス解決、全 110 件同一) と `mov [rip+rel],rax` (保存先スロット VA) も記録 |
| 束縛名 | **110** (重複 0)。関数 93 + データ 16 (`PyExc_*`・`Py*_Type`・`_Py_{None,True,False}Struct`・`Py_DontWriteBytecodeFlag`) + lib に無い 1。保存先スロット 110/110 |
| `libpython3.12.a` との照合 | 109 件が定義済み (`llvm-nm --defined-only`)。残り 1 件 `_PyInterpreterState_GetRefTotal` は CPython 3.12.1 の `Objects/object.c` で `#ifdef Py_REF_DEBUG` 内のみ定義 = release build に存在しない。FL 同梱の python312.dll は `Py_REF_DEBUG` 付きではないので束縛は実行時に失敗し得るが、FL 側の使用有無は未確認 (下記未解決)。`ALLOW_ABSENT` に根拠付きで 1 件だけ許容し、根拠が成立しなくなったら gate が落ちる |
| 静的版での解決 | `flpy_resolve(name)` が 109 件全てを非 NULL で返す (`pybind_refs.inc` を生成して `src/pybind_resolve.c` が表を持つ)。`wasmTable.get(resolve("Py_IsInitialized"))()` が 1、`PyEval_SaveThread` → `PyEval_RestoreThread` の後も tool が動く |
| サブインタプリタ | `Py_NewInterpreterFromConfig`・`Py_EndInterpreter`・`PyInterpreterState_*`・`PyThreadState_{New,Clear,DeleteCurrent,Swap,Get}` を FL が束縛し、`libpython3.12.a` にも在る。`flpy.wasm` (SAB 版) は REPORT.md §11 で 3 構成 (isolated+OWN_GIL / isolated+SHARED_GIL / legacy) の成功を実測済み。**静的版 (`flpy_static`) では未検証** (子 #2633 PY-80) |
| FL が使う初期化 | `PyConfig_InitIsolatedConfig` + `Py_InitializeFromConfig` + `Py_DecodeLocale` + `PyWideStringList_Append`、`PyImport_AppendInittab` (組込 module 登録は `flpy.c` と同方式)、`Py_DontWriteBytecodeFlag`。`PyGILState_*` は束縛されない = FL は `PyEval_SaveThread/RestoreThread` と `PyThreadState_New/Swap` で GIL を扱う |

gate (`pybind_extract.py --check`、不合格は exit 1): 抽出件数 = 110、全名が lib に在る (許容 1 件を除く)、許容の根拠が成立、must-have 5 名 (`Py_InitializeEx` `Py_NewInterpreterFromConfig` `PyRun_SimpleString` `PyEval_SaveThread` `PyImport_AppendInittab`) が抽出済み、重複なし、スロット抽出率。

### ネガティブコントロール (全て exit 1 を確認)

| 変異 | 結果 |
|---|---|
| `mixer.getTrackName` ハンドラを削除して静的版を再リンク | `static_check` FAIL: 33/48 ok・soft_error 15・host_calls 1,079 (SAB+provider 版と tool 別差多数。`get_session_context` 151 対 18,056) |
| `getTrackName` の戻り値だけ `"!"` を付ける (全 tool は ok のまま) | FAIL: status 不変 (48/48 ok) でも結果文字列の差 **4/48** (route_channels_to_mixer / get_mixer_tracks_volume / get_mixer_routing / set_mixer_routing) = ok だけの gate では見逃す変異を検出 |
| `pybind_extract --inject PyFoo_Bar` | FAIL (`not in libpython`) |
| `--expect 111` / `LLVM_NM` で `PyDict_New` を除外 | FAIL (`extracted 110 != expect 111` / `not in libpython: PyDict_New`) |
| 対応表 JSON に存在しない `PyFake_Api` を追加 | `static_check` FAIL (`flpy_resolve が NULL` + `resolve 表 109 != 対応表 110`) |
| `--func 0xc3b340` (別関数) | FAIL (抽出 0 件)。**生き残り**: `--func 0xc393a0` (束縛関数の呼出し元で epilogue が同じ 0xc3a118) は同じ 110 名を返し PASS = 既定アドレスの取り違えは検出できない (どちらも同じ名前集合が正解のため等価) |

### スレッド / GIL 方針

- **Python を実行してよいのは UI スレッドと MIDI スレッドだけ。audio スレッド (AudioWorklet) からは呼ばない**。FL の API 自身が audio 側で `Operation unsafe at current time` (code 3) を返す設計と一致。AudioWorklet 内では `Atomics.wait` が TypeError で使えない (runtime REPORT)。
- 同一 wasm 内なので `_flhost.call` は呼出し元スレッドの上で同期に完結し、callback (`ilmcp.showHighlight` の `whenDone` など) も同じスレッドで戻る。FL 本来の「同一プロセス・同一スレッド」と同じ。
- GIL: FL は `PyGILState_*` を使わず `PyEval_SaveThread/RestoreThread` + `PyThreadState_New/Swap` を束縛する (上表)。静的版では `SaveThread → RestoreThread` の往復後も tool が動くことを確認済み。**pthread (複数スレッドから同時に Python) 版のビルド・実行は未検証**。単一スレッド wasm 版 (本 PR) は MIDI と UI を 1 つのスレッドで直列に処理する前提で、MIDI スレッドを別スレッドにする場合は pthread ビルド + `PyThreadState_New` 方式が要る (子 #2633 PY-80)。
- メモリモデル (#25): **wasm32 に決定済み** (`tools/runtime/REPORT.md`、Memory64 は退避路)。本 PR は wasm32 でリンクしており、wasm32 の範囲では依存を満たす。provider の追加は +34,146B と小さく、Memory64 へ移る場合も同じ手順で再リンクできる想定 (**Memory64 でのリンクは未検証**)。

### 検証範囲 / 範囲外

- **HEAD 再現 (`e872dbb`。素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` に設定、`toolchain-emsdk` は `/opt/emsdk`。`build_cpython_wasm.sh` は 3 分 17 秒 rc=0。load 2.07)**: `build_flpy.sh` / `provider/build.sh` / `build_flpy_static.sh` 全て rc=0 (static 4.9 秒)。`provider_check` `"PASS":true`、`pybind_extract --check` PYBIND CHECK OK (110 件、lib 内 109、許容 1)、SAB+provider `all_tools` 48/48・host_calls 37,425、`static_check` **STATIC CHECK OK** (48/48 ok、host_calls 37,425、callback 往復 true。SAB+provider 版と 0/48、mock 基準と 0/48)、`ilmcp_e2e` rc=0 (0.32 秒)。
- **往復コスト (`e872dbb`、`static_bench.mjs 5`、5 trial の min / median / max、µs/呼出し、load 2.07)**: 静的 C `fl_api_call` のみ 0.013 (0.010 / 0.015)、Python `_flhost.call(fn,())` 直 0.225 (0.221 / 0.278)、Python `channels.channelCount()` (fl_api ラッパ経由) 0.410 (0.392 / 0.438)、戻り str 0.297 (0.283 / 0.320)、空の Python 呼出し 0.077 (0.075 / 0.097)、Worker + SAB (同一 provider、`channelCount()`) 26.206 (25.066 / 27.260)。median 同士で SAB 版の約 64 倍。上の表の f6352cd 行より load が高い run のため、数値は本行を正とする。
- **mock 基準との既知の差 (2 件、本 PR では除外)**: `get_highlight_names` と `get_browser_names` は、mock (`host/ilmcp.mjs`、main の PY-3 #82 由来) と C provider (`provider/fl_engine.c` の最小スタブ) で **result 文字列だけ**が違う。mock は FL 実物 rodata 由来の 21 件 / 木構造、C は固定 4 件 / `[object Object]` 相当。`tests/static_check.mjs` の `KNOWN_MOCK_RESULT_GAP` で、この 2 件のみ mock 比較の result を除外し、status・host_calls・api_calls は従来どおり完全一致で比較する。解消 (C 側の仕様統一) は未着手。起票先は #82 (OPEN。2026-10-14 にコメントで差分と解消条件を追記)。
- 旧記録 (f6352cd、main 取り込み前の HEAD): `static_check` STATIC CHECK OK (差 0/48 ×2)、SAB 48/48・37,425、`tool_coverage.json` を 37,425 に再生成 (`plugins.getParamValueString/4` を反映)。mock 側の `get_highlight_names` は当時 main 未取り込みのため差が出なかった。
- 旧記録 (5a0b3c3、クリーン worktree): `pybind_extract --check` OK、SAB+provider `all_tools` 48/48・37,424、`static_check` 3 回とも STATIC CHECK OK、0.29 / 0.30 / 0.28 秒 (load 1.10)。main 取り込み前の値で、現 head では使わない。
- 範囲: node (メインスレッド) での静的版 48 tool と対応表。入力 (MCPTools.pyc 100,674B / midi.py / utils.py / `block00031_PE.bin`) は `fl-win64` 素材から配置 (`fetch_inputs.sh` が `work/fl-stubs` を clone する)。
- 範囲外: **実 FLEngine wasm へのリンクは未実施** (実 FLEngine は MS5 部分起動止まりで `fl_api_call` を持たない)。本節の「FLEngine 側」は `provider/fl_engine.c` の最小エンジン状態。headless Chrome・Worker 内での静的版は §7f で実施 (#2634)。`run_all.sh` 全体は未達 (子 #2649)。静的版でのサブインタプリタ・複数スレッド・Memory64 は未検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine wasm へのリンク (`fl_api_call` を FLEngine の内部 API に繋ぐ) | 本節は provider のモック状態で実測しており、実エンジンの意味差は未検証 | 子 #2631 (PY-79)。FLEngine 起動 (MS5) が前提 |
| `_PyInterpreterState_GetRefTotal` を FL が実際に使うか | 使うなら upstream release build では束縛が失敗する (FL 側の失敗時挙動は未確認) | 子 #2633 (PY-80)。旧 #76 (CLOSED) の T6 から移管 |
| wasm でのサブインタプリタ (`Py_NewInterpreterFromConfig`) 動作 | FL がサブインタプリタ運用なら MIDI/piano roll の分離に影響 | 子 #2633 (PY-80)。旧 #76 (CLOSED) の T6 から移管 |
| pthread 版での複数スレッド + GIL | MIDI スレッド分離の可否 | 子 #2633 (PY-80)。旧 #76 (CLOSED) の T6 から移管 |

## 7e. 再検証 (測定 commit 322f81b6) と #83 の受入条件の判定

- 理由: 7d の実測は `e872dbb` 時点。その後 `tools/python/provider/fl_engine.c` が 124 行追加・40 行削除され、テスト類も変わったため、7d の値は現 main の証跡にならない。現 HEAD で全工程を再実行した。
- 測定 commit: `322f81b6` (当時の origin/main)。本節の PR はコードを変えない。差分 0 の証跡: `git diff 322f81b6 HEAD -- tools/python ':!tools/python/REPORT_PY2.md'` の出力は 0 行 (`build_*.sh`・`fetch_inputs.sh`・`analysis/pybind_extract.py` を含む `tools/python` 全体)。
- その後の main の差分 (`git diff 322f81b6 origin/main -- tools/python`) は 2 件のみ: `tools/python/REPORT_PY72.md` (追加) と `tools/python/analysis/flapi/pe_rip_consts.py` (追加)。後者は測定経路から参照されていない (`git grep -n pe_rip_consts 322f81b6 -- tools` は 0 件)。測定対象のコードは変わっていない。
- 手順: 素材 `fl-win64` ([WIN64]) を展開して `FL_WIN64_DIR` に設定、emsdk は [EMSDK] (`EMSDK_ENV`)。`tools/python` 直下で実行。

| 手順 | 結果 |
|---|---|
| `fetch_inputs.sh` | MCPTools.pyc 100,674B・midi.py・utils.py を `work/` に配置 |
| `build_cpython_wasm.sh` | 4 分 05 秒、rc=0 |
| `build_flpy.sh` / `provider/build.sh` / `build_flpy_static.sh` | 全て rc=0。`flpy_static.wasm` 5,966,942B |
| `FL_ENGINE=wasm node tests/all_tools.mjs` (SAB + provider) | 48/48 ok、host_calls 37,425、rc=0 |
| `node tests/static_check.mjs` | `STATIC CHECK OK`、rc=0。48/48 ok、callback 往復 true、wasm の flhost import 0 件。SAB 版と 0/48 差、mock と 0/48 差 (分母 48。result 2 件 (`get_highlight_names`・`get_browser_names`) は `KNOWN_MOCK_RESULT_GAP` で mock 比較から除外、#82。status・host_calls・api_calls は除外なし) |
| `node tests/provider_check.mjs` | `PASS:true` (435 関数、実装 70、未実装 365、MCP 静的 60)、rc=0 |
| `analysis/pybind_extract.py --check` (`--pe` は FL の block00031_PE.bin、`--lib` は build-wasm の libpython) | `PYBIND CHECK OK`、rc=0。110 件、lib 内 109、許容 1 (`_PyInterpreterState_GetRefTotal`) |

往復コスト (`tests/static_bench.mjs 5`、µs/呼出し、5 trial の median (min–max)、同一 run・load 1.14):

| 経路 | median (min–max) |
|---|---|
| 静的: C から `fl_api_call` のみ | 0.018 (0.013–0.025) |
| 静的: Python `_flhost.call` 直 | 0.291 (0.288–0.601) |
| 静的: Python `channels.channelCount()` (fl_api ラッパ経由) | 0.569 (0.509–0.843) |
| 静的: 戻り str | 0.422 (0.418–0.604) |
| 参考: 空の Python 関数呼出し | 0.108 (0.102–0.232) |
| Worker + SAB (同一 provider、`channelCount()`) | 42.7 (38.587–45.076) |

同一 run の median 比は 42.7 ÷ 0.569 = 75.0 倍。7d の過去値 (0.34µs / 21.5〜25.7µs) より両経路とも大きいのは、推定で runner の負荷差による。根拠: 本 run の load 1.14 は、7d の f6352cd 行 (load 0.96) と 5a0b3c3 行 (load 0.78) より高い。f6352cd 行の median と比べると両経路とも約 2 倍に伸びた (静的 `channelCount()` 0.289→0.569µs、×1.97。SAB 版 21.545→42.7µs、×1.98)。ただし provider 側の変更が両経路に効いた可能性は切り分けていない (負荷だけを変えた再測定はしていない)。比較は本 run 内の値だけで行う。<1µs は 5 trial の max 0.843µs まで満たす。

ネガコン: 静的版だけ `channels.channelCount` の戻り値を +1 に改変 (`provider/fl_engine.c` 1 行。SAB 版 (`provider/build.sh` の出力) は再ビルドしていない) → `build_flpy_static.sh` のみ再リンク → `static_check.mjs` は FAIL (rc=1)。mock 比較で 19/48 差、summary の ok は 47/48、host_calls 37,461 (期待 37,425)。改変を戻して再リンク → `STATIC CHECK OK` (rc=0)。

#83 本文の受入条件の判定:

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| Worker+SAB と同一の tools/call 結果 (48 tool、class A 38 を含む) | 満たす (provider 版) | 48/48 ok、SAB 版と 0/48 差。実 FLEngine 版は子 #2631 |
| 往復コストの再計測と記録 (<1µs 目標) | 満たす (provider 版) | 上の表。Python 込み median 0.569µs、5 trial の max 0.843µs。実 FLEngine 版は子 #2631 |
| スレッド / GIL 方針の文書化 | 満たす | `BRIDGE.md` §7 |
| メモリモデル (#25) への依存の明記 | 満たす | #25 は CLOSED (wasm32 決定)。Memory64 でのリンクは未検証 (下表) |

#83 の題目と受入条件は provider 版で満たした範囲に縮めた。旧題目「CPython を FLEngine wasm に静的リンク」の実 FLEngine への接続部分は子 #2631 (PY-79) に分離した。`fl_api_call` の実 FLEngine 接続は `BRIDGE.md` §5 B が「FLEngine lift 後に移行」としている。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine wasm への `fl_api_call` 接続 | 本節の実測は provider の最小エンジン状態。実 FLEngine は `fl_api_call` を持たない | 子 #2631 (PY-79)。FLEngine 起動 (MS5) が前提 |
| mock と C provider の result 文字列差 2 件 (`get_highlight_names` / `get_browser_names`) | `static_check` が 2 件のみ mock 比較の result を除外 (`KNOWN_MOCK_RESULT_GAP`) | #82 (OPEN。差分の内容と解消条件をコメントで追記済み) |
| サブインタプリタ・pthread+GIL・Memory64 での静的版の検証、`_PyInterpreterState_GetRefTotal` を FL が使うか | 未検証 | 子 #2633 (PY-80)。旧 #76 (CLOSED) の検証項目を移管 |
| headless Chrome / Worker 内の静的版、`run_all.sh` 全体 | 未実施 | 子 #2634 (PY-81) |
| #115 (ST-T7、OPEN) の Py_* 動的束縛 | §7d の対応表で 110 件の解決を実測済み。#115 の範囲はこの節で処理 (§7d) | #115 にクローズ提案のコメントを投稿済み (閉じるかは PM 判断) |

## 7f. 静的版の Worker 内実行と headless Chrome 比較・run_all.sh 全体 (PY-81, #2634)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。検証は JS 側の経路と wasm の結果比較)。

**結論**: `flpy_static.wasm` を module Worker 内で動かし、headless Chrome 上で SAB 版 (flpy + provider) と 48 tool を比較した。tool 別の status・result・host_calls・api_calls は **差 0/48** で、48/48 ok。`run_all.sh` 全体は **rc=2 (前提チェックで停止)** のため rc=0 は未達。mac 素材を要する部分は子 #2649 (PY-83) に分離。

測定 commit: **`982c4a2e`** (main 取り込みの merge。コードを変えた最後の commit)。前回の測定 commit は `77448069` で、その後の main 取り込みで `tools/python` に 4 ファイルが入ったため再測定した (下の「main 取り込み後の再測定」節)。以降の commit は本節を含む文書のみ。`git diff 982c4a2e HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行 (差分 0)。

### 構成 (検証の作り)

- `tests/browser/static.html` (main thread): (a) SAB 版 = `createWasmEngine` (`dist/flprov.js`) + `FlPython` (`dist/flpy.js`、module Worker + SAB 同期 RPC) で 48 tool を実行し、tool 別の 4 キーを集計。(b) 静的版 = `tests/browser/static_worker.mjs` を module Worker として起動し、Worker 内で `dist/flpy_static.js` を読んで 48 tool を実行 (JS import・SAB・JSON 往復なし)。trace の数え方は `tests/static_check.mjs` と同じ (通し番号の差分)。
- `tests/static_browser_check.mjs`: `serve.mjs` + headless Chrome (CDP) で上の page を開き、結果 `RESULT {...}` を読んで判定。`STATIC_WASM=<名前>` で比較対象の静的 wasm を差し替える (負例用)。
- 合格条件: 48 件すべて status ok、tool 別 4 キーの差 0、`static_host_calls` = `sab_host_calls`、callback 往復 true、静的版が Worker 内で動いた (`static_in_worker`)。
- `run_all.sh` に step `10b` として追加 (step 10 の直後)。

### main 取り込み後の再測定 (HEAD `982c4a2e`、merge commit)

main の取り込みで `tools/python` に次の 4 ファイルが入った (`analysis/py71_callers.py`・`analysis/py71_slot.py`・`analysis/py71_vtable.py` 追加、`analysis/flapi/pe_rip_consts.py` 変更)。`git diff 77448069 982c4a2e -- tools/python ':(exclude)*.md' --stat` の出力は次のとおり (全文 386 行は本節の行数上限のため省略)。

```
 tools/python/analysis/flapi/pe_rip_consts.py |   4 +-
 tools/python/analysis/py71_callers.py        | 104 ++++++++++++++++
 tools/python/analysis/py71_slot.py           | 171 +++++++++++++++++++++++++++
 tools/python/analysis/py71_vtable.py         |  71 +++++++++++
 4 files changed, 349 insertions(+), 1 deletion(-)
```

この 4 ファイルは測定経路 (`fetch_inputs.sh`・`build_*.sh`・`provider/`・`tests/`・`analysis/pybind_extract.py`) から参照されない。`git grep 'py71_\|pe_rip_consts' 982c4a2e -- tools docs .github` の参照は、各スクリプト自身の usage 行・`REPORT_PY72.md`・`docs/DOC_MAP.md` のみ。`tools/python` の上記 4 ファイル以外は 77448069 と同一 (`--stat` の 4 行が全差分)。同じ手順を `982c4a2e` で再実行した。

| 手順 / 検証 | コマンド | 結果 | 所要 (real) | load |
|---|---|---|---|---|
| 入力配置 | `bash fetch_inputs.sh` | rc=0。MCPTools.pyc 100,674B・midi.py・utils.py を `work/` に配置 | 0.85 s | — |
| CPython wasm | `bash build_cpython_wasm.sh` (素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開、emsdk は [EMSDK] (`EMSDK_ENV`)) | rc=0 | 3 分 53.99 秒 | — |
| flpy / provider / static | `FLPY_SKIP_TABLE=1 bash build_flpy.sh`・`bash provider/build.sh`・`bash build_flpy_static.sh` | 全て rc=0。`flpy.wasm` 5,924,680B・`flpy_static.wasm` 5,967,865B (追跡済み `flapi_table.json` は変更なし) | flpy 6.15 s・static 6.37 s (provider は未計時) | — |
| provider 単体 | `node tests/provider_check.mjs` | `"PASS":true` (functions 435・implemented 70・unimplemented 365・mcp_static 60) | 0.40 s | 2.53 (直前) |
| SAB + provider 48 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.64 s | — |
| 静的版 node 検査 | `node tests/static_check.mjs` | `STATIC CHECK OK`。48/48 ok、host_calls 37,425、callback 往復 true | 0.39 s | — |
| 静的版 Worker + headless Chrome (正例) | `node tests/static_browser_check.mjs` | **PASS** (`STATIC BROWSER OK`)。48/48 ok (SAB 48・静的 48)、差 0/48、host_calls 37,425 = 37,425、callback 往復 true、Worker 内 true。SAB init 203 ms・tools 1,439 ms、静的 init 127 ms・tools 85 ms、スクリプト内 wall 2,730 ms | 11.85 s (Chrome 起動込み) | 2.77 (終了時) |
| pybind 束縛表 | `python3 analysis/pybind_extract.py --pe <block00031_PE.bin> --lib work/build-wasm/libpython3.12.a --out work/pybind --expect 110 --check` | `PYBIND CHECK OK` (names 110・unique 110・in_lib 109・許容 1)。`--out` は追跡ファイルを避けて `work/` へ | 0.13 s | — |

負例 (`STATIC_WASM=flpy_static_neg`) は本再測定では未実施で、結果は下の 77448069 の節のとおり。`run_all.sh` 全体は未実施 (#2649)。

### 実測 (HEAD `77448069`。load は各 run 直前の `/proc/loadavg` 1 分値、runner 4 core、node v22.23.3、Chrome 155.0.8059.39 headless、emsdk は `[EMSDK]` 6.0.12)

| 検証 | コマンド | 結果 | 所要 | load |
|---|---|---|---|---|
| 静的版 Worker + headless Chrome (正例 1 回目) | `node tests/static_browser_check.mjs` | **PASS**。48/48 ok (SAB 48・静的 48)、差 0/48、host_calls 37,425 = 37,425、callback 往復 true、Worker 内 true。SAB init 155 ms・tools 1,000 ms、静的 init 92 ms・tools 50 ms | wall 2.23 s | 0.67 |
| 同 (正例 2 回目) | 同上 | PASS (同値。SAB init 150〜196 ms の範囲) | wall 2.26 s | 0.67 |
| 同 (正例 3 回目) | 同上 | PASS (同値) | wall 2.44 s | 0.94 |
| 負例: `getTrackName` の戻り値だけ `"NEG"` にした `flpy_static_neg` | `STATIC_WASM=flpy_static_neg node tests/static_browser_check.mjs` | **FAIL (rc=1)**。差 4/48: `route_channels_to_mixer`・`get_mixer_tracks_volume`・`get_mixer_routing`・`set_mixer_routing` の **result のみ** (status は全件 ok のまま)。host_calls 37,422 | wall 2.29 s | 0.94 |
| 静的版 node 検査 (既存、メインスレッド) | `node tests/static_check.mjs` | **PASS** (STATIC CHECK OK)。SAB+provider 0/48・mock 0/48、48/48 ok、host_calls 37,425、callback 往復 true | 0.30 s | 0.94 |
| 同 負例 | `STATIC_WASM=flpy_static_neg node tests/static_check.mjs` | **FAIL (rc=1)**。FAIL 10 行 (mock 比較で 4/48 + host_calls 合計 37,422 != 37,425 ほか) | — | — |
| provider 単体 | `node tests/provider_check.mjs` | **PASS** (`"PASS":true`、functions 435・implemented 70) | 0.26 s | — |
| SAB+provider 48 tool (wasm 版) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.16 s | 1.51 (直後) |
| 既存 headless Chrome (SAB・mock) | `node tests/browser_check.mjs` | **PASS** (BROWSER OK、tools 48) | 1.04 s | 1.51 (直後) |
| PY-2 Py_* 束縛対応表 | `analysis/pybind_extract.py --check --expect 110` | **PASS** (PYBIND CHECK OK、names 110・lib 内 109・許容 1) | 0.09 s | — |

ビルド (本 run。素材 `fl-win64` の win 経路のみ、`FLPY_SKIP_TABLE=1`): `build_cpython_wasm.sh` 3 分 46.7 秒 rc=0 (開始時 load 0.49)。`build_flpy.sh` + `provider/build.sh` + `build_flpy_static.sh` 合計 11.3 秒、いずれも rc=0。サイズは `flpy_static.wasm` 5,967,865B・`flpy.wasm` 5,924,680B (§7d の値とは再ビルドによる差。同一ソースでも数百 B 変わる)。

### run_all.sh 全体 (未達・理由を記録)

- `bash tools/python/run_all.sh` は **rc=2、0.008 秒** で、前提チェックで停止: `FLEngine_x64.dylib が無い` (mac pkg の `pkg_extract/payload_out/.../Contents/Libs/`)。`analysis-mac-shared` は `docs/WORKFLOW.md` §11 の記述では `Shared/` の dylib 群 (25 本) だけで、この実行ファイルを含まない。
- mac pkg を要する step は、前提チェックのほかに step 3b (`scripts_inventory.py`) と step 4 (`flapi_extract.py` の mac 版) (`run_all.sh` 内の注記どおり)。`build_flpy.sh` は表の再生成 (`flapi_table.py`) の入力を要するため、今回は `FLPY_SKIP_TABLE=1` で追跡済みの表を使った (mac 無しでの再生成の可否は未検証)。
- step 5 以降 (win 素材だけで走る部分) は本節では個別に実行したもの (9b・9c・10・10b) だけで、残りは未検証。全体の再実行は子 #2649 (PY-83) で行う。

### 観測 (未解決に残す点)

- 本節の検証ページの**初版**で、1 回だけ `PENDING` のまま 180 秒止まった (段階表示が無く、SAB 段階か静的段階かは切り分けられなかった)。以後、最終版の正例を 9 回 (上表の 3 回 + 0849bd5c 時の 3 回 + 77448069 時の 3 回) 実行し、いずれも PASS。原因は特定していない。
- `FlPython.create` の既定経路 (Worker の自動生成) と、呼び出し側が Worker を渡す経路の両方で、provider 版エンジン併用時に PASS を確認した (後者は最終版では使っていない)。

### 検証範囲 / 範囲外

- 範囲: Linux・headless Chrome 155 (`--no-sandbox`)・48 tool (`tests/tool_args.mjs` の引数表)・基準は同じ `flprov.wasm` を使う SAB+provider 版。
- 範囲外: 実 FLEngine wasm への接続、MIDI スレッド・pthread・サブインタプリタ (静的版)、Memory64、他ブラウザ (Firefox・Safari) は未検証。`run_all.sh` の win 素材だけでの全体実行は未検証 (#2649)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `run_all.sh` 全体 rc=0 (前提チェックで rc=2。mac の `FLEngine_x64.dylib` が素材に無い。step 3b・4 も mac 依存。step 5〜15 は win のみで未検証) | run_all 全体の合格は未主張 | #2649 (PY-83) |
| 初版ページの 180 秒 `PENDING` 1 回 (原因未特定、再現せず) | 検証の再現性に一抹の不確かさ | #2634 (本 PR で追跡。再発したら本節に追記) |
| 静的版の実 FLEngine 連携・サブインタプリタ・pthread・Memory64 | §7d の未解決と同じ | 子 #2631・#2633 (PY-79・PY-80) |
