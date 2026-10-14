# tools/shared REPORT 付録 — 分割移動節 (内容は削除せず移動)

> **正本**: 本ファイル (移動節の全文)。結論と索引は `tools/shared/REPORT.md`。

## A. win freetype.dll の版判定 (#145) — REPORT §3.1 から分割移動

- **fl-win64 の export 突合**: `extracted/block24358_PE.bin` (i386, export 270) と `block24359_PE.bin` (x64, export 271) の 2 つが `freetype.dll`。両方とも前回の欠け 17 本を含み、差は `FT_MulFix` 1 本のみ。export 宣言の突き合わせ (`name(` の grep) は 2.4.10 / 2.4.11 / 2.4.12 で 271/271、2.4.9 は `FT_Outline_EmboldenXY` 欠け (270/271)、2.5.0 は 14 本欠け。x64 DLL の PE timestamp は 2012-09-20 (2.4.10 = 2012-06-15 と 2.4.11 = 2012-12-20 の間)。ここまでは版の帯の根拠で、patch 版は特定できなかった。
- **版定数の機械語**: x64 `block24359_PE.bin` の `FT_New_Library` (VA 0x180018150) は library 構造体へ `movl $0x2,0x8(%rbx)` / `$0x4,0xc` / `$0xa,0x10` を書く (`llvm-objdump -d`)。i386 `block24358_PE.bin` は minor=4 / patch=10 の即値まで確認 (major は未確認)。
- **上流 3 タグ照合 (確定根拠, 2026-10-14 取得)**: `git clone --branch VER-2-4-{10,11,12}` (gitlab.freedesktop.org) の `src/base/ftobjs.c` で、3 版とも `FT_New_Library` が `library->version_major/minor/patch = FREETYPE_MAJOR/MINOR/PATCH` を代入する。`FT_LibraryRec_` は `memory` (x64 で 8B) の直後に `version_major/minor/patch` が続き、オフセットは 0x8/0xc/0x10。`freetype.h` の版マクロは 2.4.10 = 2/4/10, 2.4.11 = 2/4/11, 2.4.12 = 2/4/12。
- **バイト列照合**: x64 `block24359_PE.bin` の `c7 43 disp imm32` を検索すると、`[+0x8]=2`・`[+0xc]=4`・`[+0x10]=10` の並びが 0x175de / 0x175e5 / 0x175ec に連続して 1 箇所だけ出現。`[+0x10]=11` と `=12` は 0 件。**結論: win freetype.dll (x64) = FreeType 2.4.10 (確定)**。export 集合は 3 版とも 271/271 で同一。
- **撤回した旧記述 (経緯)**: 「厳密な patch 版は未特定」「2.4.10〜2.4.12 のいずれか」「上流ソース照合は未実施 (gitlab が取得不可)」は、上記の照合で確定したため撤回。

## B. FT_* 呼出面の調査 (#1144, 2026-10-13)

