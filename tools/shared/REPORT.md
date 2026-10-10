# tools/shared REPORT — FL Shared ライブラリ群の分類・IPP 実測・OSS wasm 再ビルド PoC・プロプラ lift PoC

日付: 2026-10-10 (検収・訂正 2026-10-10: §8) / 担当: F shared-libs / 再現: `bash tools/shared/run_all.sh` (~6 分, 素材は analysis/ を読むのみ)
素材: mac `Contents/Resources/FL/Shared` (+ `Libs/FLEngine`, Plugins 全 dylib = Mach-O 222 本) / win `analysis/win64/extracted` (PE 313 本; 対応 DLL は PDB・export・VERSIONINFO・文字列で特定)

## 0. 結論 (先出し)

| 項目 | 結論 (実測) |
|---|---|
| 分類 | 22 項目: **OSS 系 9** (純 OSS 5 = freetype/ffmpeg/CPython/LAME/WavPack, OSS+IL wrapper 4 = Blend2D/liboggio/EasyFLAC/ILSvg) / **Intel IPP 複合 1** (dsp_ippv2 = IPP 2021.7 + AGG + GPC) / **第三者プロプラ 3** (élastique, REX, libkio=NI K4PL 派生) / **IL プロプラ 9** (ILTools, SGv2, QuickFontCache, winbridge, DirectWaveCt, beat_tracker, ildsp, reverb, ILRemote)。根拠 50 件 (検収で REX の弱い根拠 1 件を著作権表示+REX2 クラス名の 2 件に差替え) を strings/symbol 正規表現で機械検査し **50/50 hit** (§1)。hit = 文字列の存在であり、IL 自社分類は「FPC 3.2.3 署名・IL ソース名」による状況証拠 |
| IPP | dsp_ippv2 は win 446 / mac 434 export (ipps 366 / ippi 71)。**全 Delphi/FPC バイナリが同一 unit を静的リンクし、ロード時に 420 distinct 名 (423 は呼出箇所数) を動的解決**する。**使用関数数は本 tool の初版 (win 12 / mac 159) が過少** — 二段間接呼出 (win `mov r,[slot]; call [r]` / mac `lea r,[VAR]; call [r]`) を数え落とした。`tools/ipp` (S, f7152df) の実測が正: **win 229 / mac x86_64 234 / arm64 234、和集合 239、FLEngine(win) 単体 143** (§2 訂正表)。**lift しない・自前 C 実装**。arm64 slice (**408,224B**, 259 export) は **Accelerate/vImage + FL 自前 NEON/C による FL 自作の別実装** (Intel IPP の派生ではない) で、使用 239 のうち 232 を提供 |
| OSS wasm 再ビルド | **3 本成功** (node 検証): **FreeType 2.7** (native==wasm32==wasm64 40 行完全一致, export 190/190 被覆), **libogg 1.3.2+libvorbis 1.3.5** (エンコード ogg 30,695B **byte-exact**・復号 PCM hash 一致), **Blend2D 0.11.5 (pre-v0.20)** (JIT==no-JIT==wasm の 320×240 **画素完全一致**, 差 0/230,400B = 全 payload; 3 ファイル sha256 一致)。いずれも `bash tools/shared/oss/<lib>/build.sh` で再現 (§3) |
| 重要知見 | (1) FreeType 2.7 は **`long` 幅依存** (ftgrays.c): wasm32 では FT_LONG64 経路強制 + 2 行 patch、または **wasm64 無改変**で LP64 と bit 一致。 (2) **libm 差** (glibc vs musl の sinf) で入力生成が変わると ogg が 1B ずれる → 検証入力は libm 非依存にする。 (3) Blend2D は JIT 不可の wasm でも no-JIT で画素一致、但し速度は native JIT 0.054 ms/frame に対し native no-JIT 0.12–0.16 (2.2–2.9x)、**wasm 0.21–0.27 (約 4–5x)** (検収再計測 3 回) |
| プロプラ lift PoC | **libkio** x86_64 slice の純粋関数 15 本を RetDec→IR pass→wasm 化し、**元 mac 機械語を ctypes で直接実行した結果と 760 ケースで差分テスト**: RetDec + 構文正規化のみ (意味修復なし) **228/760 (30%)** → 最小 pass ([C][E][A]) 適用後 **621/760 (82%)**、9 関数が 40/40・40/40 完全一致。残欠陥は M7/M8 と同型の 3 類型 (§4) |
| 下流チケット | T-SH-01..16 (§5)。最優先 = **T-SH-07 (IPP 自前実装 = CAB-37 に統合; 範囲は tools/ipp の 239 関数)** と **T-SH-02 (Blend2D+Agg2D glue)**。CPython wasm は tools/python (CAB-20) で完了済のため T-SH-05 は実質完了 |

