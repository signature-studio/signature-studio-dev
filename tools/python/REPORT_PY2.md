# python 付録: PY-2 静的リンク + Py_* 動的束縛の対応表 (#83 / #115)

(REPORT.md の 250 行上限のため §11 を無変更で分割移動。本体からは §7c として参照)

## 11. CPython を provider と同一 wasm に静的リンク (PY-2, #83 / #115 の対応表)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。PE 側は束縛名の機械抽出のみ)。flapi の実体は §7b の provider (最小エンジン状態) で、**実 FLEngine wasm ではない** (範囲外の節参照)。

構成: `build_flpy_static.sh` が `libpython3.12.a` + `flpy.c` (`-DFLPY_STATIC`) + `provider/{fl_dispatch,fl_engine,gen/fl_table}.c` を 1 つの wasm (`dist/flpy_static.{js,wasm,data}`) にリンクする。`_flhost.call` は `flhost_call` を JS import ではなく同一 wasm 内の `fl_api_call` 直呼びにしたもの (引数・戻りの 16B スロットはそのまま、**JSON 化は構造値の戻り `J` だけ**で、これは C 内で完結)。Worker・SAB・JS import は経路に無い。

| 項目 | 実測 (HEAD は末尾の検証欄、GitHub Actions runner 4 core、node 22.23.3、emsdk 6.0.12) |
|---|---|
| wasm サイズ | `flpy_static.wasm` 5,955,357B。`flpy.wasm` 5,921,211B との差 +34,146B (どちらもクリーン HEAD 5a0b3c3 での再ビルド値。同一ソースでも作業ツリーの再ビルドとはパス文字列分で数百 B 変わる) (provider 単体は `flprov.wasm` 43,225B) |
| JS import 排除 | `WebAssembly.Module.imports` に `flhost|fl_api|flprov|flHostCall` 一致 **0 件**。同じ検査を `flpy.wasm` に掛けると `env.flhost_call` が 1 件出る (検査が空振りしていないことのポジコン)。`fl_api_call` は export に有り |
| 48 tool 実行 | `tests/static_check.mjs`: **48/48 ok**、soft_error 0・raised 0、callback 往復 true、host_calls 37,424 (tool 別合計 37,423 + callback 1) |
| 結果の同一性 | tool 別 (status・結果文字列・api_calls・host_calls) の差: **SAB+provider 版 (`FL_ENGINE=wasm all_tools`) と 0/48、モック版 (追跡中 `tool_coverage.json`) と 0/48**。class A 38 を含む 48 全件 |
| 所要 | `static_check.mjs` 全体 0.27 / 0.28 / 0.28 秒 (3 回、load average 0.56〜1.35、直列 1 本。起動・FS 配置・48 tool 込み)。同条件の SAB 版 `all_tools` 1.26 / 1.32 / 1.37 秒 |

### 往復コスト (`tests/static_bench.mjs`、1 trial = 20,000 回、5 trial の min / median / max、µs/呼出し)

| 経路 | 試行 1 (load 0.89) | 試行 2 (load 0.90) | クリーン HEAD 5a0b3c3 (load 0.78) |
|---|---|---|---|
| 静的: C から `fl_api_call` のみ (Python 無し) | 0.013 / 0.013 / 0.015 | 0.012 / 0.013 / 0.018 | 0.012 / 0.013 / 0.018 |
| 静的: Python `_flhost.call(fn,())` 直 (戻り int、lambda 込み) | 0.216 / 0.220 / 0.614 | 0.214 / 0.216 / 0.607 | 0.215 / 0.218 / 0.291 |
| 静的: Python `channels.channelCount()` (fl_api ラッパ経由 = MCPTools が通る経路) | 0.333 / 0.337 / 0.522 | 0.339 / 0.342 / 0.547 | 0.332 / 0.339 / 0.367 |
| 静的: 戻り str (`mixer.getTrackName`、malloc/free + decode) | 0.285 / 0.299 / 0.428 | 0.286 / 0.296 / 0.418 | 0.294 / 0.303 / 0.323 |
| 参考: 空の Python 関数呼出し (計測ループの下限) | 0.074 / 0.075 / 0.168 | 0.077 / 0.077 / 0.178 | 0.075 / 0.076 / 0.122 |
| Worker + SAB (同一 provider、`channels.channelCount()`) | 24.321 / 26.575 / 27.165 | 22.827 / 25.049 / 26.224 | 24.058 / 25.675 / 26.961 |

結論: 「<1µs」目標は **Python 呼出し込みで 0.34µs (median) で達成**。SAB 版との比は 73.2〜78.9 倍 (試行ごとの median 同士: 25.049/0.342、26.575/0.337、HEAD 25.675/0.339)。§5 の過去値 (bimodal 15〜130µs) と違い、本 runner の SAB 版は 22.8〜27.2µs の単峰で、15µs 側・100µs 側は再現しなかった (環境差。比較は同一 run 内の値だけを使う)。内訳 (上表の median の差からの推定) は Python のラッパ (`fl_api._make.f` の `bind` + try) が約 0.12µs、`_flhost.call` の引数組立+C 呼出しが約 0.14µs、`fl_api_call` 自体が約 0.013µs。

### Py_* 動的束縛の対応表 (#115 の範囲を本 issue で処理: PM 判断)

FL は `LoadLibrary("Python312")` 後に `Py_*` を動的束縛する。`analysis/pybind_extract.py` が FLEngine PE の `0xc395a0` (InitSharedPython 配下の束縛関数) から名前を機械抽出する。§7 の「平文で無いため未抽出」は**ASCII 検索だけが原因で、名前は UTF-16LE の Delphi 文字列定数として 0x839554〜0x83a520 に連続して入っていた**ので訂正する。