- **素材**: `fl-win64` (`flstudio_win64_26.1.7.5653.exe`) の `extracted/` から PE 313 本 (`*_PE.bin`) を `tar --zstd -xf fl-win64.tar.zst --wildcards 'extracted/*_PE.bin'` で展開して調査 (`work/ft/extracted/`・gitignore)。`--wildcards` は必須で、無いと GNU tar が `Not found in archive` で空展開する。再現は `bash oss/freetype/callers_scan.sh <extracted_dir>`。
- **再現確認 (HEAD 上)**: 上記の `--wildcards` 付き展開で 313 本を取得し、`callers_scan.sh work/ft/extracted` が rc=0 で完了 (FT_names=0 GPA=2、FT_ 名を持つ PE 23 本、`DLL Name: freetype` を import する PE 3 本)。
- **FL 本体 `block00031_PE.bin`**: `FT_*` の名前が 0 件、`freetype` の文字列も無い。GetProcAddress/LoadLibraryA は import 済み (ただし解決する名前は文字列に現れない)。
- **`freetype.dll` を import する PE は 0 件**。`freetype.dll` の名前を持つのは installer file table (`block25162_PE.bin`: `Shared\freetype.dll/486712`・`Shared\freetype_x64.dll/607032`) と DLL 自身 (`block24358`/`block24359`) のみ。`Shared\` 配下の FL 製 DLL (ILSvg / Blend2D / ildsp / dsp_ippv2 / QuickFontCache 等) も `freetype` を import していない。
- **`FT_*` を import する PE**: `block24836`・`block24851`・`block24856` (`libfreetype-6.dll` を import = GTK/pango 系の同梱ライブラリ用。FL 本体ではない)。`block24837` (`libfreetype-6.dll` 本体・227 名)・`block24890` (pango 系の文字列) も FL 本体ではない。`block24435` は libass (字幕) の文字列。
- **結論 (前 run, 静的 import)**: `freetype.dll` (2.4.10) の FT_* を呼ぶ FL 側の呼出元は、静的 import の経路では特定できなかった。
- **呼出元の特定 (本 run, 2026-10-14, #1356)**: 前 run の走査は ASCII 限定だったため漏れがあった。UTF-16LE で走査すると、FL 製 `QuickFontCache.dll` (i386 `block24349_PE.bin` / x64 `block24350_PE.bin`) が `freetype.dll` と FT_* 名 14 本を UTF-16LE で持つ。
  - **動的解決の実体**: x64 `block24350` は `LoadLibraryW` (IAT `0x1dc494`) で `freetype.dll` を開き、`GetProcAddress` (IAT `0x1dc340`) で名前解決する。`objdump -d -M intel --start-address=0x563020 block24350_PE.bin` の出力で、`0x563020` が `lea rcx,[rip+0x529]` (= VA `0x563550`、UTF-16 `freetype.dll`) を読み、`call 0x522d20` に続く (本 run で確認)。その後 `0x5630c3` 以降に `lea rcx,[name]` + `call 0x411540` + `call 0x41d760` の組が 14 回並ぶ (`lea` 先 VA `0x563578` = `FT_Init_FreeType` の UTF-16 名を確認)。14 組の名前がすべて対応することは未確認 (一覧は `strings` 抽出による)。解決を担う thunk `0x411540` の同定は未実施。i386 `block24349` は UTF-16 の名前一覧 (`strings` 抽出) が x64 と同一であることを確認 (VA の対応は未確認)。
  - **解決される名前 (14 本, 両版で一致)**: `FT_Attach_File` / `FT_Done_Face` / `FT_Done_FreeType` / `FT_Get_Char_Index` / `FT_Get_Kerning` / `FT_Init_FreeType` / `FT_Load_Glyph` / `FT_New_Face` / `FT_New_Memory_Face` / `FT_Render_Glyph` / `FT_Select_Charmap` / `FT_Set_Char_Size` / `FT_Set_Charmap` / `FT_Set_Pixel_Sizes`。
  - **2.7 との対応**: 上記 14 本は `freetype_export_diff.json` の win 欠落 17 本に含まれない (= 2.7 の export に存在)。
  - **17 本の到達性 (受入条件 2)**: 欠落 17 本 (`FT_Alloc`/`FT_Free`/`FT_Realloc`/`FT_Sqrt32`/`FTC_*` 等) は QuickFontCache の名前表に **0 件**。全 PE の ASCII / UTF-16LE の名前文字列を走査しても、この 17 本は `block24837` (libfreetype 本体の内部) と `block24890` (pango 系) にのみ現れる (`block24358`/`block24359` は freetype DLL 自身)。**結論 (名前ベース): FL 側の PE に、欠落 17 本を名前で解決する経路は実測で見つからなかった → shim/stub は呼出元から到達しないと判断できる。** ただし、序数・ハッシュによる解決は本走査では除外できていない。これは子 issue で確認する。
  - **GetProcAddress 呼出経路の全数 (#1356, 2026-10-14, x64 `block24350`)**: `GetProcAddress` の IAT 実体は VA `0x5db9c8` (import 61 番目)。直接の呼出し thunk は 3 つ (`0x406e70`・`0x419480`・`0x41d750`)。`0x41d750` は `0x41d760` (汎用 wrapper) の末尾で、`0x41d760` の呼出しは 1041 箇所。wrapper の `rdx < 0x10000` 分岐 (序数経路) へ入る呼出しの引数は、`0x411540` の戻り値 (名前ポインタ) 860 件・`lea rdx,[rip+...]` (文字列アドレス) 181 件で、即値の序数・計算されたハッシュは 0 件。FT 解決 14 組はすべて QuickFontCache の関数 `0x563000` 周辺 (`freetype` ハンドル `0x5d9f28` の参照元もこの関数群のみ)。
  - **直接 thunk の全数 (#1648, 2026-10-14, x64 `block24350`)**: `0x406e70` は `jmp [0x5db9c8]` (GetProcAddress IAT) の素通し thunk で、呼出し 6 箇所。うち 5 箇所 (`0x4095b3`・`0x40d7e9`・`0x4155fe`・`0x415620`・`0x415642`・`0x415f2c`) は第 2 引数が `lea rdx,[rip+...]` の文字列アドレスで、文字列は `GetLogicalProcessorInformation`・`GetThreadPreferredUILanguages`・`SetThreadPreferredUILanguages`・`GetThreadUILanguage`・`GetLongPathNameW` 等 (kernel32 の API 名)。FT 名は 0 件。残り 1 箇所 `0x419fe9` は `0x419480` (同じく `jmp [0x5db9c8]`) 経由で、第 2 引数は `[rbp-0x28]` (変数)。この変数を受ける関数 `0x419e71` は汎用のインポート解決器で、直接 call・RIP 相対参照・絶対ポインタのいずれからも参照されず (PE 内に `0x419e71` の rva32/abs64 が無い)、上流の名前データは未追跡。
  - **i386 `block24349` (#1648)**: `GetProcAddress` IAT VA `0x51e534` (kernel32, 実測。thunk `0x4052a0` = `jmp [0x51e534]`)。`GetModuleHandleW` IAT VA `0x51e48c` (kernel32) の thunk は `0x405298` (= `jmp [0x51e48c]`)。直接 thunk は `0x4052a0`(呼出し 6 箇所)・`0x40ffac`(1)・`0x412abc`(3)。
    - **`0x4052a0` の 6 呼出し (逆アセンブル `objdump -d -M intel`、再実測)**: 5 箇所 (`0x407017`・`0x4084e3`・`0x40d4f4`・`0x40d50e`・`0x40d528`) は `push <API 名>` (= `lpProcName`) → `push <kernel32.dll>` → `call 0x405298` (= `GetModuleHandleW`) → `push eax` (hModule) → `call 0x4052a0` (= `GetProcAddress`) の順。`0x40dbc6` は `call 0x405298` の戻り値を `ebx` に保存し (`test`/`je` を挟む)、`push <API 名>` (`0x40dd84`) → `push ebx` (hModule) → `call 0x4052a0` の順で、`push eax` は無い。
      | 呼出し | `lpProcName` (push 行 / VA) | hModule の文字列 (push 行) | API 名 |
      |---|---|---|---|
      | `0x407017` | `0x4070dc` (`0x407007`) | `0x4070fc` (`0x40700c`) | `GetLogicalProcessorInformation` |
      | `0x4084e3` | `0x408594` (`0x4084d3`) | `0x4085b4` (`0x4084d8`) | `GetLogicalProcessorInformation` |
      | `0x40d4f4` | `0x40d534` (`0x40d4e4`) | `0x40d554` (`0x40d4e9`) | `GetThreadPreferredUILanguages` |
      | `0x40d50e` | `0x40d570` (`0x40d4fe`) | `0x40d554` (`0x40d503`) | `SetThreadPreferredUILanguages` |
      | `0x40d528` | `0x40d590` (`0x40d518`) | `0x40d554` (`0x40d51d`) | `GetThreadUILanguage` |
      | `0x40dbc6` | `0x40dd84` (`0x40dbc0`) | `0x40dd68` (`0x40dbb0`、`call 0x405298` の戻り値 `ebx`) | `GetLongPathNameW` |
    - `lpProcName` の文字列は 6 箇所すべて UTF-16 復号で確認 (文字列を取れない呼出しは 0 件)。`0x40dbc6` のみ `GetModuleHandleW` を先に呼んでから `lpProcName` を push する順で、hModule は `ebx` (戻り値)。
  - `0x412abc` は汎用ラッパーで、呼出元は `0x42dfb1` (引数 `[eax-0x4]` の変数)・`0x412ae8` (`ebx` の序数判定)・`0x412b0a` (`0x40a40c` の戻り値)。`0x40ffac` は `0x4108b8` (`[ebp-0x44]` の変数)。変数の上流 (名前・序数の実値) は**未確定**、未追跡。FT 名は UTF-16LE で 14 本 (x64 と同一)、ASCII の FT_ 名は 0 件。
  - **変数引数の上流 (#1648, 2026-10-14 追補, x64 `block24350`)**: 前項の `0x419e71` は関数先頭ではない。関数先頭は `0x419e70` (`push rbp`)。`0x419e70` の参照は直接 call 1 件 (`0x41a936`) と、`.data` の abs64 1 件 (`0x5add60`)。`0x5add60` は `0x419490` の間接 call 先 (`call [0x5add60]`)。`0x419490` の呼出元は xref 上 `0x41d508` を含む数件 (出力の途中で切れており全数は未確認)。`0x419e70` の中身は、引数 `rcx` を基点に PE ヘッダ (`[r15+0x3c]`・`PE\0\0`) を読み、thunk の最上位ビットで序数 (`movzx eax,ax`) と名前を分岐する import 解決器。見た範囲では計算ハッシュの処理は無い。`[rbp-0x28]` は thunk の下位 16 bit (序数) か名前由来値。よって変数引数の値は、このローダが読むイメージ側の import テーブル (ILT) に依存する。どの 17 本がこの経路か、テーブルの中身は未実測。
  - **i386 `block24349` 変数引数 (#1648 追補)**: `0x40a40c` は値を返すヘルパ (`eax` または `[0x510a10]+0xc` を返す) で、名前源ではないことを確認。`0x42df98` は `0x412abc` を呼ぶ関数 (呼出元は未追跡。xref の参照数 26 は call に限らない総数)。`0x40ffac` は `.text` 内 `0x413308` に rva32 で現れる (テーブルか定数かは未確認)。
  - **変数引数の上流 (#1648, 2026-10-14 第 3 追補, x64 `block24350`・測定 commit 4b2762ce)**: `0x419fe9` の `[rbp-0x28]` を受ける関数先頭は `0x419e70`。呼出元は `0x41a936` (直接 call 1 件) のみで、`0x41a936` を含む `0x41a800` 系の関数は自モジュールの **Delay Import 記述子 (data directory 13)** を読む。RVA `0x419e70` を持つ表 (file off `0x1ac360`) は関数テーブル候補で、由来は未確定 (呼出し経路ではない)。よって `[rbp-0x28]` の値は delay-import の ILT 名 (静的データ) で、Delay Import の名前は 6 DLL の 7 本 (`GetLogicalProcessorInformation`・`MessageBoxA`・`AlphaBlend`・`NormalizeString`・`GetNativeSystemInfo`・`DwmFlush` 等) で、**FT 名 0 件・序数 0 件**。`0x41a960` は別の解決器で、呼出元 `0x41aca4` は未確認。
  - **i386 `block24349` 変数引数 (#1648 第 3 追補)**: `0x42df98` の呼出し 22 件は、各呼出し直前の定数 (`0x42e1d8`〜`0x42e2cc`) を `eax` に渡し、その ASCII 名を読む。名前は **oleaut32 の `VariantChangeTypeEx`・`VarNeg`・`VarNot`・…・`VarCmp`・`VarI4FromStr`・…・`VarBoolFromStr`・`VarBstrFromBool` (22 本)** で、FT 名 0 件。`0x412abc` の呼出元 `0x412ae8`・`0x412b0a`・`0x42dfb1` は、序数判定 (`shr eax,0x10`) 後に `0x412abc` (= `GetProcAddress` IAT `0x51e534`) を呼ぶ。`0x412b0a` の引数は `0x40a40c` の戻り値、`0x42dfb1` の引数は `[eax-0x4]` (`0x42df98` の名前源 = 上記 oleaut32 名)。`0x40ffac` (呼出元 `0x4108b8`) の `[ebp-0x44]` は**未追跡**。
  - **名前表の機械照合**: `python3 tools/shared/oss/freetype/pe_import_names.py <block*_PE.bin>` で import / delay-import の全名を列挙 (新規)。**block24350: 名前 223 本・序数 0 件・FT 名 0 件。block24349: 名前 222 本・序数 0 件・FT 名 0 件** (測定 commit 4b2762ce, 実行 08:10 UTC)。`git diff 4b2762ce HEAD -- tools/shared/oss/freetype/pe_import_names.py` は空 (script 差分 0)。
  - **残る限界 (#1648 で未確定)**: i386 `0x40ffac` (`[ebp-0x44]`) と `0x412b0a` の `0x40a40c` 戻り値の上流は未追跡。x64/i386 とも、17 本 (`FT_Alloc` 等) が名前・序数で解決される経路は、この範囲の静的走査では見つからなかった。動的トレース (QuickFontCache を実行して GetProcAddress の引数を記録) で確定する必要がある。
  - **shim 結線と wasm 一致 (受入条件 3)**: `oss/freetype/build.sh` を、システム標準の DejaVuSans.ttf を `FONT` 環境変数で指定して実行 (rc 0, 76.7 s)。`[ft] PASS wasm32: native == wasm (40 lines, TOTAL 82b7580a3d8e846b)`、`[ft] PASS wasm64` も同じ TOTAL。**OpenSans-Regular.ttf は当時の環境・素材のどちらにも無かったため DejaVuSans での代替測定** (OpenSans の実測は下の #1649 が正)。
  - **OpenSans 再測定 (#1649, 2026-10-14, 測定 commit 72260b63 = origin/main)**: `FONT="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf" bash oss/freetype/build.sh` (`FL_MAC_DIR` = `[MAC]`、`docs/REFERENCES.md`) を worktree `ws-1649` で foreground 実行。**rc 0 / 79 s** (load average 開始 0.59 → 終了 2.80, nproc=4)。`[ft] PASS wasm32: native == wasm (40 lines, TOTAL 1c0c857a3891256f)`、`[ft] PASS wasm64: native == wasm (40 lines, TOTAL 1c0c857a3891256f)`。DejaVuSans の代替値 (TOTAL 82b7580a3d8e846b) とは別値で、OpenSans 値は本測定が正。libfreetype.a: native 5,718,718 B / wasm32 714,774 B。
  - **14 本の定義確認 (受入条件 3 の一部)**: 上記 14 本の `FT_*` は native・wasm32・wasm64 の 3 つの `libfreetype.a` すべてに `T` シンボルとして存在することを `nm` / `llvm-nm` で確認。**shim の import 表 (QuickFontCache 側の 14 本を wasm 側へ結線するコード) は未実装**。本 run は定義の存在確認までで、結線は未解決。
  - **QuickFontCache 14 本の import 表 結線 (#1748 / T-SH-33, 2026-10-14)**: `oss/freetype/qfc_import.c` に名前→関数ポインタの表を実装 (14 本、表外の 4 名 `FT_Alloc`/`FT_Free`/`FT_Realloc`/`FT_Sqrt32` は NULL)。検証 `bash oss/freetype/qfc_import_e2e.sh` は、表経由で `FT_Init_FreeType`〜`FT_Set_Pixel_Sizes` を呼び、描画・カーニングの hash を native / wasm32 / wasm64 で比べる。測定 commit 2150a44d (HEAD)、**rc 0 / 2.54 s / load 1.21→1.26 (nproc=4)**。`[qfc-import] PASS wasm32: native == wasm (46 lines, TOTAL f5d9d812e8a3a54c)`、`PASS wasm64` も同じ TOTAL。`table n=14 resolved=14/14 absent_null=4/4`。前提の `build.sh` は OpenSans の実測 (TOTAL 1c0c857a3891256f) を同日に再現。
  - **i386 `0x4108b8` 変数引数の上流 (#1648 第 4 追補, i386 `block24349`・測定 HEAD 7060ff07)**: 呼出元 `0x4108b8` の `[ebp-0x44]` は関数 `0x410678` 内で代入される。代入元は `[edi]` (`edi = [ebp-0x24] + index*4`) で、`[ebp-0x24]` は `0x410b3c(esi+0x10)` の戻り値、`esi` は `0x410678` の引数ポインタ。`0x410b0c`・`0x410b1c`・`0x410b2c`・`0x410b3c` の 4 ヘルパの実体と `esi` の呼出元は未追跡。値は下位 16 bit (序数) か上位ビット 0 の名前ポインタ (`0x410b4c` 経由) のどちらか。`0x40ffac` 自体は GetProcAddress IAT `0x51e534` の `jmp` thunk と確定。(#2190 で訂正: 当初は「Wine が無く動的実行できない」と書いたが誤り。wine64 9.0 は apt で導入でき、動的実行は可能。下記 2190 の項を参照。この bullet の静的走査の結論はそのまま有効。)
  - **動的トレース (#2190 / T-SH-34, 2026-10-14, x64 `block24350`)**: 従来「Wine が無い」としていた前提は誤りで、apt の `wine64` 9.0 (+ `xvfb`・mingw) で実行できた。再現手順は `oss/freetype/qfc_gpa_trace/run.sh` (素材の複製に entry point を `mov eax,1; ret` で置換、依存 DLL `dsp_ippv2_x64`・`freetype_x64` は空の stub)。**実測: LoadLibrary は成功 (`0x7bde0000`)、`InitDll` は解決 0、`CreateVST3Instance` は `0x7bf6a200` で解決。** QuickFontCache の内部 (VA `0x7bde0000`〜) からの GetProcAddress 呼出しは **0 件**で、FT 解決 (`0x563000`) には到達していない。
  - **検出式 (修正, 2190 レビュー対応)**: 旧式 `ret=7bd[e-f]…|ret=7b[e-f]…` (9 桁) は 8 桁の戻り番地 (`7bde0000` 系) を拾えず、0 件が偶然正しいだけだった。新式は `tools/shared/oss/freetype/qfc_gpa_trace/filter_gpa.py` で、LoadLibrary の基底 (実測 `0x7bde0000`) と PE の SizeOfImage から範囲 `[0x7bde0000, 0x7bfee000)` を整数比較で判定する。件数の定義は **Call 行のみ** (`Call KERNEL32.GetProcAddress(...) ret=...`)。Ret 行は含めない。
  - **陽性対照 (同じ判定器)**: probe.exe (ImageBase `0x140000000`、範囲 `[0x140000000, 0x14003f000)`) の Call 行は **26 件** (旧 grep `ret=14[0-9a-f]{7}` の Call 行も 26 件で一致)。うち `InitDll`/`CreateVST3Instance` の 2 件 (`ret=140001550`・`ret=140001579`) を名前で抜けることを確認。QuickFontCache 側の 0 件は、陽性対照が通ったうえでの 0 件である。
  - **最終測定 (測定 commit 3a35cb58 = HEAD, clean 作業ツリー)**: `bash oss/freetype/qfc_gpa_trace/run.sh` を foreground 実行。**rc 0 / 41.3 s / load 0.42→0.51 (nproc=4)**。Call 行 254 件 (全体)、QuickFontCache 範囲 `[0x7bde0000, 0x7bfee000)` = **0 件**、probe 陽性対照 = **26 件** (うち `InitDll`/`CreateVST3Instance` 2 件)。`git diff 3a35cb58 HEAD -- tools/shared/oss` は 0 件 (3a35cb58 以降の差分は REPORT_APPENDIX のみ = 測定コードに差分なし)。
  - **実行条件**: `run.sh` は毎回 wine prefix を作り直す (旧版は prefix 残存で relay 行数が変わった: 10.6M 行 → 0.37M 行)。再現は `apt-get install wine64 gcc-mingw-w64-x86-64 xvfb` の後に `bash oss/freetype/qfc_gpa_trace/run.sh`。`0x563000` は abs64 参照が無く、`0x563820`/`0x563840` (refcount init/fini) の 2 つの abs64 参照元 (`.text` 内 `0x19cac0`/`0x19cac8`) の経路を未特定。よって 17 本の到達性は**依然未確定**。次の一手: `0x19cac0` 付近の参照テーブルの持ち主を同定し、その経路を実行する export を探す。
  - **残り**: (b) `0x406e70`・`0x419480` の呼出元と引数の全数確認 (17 本の序数・ハッシュ除外)。(b) は #T-SH-29 (親 #1144 の子) で扱う。
- **走査スクリプト**: `oss/freetype/callers_scan.sh` を UTF-16LE 走査込みに改訂 (本 run)。`bash oss/freetype/callers_scan.sh <extracted_dir>` が rc 0 で完了することを実測。

## 10. 各ライブラリのビルド詳細

### 10.1 libFLAC 1.5.0 / 1.3.1 (`bash oss/flac/build.sh` + `bash oss/flac/negctl.sh <ver>`)
- upstream: `downloads.xiph.org/releases/flac/flac-{1.3.1,1.5.0}.tar.xz`。autotools cross 判定を避け 23 ソースを直接 `emcc`/`gcc` へ。config.h は native configure 生成物を `-DHAVE_CONFIG_H` で共有、wasm は更に `HAVE_CPUID_H`/`HAVE_SYS_AUXV_H`/`FLAC__HAS_X86INTRIN` を落とした版を使う (素のままでは emcc sysroot に無いヘッダを include して失敗)。
- `FLAC__stream_encoder_init_FILE`/`init_FILE` (FILE* 直結) を使うと seek/tell は libFLAC 内部 `file_*_callback_` で解決され native/wasm 一致。自前 callback だと `CLIENT_ERROR` (24bit の sample 桁あふれ、callback 間の状態不整合) が出た。
- 実測: 1.5.0 = FLAC 60,171B hash **e22fc4abefae830e** / 1.3.1 = 60,171B hash **645fb4f042eb9ede** (3 arch byte-identical)。復号 hash は両版とも **d3d89c007626c2b1** = 入力 PCM hash (可逆)、`PCM identical 22050/22050`。wasm: 1.5.0 = 169,807/173,204B、1.3.1 = 156,216/158,503B。
- ネガコン: 音声フレーム 1B 反転 → 復号 hash `faef95f116a11dc7` (1.5.0) / `4479db75ffe71dc7` (1.3.1) が baseline `d3d89c007626c2b1` と不一致 & rc=1。magic `fLaC` 破壊 → rc=1。

### 10.2 LAME 3.99.5 (`bash oss/lame/build.sh` + `bash oss/lame/negctl.sh`)
upstream: sourceforge ミラー (savannah の `/releases/lame/` は 404)。native は `vector/xmm_quantize_sub.c` 込み、wasm は `HAVE_XMMINTRIN_H`/`MIN_ARCH_SSE` を落として `init_xrpow_core_c` のみ。実測: MP3 16,181B hash **18dd8a4a4c91ee23** (3 arch byte-identical)。wasm 189,172/192,446B。ネガコン: 別 seed PCM → `1132a9cde5cb3e85` ≠ baseline、同一 PCM の再エンコードは同 hash (determinism)。

### 10.3 WavPack 4.80.0 / 4.60.1 (`bash oss/wavpack/build.sh` + `bash oss/wavpack/negctl.sh`)
upstream: github tag archive (release asset 無し)。24/11 ソースを直接 `emcc`/`gcc`。`WavpackOpenFileOutput` はメモリコールバックなので FILE* 非依存、読み側のみ NODERAWFS。実測: .wv 115,378B sha256[:16] **25d66af8deedf311** (native==wasm32==wasm64、両 version 同ハッシュ)、復号 PCM hash **7819af6dd0d37cf0** = 入力 (可逆)、`WM identical 48000/48000`。wasm 142,907/145,216B (4.80.0)・149,387/151,027B (4.60.1)。ネガコン: 入力 1 sample+1 → `f6185d5d11783983`、.wv 1B 破損 → `WM identical 24000/48000`。

### 10.4 FFmpeg n4.4.2 (`bash oss/ffmpeg/build.sh` + `bash oss/ffmpeg/negctl.sh`)
upstream: `ffmpeg-4.4.2.tar.bz2` (win 実測 version)。configure: `--disable-everything` + decoder {flac,mp3,vorbis,pcm_s16le,wmav2,aac}・demuxer {wav,flac,ogg,mp3,matroska,aiff}・parser {flac,mpegaudio,vorbis,aac}・protocol file、`--disable-x86asm --disable-inline-asm --disable-bzlib --disable-zlib --disable-lzma --disable-iconv` (nasm 非搭載 & sysroot 不在)。**License: LGPL version 2.1 or later** (`config.h` の `CONFIG_VERSION3 0`)。wasm64 は `-sMEMORY64=1` が configure の try-compile を壊すため `ffbuild/config.mak` の CFLAGS に直接注入してから make。
実測 (native == wasm32 == wasm64): gen.wav|pcm_s16le 22050 samples hash **9249b2e1bb6ce0b2** / ok.flac|flac 22050 hash **693fe9f21e378245** / enc_native.ogg|vorbis 176640 hash **b51917f65bbce87d** / out.mp3|mp3 39168 hash **1d45943fec1748ca**。wasm 846,430/873,768B、avcodec.a 7.86MB (native) / 5.32MB (wasm32)。注記: planar float (fltp/s16p) の hash は `data[0]` ではなく `extended_data` 全 plane から取る必要がある (初版は `data[0]` のみで native でも実行ごとに hash が変わった = 未初期化読)。ネガコン: FLAC 1B 反転 → `abd5786130dfee29` ≠ baseline `693fe9f21e378245`、WAV の PCM 1 sample+1 → `30e5eb7d33facb1f` ≠ baseline `9249b2e1bb6ce0b2`。

### 10.5 FFmpeg のリンク方針 (CAB-148 の決定事項)
lift 済み FL コードと同一 wasm に FFmpeg を **静的リンクしない** (LGPL version3 論点最小化)。win バイナリは `--enable-version3` 付きで混ぜると version3 論点が複雑化する。FL が読むのは wav/flac/mp3/ogg なので最小デコーダで足りる。構成: FFmpeg は **独立 wasm モジュール / Worker** (本 build.sh の通り)。FL 側 `libILVideo` glue (26 export) は非互換の代替を持ち ABI 非互換のまま疎結合。本 build は `CONFIG_VERSION3=0` (LGPL-2.1+) なので静的リンクしても version3 の条項は持ち込まない。

### 10.6 ILSvg (CAB-150) — version 特定 (実測: `data/ilsvg_version.json`, 再計算: `scripts/ilsvg_version_recount.py`)
ILSvg は **version 文字列が無い** (旧 "AGG 2.4 系は推定" を訂正)。`ILSvg_x64.x86_64.dylib` の (a) Xcode object ファイル名 95 個 (`/Volumes/imageline/flextra/sdks/ILSvg/…`) と (b) def symbol 2,780 個 (`llvm-nm --defined-only` + `llvm-cxxfilt`) を upstream repo の tag と突合:

| 構成要素 | version 決定 | 決定的根拠 |
|---|---|---|
| **svgdom** | **0.3.59〜0.4.9** | `style_stack_cache`・`finder_by_{class,id,tag}` symbol = commit ddb828e (2021-04-03) 以降。`.cpp` 集合 26 本が 0.3.59〜0.4.9 の全 tag と一致 |
| **svgren** | **0.5.9〜0.6.3** [検収で下限を修正] | `canvas.cpp` あり = 0.4.75〜0.6.19、`gradient_setter` symbol = **0.5.9 以上** (初出 0.5.9/2021-04-03; old「0.6.0 以上」は下限の取り違え)、`path_type`/`spread_templ` なし = 0.6.4 未満 |
| **agg** | **未確定 (2.7.4〜2.8.42 のいずれか)** | `agg_*.o` 25 本のファイル集合は 2.7.4〜2.8.42 の全 tag に含まれる。svgren 0.6.3 の AGG API を写した probe も 2.7.0〜2.8.42 でコンパイル成功 (API 形状では絞れない)。svgren は agg を pin しない (`agg/[>=0.0.0]` / `io.github.cppfw:agg:+`)。**old「AGG 2.4 推定」「cppfw/agg 2.8.x」ともに決定的根拠無し (検収で弱めた)** |
| **pixman** | vendored (version 未特定) | `pixman-*.o/.c` 25 本・230 symbol が静的リンク |
| **cssom** | **0.2.x** | `cssom::parser/selector/sheet/style/…` 6 class 一致 |
| **papki** | **1.0.101 以前 = 2021-06-09 未満** (tag なし) [検収で修正] | シンボルは `papki::dir(std::string const&)`。papki が引数を `std::string` → `std::string_view` に変えたのは commit 7255fb8 (release 1.0.102, 2021-06-09) なのでそれ以前。**old「72b5b58 (2024-02-25) 以降」は誤り** (72b5b58 が追加したのは `as_dir()`)。→ papki は svgdom/svgren と矛盾しない |
| **IL 独自グルー** | 15 本 (非 OSS) | PascalCase `.o` (Element, Filter, Gradients, Length, Parser, Referencing, Renderer, Shapes, Source, Structurals, Styleable, Surface, Transformable, Visitor, File) |

実ビルド: cppfw/agg 2.8.9 の svgren 使用サブセット 25 cpp は emcc でコンパイル成功 (native .so 173,224B) — ただし agg version 特定の根拠にはならない (上記)。**連結ビルドはブロック**: svgdom/svgren は `papki/file.hpp`・`r4/vector.hpp` 等が header パス未解決 (upstream 単体では不可) → 子チケット。推定: papki の日付 (2024-02-25 以降) が他要素 (2021-2023) と矛盾 → FL 26 向けに後年リビルドの可能性。


## 12. 検収記録 (2026-10-11, 検収 subagent / tools/shared / CAB-146,147,148,150,18)

### 12.0 run_all.sh e2e (\`bash tools/shared/run_all.sh\`) も clean HEAD から再現
**rc=0 / 実測 178 s** (load average 開始 1.29 → 終了 4.56, nproc=16, 直列実行)。分類 22 項目・FreeType 40 行一致 + export 被覆 190/190 (win 254/271・欠 17 は FT_Alloc 系)・ogg 30,695B hash cac14495a26b1641 3 arch identical・Blend2D \`PASS: native(no-JIT) == wasm(no-JIT) pixel-exact\` (差 0/230,400B)・libkio difftable 228/760 → 621/760。※ REPORT §0・§11.3 の「~6 分」「~90 s / ~40 s / ~60 s / ~10 分」は単発の負荷依存値で、本検収の実測 178 s (一括)・FLAC 29 s・LAME 36 s・WavPack 36 s・FFmpeg 119 s とは異なる (負荷とキャッシュ状態依存)。
**\`status.sh\` は tools/shared に存在しない** (run_all.sh のみ)。

### 12.1 e2e 再現結果 (native == wasm32 == wasm64 の byte-identical を実測で確認)

| lib | 検証ハーネス | 実測 (clean HEAD から再現) | 判定 |
|---|---|---|---|
| libFLAC 1.5.0 | `oss/flac/build.sh` | FLAC **60,171B** hash **e22fc4abefae830e** / 復号 hash **d3d89c007626c2b1** = 入力 PCM / `PCM identical 22050/22050`。wasm 169,807 / 173,204B、実測 29 s | PASS |
| libFLAC 1.3.1 | 同 | FLAC **60,171B** hash **645fb4f042eb9ede** / 復号 hash **d3d89c007626c2b1**。wasm 156,216 / 158,503B | PASS |
| LAME 3.99.5 | `oss/lame/build.sh` | MP3 **16,181B** hash **18dd8a4a4c91ee23**、3 arch identical。wasm 189,172 / 192,446B、実測 36 s | PASS |
| WavPack 4.80.0/4.60.1 | `oss/wavpack/build.sh` | .wv **115,378B** sha256[:16] **25d66af8deedf311**、復号 hash **7819af6dd0d37cf0** = 入力、`WM identical 48000/48000`。wasm 142,907 / 145,216B と 149,387 / 151,027B、実測 36 s | PASS |
| FFmpeg n4.4.2 | `oss/ffmpeg/build.sh` | 4 codec 復号 PCM hash が **3 arch 完全一致**: pcm_s16le 22050 → **9249b2e1bb6ce0b2** / flac 22050 → **693fe9f21e378245** / vorbis 176640 → **b51917f65bbce87d** / mp3 39168 → **1d45943fec1748ca**。実測 119 s | PASS (要修正、下記) |
| libogg/vorbis | `oss/ogg/build.sh` | ogg 30,695B hash cac14495a26b1641、3 arch identical・decode hash 一致 | PASS |

**FFmpeg e2e の欠陥を 1 件修正**: コミット 3fdb1bb の `oss/ffmpeg/build.sh` は `FF_CFG . emconfigure` とだけ呼んでおり (a) `./configure` が抜けて `emconfigure --prefix=...` になり即 FileNotFoundError、かつ (b) ffmpeg の configure は `CC` 環境変数を無視して `cc_default="gcc"` を使うため `emconfigure` だけでは `CC=gcc` のまま = wasm ではなく native オブジェクトができて emcc リンクが落ちる。したがって **コミット時点のスクリプトは wasm32/wasm64 を一度もビルドできておらず、§10.4 の wasm 846,430B / 873,768B は手動手順 (`docs/REFERENCES.md` `[STRATEGY]` 同梱の `ffmake.log` の `emmake make` と `--cc=emcc` 明示) の産物で、1 コマンド e2e では再現できない**。検収で `FF_CFG . emconfigure ./configure --cc=emcc --cxx=em++ --ar=emar --ranlib=emranlib --nm=llvm-nm --strip=llvm-strip` に修正し、3 arch の復号 hash 一致を再現。なお wasm バイナリサイズは **845,872B / 873,256B** (旧記載 846,430 / 873,768 とは 558B / 512B 差。toolchain と configure 差分によるもので、合否基準の decode hash は完全一致)。
ライセンス実測: configure 出力 `License: LGPL version 2.1 or later`、`ffbuild/config.h` は `CONFIG_GPL 0` / `CONFIG_NONFREE 0` / `CONFIG_VERSION3 0`。

### 12.2 独立再計算 (別アルゴリズム) — `python3 scripts/indep_audio_verify.py <files>`

FVN hash 比較のみの harness に対し、以下を自前実装して検算 (数え方の定義はスクリプト冒頭 docstring):
- **入力 PCM を自前生成** (resonator 漸化式 + xorshift64、libm 非依存・test_flac.c と同一式) し、3 バイト little-endian パック後の **MD5** を計算 → FLAC ファイルの STREAMINFO に記録された MD5 と **完全一致** (`88ce5836cc009f35cb1ec8794c1c7355`)。= エンコード→復号の可逆性を harness とは別の暗号学的検算で確認。
- **自前 CRC-8 (poly 0x07) / CRC-16 (poly 0x8005)** を実装し FLAC の 3 frame を検算 → **全 frame で CRC-8 / CRC-16 一致**、frame offset 86 / 22406 / 44717、最終 frame の終端 = ファイルサイズ 60,171B、channel assignment は 3 frame すべて MID_SIDE。
- **自前 RIFF/WAV パーサ**で `gen.wav` の data payload を読み FNV-1a を計算 → **9249b2e1bb6ce0b2** = FFmpeg の pcm_s16le 復号 hash と一致。
- **自前 WavPack `WavpackHeader` パーサ** → 2 block (offset 0 / 57880) がファイル 115,378B を隙間なく覆う、version 0x407、3 bytes/sample、sample rate index 9 = 44100 Hz。
- **自前 MPEG frame header パーサ** → 16 frame・128 kbps stereo、payload 16,077B (残差 104B は LAME info header)。

### 12.3 ネガティブコントロール (規則 41)
- harness 側: FLAC 音声 frame 1B 反転 → 復号 hash `b50bcf…`/`4479db…` ≠ baseline・rc=1、magic 破壊 → rc=1。LAME 別 seed → hash 変化 + determinism 確認。WavPack 入力 1 sample シフト / .wv 1B 破損を検出。FFmpeg FLAC 1B 反転・WAV 1 sample+1 を検出。→ すべて clean HEAD から再現。
- **検収側の独立ネガコン**: `indep_audio_verify.py` に bad- ファイルを与えると自前 CRC-16 で破損を検出 (`crc16_all=False` を観測)。正常ファイルでは全 CRC が一致するので検査は実効性を持つ。

### 12.4 ILSvg version 特定の裏付け (CAB-150) — 独立確認した結果と訂正
| 項目 | 実装側記載 | 検収の独立確認 | 判定 |
|---|---|---|---|
| svgren 下限 | `gradient_setter` = 0.6.0 以上 | `gradient_setter` の初出は **0.5.9 (2021-04-03)**。0.5.9〜0.5.26 も canvas.cpp あり・path_type なしなので範囲は **0.5.9〜0.6.3** | **誤記 (修正済)** |
| agg version | cppfw/agg 2.8.x | agg_*.o 25 本のファイル集合は **2.7.4〜2.8.42 の全 tag** に含まれる。svgren 0.6.3 の AGG API を写した probe も **2.7.0〜2.8.42 でコンパイル成功**。svgren は agg を pin しない | **根拠不足 → 「未確定 (2.7.4〜2.8.42)」に弱めた** |
| papki | 2024-02-25 以降 | 根拠 commit 72b5b58 は `as_dir()` 追加であり `dir()` は以前から存在。シンボル `papki::dir(std::string const&)` は引数が `std::string_view` に変わる **7255fb8 (1.0.102, 2021-06-09) より前** = 1.0.101 以前 | **誤記 (修正済) → 日付矛盾は解消** |
| cssom 0.2.x | 6 class 一致 | cssom tags 0.2.0〜0.2.24 で class 集合は安定しており class 集合だけでは絞れない。`cssom::read(...)` は 0.2.x 系の形状 | 範囲内 (単一点特定は不可) |
| svgdom | 0.3.59〜0.4.9 | `.cpp` 集合・`style_stack_cache`・`finder_by_*` symbol で再現を確認。0.4.x 間で差なし | 範囲内 (単一点特定は不可) |
| pixman | version 未特定 | pixman-*.o 25 本・`/Volumes/imageline/.../pixman/pixman/` に vendored。version 文字列なし | 未特定のまま |
| win/mac 実バイナリ照合 | (対象) | **win 側に ILSvg バイナリは存在しない** (mac `Shared/ILSvg_x64.dylib` のみ。win の PE 25166 個からも ILSvg は検出されず)。ILSvg の version 特定は mac slice (sha256 f9c13d8c…, work/slices/ILSvg_x64.x86_64.dylib) のみで実施 | 範囲外 (win バイナリ無し) |

### 12.5 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FFmpeg `oss/ffmpeg/build.sh` が wasm ビルド不能 (`emconfigure` のみ) | 1 コマンド e2e が再現できなかった | **本コミットで修正** (下記 fix)。CAB-148 に検収コメント |
| agg version が未確定 (2.7.4〜2.8.42) | ILSvg 再ビルド時の agg 選定が決まらない | CAB-150 コメント (子チケット化を提案) |
| pixman version 未特定 | 同上 | CAB-150 コメント |
| svgdom/svgren 連結ビルドがブロック (papki/r4/utki/cssom/mikroxml の header パス) | ILSvg wasm 再ビルド未完 | 新規子チケット (親 CAB-18 / project signature-studio / milestone 統合)。CAB-150 にもコメント |
| liboggio `Oggio*` 9 export 再実装・静的 IPP 部置換 | FL の ogg 読み書き経路が未置換 | CAB-146 コメント (既存) |
| win/mac 実バイナリとのビット一致 | 差し替え時の互換性 | 各 CAB に「同一ソースの別環境一致のみ」と明記済 (運用) |
| REPORT.md が 200 行超 (本節追加で 233 行) | 規則「REPORT.md ≤ 200 行」未達 | 本コミットで圧縮を試みたが積層で超過。メインに整理依頼 |

### 12.6 ファイル (本節の検出物)
`oss/ffmpeg/build.sh` (emconfigure 引数修正) / `scripts/indep_audio_verify.py` (独立再計算・別アルゴリズム) / `data/ilsvg_version.json` (svgren 下限・agg・papki の訂正) / `work/` は gitignore。

### 12.7 検収時の運用変更 (記録)
検収中に運用ルールが改訂された。**ルールの正本は `docs/WORKFLOW.md`** (repo 内に import 済み。旧 preflight 読了証跡は `docs/DECISIONS.md` D6 で廃止)。当時の主な変更は ① `git reset`/`stash`/`checkout --` の全面禁止と「reset せず fix コミットを積む」、② **Linear free issue limit 到達** (子チケット作成を試み \`invalid_request: You've exceeded the free issue limit\` で失敗し起票案コメントに変更した)、③ **Linear 廃止・GitHub Issues + worktree/PR フローへの移行** (旧 Linear は 2026-10-12 以降読み取り専用、対応表は \`docs/REFERENCES.md\` \`[CAB_TO_GH]\`)。Linear 側の検収コメント・状態変更は変更前に実施済み。GitHub 側への反映は main 判断。