## 1. 分類表 (根拠は data/classification.json の evidence に regex+hit 記録)

| lib | 分類 | upstream / version (実測根拠) | mac fat / win | export mac/win | 方針 |
|---|---|---|---|---|---|
| libfreetype | **OSS** | FreeType **2.7** (mac 内 `/Users/eugene/Documents/freetype-2.7/`)。win は別 version (rebuild に無い export 17 本: `FT_Alloc`/`FTC_Image_Cache_*` 等) | 1.9M / 0.6M | 190/271 | wasm 再ビルド **PoC 済** |
| libblend2d | OSS + IL glue | Blend2D **pre-v0.20 (camelCase `blArrayInit`)** + asmjit **abi_1_13** + FL 独自 `Agg2D` glue (`AggCreateInstance` 1 export, ~140 symbol) | 4.7M / 2.1M | 1/1 | 本体 wasm **PoC 済**; glue は lift/再実装 |
| liboggio | OSS 集合 + IL wrapper + **静的 IPP** | libogg 1.3.x + **libvorbis 1.3.5** + **libFLAC 1.3.1 (+FLAC++)**; IPP 静的 (`e9_ippsConvert_*`, win は IPPCODE 332KB) | 2.5M / 1.9M | 1496/9 | ogg/vorbis **PoC 済**; Oggio* 9 export は再実装 |
| ffmpeg 6 本 | **OSS** | FFmpeg **n4.4.3** (mac, `n4.4.3-1-ga1f13b592b`, avcodec 58.134.100; license 文字列 "LGPL version 2.1 or later"; configure に `--enable-gpl`/`--enable-version3` 無し, `--disable-x86asm`) / **n4.4.2** (win, `n4.4.2-2-g7ffb7d4b04-20220622`; configure に **`--enable-version3`** = "LGPL version 3 or later"、`--enable-gpl` 無し)。※ `analysis/win64/REPORT.md` の「FFmpeg 6.x」は誤り (tools/docs/LEGAL.md と整合)。再ビルドの version 選定は 4.4 系・version3 は避ける(LGPL-2.1+ に揃える) | 37M / 70M | – | emscripten 再ビルド (ffmpeg.wasm 先例) |
| Python.framework | **OSS** | CPython **3.12.1** (mac/win 一致; win は python.org 公式 build + 拡張・関連 DLL 31 本) | 65M / 7M+ | – | **wasm32-emscripten ビルドは tools/python (CAB-20) で成功済** (flpy.wasm 5.92MB, パッチ無し) |
| libmp3lame / wavpack | OSS | LAME **3.99.5** / WavPack **4.80** (mac) 4.60 (win) | 0.9M / 0.5M | 402 / 54 | wasm 再ビルド (自明) |
| EasyFLAC | OSS + 薄い wrapper | libFLAC **1.5.0** (mac)。crc8 は M2/M3 で lift 済 | 0.6M / 0.4M | 524/10 | libFLAC 再ビルド + 10 関数再実装 |
| ILSvg | **OSS 派生** | cppfw **svgdom + svgren** + papki/utki/mikroxml + **AGG** (version 文字列なし。2.4 系は API 形状 `agg::trans_affine::parl_to_parl` / `gradient_radial_focus` からの**推定**) (3 export `svgCreate/Render/Destroy`) | 3.3M / 1.5M | 3/3 | upstream version 特定→再ビルド (T-SH-06) |
| dsp_ippv2 | **Intel プロプラ + OSS 同梱** | Intel oneAPI **IPP 2021.7** (ippCore 文字列) + **AGG(Agg2D)** + **GPC** (`tristrip node creation`; 非商用条項) | 34M / 39.9M | 434/446 | **lift せず自前実装** (§2) |
| elastique | 第三者プロプラ | zplane élastique **2.2.15** (`TElastiquePro`); win は静的 IPP 979KB 含む | 1.2M / 5.0M | 12/15 | lift (EULA 要確認) |
| REX Shared Library | 第三者プロプラ | REX2 (`CREX2DecompressCallback`/`XREX2BadFormat`), 著作権表示 "Propellerhead Software AB 2000-2010" (Reason Studios 前身; win DLL の UTF-16 リソース) | – / 0.3M | – / 14 | 低優先 |
| libkio | 第三者(NI) 派生 | GCC C++ + boost, 名前空間 **NI::GP / K4PO / K4PatchLib** (Kontakt4 patch lib); win は DirectWaveCtEngine.dll に内蔵 | 5.5M / 4.8M | 126/2 | T-SH-13; **lift PoC 済(部分)** |
| ILTools / SGv2 / QuickFontCache | IL プロプラ (**FPC 3.2.3** mac / Delphi win, 同一 Pascal ソース) | `FPC 3.2.3 [2023/12/20] for x86_64 - Darwin` を 4 lib で確認。SGv2 ↔ win `FruityPlug_x64.dll` (export `CreatePlugInstance` 一致; 推定) | 4.6/8.1/4.7M / 3.7/5.9/2.1M | 5/2/8 | FLEngine と同 Delphi パイプライン (T-SH-12) |
| libwinbridge | IL プロプラ **mac 専用** | FPC; Win32 型 (HKEY/IDropTarget) を mac に橋渡しする層 | 1.4M / – | 34 | **移植不要** (tools/shim + M2 SHIM_INVENTORY) |
| DirectWaveCtEngine | IL プロプラ | C++ (libc++) `SampleImport/*` (Kontakt/EXS/Akai/SF2/SFZ/REX importer)。mac は 3717 export (visibility 漏れ), win は 2 | 9.3M / 4.8M | 3717/2 | T-SH-13 (低優先) |
| beat_tracker | IL プロプラ + Eigen | C++ + Eigen, librosa/madmom 風 (`estimate_bpm`, `forward_backward_decode`, `bar_position_hmm`) | 2.6M / 1.0M | 305/14 | T-SH-14 |
| ildsp / libreverb / ILRemote | IL プロプラ | C++ DSP (Limiter/PSOLA/Shimmer…, Reverb) / リモート制御 | 0.8/0.2/0.2M | 10/31/7 | OTT 型 lift (T-SH-15) / ILRemote は対象外 |