| 項目 | 実測 (`analysis/pybind/pybind_map.{json,tsv}`) |
|---|---|
| 抽出方式 | `0xc395a0` から最初の epilogue までの `lea reg,[rip+rel32]` の参照先を UTF-16LE 文字列として読み、`_?Py[A-Z_]` に一致したものを採る。直後の `call 0x4235f0` (名前→アドレス解決、全 110 件同一) と `mov [rip+rel],rax` (保存先スロット VA) も記録 |
| 束縛名 | **110** (重複 0)。関数 93 + データ 16 (`PyExc_*`・`Py*_Type`・`_Py_{None,True,False}Struct`・`Py_DontWriteBytecodeFlag`) + lib に無い 1。保存先スロット 110/110 |
| `libpython3.12.a` との照合 | 109 件が定義済み (`llvm-nm --defined-only`)。残り 1 件 `_PyInterpreterState_GetRefTotal` は CPython 3.12.1 の `Objects/object.c` で `#ifdef Py_REF_DEBUG` 内のみ定義 = release build に存在しない。FL 同梱の python312.dll は `Py_REF_DEBUG` 付きではないので束縛は実行時に失敗し得るが、FL 側の使用有無は未確認 (下記未解決)。`ALLOW_ABSENT` に根拠付きで 1 件だけ許容し、根拠が成立しなくなったら gate が落ちる |
| 静的版での解決 | `flpy_resolve(name)` が 109 件全てを非 NULL で返す (`pybind_refs.inc` を生成して `src/pybind_resolve.c` が表を持つ)。`wasmTable.get(resolve("Py_IsInitialized"))()` が 1、`PyEval_SaveThread` → `PyEval_RestoreThread` の後も tool が動く |
| サブインタプリタ | `Py_NewInterpreterFromConfig`・`Py_EndInterpreter`・`PyInterpreterState_*`・`PyThreadState_{New,Clear,DeleteCurrent,Swap,Get}` を FL が束縛し、`libpython3.12.a` にも在る。**wasm で実際に新規サブインタプリタを作れるかは未検証** (#76 PY-6) |
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
- GIL: FL は `PyGILState_*` を使わず `PyEval_SaveThread/RestoreThread` + `PyThreadState_New/Swap` を束縛する (上表)。静的版では `SaveThread → RestoreThread` の往復後も tool が動くことを確認済み。**pthread (複数スレッドから同時に Python) 版のビルド・実行は未検証**。単一スレッド wasm 版 (本 PR) は MIDI と UI を 1 つのスレッドで直列に処理する前提で、MIDI スレッドを別スレッドにする場合は pthread ビルド + `PyThreadState_New` 方式が要る (#76 PY-6)。
- メモリモデル (#25): **wasm32 に決定済み** (`tools/runtime/REPORT.md`、Memory64 は退避路)。本 PR は wasm32 でリンクしており、wasm32 の範囲では依存を満たす。provider の追加は +34,146B と小さく、Memory64 へ移る場合も同じ手順で再リンクできる想定 (**Memory64 でのリンクは未検証**)。

### 検証範囲 / 範囲外

- **HEAD 再現 (5a0b3c3、クリーン worktree にコミット済み内容を展開し、`build_flpy.sh` → `provider/build.sh` → `build_flpy_static.sh` を再実行)**: `pybind_extract --check` OK、SAB+provider `all_tools` 48/48・37,424、`static_check` 3 回とも STATIC CHECK OK (差 0/48 ×2)、0.29 / 0.30 / 0.28 秒 (load 1.10)。
- 範囲: node (メインスレッド) での静的版 48 tool と対応表。入力 (MCPTools.pyc 100,674B / midi.py / utils.py / `block00031_PE.bin`) は `fl-win64` 素材から配置。CPython wasm は本 run でクリーンビルド 3m21.904s (4 core)、`build_flpy_static.sh` 5.0 秒。
- 範囲外: **実 FLEngine wasm へのリンクは未実施** (実 FLEngine は MS5 部分起動止まりで `fl_api_call` を持たない)。本節の「FLEngine 側」は `provider/fl_engine.c` の最小エンジン状態。headless Chrome・Worker 内での静的版・`run_all.sh` 全体は未実施。サブインタプリタ・複数スレッド・Memory64 は未検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine wasm へのリンク (`fl_api_call` を FLEngine の内部 API に繋ぐ) | 本節は provider のモック状態で実測しており、実エンジンの意味差は未検証 | #35 (親)。FLEngine 起動 (MS5) 完了後に PY-2b を起票 |
| `_PyInterpreterState_GetRefTotal` を FL が実際に使うか | 使うなら upstream release build では束縛が失敗する (FL 側の失敗時挙動は未確認) | #76 (PY-6) に確認項目として記載 |
| wasm でのサブインタプリタ (`Py_NewInterpreterFromConfig`) 動作 | FL がサブインタプリタ運用なら MIDI/piano roll の分離に影響 | #76 (PY-6、REPORT §9 の T6) |
| pthread 版での複数スレッド + GIL | MIDI スレッド分離の可否 | #76 (PY-6、REPORT §9 の T6) |
| `build_flpy.sh` が追跡中の `flapi_table.json` / `FLAPI.md` を書き換える (runner に win PE / mac dylib が無いため) | 本 PR では再生成物をコミットしていない | 既存 (§10 の未解決と同一。env 化は別 issue で提案済み) |
