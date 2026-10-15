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

## mac dylib との比較の試行 (#1148 / 親 #927)

結論 1 行: mac 版 `ILSvg_x64.dylib` は素材 (`analysis-mac-shared`) から取得できたが、x86_64 Mach-O のため Linux runner では実行できず、出力比較 (受入条件 1・2) は未実施。実行比較は #1348 `[T-SH-28]` へ分割。

抽出: `analysis-mac-shared.tar.zst` の `FL Studio 2026.app/Contents/Resources/FL/Shared/ILSvg_x64.dylib` (universal, 3297952 B)。x86_64 スライス (offset 16384, 1641088 B) を `tools/shared/work/mac_ilsvg/x86/` に切り出し (gitignore)。sha256 先頭 16 桁 `c2a14c1b94323cd0`。

静的確認 (`llvm-objdump --macho`):

| 項目 | 実測 |
|---|---|
| export (exports trie) | `_svgCreate` / `_svgRender` / `_svgDestroy` の 3 件。wrapper (`oss/ilsvg/wrap/ilsvg_wrap.cpp`) と同名 |
| 依存 dylib | `/usr/local/lib/ILSvg_x64.dylib` (自己参照) / `libc++.1.dylib` / `libSystem.B.dylib` の 3 件 |
| 埋め込みパス | `strings -n 8` で 114 件 (x86_64 スライス)。大半 108 件は小文字 `/Volumes/imageline/flextra/sdks/ILSvg/` 配下 (pixman 6 / cssom 3 / svgdom 1 / agg 1 / mikroxml 1 / utki 1 のソース参照・`xcode/` 配下のビルド中間物 `.o` 95 件を含む)。大文字 `SDKs` は 6 件 (svgdom 3 / papki 1 / svgren 1 / 末尾 `ILSvg/` のみ 1)。含まれるコンポーネントは svgdom / svgren / cssom / papki / mikroxml / utki / pixman / agg |
| enum 名 | `spread_method_to_string` 等の C++ シンボルが残る。版文字列 (`@PIXMAN_VERSION_*@` は未展開の雛形) からは版番号を特定できず |

実行不可の根拠: この runner は x86_64 Linux。mac バイナリを動かす qemu・Rosetta・box64・wine が無い (`which` で確認)。workflow にも mac runner が無い。よって (1) mac dylib と wasm / native の画素比較 (2) papki `make_unique` / cssom `kilobyte` 置換の挙動一致 は、この環境では成立しない。

未解決 (起票先): 実行比較の基準定義・実行環境の確定・比較本体 → #1348 `[T-SH-28]` (親 #1148)。

## 版の組の再検討 (#151): svgdom 0.3.61 + svgren 0.6.3 (probe)

結論 1 行: svgdom 0.3.61 と svgren 0.6.3 は symbol 解析の判定範囲内 (svgdom 0.3.59〜0.4.9 / svgren 0.5.9〜0.6.3) で、この組は連結 wasm・native で通り smoke 64x64 の画素が IDENTICAL。cssom は判定 (0.2.x) の範囲外の 0.1.19 を使っており、0.2.x と組んだ probe は未実施。採用の確定は PM 判断 (#151)。

根拠 (上流 tag の実測):
- svgdom は 2f138bb (2021-04-04) で cssdom → cssom に切り替え。0.3.59 は cssdom を使うため除外、0.3.60 以降が FL の cssom 使用と整合。
- svgdom 0.3.60〜0.3.70 の `spread_method` enum は `default_` (svgren 0.6.3 と一致)。0.4.7 は `default_method` (0.6.4 向け)。
- svgren 0.6.3 の debian 定義は libsvgdom-dev >= 0.3.61 (上流の宣言)。
- cssom の版: svgdom 0.3.61 の debian 定義は libcssom-dev >= 0.1.19 (上流の宣言)。probe の 0.1.19 はこの下限の版。一方 symbol 解析の判定は cssom 0.2.x (tags 0.2.0〜0.2.24、`tools/shared/data/ilsvg_version.json`・`tools/shared/REPORT_APPENDIX.md`)。cssom は判定と食い違うため、判定の範囲内の cssom で組んだ probe は未実施。

組 (`bash tools/shared/oss/ilsvg/probe_pair_0361.sh`、emcc 6.0.12、-O2):

| 部品 | 版 | probe 限定の処置 |
|---|---|---|
| svgdom | 0.3.61 (2021-04-09) | なし |
| svgren | 0.6.3 | `scope_exit.release()` → `reset()` (utki 1.1.124 の名前。動作同一) |
| cssom | 0.1.19 (cssdom repo tag, 2021-04-08。判定 0.2.x の範囲外) | なし |
| utki | 1.1.124 (2021-04-09) | native g++ 13 用に `-include cstdint -include limits` |
| r4 | 1.0.53 | なし |
| mikroxml | 0.1.36 | なし |
| papki | 6ec4c66 (= 1.0.93, 2021-04-08) | `fs_file.cpp` 除外 |
| agg | 2.8.9 | なし |

実測 (作成者 run: exit 0・real 1 m 12.0 s、開始時 load average 未記録)。検証 run (測定 commit 42d347004 の clean worktree、emsdk 6.0.12 を新規導入、libz 初回生成を含む): exit 0・real 111.3 s・開始時 load average 0.52 0.27 0.11。wasm 381998 B、native / wasm とも dims 64 64 nonzero_px 4096、ARGB32 16384 B が `cmp` で IDENTICAL。

- 測定 commit: `42d347004` (コードを変えた最後の commit)。`git diff 42d347004 HEAD -- tools/shared/oss/ilsvg ':(exclude)tools/shared/oss/ilsvg/REPORT.md'` の出力は空 (差分 0)。REPORT.md を除くのは、本節の追記が REPORT.md のみを変えるため。
- ネガティブコントロール: wasm 側の入力だけ円の色を `#00fe00` (1 LSB) にした SVG (`sed 's/#00ff00/#00fe00/' wrap/smoke.svg > neg_smoke.svg`) を `wasm_smoke.cjs` で描くと、native と `cmp` で DIFFER (812 バイト不一致、最初の差は byte 4210)。

未解決 (起票先):
- utki は svgren 0.6.3 が要求する `release()` のため 1.1.162 (2021-10-12) 以降が必要。1.1.162 では mikroxml 0.1.36 / cssom 0.1.19 の `utki::span::const_iterator` 欠落と、utki 自身の `unicode.cpp` (libc++ の `char_traits<unsigned char>`) で連結不可。この組は未探索 → #151 (PM 判断)。
- 採用版の確定 (svgren 0.6.3 + svgdom 0.3.61 案 と 0.6.4 + 0.4.7 案のどちらを正本にするか) → #151 (PM 判断)。
- mac dylib との比較 → #1148 / #1348 (変更なし)。
- cssom 0.2.x (判定の範囲内) と組んだ probe は未実施 → #151 (PM 判断)。
- vendored pixman (version 未特定) は ILSvg の構成 stack に含まれるが、本 probe の組には入っていない → #151 (PM 判断)。