## 2. Intel IPP 実測インベントリ (`scripts/ipp_*.py`, `data/ipp_inventory.json`)

> **検収訂正 (2026-10-10)**: 本節の「使用関数数」(win 12 / FLEngine 6 wrapper・23 site / mac 159) は **VAR 直接参照のみを数えた下限値**で過少。`tools/ipp` (S: ipp-eval, f7152df) が二段間接を含めて再測定した値が正: **loader 420 distinct 名 (423 は呼出箇所数)・使用 win 229 / mac x86_64 234 / arm64 234・和集合 239・FLEngine(win) 143**。arm64 slice (408,224B・259 export) は FL 自作の別実装で、使用 239 のうち 232 を提供 (欠 7 は dead/未到達の疑い)。実装方針・差分テスト(実 IPP 比 24 関数中 21 bit-exact)・性能は `tools/ipp/REPORT.md` を正とする。以下の本節数値は「F の初版実測」として残し、訂正済み箇所に ※ を付す。静的 IPP (oggio/MBDelay 等)・export 数・SIMD 規模・ローダ idiom の記述は有効。

**方法**: 全 PE/Mach-O から (a) UTF-16 リテラル `ippMalloc` を含むものを抽出、(b) ローダ idiom (win `lea rdx,[VAR]; lea r8,[NAME]; xor r9,r9; call` / mac `lea rsi,[VAR]; xor cl,cl; lea rdx,[NAME]`) で **名前↔グローバル var を静的に対応付け**、(c) var への rip 相対参照 (call/mov/other) を数える。**独立検証**: capstone で win FLEngine を .pdata 全 57,816 関数・2,566,540 命令逆アセンブルし byte-pattern 結果と一致 (call 6/6)、mac FLEngine は 4,193,856 命令で distinct **115=115**・call site 406 vs 410。

