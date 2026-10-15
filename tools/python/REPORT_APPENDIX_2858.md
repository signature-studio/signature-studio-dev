# PY-98 (#2858) MEMORY64 静的版の headless Chrome 読込と subinterp heap 測定

**測定 commit: `f96998d5`** (コードを変えた最後の commit。main `3d37a190` を取り込んだ merge `694a6a75` の後に、build スクリプトを main 版へ戻した commit)。
ビルドと probe は `f96998d5` で行った。作業ツリーは clean。
以降の commit は本 REPORT と `docs/DOC_MAP.md` の記録だけ (`git diff f96998d5 HEAD -- tools/python ':!tools/python/REPORT_APPENDIX_2858.md'` は 0 行)。

旧経路 (`build_cpython_wasm.sh` の `CPY_MEMORY64=1` で wasm64 libpython を作る版。測定 commit `38344a16`・`10156444`・`f69b2bb8`) は撤回した。その測定値は git 履歴の `ed7d29fe:tools/python/REPORT_APPENDIX_2858.md` §6・§11 に残す。

## 0. 結論

- `flpy_static64` (`-sMEMORY64=1`) は headless Chrome 154 で読め、probe は **PROBE OK 3/3**。wasm32 版 `flpy_static` も **3/3 PASS**。
- 負のコントロール (`flpy_static64.wasm` を 1 byte 切り詰め) は validate false となり、**STATIC64 PROBE FAIL**・exit 1。
- heap: 160 回の subinterp 作成/破棄の後も 33,554,432 B のまま (途中値 n = 0, 1, 20, …, 160 も全て同じ)。
- 受入 1 (縮小後の範囲) は達成。受入 2 (MEMORY64=2 の heap 増加の切り分け) は未達で子 #2918。12 check 版は子 #2919。
- wasm64 libpython は main の `tools/python/build_cpython_wasm64.sh` (PY-80) だけで作る。本 PR は build スクリプトを変えていない。

## 1. 変更点 (main との差分)

- `tools/python/build_cpython_wasm.sh`・`tools/python/build_flpy_static.sh`: 基準 commit `3d37a190` (main) と同一 (本 PR で変更なし)。`origin/main` (`940c0d6a`) では両スクリプトが変わっており、merge 後の main 上の build は本 REPORT の測定対象ではない。`build_cpython_wasm64.sh` は基準と `origin/main` で同一。
- `tools/python/tests/static64_browser_probe.mjs` (driver): `browser/serve.mjs` で配信し、headless Chrome で `tests/browser/static64.html` を開く。`RESULT` 行を読んで `STATIC64 PROBE OK|FAIL {json}` を出す。
- `tools/python/tests/browser/static64.html` と `static64_probe.mjs`: main thread で読込 → validate → init → `print(1 + 1)` → subinterp 1 回 → 160 回 (heap を記録)。
- `docs/DOC_MAP.md`: 本 REPORT の索引行。

## 2. 環境

