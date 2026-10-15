> **正本**: 本ファイル (REPORT §9 の全文を分割移動)。結論と索引は `tools/qfclift/REPORT.md` §9。

## 9. FT_* の GetProcAddress 解決と FreeType wasm32 ビルド (T-SH-79 / #3412)

既知類型との関係 (DEFECTS.md): 該当なし。測定 commit = `c9767a62f` (コード最終 commit。`test_qfc_gpa.c` に token 経由の残り 5 本の照合を追加)。`git diff c9767a62f HEAD -- tools/shared/oss/freetype` の出力は空 (本節は REPORT のみの変更)。

**結論 (部分達成)**: FT_* 14 本の解決経路を実装し、token 経由で 14 本すべての呼出を直接呼出と照合して native / wasm32 / wasm64 で同一結果であることを確認した。
guest の `imp_GetProcAddress` への結線と FontCache_GetStats / CleanUp の実行は未着手 (子 #3434。DllMain の 0x563000 は #3410・#3411 の後段で未到達)。

### 9.1 経路の選び方
- guest の間接 call 先は lift VA と IAT pseudo-VA (`IMP_VA_BASE` 系) だけである。FreeType は host の C 関数なので、関数ポインタを guest に渡さない。
- 採用: `GetProcAddress` が表で解決できる名前にだけ擬似トークン `QFC_GPA_TOK_BASE (0x7F200000) + 表の index` を返す (`qfc_gpa`)。
  トークンの呼出は `qfc_gpa_call` が表の fn ポインタを型付きに cast して実行する。Win64 の RCX/RDX/R8/R9 と stack の第 5 引数を受け、
  `long` は LLP64 の 32bit として下位を符号拡張する。戻り値は eax 書込みの規則で上位 0。
- 同型の先例: `tools/flelift/boot/fle_boot.c` の FLE-6 (`IPP_TOK_BASE` と `ipp_call`)。本節は ippv2 の経路を FT 14 本に広げた形。

### 9.2 FreeType wasm32 ビルド (#145 の採用方式)
- 手順: `bash tools/shared/oss/freetype/build.sh` (FreeType 2.7、`FORCE_INT64` + `ftgrays_lp64.patch`、wasm64 は無改変 + `-sMEMORY64=1`)。
- ソース: `freetype-2.7.tar.gz` (savannah, 2,381,403 B) を `tools/shared/work/src/` に展開。`fetch_sources.sh` 全体は使わなかった。
- emcc: 6.0.12 (`[EMSDK]` = runner 同梱)。`toolchain-emsdk.tar.zst` は本 run で展開していない (未使用)。wasm64 の node は `[EMSDK]` 配下の node (v24.19.0)。
- native の gcc は 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1)。所要: build.sh の configure+make 3 種 = **36.7 s** (real, n=1)。成果: libfreetype.a native 5,722,182 B / wasm32 714,774 B / wasm64 749,072 B。
- 再ビルド (レビュー指摘への再現。同じ手順・FONT は DejaVuSans): **44.1 s** (real, n=1)。native **5,712,982 B** / wasm32 714,774 B / wasm64 749,072 B。TOTAL `82b7580a3d8e846b`、wasm32 / wasm64 とも PASS。
- native の `.a` サイズは環境で変わる (同じ gcc 13.3.0 でも 5,722,182 / 5,717,078 / 5,712,982 B)。`.a` には絶対パスが埋まっており (native は `-g` の DWARF。`grep` で 270 件、wasm32 は 0 件)、ビルドディレクトリの長さの差が原因と見ている (同一パスでの再ビルドは未実施)。wasm32 / wasm64 は全環境で一致。
- build.sh の末尾のテスト実行は既定の FONT (`analysis-mac-shared` の OpenSans) が無く失敗する (rc=1、ライブラリは生成済み)。
  テスト用フォントは **DejaVuSans.ttf** (fonts-dejavu 同梱。e2e には `$FONT` として渡す) に差し替えた。