| 観点 | 実測 |
|---|---|
| ローダ表 | win **145 PE** / mac **143 Mach-O** が同一 unit を静的リンク、**423 エントリ (重複除き 420 名)** を解決。unit 名 `dsp_ippv2(.dll/_x64.dylib)` |
| export | win x64 446 (ipps 366 / ippi 71 / core 8 / Agg 1), win x86 446, mac 434。差: win 専用 69 / mac 専用 57 (mac は `legacy90ippi*` 別名) |
| **win 使用 ※下限(正: 229)** | **直接参照 distinct 12**: `ippsMove_8u/32f` `ippsZero_8u/32f` `ippsMulC_32f_I` `ippsAdd_32f_I` (49/49/49/2/49/25 PE) + FruityPlug のみ `ippsAtan_32f_A24` `ippsTrunc_64f` `ippsExp_32f_A11` `ippsFIR64f_32f` `ippsThreshold_LTValGTVal_32f_I` `ippiFilterRoundGetBufSize32f_8u_C1R`。直接参照 PE 54 本。**FLEngine_x64.dll は 6 wrapper (0x653c60-0x653d70) の直接 call 23 site のみを検出 ※ 実際は wrapper 外の二段間接で 143 関数を使用 (tools/ipp)** |
| **mac 使用 ※下限(正: x86_64 234)** | FPC が wrapper を inline するため **直接参照 distinct 159** (Mach-O 143 本が参照; FLEngine 115 distinct / ~410 site)。族別: arith_reduce 43 / image(ippi) 43 / transcendental 31 / memory 21 / dsp_filter_fft 11 / convert 10 |
| 静的 IPP | win **6 PE** に IPPCODE 節: élastique 979KB, Frequency Splitter 676KB, ildsp 634KB, FLEX engineV2 556KB, Multiband Delay 544KB, oggio 332KB (win は symbol 無し)。mac は symbol 有: Multiband Delay **57 関数** (複素 FFT 4..128 点 `ipps_cFFT*_32fc` + Conj/Mul/Sin/Cos), liboggio **11 関数** (Convert/Copy/CplxToReal/Threshold) |
| 規模 | dsp_ippv2 x86_64: **11.66M 命令・SIMD 43%** (AVX-512 408K / AVX 1.66M / SSE 3.0M 命令、CPU 別 variant `y8/e9/k0/l9`) → lift 非現実的 |
| **arm64 slice** | 同 dylib の arm64 は **408,224B・259 export** (ipps 205 / ippi 49 / core 4 / Agg)、`vImage_Error` 文字列 = **Accelerate/vImage ベース (+ 自前 NEON/C) の FL 自作 IPP 互換実装** (Intel 実装の派生ではない; `tools/ipp` §3)。初版の被覆 10/12・153/159 は下限値同士の比で、正は使用 239 中 232 |

