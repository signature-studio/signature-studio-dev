# PY-298 (#4082): flpy の zlib port 取得を GitHub タグ 404 から守る

親: #4052 (PY-295)。前段: 2026-10-15 の run で `build_flpy.sh` が emcc の zlib port 取得 (GitHub tag URL) の 404 で rc 1 になった件。

## 結論

- `tools/python/fetch_zlib_port.sh` を追加し、`build_flpy.sh` が emcc を呼ぶ前に zlib 1.3.2 を emsdk の port キャッシュへ用意する。
- 取得順は公式 tag URL → codeload の同一 tarball。emsdk の pin (sha512) と照合し、不一致・全失敗は非 0 で停止する。
- emcc が照合する `.emscripten_url` は公式 URL に固定する。取得元の上書きとは独立。手作業のキャッシュ配置は無し。

## 受入条件の実測

測定 commit: `af9d2390b` (コードを変えた最後の commit)。

| 受入条件 | 結果 |
|---|---|
| tag URL の 404 があっても zlib port を取得して rc 0 で `dist/flpy.js` を作る | PASS。`ZLIB_TAG_URL` を 404 の URL にし、emsdk の zlib キャッシュ (`cache/ports/zlib` と `zlib.tar.gz`) を削除した状態で `build_flpy.sh` rc 0 (7.7 秒)。`fetch_zlib_port: 取得失敗 ... 404` → `sha512 一致 (取得元 codeload)` → `展開済み`。ログに emcc の `retrieving port` が無く、emcc 側の再取得なし |
| 取得した tarball の sha512 を emsdk の pin と照合 (不一致なら非 0) | PASS。`ZLIB_SHA512` を偽の値にすると `sha512 不一致` で rc 1。両経路とも失敗すると `取得できない` で rc 1 |
| 新規 runner (emsdk キャッシュ無し) で rc 0 を実測 | PASS (同上)。`EM_CACHE` を空の一時 dir にした `fetch_zlib_port.sh` 単体も rc 0 (0.6 秒)。二回目はキャッシュ済みで即 rc 0 |

- 公式 tag URL は本 sandbox では 200 を返し、404 は再現していない。404 経路は URL を存在しないものに置換して検証した。

## 検証環境

- emsdk 6.0.12 (`[EMSDK]`)・`toolchain-emsdk` 展開元
- `fl-win64` (`[WIN64]` の `extracted/block00031_PE.bin` 22,227,016 B)
- CPython 3.12.1 wasm: `bash tools/python/build_cpython_wasm.sh` rc 0 (4 分 25 秒、4 コア)
- 入力: `fetch_inputs.sh` rc 0 (`ANALYSIS_DIR` と `FL_WIN64_DIR` に `[WIN64]` の展開先を指定)

## 本番への影響

なし。`launch` の経路・`infra/pm-worker` は変更しない。

## 既知の制約

- `flapi_table.py` は mac dylib 無しのため `midi_script_callbacks_in_binary` を既存値 27 件で引き継いだ (WARN)。build の rc には影響しない。
- 本 run は `flpy.js` / `flpy.wasm` / `flpy.data` のビルド確認まで。実機での起動 (KPI) は動かしていない。