| 項目 | 値 |
|---|---|
| ブラウザ | google-chrome 154.0.8037.97 (HeadlessChrome/154.0.0.0)。`--headless=new --no-sandbox --disable-gpu` |
| node (比較用のみ) | v22.23.3 |
| emcc | 6.0.12 ([EMSDK] の pin)。上流 `emscripten-core/emsdk` を `git clone --depth 1` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12` で導入 |
| [EMSDK] の所在 | 上の導入先へのシンボリックリンク (`docs/REFERENCES.md` の [EMSDK])。`build_cpython_wasm.sh` と `build_flpy_static.sh` (既定) は [EMSDK] の `emsdk_env.sh` を直書きしているため |
| CPython | 3.12.1 (python.org の Python-3.12.1.tgz、record の source sha256 は d01ec6a33bc1…) |
| 機械 | nproc = 4。ビルドは `make -j4` |

素材: `$ARTIFACTS_DIR` には `fl-win64` だけがあり、`toolchain-emsdk` は無かった。素材は使わず、上流の emsdk を pin 版で導入した。

## 3. 再現手順

```
bash tools/python/build_cpython_wasm.sh                                       # native build-python + wasm32 (work/build-wasm)
EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/python/build_cpython_wasm64.sh   # wasm64 libpython (work/build-wasm64)
cd tools/python
FLPY_MEMORY64=1 CPY_BUILD=$PWD/work/build-wasm64 STATIC_OUT=flpy_static64 bash build_flpy_static.sh  # dist/flpy_static64.*
bash build_flpy_static.sh                                                     # dist/flpy_static.* (wasm32 既定)
for i in 1 2 3; do cut -d' ' -f1-3 /proc/loadavg; node tests/static64_browser_probe.mjs flpy_static64; done
for i in 1 2 3; do cut -d' ' -f1-3 /proc/loadavg; node tests/static64_browser_probe.mjs flpy_static; done
```

## 4. 所要 (wall・rc 0 は全件)

- `build_cpython_wasm.sh` (native + wasm32): 256.1 s。
- `build_cpython_wasm64.sh` (`EMSDK_ENV` 指定): 172.2 s。
- `build_flpy_static.sh`: flpy_static64 6.6 s・flpy_static 6.5 s。
- 再リンク (同じ HEAD): flpy_static64 と flpy_static の各 1 回。sha256 は 1 回目と一致 (§5-2)。
- probe: 6 回 + 負のコントロール 1 回。

## 5. 測定結果 (`f96998d5`)

### 5-1. n=3 の probe (直列)

測定方法: 各 probe の直前に `/proc/loadavg` の 1 分値 (先頭 1 列) を記録し、probe を 1 本ずつ直列で実行した。
所要の単位は ms (`load_ms`・`init_ms`・`run_ms`・`sub_once_ms` は page 内の計測、`sub_loop_ms` は 160 回の合計、`wall_ms` は driver の navigate → RESULT)。

| 版 | n | probe 直前の load1 | validate | wasm bytes | load | init | run | subinterp 1 回 | subinterp 160 回 | heap (n = 0〜160) | wall | 判定 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| flpy_static64 | 1 | 1.37 | true | 6,375,768 | 179 | 118 | 15 | 101 | 3,394 | 33,554,432 → 33,554,432 (途中値も同じ) | 3,917 | PROBE OK |
| flpy_static64 | 2 | 1.37 | true | 6,375,768 | 187 | 111 | 25 | 139 | 3,481 | 同上 | 4,029 | PROBE OK |
| flpy_static64 | 3 | 2.14 | true | 6,375,768 | 174 | 123 | 28 | 94 | 3,622 | 同上 | 4,121 | PROBE OK |
| flpy_static | 1 | 2.37 | true | 5,969,873 | 187 | 81 | 22 | 92 | 2,500 | 同上 | 2,955 | PROBE OK |
| flpy_static | 2 | 3.06 | true | 5,969,873 | 170 | 93 | 14 | 114 | 2,869 | 同上 | 3,357 | PROBE OK |
| flpy_static | 3 | 2.89 | true | 5,969,873 | 199 | 80 | 15 | 84 | 2,697 | 同上 | 3,156 | PROBE OK |

- min–max: flpy_static64 は load 174–187 ms・init 111–123 ms・run 15–28 ms・subinterp 1 回 94–139 ms・160 回 3,394–3,622 ms (wall 3,917–4,121 ms)。flpy_static は load 170–199 ms・init 80–93 ms・run 14–22 ms・subinterp 1 回 84–114 ms・160 回 2,500–2,869 ms (wall 2,955–3,357 ms)。
- 6 回とも `run_stdout: "2"`・`sub_once` ok・`sub_loop_ok: 160`・`ptr_is_bigint` (flpy_static64 は true、flpy_static は false)・`crossOriginIsolated: true`・rc 0。
- load の注記: 直前の 1 分値は、前の probe の Chrome 起動で上がっている (1.37 → 3.06)。probe は build が終わった後に流した。5 分値・15 分値は測っていない。

### 5-2. 負のコントロールと再現性

- 負のコントロール: `dist/flpy_static64.wasm` (6,375,768 B) を `truncate -s -1` (6,375,767 B) → `validate: false`・`STATIC64 PROBE FAIL`・rc 1。
  error: `CompileError: WebAssembly.instantiate(): section (code 11, "Data") extends past end of the module`。退避先から戻し、`cmp` で一致を確認。
- 再リンク: 同じ HEAD で 2 回ずつ link し、sha256 は一致。
  - `flpy_static64.wasm` = `def49c4d3a70c8ab5685762e65fbddd76ecc48983d4c7da6bae3ffde0b67af49`
  - `flpy_static.wasm` = `3fe7981d6be46f58c0fb44c9a2e4aa9b31ea3e51f1fadf100f89dbbf1546b47d`

### 5-3. wasm64 の配線

- main の `build_cpython_wasm64.sh` (`--host=wasm64-unknown-emscripten`) は configure・make とも rc 0。`work/build-wasm64/pyconfig.h` の `SIZEOF_LONG` は 8、`SIZEOF_VOID_P` は 8 (wasm32 の `work/build-wasm` は 4 / 4)。sizeof の上書きは不要だった。
- `make.log` の `-sMEMORY64=` は 215 件。`-sMEMORY64=1` の deprecation 警告 (emcc 6.0.12) は出ている。

## 6. 失敗と対処

1. **旧経路の失敗 (撤回済み)**: 旧経路 (wasm32 host・`CONFIG_SITE` で sizeof を 8 に上書き) では `Include/pyport.h:586: error: "LONG_BIT definition appears wrong for platform"` で make が止まった。main の `--host=wasm64` 経路では発生せず rc 0 (§5-3)。旧経路は撤回した。
2. **probe 初版が `TypeError: Cannot convert 10268760 to a BigInt` (`_flpy_init`)**: `flpy_init` の pointer 引数は i64 (JS では BigInt)。`_malloc` / `_free` は Number を受ける。probe で `is64 = typeof M._flpy_last_error() === "bigint"` を判定し、flpy 系には BigInt を渡す。修正後に PASS。

## 7. 受入条件の判定

| 条件 | 判定 | 根拠 |
|---|---|---|
| 1 (縮小後). MEMORY64=1 を headless Chrome で読み、smoke probe の結果 (PASS/FAIL・所要・load) を記録 | **達成** | §5-1 (PROBE OK 3/3・load 174–187 ms・1 分値 1.37–2.14)。負のコントロールは §5-2。元の 12 check 版は #2919 |
| 2 (縮小前の受入。縮小後の範囲から外し #2918 へ). MEMORY64=2 の heap 増加 (160 回後) の原因を切り分ける | **未達 → #2918** | MEMORY64=1 と wasm32 では増加が出ない (§5-1)。MEMORY64=2 版は本 PR で作っていない |

## 8. 未達・子 issue

1. **#2918 `[PY-108]` MEMORY64=2 の subinterp 160 回後の heap 増加 (33,554,432 → 48,365,568 B) の再現と原因切り分け**
   受入: `build_flpy_static.sh` の MEMORY64 分岐を 2 にも対応させ、`static64_browser_probe.mjs` で before/after を記録する。
2. **#2919 `[PY-109]` 12 check の subinterp probe を静的版 (headless Chrome) で実行する**
   受入: `tests/subinterp_probe.mjs` と同じ 12 check を `flpy_static64` と `flpy_static` に対して実行し、PASS/FAIL・load・所要を記録する。
3. **起票せず (PM 判断)**: `flpy_static64` の 48 tool 比較 (Worker 版)・wasm64 の LGL 記録・`-sMEMORY64=1` の deprecation 警告の解消。受入条件の外にあるため子 issue は作らない。

子 #2918・#2919 の本文は main の経路 (`build_cpython_wasm64.sh`・`FLPY_MEMORY64`・`CPY_BUILD`) へ直した。撤回した `CPY_MEMORY64` の手順と §6-1 の参照は外し、上流の実測は §5-1・§5-3 に向けた (本文のみの編集。測定は変えていない)。

## 9. 本 PR で行っていないこと

- MEMORY64=2 は未ビルド (#2918)。node 側の `tests/subinterp_probe.mjs` / `tests/static_check.mjs` は wasm64 に適用していない (node v22 は table64 を読めない。`WebAssembly.validate` は false)。
- wasm32 版 `flpy_static` の 48 tool 比較 (`static_browser_check.mjs`) は未実行 (SAB 版 `dist/flpy.js` / `flprov.js` が無い)。
- probe は main thread で実行 (Worker ではない)。load の 5 分値・15 分値は記録していない。