**代替方針 (lift せず自前 C + wasm SIMD128, 420 名を同名 export)** ※ 段階 P0/P1/P2 の関数数は下限ベースの初版案。確定計画は tools/ipp §5・§9 / CAB-37
- P0 (初版案): win 6 関数 (Move/Zero/MulC_I/Add_I: 数行の C)。FLEngine 起動に必要な最小。
- P1 (初版案): win 12 (+ Atan/Exp/Trunc/FIR64f/Threshold: libm + 単純ループ; A11/A24 は精度段=許容誤差一致)。
- P2 (初版案): mac 159 → 正は 239 (image 43 = Resize/Warp/Filter/Alpha が最難; FFT/FIR/Conv 11; transcendental 31)。静的 IPP (oggio/MBDelay の FFT 等) は同実装で置換。
- 未実装名は fail-fast stub で 423 名すべて export (ローダが 1 つでも解決失敗すると `xor ebx,ebx` で失敗を返すため)。IPP 実機との bit-exact は不可 (Intel 非公開): 許容誤差 + 既存 FL 出力との整合で検証。
- 付随: dsp_ippv2 は **Agg2D (AGG) と GPC polygon clipper** を同梱 (GPC は非商用条項あり → 事実のみ記録)。Agg 経路は Blend2D 側 (§3.3) に統一する想定。

## 3. OSS wasm 再ビルド PoC (upstream ソースから; lift しない)

共通: emsdk 6.0.12, node 検証。version は**バイナリ実測**で決定 (`oss/fetch_sources.sh`: savannah ミラー不通のため sourceforge 優先)。`work/` は gitignore。

### 3.1 FreeType 2.7 — `bash oss/freetype/build.sh` (~50s)
- native gcc / wasm32 / wasm64 を同一ハーネス (`test_ft.c`: Init/New_Face/Set_Pixel_Sizes/Load_Glyph/Render/Outline CBox, OpenSans, 3 サイズ×6 字×hint on/off) で比較。**3 者 40 行完全一致 (TOTAL 1c0c857a3891256f)**。libfreetype.a wasm32 715KB, 試験 wasm 489KB。
- **LP64 依存 (要注意)**: 素の wasm32 は 30/40 行がずれる (検収で `oss/freetype/unpatched_check.sh` を追加し 30/40 を再現確認; 「1LSB」の程度は未検証)。原因 2 点: ① `ftoption.h` が `#undef FT_CONFIG_OPTION_FORCE_INT64` (clang は `__STDC__` 定義のため FT_LONG64 が立たず**別 rasterizer 実装** `gray_render_scanline` を使う)、② `FT_UDIV` が `long` 幅依存。対策 = (wasm32) FORCE_INT64 有効化 + `ftgrays_lp64.patch` (2 行)、または **wasm64 (-sMEMORY64=1) は無改変で bit 一致**。
- export 被覆: mac 190/190、win freetype.dll 254/271 (win は別 version: `FT_Alloc` 等 17 本が 2.7 に無い → T-SH-01 で win version 特定)。

### 3.2 libogg 1.3.2 + libvorbis 1.3.5 — `bash oss/ogg/build.sh` (~15s)
- 23 ソースを直接 emcc (autotools は cross 判定で Ogg check が落ちる)。合成 PCM 2s→Vorbis VBR(0.4) エンコード→Ogg→復号。**ogg 30,695B hash 一致 (wasm32/64)**、復号 88,200 frame の PCM hash 一致。wasm 504KB (wasm32)。
- **教訓**: 入力生成に `sinf` を使うと native(glibc) と wasm(musl) で 1B ずれた (31108 vs 31109B) → ライブラリ差ではなく libm 差。検証入力は共振器漸化式+LCG で libm 非依存化。FL 本体 (Delphi/FPC) の三角関数も同種の差を持ちうる (§5 T-SH-16)。
- libFLAC 1.3.1 (oggio) / 1.5.0 (EasyFLAC mac) は同手法で可 (**未実施**; autotools→直接 emcc)。

