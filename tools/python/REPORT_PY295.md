# PY-295 (#4052): flpy 経路 (dist/flpy.js) で all_tools 48/48 と provider_check を通す

親: #3706 (PY-236)。前段: `tools/python/REPORT_PY130_3007.md` (flpy 経路が未実行)。

## 結論

- 受入 1〜4 を全て満たした。`dist/flpy.js` を作り、`FL_ENGINE=wasm node tests/all_tools.mjs` は 48/48 ok、`node tests/provider_check.mjs` は全 assert を通過して `PASS: true`。
- コードの変更は無し。本 PR は測定結果の記録だけ。
- 本 run で通すために、emsdk の zlib port の取得経路を差し替えた (§2)。`build_flpy.sh` 自体は無変更。GitHub の zlib 1.3.2 タグ取得が 404 になるため、Actions で `build_flpy.sh` を通すには同じ差し替えが要る (未解決 §4)。

## 0. 測定の前提

- 測定 commit: `0d1f2a8fa` (origin/main `4413f932f` を取り込んだ merge commit。本 PR はこの上に REPORT と DOC_MAP の追記のみを足す)。
- 素材: `$ARTIFACTS_DIR` の `fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf` で展開し、その展開先を `FL_WIN64_DIR` ([WIN64])、`toolchain-emsdk.tar.zst` の展開先を `EMSDK_DIR` ([EMSDK]) に指定した (各 6 秒前後)。
- `FL_MAC_DIR` は無い。`fetch_inputs.sh` は win64 の DATA block から MCPTools.pyc・midi.py・utils.py・device script を取った (rc 0)。`flapi_table.py` は mac dylib 無しの WARN を出し、midi_script_callbacks_in_binary は既存値 27 件を引き継いだ (`analysis/flapi/` に差分は出ない)。

## 1. 実測

| 手順 | コマンド | rc | 所要 | 結果 |
|---|---|---|---|---|
| CPython wasm | `bash tools/python/build_cpython_wasm.sh` | 0 | 3 分 36 秒 | `python.js` / `python.wasm` / `libpython3.12.a` を生成 (`work/build-wasm`) |
| 入力 | `bash tools/python/fetch_inputs.sh` | 0 | 0.6 秒 | `work/midi.py`・`utils.py`・device script・`fl-stubs` (clone) |
| flpy | `bash tools/python/build_flpy.sh` | 0 | 5.5 秒 | `dist/flpy.js` 120,454 B・`flpy.wasm` 5,923,675 B・`flpy.data` 3,295,630 B (zlib 取得は §2) |
| provider | `bash tools/python/provider/build.sh` | 0 | 1.1 秒 | `dist/flprov.js`・`flprov.wasm`。`fl_table.c`: 435 関数・ハンドラ 203 (測定 HEAD `0d1f2a8fa`) |
| all_tools | `FL_ENGINE=wasm node tests/all_tools.mjs` | 0 | 1.37 秒 | `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` |
| provider_check | `node tests/provider_check.mjs` | 0 | 0.28 秒 | `{"functions":435,"implemented":203,"unimplemented":232,"mcp_static":60,"PASS":true}` |

- load (計測時): `uptime` の 1 分平均 0.75 (4 vCPU)。
- all_tools と provider_check は、assert 失敗時に例外で止まる構成。最後の `console.log` に到達した時点で全 section を通過している。

## 2. zlib port の取得 (環境の回避。repo は無変更)

- `build_flpy.sh` は `-sUSE_ZLIB` を使う。emcc の zlib port は `https://github.com/madler/zlib/archive/refs/tags/v1.3.2.tar.gz` を取りに行くが、この URL は本 run で **HTTP 404** だった。
- 対策: emsdk の pin (`upstream/emscripten/tools/ports/zlib.py` の sha512) と一致する tarball を `https://codeload.github.com/madler/zlib/tar.gz/refs/tags/v1.3.2` から取得 (sha512 一致を確認)。`cache/ports/zlib.tar.gz` に置くと emcc は既存の取得済み tarball として展開する (emsdk はこの場合ダウンロードもハッシュ検査も行わない)。
- 参考: `zlib.net/zlib-1.3.2.tar.gz` は同じ版名だが、sha512 は pin と一致しない (別アーカイブ)。使っていない。
- bzip2 port は `github.com/emscripten-ports/bzip2` からの取得が通った (rc 0)。

## 3. 検証の手順 (再現用)

```
EMSDK_DIR=<emsdk 展開先> FL_WIN64_DIR=<fl-win64 展開先> bash tools/python/build_cpython_wasm.sh
EMSDK_DIR=... FL_WIN64_DIR=... bash tools/python/fetch_inputs.sh
EMSDK_DIR=... FL_WIN64_DIR=... bash tools/python/build_flpy.sh          # §2 の zlib を置いた後
EMSDK_ENV=$EMSDK_DIR/emsdk_env.sh bash tools/python/provider/build.sh
cd tools/python && FL_ENGINE=wasm node tests/all_tools.mjs && node tests/provider_check.mjs
```

- 注意 (main 取り込み後の再実行で判明): `build_cpython_wasm.sh` は `EMSDK_DIR` を見ず `[EMSDK]` の `emsdk_env.sh` をハードコードしている (`[EMSDK]` の既定位置)。`[EMSDK]` が無いと rc 1 でログ無しに落ちる。この run では `[EMSDK]` を emsdk 6.0.12 の展開先へのシンボリックリンクにして通した。`build_flpy.sh` は `build_cpython_wasm.sh` の成果物を要求するため、この順で実行する。
- `build_flpy.sh` は `fetch_inputs.sh` の後でないと `fl-stubs` 不足で落ちる。`provider/build.sh` は `build_flpy.sh` の後に `dist/flprov.js` を作る。`fl_provider.mjs` が `dist/flprov.js` を要求するため、これが無いと `all_tools` は ERR_MODULE_NOT_FOUND で落ちる。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| emsdk の zlib port の取得 URL (GitHub タグ) が 404。Actions の `build_flpy.sh` は §2 の手作業なしでは通らない | flpy 経路を新しい runner で作れない [PY-298] #4082 |
| `FL_MAC_DIR` 無し (mac dylib 無し)。`midi_script_callbacks_in_binary` は既存値 27 件を引き継いだ | `flapi_table.json` の mac 由来の値は更新されていない (本測定の PASS には影響しない) | 起票しない (既知の運用。本 REPORT の §1 に記録のみ) |
