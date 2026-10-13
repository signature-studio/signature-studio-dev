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

## 結論

- utki 1.1.200 + svgdom 0.4.7 の組で svgdom 26 cpp は emcc で全て通る (実測)。
- svgren は svgdom 0.4.7 と enum 名が合わない (0.5.9 / 0.6.3 とも)。版の組は未確定。
- 連結ビルド・3 関数 wrapper は未達。残りは子 issue へ。

## 未解決 (起票先)

| 未解決 | 起票先 |
|---|---|
| svgdom と svgren の enum 名が合う版の組の確定、連結 wasm ビルド、3 関数 wrapper、mac dylib との照合基準 | #927 `[T-SH-21]` (親 #877) |
| papki 1.0.101 の `make_unique` 置換が FL バイナリの papki と一致するか (推定) | #927 (同上) |