### 3.3 Blend2D (pre-v0.20) — `bash oss/blend2d/build.sh` (~2 分, 2 回目以降 4s)
- version 特定: mac バイナリの C ABI が **camelCase `blArrayInit`**、asmjit 名前空間 `_abi_1_13` (asmjit 2024-01→2025-03)。upstream は 2025-09 (v0.20.0) で snake_case 化 → master(v0.21.3) は不一致。**blend2d fc827d5 (2024-12-13, 自己申告 v0.11.5) + asmjit 029075b** を採用。
- 3 構成 (native JIT / native no-JIT / wasm32 no-JIT) で 320×240 シーン (rounded rect 線形グラデ・半透明円・放射グラデ楕円・stroke bezier・OpenSans テキスト 2 サイズ) を描画: **hash e467bd5b7dbcd277 全一致、画素差 0/230,400B (PPM payload 全域; 3 枚 sha256 同一)** (JIT と no-JIT も一致)。libblend2d.a: JIT 4.0MB / no-JIT 2.6MB / wasm 2.8MB。
- **性能**: ms/frame (300 回平均): 初回 native JIT 0.054 / no-JIT 0.159 / wasm32 0.214 (node24)。**検収再計測 (node 26.10, 3 回)**: JIT 0.053–0.058 / no-JIT 0.121–0.137 / wasm 0.225–0.272 → wasm は JIT 比 **約 4–5x**、native no-JIT は 2.2–2.5x (測定は VM 共有で ±15% ぶれる)。`-msimd128` 試験と glue (Agg2D ~140 symbol) は T-SH-02。

## 4. プロプラ lib 評価と lift PoC

| lib (mac x86_64) | 言語 | 命令数 | SIMD | 間接 call 率 | 難度 | lift 計画 |
|---|---|---|---|---|---|---|
| libreverb | C++ | 5.7K | 35% | 3% | 易 | 最小 DSP。Process_* は SSE scalar → `__asm_*` helper (M6-M11) |
| ildsp | C++ | 146K | 40% | 15% | 中 | OTT 型 DSP、M6-M11 手法 |
| libwinbridge | FPC | 213K | 0.3% | 15% | n/a | 移植しない (shim) |
| ILSvg | C++ (OSS 派生) | 339K | 11% | 21% | 中 | OSS 再ビルド優先 |
| beat_tracker | C++/Eigen | 461K | 23% (SSE packed) | 12% | 中-難 | 14 export; Eigen 展開部大 |
| ILTools / QuickFontCache | FPC/Delphi | 673K / 696K | 3-4% | 17-18% | 難 / 中-難 | win Delphi を FLEngine 同パイプライン |
| libkio | GCC C++ | 794K | 2% | 16% | 中-難 | PoC 参照 |
| SGv2 (FruityPlug) | FPC/Delphi | 1.15M | 7% | 17% | 難 | FLEngine 後 |
| DirectWaveCtEngine | C++ | 1.71M | 2.6% | 23% | 難 | FS shim 後 |
| dsp_ippv2 | C++/asm | 11.7M | 43% | 3% | (lift しない) | §2 |

