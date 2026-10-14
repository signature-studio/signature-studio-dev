# PY-98 (#2858) MEMORY64 静的版の headless Chrome 読込と subinterp heap 測定

**測定 commit: `38344a16`** (コードを変えた最後の commit)。以降の commit は本 REPORT と PR 本文の記録だけ。
測定の検証 HEAD は `10156444` (fix 対応の前の PR 枝 HEAD)。作業ツリーは clean で、ビルドと probe はこの HEAD で行った。
親 issue #2633 (PY-80) の成果物 (`REPORT_PY80.md`・`static_subinterp_probe.mjs`) は main に無いため、
既存スクリプトを土台に手順を作り直した。

## 1. 結論

- **main 取り込み後の最新 (merge `f69b2bb8`)**: 同じ probe を wasm64・wasm32 で各 n=3 再測定し、6/6 PROBE OK。負のコントロールは FAIL。値は §11。以下の §1〜§10 は `38344a16`・`10156444` 版の記録。
- **受入 1 (縮小後の範囲で達成。12 check 版は #2919)**: `flpy_static64` (`-sMEMORY64=1`) は headless Chrome 154 で読めた。
  n=3 の全回で validate true、`_flpy_init` 0、`print(1 + 1)` が `2`、`_flpy_subinterp_run` は 1 回と 160 回の全てで ok。
  判定は **PROBE OK (3/3)**。同じ probe の wasm32 版 `flpy_static` も 3/3 PASS。
- **所要 (n=3 の min–max)**: `flpy_static64` は load 134–205 ms・init 114–128 ms・run 19–28 ms・subinterp 1 回 94–115 ms・160 回 3,360–3,681 ms。
  load average (probe 直前の 1 分値) は 1.97–2.25。詳細は §6-1。
- **負のコントロール**: `flpy_static64.wasm` を 1 byte 切り詰めると validate が false になり、`STATIC64 PROBE FAIL`・exit 1 (§6-2)。
- **受入 2 (縮小前の受入。未達・子 #2918 へ分割)**: 160 回の subinterp 作成/破棄の前後で heap は増えなかった。
  MEMORY64=1 は 33,554,432 B → 33,554,432 B、wasm32 も同じ。
  issue にある MEMORY64=2 の増加 (33,554,432 → 48,365,568 B) は、MEMORY64=2 版を作っていないため再現も比較もしていない。
  増加の原因は未切り分け (子 issue は §8)。
- node v22.23.3 では `flpy_static64.wasm` の `WebAssembly.validate` が false (table64 非対応) のため、
  MEMORY64 版の検査は headless Chrome でのみ行える。

## 2. 環境

| 項目 | 値 |
|---|---|
| ブラウザ | google-chrome 154.0.8037.97 (HeadlessChrome/154.0.0.0)。probe の起動引数 `--headless=new --no-sandbox --disable-gpu` |
| node (比較用のみ) | v22.23.3 |
| emcc | 6.0.12 ([EMSDK] の pin)。この run で上流から取得し `activate 6.0.12`。`-sMEMORY64=1` で "MEMORY64 is deprecated (prefer the standard -m64 or --target=wasm64 flags)" の警告が出る (ビルドは成功) |
| CPython | 3.12.1 (python.org の Python-3.12.1.tgz、record の source sha256 は d01ec6a33bc1…) |
| 機械 | nproc = 4。ビルドは `make -j4` (`nproc`) |

素材: `$ARTIFACTS_DIR` には `fl-win64` だけがあり、`toolchain-emsdk` は無かった。
この run では [EMSDK] の pin (6.0.12) を上流から取得して使った (素材は使っていない)。
wasm32 の stdlib zip (`work/build-wasm/usr/local/lib/python312.zip`) を wasm64 版でも流用した。

## 3. 再現手順

```
bash tools/python/build_cpython_wasm.sh                     # native build-python + wasm32 (work/build-wasm)
CPY_MEMORY64=1 bash tools/python/build_cpython_wasm.sh      # wasm64 libpython + 補助 lib (work/build-wasm64)
FLPY_MEMORY64=1 bash tools/python/build_flpy_static.sh      # dist/flpy_static64.{js,wasm,data}
bash tools/python/build_flpy_static.sh                      # dist/flpy_static.{js,wasm,data} (wasm32 既定)
for i in 1 2 3; do cut -d' ' -f1-3 /proc/loadavg; node tests/static64_browser_probe.mjs flpy_static64; done
for i in 1 2 3; do cut -d' ' -f1-3 /proc/loadavg; node tests/static64_browser_probe.mjs flpy_static; done
```

負のコントロール (§6-2): `cp -p dist/flpy_static64.wasm <退避先>` → `truncate -s -1 dist/flpy_static64.wasm` → probe → 退避先から戻す。

## 4. 変更点 (commit `38344a16`)

- `tools/python/build_cpython_wasm.sh`
  - `CPY_MEMORY64=1` で `work/build-wasm64` を作る。configure は wasm32 と同じ引数。
    ただし CONFIG_SITE に `ac_cv_sizeof_long` / `void_p` / `size_t` / `uintptr_t` / `pthread_t` = 8 を追記した
    `work/build-wasm64/config.site-wasm64` を使う (§5-1)。
  - make は `libpython3.12.a` と、`build_flpy_static.sh` が使う補助 lib 3 本 (libmpdec・Hacl SHA2・expat) だけ。`OPT` に `-sMEMORY64=1`。
  - LGL の記録 (`tools/legal/notices/records`) は wasm64 では書かない (wasm32 の記録を変えないため)。
  - 既定 (wasm32) は configure 引数・make 対象・記録とも変えていない。
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

### 6-1. n=3 の所要 (HEAD `10156444`・コード差分なし)

- 測定方法: 同じ HEAD で作ったビルド物に対し、probe を各 3 回ずつ実行。probe は 1 本ずつ直列 (Chrome は 1 インスタンス)。
  load は各 probe の直前の `/proc/loadavg` の 1 分値 (先頭 1 列)。機械は nproc = 4。
- 所要の単位は ms (`load_ms`・`init_ms`・`run_ms`・`sub_once_ms` は page 内の計測、`sub_loop_ms` は 160 回の合計、`wall_ms` は driver の navigate → RESULT)。

| 項目 | flpy_static64 (MEMORY64=1) 1 回目 / 2 回目 / 3 回目 | min–max | flpy_static (wasm32) 1 回目 / 2 回目 / 3 回目 | min–max |
|---|---|---|---|---|
| probe 判定 | PASS / PASS / PASS | 3/3 | PASS / PASS / PASS | 3/3 |
| validate (Chrome) | true ×3 | | true ×3 | |
| wasm bytes | 6,375,192 | | 5,969,243 | |
| load_ms | 205 / 197 / 134 | 134–205 | 159 / 188 / 185 | 159–188 |
| init_ms (rc 0) | 128 / 128 / 114 | 114–128 | 85 / 95 / 106 | 85–106 |
| run_ms (`print(1 + 1)`, rc 0, stdout `2`) | 19 / 25 / 28 | 19–28 | 19 / 18 / 18 | 18–19 |
| subinterp 1 回 (ok `2`) ms | 94 / 115 / 115 | 94–115 | 89 / 114 / 96 | 89–114 |
| subinterp 160 回 (ok) ms | 3,360 / 3,449 / 3,681 (ok 160 ×3) | 3,360–3,681 | 2,728 / 3,104 / 3,212 (ok 160 ×3) | 2,728–3,212 |
| heap before / after 160 回 | 33,554,432 / 33,554,432 (×3) | | 33,554,432 / 33,554,432 (×3) | |
| heap 増加 | なし (×3) | | なし (×3) | |
| heap の途中値 (n = 0, 1, 20, …, 160) | 全て 33,554,432 (×3) | | 全て 33,554,432 (×3) | |
| driver wall_ms | 4,023 / 4,010 / 4,158 | 4,010–4,158 | 3,179 / 3,608 / 3,725 | 3,179–3,725 |
| probe 直前の load (1 分値) | 2.25 / 2.05 / 1.97 | 1.97–2.25 | 1.81 / 1.99 / 2.71 | 1.81–2.71 |

注記: 直前の load は、同じ作業の直前に行ったビルド (wasm64 link・flpy link) の影響を受けている。
load の 5 分値・15 分値は測っていない。

### 6-2. 負のコントロール (validate を false にして FAIL することを確認)

| 項目 | 値 |
|---|---|
| 操作 | `dist/flpy_static64.wasm` を `truncate -s -1` (6,375,192 → 6,375,191 B)。probe 後に退避先から戻し、sha256 が測定時と一致することを確認 |
| validate | **false** |
| 判定 | **`STATIC64 PROBE FAIL`・exit 1** |
| error | `CompileError: WebAssembly.instantiate(): section (code 11, "Data") extends past end of the module (length 3123900, remaining bytes 3123899) @+3251287` |
| 所要 | driver wall_ms 462 / `node` 実行の real 0.992 s |

### 6-3. 再現性 (同一環境での再リンク)

| wasm | 測定時の sha256 | 再リンク後の sha256 | 一致 |
|---|---|---|---|
| `flpy_static64.wasm` | `086e82e88cb10e3add46f4f415dd8bf09ea9da4a610badf031d7e06aeca48a16` | 同じ値 (`FLPY_MEMORY64=1 bash tools/python/build_flpy_static.sh` を再実行) | 一致 |
| `flpy_static.wasm` | `98612d4d102374ce7d2cb7b8431076a53c6de9c591c9fa1b914727215d23be4c` | 同じ値 (`bash tools/python/build_flpy_static.sh` を再実行) | 一致 |

- 前回 (PY-98 初版の環境) の sha256 は `flpy_static64.wasm` = `6f8ec11f…`・`flpy_static.wasm` = `2771d1a7…` で、今回と一致しない。wasm のバイト数は一致 (6,375,192 / 5,969,243)。
  差の原因は未切り分け (emsdk の取得元・環境差の可能性)。どちらも同一環境では再現した。
- 差分 0 の確認: `git diff 38344a16 10156444 -- tools/python ':!tools/python/REPORT_APPENDIX_2858.md'` は 0 行。
  本 REPORT を含む commit の後も同じ pathspec で 0 行。

### 6-4. wasm32 の配線確認

- `bash tools/python/build_cpython_wasm.sh` (native build-python と wasm32 の全段) を HEAD で再実行し rc 0。
  `records/cpython-3.12.1.json` は再記録されたが、`git status` は変化なし (内容は変わらなかった)。
- wasm32 の `flpy_static` は 6-1 のとおり 3/3 PASS。

## 7. 受入条件の判定

| 条件 | 判定 | 根拠 |
|---|---|---|
| 1 (縮小後). MEMORY64=1 を table64 対応エンジン (headless Chrome) で読み、smoke probe の結果 (PASS/FAIL・所要・load) を記録 | **達成** | §6-1 (PROBE OK 3/3、load 134–205 ms・load average 1.97–2.25)。負のコントロールは §6-2。元の 12 check 版は未実施 → #2919 |
| 2 (縮小前の受入。縮小後の範囲から外し #2918 へ). MEMORY64=2 の heap 増加 (160 回後) の原因を切り分ける | **未達 → #2918** | MEMORY64=1 と wasm32 では増加が出ない (§6-1)。MEMORY64=2 版は本 run で作っていない (範囲外) |

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
- load の 5 分値・15 分値は記録していない (§6-1 の注記を参照)。

## 10. 所要

- ビルド (fix 対応の run、UTC): wasm32 (native 含む) `20:20:40 → 20:25:09` = 4 分 29 秒 (make -j4、開始時の 1 分 load 0.40)。
  wasm64 libpython `20:25:17 → 20:27:22` = 2 分 05 秒 (rc 0、native は流用)。
  flpy link 2 本 (`20:27:22 → 20:27:48`)。flpy64 単独の `time` real は 20.0 秒。
- probe: 6 回 (flpy_static64 3 回・flpy_static 3 回)。負のコントロール 1 回。再リンク 2 回 (sha 確認)。

## 11. main 取り込み後の再測定 (merge `f69b2bb8`)

- 測定 commit: `f69b2bb8` (main `2899945e` を merge したコミット。競合は `tools/python/build_flpy_static.sh` の 2 ブロック。解消方針は PR コメント)。
- 再測定の理由: main 取り込みで `tools/python` が測定 commit `38344a16` から変わった。
  `git diff 38344a16 f69b2bb8 -- tools/python ':!tools/python/REPORT_APPENDIX_2858.md'` は 2,275 行 (25 file)。§6 の値は `38344a16`・`10156444` 版の記録として残す。
- 測定後のコード差分: `git diff f69b2bb8 HEAD -- tools/python ':!tools/python/REPORT_APPENDIX_2858.md'` の出力は 0 行 (本節の REPORT の commit だけが後に続く)。
- 環境: emcc 6.0.12 ([EMSDK] の pin) を上流から install・activate (素材 `toolchain-emsdk` は使わず)。nproc = 4。google-chrome 154.0.8037.97 (headless)。
- 手順と所要 (UTC・rc 0 は全件):
  - `bash build_cpython_wasm.sh` (native と wasm32): 4 分 23 秒 (`20:43:51 → 20:48:14`)。
  - `CPY_MEMORY64=1 bash build_cpython_wasm.sh`: 2 分 02 秒 (`20:48:25 → 20:50:27`)。
  - `FLPY_MEMORY64=1 bash build_flpy_static.sh` (既定の出力名 `flpy_static64`): 19.5 秒。
  - `bash build_flpy_static.sh` (wasm32 の `flpy_static`): 完了 (`20:51:01`)。

### 11-1. probe (n=3・直列)

| 版 | n | probe 直前の load1 | validate | load ms | init ms | run ms | subinterp 1 回 ms | subinterp 160 回 ms | heap (160 回の前後) | wall ms | 判定 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|---:|---|
| flpy_static64 | 1 | 3.44 | true | 238 | 151 | 26 | 121 | 3,561 | 33,554,432 → 33,554,432 | 4,175 | PROBE OK |
| flpy_static64 | 2 | 3.25 | true | 212 | 133 | 21 | 97 | 3,385 | 同上 | 3,923 | PROBE OK |
| flpy_static64 | 3 | 3.71 | true | 159 | 120 | 26 | 122 | 3,395 | 同上 | 3,945 | PROBE OK |
| flpy_static | 1 | 3.49 | true | 176 | 101 | 22 | 98 | 2,786 | 同上 | 3,280 | PROBE OK |
| flpy_static | 2 | 3.49 | true | 187 | 115 | 16 | 98 | 2,738 | 同上 | 3,272 | PROBE OK |
| flpy_static | 3 | 3.69 | true | 179 | 87 | 23 | 89 | 2,823 | 同上 | 3,308 | PROBE OK |

- 6 回とも `heap_grew: false`・`run_stdout: "2"`・`sub_loop_ok: 160`・rc 0。
- load1 は 1 分値で、直前の link・build の影響を受けている (4 コア・load 3.2〜3.7)。5 分値・15 分値は測っていない。

### 11-2. 負のコントロールと再現性

- 負のコントロール: `dist/flpy_static64.wasm` (6,375,560 B) を `truncate -s -1` → `STATIC64 PROBE FAIL`・rc 1。退避先から戻し、`cmp` で一致を確認。
- 再現性: 同一 HEAD で 2 回目の link をし、sha256 は 1 回目と一致 (`flpy_static64.wasm` = `6b22fd07…d76aa`、`flpy_static.wasm` = `91b95e52…2336e`)。
  §6-3 の sha256 (`38344a16` 版) とは一致しない。`tools/python` のソースが main 取り込みで変わったため (原因の切り分けはしていない)。
- 変更点の確認 (zip 取得元): wasm32 の既定は `$WORK/build-wasm` の stdlib zip を使い、link と probe 3/3 PASS を確認。
  `FLPY_MEMORY64=2` (`CPY_BUILD=work/build-wasm64l`) の経路は本節では回していない (`build_cpython_wasm64.sh` 未実行)。zip 取得元の変更がその経路に効く点は未確認。