### 9.3 検証 (実測。n=1、e2e 実行時 load 0.23 → 0.30)
| 検査 | 結果 |
|---|---|
| 表経由 (`test_qfc_import.c`) | `table n=14 resolved=14/14 absent_null=4/4`。native == wasm32 == wasm64 (46 行, TOTAL `6e3c628e7e4a12df`) |
| トークン経由 14 本の呼出 (`test_qfc_gpa.c`) | `gpa table n=14 tokens=14/14 absent_zero=4/4`。'A' の描画 hash がトークン経由 `5a2005fb24544481` = 直接呼出 `5a2005fb24544481`。native == wasm32 == wasm64 (27 行, TOTAL `d77adc88f7ca92a4`) |
| 残り 5 本 (トークン経由 vs 直接呼出。戻り値・出力を照合) | 全て一致。FT_Get_Kerning (A,V)=-64 / (T,o)=-128 / (A,A)=0 (x は両経路で一致)。FT_Attach_File: 有効パス=7 (TrueType は attach 無しで Unimplemented_Feature) / 存在しないパス=1 / NULL=6。FT_New_Face: index 0 = 成功 (6253 glyphs) / index 0xFFFFFFFF = 成功 (faces=1) / 存在しないパス=1。FT_Set_Charmap: 5 種すべて rc 0、'A' gi=36。FT_Set_Pixel_Sizes 12 の後の 'g' (gi=74) 描画 hash `f93e5319ae852b5b` が一致 |
| e2e 全体 `qfc_import_e2e.sh` (DejaVuSans) | rc 0。所要 5.05 s (real, n=1) |
| ネガコン 1 (既存。引数の marshalling) | `FT_Get_Char_Index` の charcode を a[1]→a[2] にずらした複製: gi=0 (3 字とも)、`NG token route != direct call`、**exit 1** (検出)。照合で先に止まるため TOTAL 行は出ない |
| ネガコン 2 (新規。5 本) | `FT_Get_Kerning` の left / right を入れ替えた複製 (native): (T,o) が x=0 (直接 -128)、`NG token route (5 extra fns) != direct call`、**exit 1** (検出) |
| ネガコン 3 (新規。`long` 符号拡張) | `FT_New_Face` で 32bit の `long` 符号拡張を外した複製 (native): index 0xFFFFFFFF の結果が変わらず、**検出されない** (§9.4) |

### 9.4 検証範囲 / 範囲外
- 範囲内: 表と token の解決一致 (14/14、表外 4/4)、token 経由の 14 関数すべての呼出の marshalling (DejaVuSans 1 本、サイズ 16、3 字。5 本は戻り値・出力を直接呼出と照合)、wasm32/wasm64 の一致。
- 範囲外 (未検証):
  - 負の `face_index` による `long` 符号拡張 (FT_New_Face の index -1)。単一フェースの TrueType では FreeType が index を無視するため区別できず、複数フェースの TTC も環境に無い。本 PR の経路 (index 0) には影響しない。Win64 の `long` は 32bit で、wasm32 (long 32bit) では切り詰めの結果が同じ。
  - guest の `imp_GetProcAddress` 結線、QuickFontCache の DllMain・FontCache_GetStats・FontCache_CleanUp の実行 (→ #3434)。
  - OpenSans (FL の実フォント) での一致は未確認 (素材 `analysis-mac-shared` 未指定)。

### 9.5 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| guest の `imp_GetProcAddress` への qfc_gpa 結線と FontCache_GetStats / CleanUp の wasm 実行 | #3412 の受入の残り。QFC の boot ハーネスが無い | #3434 (T-SH-83) |
| DllMain の 0x563000 到達 (setjmp 継続・未実装 import) | 結線の実行確認が未到達 | #3410 / #3411 (既存) |
| FT_New_Face の負の `face_index` (long 符号拡張) の区別 | 本 PR の経路 (index 0) には影響しない。区別には TTC (複数フェース) が必要 | #3434 (T-SH-83) の検証範囲に含める |