(補足: libreverb `BaseReverb::Process_Fruity_32FM_32FS` (0x25c0-0x2f87, 外部 call 無し) は RetDec 0.3s で lift 可、IR 73KB に `__asm_{movss,mulss,addss,subss,xorps,movaps,cmpneqss,andps,andnps,orps}` 計 185 call — M6-M11 の helper 生成で実行可能になる見込み (**実行検証は未実施**)。
(命令数/SIMD/間接 call 率 = indirect/全 call は `llvm-objdump -d` 全逆アセンブル実測。C++/Pascal の vtable 比率の目安)

### libkio lift PoC (`bash tools/shared/lift/libkio/lift.sh`)
- 対象: libkio_x64 の純粋ユーティリティ 15 関数 (`GetFourIntel`/`GetEightIntel`/`GetFloat…`/`GetDouble…`/`SetFour…`/`SetDouble…`/`Limit`/`LimitFloat`/`Fix`/`FixHi`/`CBool`/`unilen`/`wcslen16`/`str2compare`/`str4compare`)。RetDec `--select-ranges` 1.7s → m2 `ir_normalize` → emcc standalone wasm (31.9KB)。`ConvertUTF8/16ToUTF32` は静的バッファ+libc 依存のため除外。
- **差分テスト**: 元の mac x86_64 機械語を `mmap(RWX)`+ctypes で直接実行 (SysV ABI は Linux と同一; 非循環の参照) と wasm を同一 760 ケース (small=int32 範囲 / wide=64bit 値) で比較し戻り値ビット+書込バッファを照合。
- **結果**: RetDec + `ir_normalize` (構文正規化のみ; `kio_fix` 無し) **228/760 (30.0%)** → pass 後 **621/760 (81.7%)**。完全一致 (出現する全群 40/40 = 13 群): GetFour/Eight/Float/Double, SetFour/Double, Limit, FixHi, CBool の **9 関数**。残る 6 関数 (unilen 5/40, wcslen16 39/40, str2compare 21/40, str4compare 24/40, Fix 12/40, LimitFloat 0/40) は未修復。
- **欠陥類型** (RetDec decode-only IR; M7/M8 既知と同型 → 汎用 pass 化が T-SH-16):
  - [A] **deref 落ち** `mov rax,[rsi]` が rsi そのものに化ける (Get/Set*Intel, unilen/wcslen16/str*compare) — Get/Set 6 関数のみ修復。
  - [B] **float 引数落ち** (`Fix_RCS(float)` は arg 未使用の alloca load、`LimitFloat`) — 未修復。
  - [C] **`long`(64bit) を i32 と復元** (Limit/FixHi/CBool) — demangle 署名で拡幅 (`kio_fix.py`)。
  - [D] `ucomiss` の flags が IR に接続されない (LimitFloat) — 未修復。
  - [E] `idiv` が `urem` に化ける符号欠陥 (FixHi) — srem 化。
- 示唆: **RetDec 素の IR の信頼度は低く、全関数に対する差分テスト (native 機械語実行) を標準工程にすべき**。本ハーネスは mac slice 全体に流用可 (`diff_test.py`)。

## 5. 下流チケット案

| ID | 内容 | 優先 |
|---|---|---|
| T-SH-07 | **ipp_shim** → **CAB-37 に統合** (tools/ipp の 239 関数・420 名 export・fail-fast・SIMD128・MS x64 ABI thunk)。初版の「P0 win 6 / P1 12 / P2 159」は下限値ベースで破棄 | **最高** |
| T-SH-02 | Blend2D 本採用: `-msimd128` 性能検証、**Agg2D glue (~140 symbol, `AggCreateInstance`) の lift or C++ 再実装**、FL 描画経路での画素比較 | **高** |
| T-SH-01 | FreeType 2.7 本採用 (patch か wasm64 の選択)、win freetype.dll version 特定 (17 export 差)、FT_* 呼出面の shim | 高 |
| T-SH-03 | Xiph スタック: libFLAC 1.3.1/1.5.0 再ビルド、liboggio `Oggio*` 9 export の再実装、静的 IPP 部置換 | 中 |
| T-SH-03b | LAME 3.99.5 / WavPack 4.80 再ビルド | 低 |
| T-SH-04 | FFmpeg n4.4.x (LGPL) wasm + libILVideo glue | 低 |
| T-SH-05 | CPython 3.12.1 wasm32-emscripten — **tools/python (CAB-20) で完了済**。残りは FLEngine への静的リンク(CAB-82 PY-2) | 完了 |
| T-SH-06 | ILSvg: svgdom/svgren/AGG の upstream version 特定 (symbol 集合から bisect)・再ビルド | 中 |
| T-SH-12 | Pascal 共有層 lift: QuickFontCache → ILTools → FruityPlug(SGv2)。FLEngine と同パイプライン | 中 (FLEngine 後) |
| T-SH-13 | DirectWaveCtEngine + libkio (importer 群) | 低 |
| T-SH-14 | beat_tracker lift (mac x86_64 SSE 版; Eigen) | 低 |
| T-SH-15 | ildsp / libreverb: OTT 型 DSP lift (差分テスト基盤は本 PoC を流用) | 中 |
| T-SH-16 | RetDec 欠陥 [A]-[E] の汎用 IR pass 化 + native 機械語実行による全関数差分テスト基盤 | **高** (全 lift の信頼性) |
| T-SH-10/11 | élastique / REX (第三者バイナリ): EULA 確認後に lift | ユーザ判断待ち |

## 6. 制約・未解決・ユーザ依頼
- **未実施**: libFLAC/LAME/WavPack/FFmpeg の実ビルド (方針のみ; CPython は tools/python で実施済)、ILSvg の cppfw version 特定、Blend2D の wasm SIMD 試験、Agg2D glue、win 側 Blend2D/FreeType の version 厳密特定。
- Blend2D version は「pre-v0.20 の 2024-12 時点」で近似 (FL が使う正確な commit は不明; symbol 集合比較で絞込み可)。
- IPP の使用数は静的参照数で実行時カバレッジではない。本 tool 初版の win 12 / mac 159 は VAR 直接参照のみの下限値 (二段間接の数え落とし)。確定値 239 は tools/ipp。
- **ユーザ依頼**: ① élastique / REX / IPP(再配布条件) / GPC(非商用条項) / NI 派生コードの EULA・ライセンス判断 (事実のみ記載)。② 素材追加は不要。

## 7. ファイル
`run_all.sh`(e2e) / `scripts/`(win_catalog, mac_catalog, ipp_win_scan·all·validate, ipp_mac_scan·validate, ipp_static_mac, ipp_summary, classify, simd_stats, disasm, dump_strings) / `oss/{fetch_sources.sh,freetype,ogg,blend2d}` / `lift/libkio/`(funcs.txt, lift.sh, kio_fix.py, kio_simd.c, diff_test.py, run_wasm.mjs) / `data/`(classification, ipp_inventory, freetype_export_diff, libkio_lift_difftable[_raw])。`work/` は gitignore (slice・ビルド物・大 JSON)。

## 8. 検収記録 (2026-10-10, 検収担当 subagent)
独立再計算の結果 (`run_all.sh` 再実行 exit 0, 約 6 分):
- **分類**: 22 項目の内訳 (純 OSS 5 / OSS+wrapper 4 / IPP 1 / 第三者 3 / 自社 9) と主要 version 文字列を、work/strings を介さず実バイナリ (`grep -a`) で再確認 (FreeType 2.7 パス, libFLAC 1.3.1 20141125 / 1.5.0 20250211, libvorbis 1.3.5, n4.4.3-1-ga1f13b592b, CPython 3.12.1, LAME 3.99.5, WavPack 4.80.0 (win 4.60.1), IPP 2021.7, élastique 2.2.15, FPC 3.2.3, K4PL, svgren/agg)。win FFmpeg 6 DLL は n4.4.2 + `--enable-version3` を確認。
- **wasm 再ビルド**: FreeType 3 者 40 行一致 / 190 export 被覆 (win 254/271), ogg 30,695B 3 者 md5 一致・PCM 88,200 frame hash 一致, Blend2D 3 構成 sha256 一致。
- **libkio**: difftable から 228/760 → 621/760, 9 関数完全一致を再集計。
- **訂正した誤記**: ① IPP 使用数 (win 12 / mac 159 / FLEngine 6 wrapper) は下限値 → tools/ipp の 229 / 234 / 239 / 143 を正とする (§0・§2・data/ipp_inventory.*・classification)。② Blend2D 「差 0/197,124B」は PPM ヘッダ解析バグ (header 4 行読みで先頭 ~33KB を除外) による誤値 → 正しくは 0/230,400B (修正済 `oss/blend2d/build.sh`)。③ wasm 速度 「JIT 比 3.0x」は native no-JIT の比で、wasm は 4–5x。④ FFmpeg: win n4.4.2 `--enable-version3` / mac n4.4.3 を明記 (analysis/win64/REPORT.md の 6.x は誤り)。⑤ CPython wasm は tools/python で成功済 (「未実施」から除外)。⑥ REX の根拠 regex `REX` は弱かったため著作権表示 (Propellerhead 2000-2010) に差替え。⑦ ILSvg の AGG 2.4 は推定と明記。⑧ FreeType「素 wasm32 は 30/40 行ずれる」は build.sh のスタブ関数のみで再現不能だったため `unpatched_check.sh` を追加 (30/40 再現)。⑨ libkio の「素の RetDec」は ir_normalize 適用済と明記。
- **Linear**: CAB-18 は libFLAC/LAME/WavPack/FFmpeg の実ビルドが未実施のため In Progress 維持。下流は子チケット化 (T-SH-07 は CAB-37 に統合)。
