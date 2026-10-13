# ILSvg 版の組 probe (#877 / 親 #151)

結論 1 行: svgdom 0.4.7 は emcc で 26/26 cpp が通る。svgren 0.6.3 / 0.5.9 は svgdom 0.4.7 と enum 名が合わず版の組は未確定 (詳細は下表・§結論)。

再現: `bash tools/shared/oss/ilsvg/probe_svgdom.sh` (生成物は `tools/shared/work/ilsvg_probe/`、gitignore)。
clean HEAD での実測: 1 run あたり 33.8 s (real)、load average 0.38 (開始時)。

## 実測 (emcc 6.0.12, -O0, -std=c++17, 単発)

| 構成 | 結果 |
|---|---|
| svgdom 0.4.7 + utki 1.1.200 + r4 1.0.74 + papki 1.0.101 (`make_unique` を `std::make_unique` へ置換) + cssom 0.2.4 + mikroxml 0.1.56 | **26/26 OK** |
| svgren 0.6.3 (svgdom 0.4.7 と結合) | 2/6 OK。4 件失敗: `svgdom::gradient::spread_method::default_` / `fe_composite_element::operator_` / `gradient::spread_method_` / `enable_background::new_` の名前不一致 |
| svgren 0.5.9 (svgdom 0.4.7 と結合, `-include list`) | 1/6 OK。5 件失敗: 同じ enum 名不一致と `svgren/surface.cpp` の文字列連結不一致 |
| svgdom 0.3.59 | cssdom を要求 (cssdom 最新 tag は 0.2.24)。cssom ではない。未検証 |

## 版の制約 (tag 日付と API の突合)

- `utki::make_unique`: utki 1.1.170 までで、1.1.179 で消える。papki 1.0.101 (2021-06-09) が使う。
- `utki::string_parser::get_view`: utki 1.1.187 から。svgdom 0.4.7 が使う。
- `utki::pi<T>()` (関数テンプレート): utki 1.1.209 まで。svgren 0.6.3 が使う。
- `utki::pi_degrees`: utki 1.1.209 から。0.3.x 系と 0.4.x の一部が使う。
- svgdom 0.4.7 は `default_method` / `new_background` 等の enum 名を使う。svgren 0.5.9/0.6.3 は `default_` / `new_` を使う。
  svgdom の enum 名は 0.3.32 〜 0.3.59 で `default_` 形式。0.4.x の tag 範囲内に両方の enum 名が現れる版は未確定。

## 版の組の確定 (#927)

svgren の enum 名は 0.6.4 で svgdom 0.4.x 系と揃う (0.6.3 までは `default_` / `new_`、0.6.4 以降は `default_method` / `new_background`)。
0.6.9 以降は `rasterimage`、0.6.30 は `veg` を要求する。

| 構成 | 結果 (emcc 6.0.12, -O0, -std=c++17) |
|---|---|
| svgdom 0.4.7 (26 cpp) | ok=26 fail=0 (25.7 s real) |
| svgren 0.6.4 (6 cpp) | ok=6 fail=0 (7.5 s real) |

採用する組 (wrapper: `oss/ilsvg/wrap/ilsvg_wrap.cpp`):

| 部品 | 版 |
|---|---|
| svgdom | 0.4.7 |
| svgren | 0.6.4 |
| utki | 1.1.200 |
| r4 | 1.0.74 |
| papki | 3ed8151 (= 1.0.101, probe 限定で `utki::make_unique` → `std::make_unique`) |
| cssom | 0.2.4 (probe 限定で `utki::kilobyte` → `1024`) |
| mikroxml | 0.1.56 |
| agg | 2.8.9 |
| rasterimage / veg | 不要 (0.6.4 は使わない) |

連結ビルド: `bash tools/shared/oss/ilsvg/build_pair.sh` (生成物 `tools/shared/work/ilsvg_pair/`)。
wasm 連結には `-fno-sized-deallocation` と `em++` が必要 (`emcc` のみだと C++ ランタイムが未リンク)。papki の `fs_file.cpp` は emscripten 非対応のため除外。
native 比較は `-lz` を追加。

3 関数 wrapper: `svgCreate` / `svgRender` / `svgDestroy` (`oss/ilsvg/wrap/ilsvg_wrap.cpp`)。

### 検証 (スモーク SVG 64x64: linearGradient 矩形 + 円, `wrap/smoke.svg`)

再現: `bash tools/shared/oss/ilsvg/build_pair.sh` (末尾で native 描画・wasm 描画 (`wrap/wasm_smoke.cjs`)・`cmp` を一括実行)。
emsdk は 6.0.12 を使用 (`EMSDK_ENV` で `emsdk_env.sh` の場所を指定可、既定は `/opt/emsdk/emsdk_env.sh`)。

HEAD `4c7057e0` (main を merge 済み、ilsvg 配下は merge 前後で差分 0) での実測 (clean 再生成、`tools/shared/work/ilsvg_pair/` を削除してから実行、load average 0.93 開始時):

| 項目 | 実測 |
|---|---|
| `build_pair.sh` real | 1 m 39.7 s (exit 0) |
| wasm 出力 (ilsvg.wasm) | 388770 B (sha256 先頭 16 桁 `0fa5c92d8eb8ba42`) |
| native 描画 (`nat`, `svgren::parameters` の `dims_request {64,64}`) | dims 64 64, nonzero_px 4096 |
| wasm 描画 (`createILSvg` → `svgCreate` → `svgRender(64,64)`) | dims 64 64, nonzero_px 4096 |
| 画素列の一致 | native / wasm の ARGB32 生データ 16384 B が `cmp` で IDENTICAL |

mac dylib (`Shared/ILSvg_x64.dylib`) は素材に無いため、受入条件 4 の「mac dylib との出力比較」は未実施。native との一致で代替。

注: 旧版の REPORT にあった `nonzero_px 3136` は、この smoke SVG (`wrap/smoke.svg`) を当時使ったという根拠が無く、今回の再現では 4096 になるため撤回する。`smoke.svg` を正本とする。

## 未解決 (起票先)

| 未解決 | 起票先 |
|---|---|
| mac dylib (`Shared/ILSvg_x64.dylib`) との出力比較。基準の定義と素材 (mac slice) の供給 | #1148 `[T-SH-26]` (親 #927) |
| papki 1.0.101 の `make_unique` 置換・cssom の `kilobyte` 置換が FL バイナリの版と一致するか (推定) | #1148 (同上) |
