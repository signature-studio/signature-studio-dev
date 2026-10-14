# PY-98 (#2858) MEMORY64 静的版の headless Chrome 読込と subinterp heap 測定

**測定 commit: `38344a16`** (コードを変えた最後の commit)。以降の commit は本 REPORT だけを追加する。
親 issue #2633 (PY-80) の成果物 (`REPORT_PY80.md`・`static_subinterp_probe.mjs`) は main に無いため、
既存スクリプトを土台に手順を作り直した。

## 1. 結論

- **受入 1 (縮小後の範囲で達成。12 check 版は #2919)**: `flpy_static64` (`-sMEMORY64=1`) は headless Chrome 155 で読めた。
  validate true、`_flpy_init` 0、`print(1 + 1)` が `2`、`_flpy_subinterp_run` は 1 回と 160 回の全てで ok。
  判定は **PROBE OK (PASS)**。同じ probe の wasm32 版 `flpy_static` も PASS。
  node v22.23.3 では `flpy_static64.wasm` の `WebAssembly.validate` が false (table64 非対応) のため、
  MEMORY64 版の検査は headless Chrome でのみ行える。
- **受入 2 (未達・子 #2918 へ分割)**: 160 回の subinterp 作成/破棄の前後で heap は増えなかった。
  MEMORY64=1 は 33,554,432 B → 33,554,432 B、wasm32 も同じ。
  issue にある MEMORY64=2 の増加 (33,554,432 → 48,365,568 B) は、MEMORY64=2 版を作っていないため再現も比較もしていない。
  増加の原因は未切り分け (子 issue は §8)。
- **検証**: 測定 commit `38344a16` の HEAD でビルドを作り直し、probe を再実行した。wasm の sha256 は再生成の前後で同一で、
  結果は PASS のまま。`git diff 38344a16 HEAD -- tools/python` の出力は 0 行 (差分 0。本 REPORT を追加する前の HEAD で確認)。

## 2. 環境

| 項目 | 値 |
|---|---|
| ブラウザ | google-chrome 155.0.0.0 (HeadlessChrome)。`--headless=new --no-sandbox --disable-gpu` |
| node (比較用のみ) | v22.23.3 |
| emcc | 6.0.12 ([EMSDK] の `emsdk_env.sh`)。`-sMEMORY64=1` で "MEMORY64 is deprecated (prefer -m64 or --target=wasm64)" の警告が出る (ビルドは成功) |
| CPython | 3.12.1 (python.org の Python-3.12.1.tgz、record の source sha256 は d01ec6a33bc1…) |
| 機械 | 4 vCPU / 15 GiB |

素材: wasm32 の stdlib zip (`work/build-wasm/usr/local/lib/python312.zip`) を wasm64 版でも流用した。
`$ARTIFACTS_DIR` の toolchain-emsdk は使わず、[EMSDK] をそのまま使った。

## 3. 再現手順

```
bash tools/python/build_cpython_wasm.sh                     # native build-python + wasm32 (work/build-wasm)
CPY_MEMORY64=1 bash tools/python/build_cpython_wasm.sh      # wasm64 libpython + 補助 lib (work/build-wasm64)
FLPY_MEMORY64=1 bash tools/python/build_flpy_static.sh      # dist/flpy_static64.{js,wasm,data}
bash tools/python/build_flpy_static.sh                      # dist/flpy_static.{js,wasm,data} (wasm32 既定)
node tools/python/tests/static64_browser_probe.mjs flpy_static64
node tools/python/tests/static64_browser_probe.mjs flpy_static
```

ビルド時間 (`date -u`):

| 段階 | 開始 → 終了 | 所要 |
|---|---|---|
| native + wasm32 (python.js まで) | 19:52:23 → 19:56:32 | 4 分 09 秒 |
| wasm64 1 回目 (失敗・§5-1) | 19:56:39 → 19:58:14 | 1 分 35 秒 |
| wasm64 再試行 (configure + libpython3.12.a) | 19:59:01 → 20:01:10 | 2 分 09 秒 |
| wasm64 補助 lib (libmpdec / Hacl / expat) | 20:01:21 → 20:01:22 | 1 秒 (前段で作成済み) |
| flpy link (MEMORY64=1) | 20:01:52 → 20:01:59 | 7 秒 |
| flpy link (wasm32 既定) | 20:04:12 → 20:04:19 | 7 秒 |

## 4. 変更点 (commit `38344a16`)

- `tools/python/build_cpython_wasm.sh`
  - `CPY_MEMORY64=1` で `work/build-wasm64` を作る。configure は wasm32 と同じ引数。
    ただし CONFIG_SITE に `ac_cv_sizeof_long` / `void_p` / `size_t` / `uintptr_t` / `pthread_t` = 8 を追記した
    `work/build-wasm64/config.site-wasm64` を使う (§5-1)。
  - make は `libpython3.12.a` と、`build_flpy_static.sh` が使う補助 lib 3 本 (libmpdec・Hacl SHA2・expat) だけ。`OPT` に `-sMEMORY64=1`。
  - LGL の記録 (`tools/legal/notices/records`) は wasm64 では書かない (wasm32 の記録を変えないため)。
  - 既定 (wasm32) は configure 引数・make 対象・記録とも変えていない。最終版の wasm32 経路を §6-3 で再実行して確認した。
- `tools/python/build_flpy_static.sh`
  - `FLPY_MEMORY64=1` で libpython の dir を `work/build-wasm64` にし、全 emcc の compile / link に `-sMEMORY64=1` を付ける。既定の出力名は `flpy_static64`。
  - `EXPORTED_FUNCTIONS` に `_flpy_subinterp_run` を追加 (wasm32 版も export が 1 つ増える。他は変えていない)。
- `tools/python/tests/static64_browser_probe.mjs` (driver): `browser/serve.mjs` で配信し、headless Chrome で
  `tests/browser/static64.html` を開く。`RESULT` 行を読んで `STATIC64 PROBE OK|FAIL {json}` を出す。
- `tools/python/tests/browser/static64.html` と `static64_probe.mjs`: **main thread** で読込 → validate → init → `print(1 + 1)` → subinterp 1 回 → 160 回 (heap を記録)。

## 5. 失敗と対処

1. **wasm64 libpython の make が失敗** (`make.log` の `Include/pyport.h:586: error: "LONG_BIT definition appears wrong for platform"`。Parser/token.o などで停止)。
   原因: wasm32 の configure 結果の `pyconfig.h` が `SIZEOF_LONG 4` / `SIZEOF_VOID_P 4` / `SIZEOF_SIZE_T 4` のままで、
   wasm64 のコンパイラでは `long` が 64 bit になるため、LONG_BIT の検査で落ちる。
   対処: CONFIG_SITE で sizeof のキャッシュ値を 8 に上書き (`pyconfig.h` で `SIZEOF_LONG 8` / `SIZEOF_VOID_P 8` を確認)。
   configure 自体に `-sMEMORY64=1` を入れると try-compile が壊れるため、configure は wasm32 のまま。
   再現: 上書きの 5 行を外して `rm -rf tools/python/work/build-wasm64 && CPY_MEMORY64=1 bash tools/python/build_cpython_wasm.sh`。
2. **probe 初版が `TypeError: Cannot convert 10268760 to a BigInt` (`_flpy_init`)**。
   原因: `wasm-dis` で確認すると `flpy_init (param i64) (result i32)`、`flpy_subinterp_run (param i64, i32) (result i64)`。
   flpy 系の pointer 引数と戻り値は i64 (JS では BigInt)。一方 `_malloc` / `_free` の JS glue は Number を受けて Number を返す。
   対処: probe で `is64 = typeof M._flpy_last_error() === "bigint"` を判定し、flpy 系には BigInt を渡す (wasm32 でも同じ probe を使える)。修正後に PASS。

## 6. 測定結果

### 6-1. flpy_static64 (MEMORY64=1) と flpy_static (wasm32) の比較

- A 列: 測定 commit 前の作業ツリー (内容は `38344a16` と同一)。`flpy_static64` は 20:03:47、`flpy_static` は 20:04:23 に実行。
- B 列: `38344a16` の HEAD で `build_flpy_static.sh` を再実行 (20:04:53) したあとの probe (20:05:15 頃)。

| 項目 | flpy_static64 A | flpy_static64 B | flpy_static A | flpy_static B |
|---|---|---|---|---|
| probe 判定 | **PASS** | **PASS** | PASS | PASS |
| validate (Chrome) | true | true | true | true |
| validate (node v22.23.3) | (未測定) | false | (未測定) | true |
| wasm bytes | 6,375,192 | 6,375,192 | 5,969,243 | 5,969,243 |
| load_ms (wasm 取得・validate・import・instantiate・preload) | 190 | 203 | 191 | 203 |
| init_ms (`_flpy_init`) / rc | 108 / 0 | 111 / 0 | 101 / 0 | 85 / 0 |
| run_ms (`print(1 + 1)`) / rc / stdout | 19 / 0 / `2` | 31 / 0 / `2` | 11 / 0 / `2` | 18 / 0 / `2` |
| subinterp 1 回 | ok `2` / 100 ms | ok `2` / 117 ms | ok `2` / 83 ms | ok `2` / 80 ms |
| subinterp 160 回 (ok) | 160 / 3,777 ms | 160 / 3,522 ms | 160 / 2,946 ms | 160 / 3,167 ms |
| heap before (init 直後) | 33,554,432 | 33,554,432 | 33,554,432 | 33,554,432 |
| heap after 160 回 | 33,554,432 | 33,554,432 | 33,554,432 | 33,554,432 |
| heap 増加 | **なし** | **なし** | なし | なし |
| heap の途中値 (n = 1, 20, 40, …, 160) | 全て 33,554,432 | 全て 33,554,432 | 全て 33,554,432 | 全て 33,554,432 |
| driver wall_ms (navigate → RESULT) | 4,279 | 4,073 | 3,423 | 3,631 |

注記: `load_ms` は各 page 内の計測。`init` と `run` は 10〜20 ms 程度の揺れが A と B の間にあった。heap の値は全て 32 MiB (`INITIAL_MEMORY`) のまま。

### 6-2. 再現性 (HEAD 再実行)

- `FLPY_MEMORY64=1 bash tools/python/build_flpy_static.sh` と `bash tools/python/build_flpy_static.sh` を HEAD (`38344a16`) で再実行した。
- wasm の sha256 は再生成の前後で同一:
  - `flpy_static64.wasm` = `6f8ec11fd1c9f19649c46e37890e7513ac1ce06568b0314ff0a3e67345762af7`
  - `flpy_static.wasm` = `2771d1a7d6044e000a7c104461ae140fd9ffbed6c2bcf23ccd44727eabe4e59d`
- 差分: `git diff 38344a16 HEAD -- tools/python` は **0 行 (差分 0)**。本 REPORT を追加する前の HEAD で確認した。

### 6-3. wasm32 の配線確認

- 最終版の `build_cpython_wasm.sh` で wasm32 経路を再実行 (20:06:22 UTC、incremental、rc 0)。`python.js` / `libpython3.12.a` は既存のものを使い、`records/cpython-3.12.1.json` は内容が変わらなかった (`git status` が空)。

## 7. 受入条件の判定

| 条件 | 判定 | 根拠 |
|---|---|---|
| 1 (縮小後). MEMORY64=1 を table64 対応エンジン (headless Chrome) で読み、smoke probe の結果 (PASS/FAIL・所要・load) を記録 | **達成** | §6-1 (PASS、load 190/203 ms、driver wall 4.1〜4.3 s)。元の 12 check 版は未実施 → #2919 |
| 2. MEMORY64=2 の heap 増加 (160 回後) の原因を切り分ける | **未達 → #2918** | MEMORY64=1 と wasm32 では増加が出ない (§6-1)。MEMORY64=2 版は本 run で作っていない (範囲外) |

## 8. 未達・子 issue

1. **#2918 `[PY-108]` MEMORY64=2 の subinterp 160 回後の heap 増加 (33,554,432 → 48,365,568 B) の再現と原因切り分け**
   受入: `build_flpy_static.sh` の MEMORY64 分岐を 2 にも対応させ、`static64_browser_probe.mjs` で before/after を記録する。増加を再現したら、増えた分の出所 (subinterp の確保・解放、allocator の挙動) を切り分ける。MEMORY64=1 との差も記録する。
2. **#2919 `[PY-109]` 12 check の subinterp probe を静的版 (headless Chrome) で実行する**
   受入: `tests/subinterp_probe.mjs` と同じ 12 check を `flpy_static64` と `flpy_static` に対して実行し、PASS/FAIL・load・所要を記録する。
3. **起票せず (PM 判断)**: `flpy_static64` の 48 tool 比較 (Worker 版) と、wasm64 の LGL 記録 (`tools/legal/notices/record.mjs --target wasm64`) と、`-sMEMORY64=1` の deprecation 警告 (emcc 6.0.12) の解消。受入条件の外にあるため、子 issue は作らない (子の上限を 2 件に留めた)。

## 9. 本 run で行っていないこと

- node 側の `tests/subinterp_probe.mjs` / `tests/static_check.mjs` は wasm64 に適用していない (node v22 は table64 を読めない)。
- wasm32 版 (`flpy_static`) の 48 tool 比較 (`static_browser_check.mjs`) は未実行 (SAB 版 `dist/flpy.js` / `flprov.js` が無い)。
- MEMORY64=2 は未ビルド (§8-1)。
- probe は main thread で実行 (Worker ではない)。

## 10. 所要

- 開始 19:50:59 UTC (作業開始の確認)、probe の最終実行 20:05:15 UTC、REPORT 作成 20:07 頃。
