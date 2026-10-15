# tools/ipp — Intel IPP (`dsp_ippv2`) 再現要否の評価と最小実装 PoC

再現: `bash tools/ipp/ipp_e2e.sh` (約 40 秒 [検収実測 38 秒], exit 0 = 12 checks PASS) / `bash tools/ipp/shim/shim_e2e.sh` (exit 0 = **13 checks PASS** [CAB-262 で S13 追加])。大物中間物は `work/` (gitignore)。数値はすべて実測、推定は「推定」と明記。検証起点 commit: `b8e762d` (HEAD, 自分の起点)。

## 0. 結論 (ユーザ質問への回答)

| 問い | 答え |
|---|---|
| IPP **本体**(win 39.9MB / mac 33.8MB の Intel 実装)を再現・lift する必要は? | **不要**。mac arm64 スライスは FL 自身が書いた **0.4MB (text 244KB)** の IPP 互換 API 別実装 (Accelerate + 自前 NEON/C) で、FL はそれで出荷・動作している |
| mac 版になければ Intel 独自という仮説は? | **半分正しい**。Intel 固有なのは「CPU 別 6 経路 (SSE2/SSSE3/SSE4.2/AVX/AVX2/AVX-512) の SIMD 実装」。**API 面 (239 関数)** は arm64 でも必要で、arm64 スライスが 257/420 名・使用関数の 232/239 を提供 |
| 全部不要か? | **否**。win64 FL も `dsp_ippv2` を 229 関数静的参照 (FLEngine 本体だけで 143)。ロード時に 420 名を要求する。→ **API 実装は必要** |
| 最小自前実装で足りるか | **足りる見込み**。PoC: **43 関数 / wasm 46KB** (420 名 lookup 表付き)。実 Intel IPP との差分: 24 関数中 **21 が bit-exact** (AVX-512 経路との比較。NaN の仮数ペイロード差は除く — §4 注。Convert/Threshold の 3 関数は NaN 入力で IPP 自身が ISA 経路間差を持つので「全 ISA 経路で決定的」ではない)、残 3 は IPP 自身が CPU 依存/低精度で bit 一致が定義不能 (§4) |
| 推奨 | **案C**: 使用関数のみ C で自前実装 → emcc。arm64 スライスを「どの関数が要るか・どう実装されているか」の仕様書、win の実 IPP DLL を差分テストの **オラクル** にする (§5) |

## 1. 予備情報の訂正 (メインの未検証メモ vs 実測)

| 予備情報 | 実測 |
|---|---|
| arm64 は ipp 約258+5 export | arm64 export は 259 = FL 要求名 257 + FL が要求しない 2 (`AggCreateInstance`, `ippiCopy_8u_C1R`)。x86_64 は 434 = plain 377 (うち FL 要求 369) + `legacy90` 接頭辞 57。`legacy90` 付きは FL の fallback 名で、plain と合わせ 420 名全てを提供 |
| 423 エントリ | **420 distinct 名** (423 はローダ呼出箇所数; 3 重複)。FLEngine x86_64 と arm64 は**同一 420 名・同順**の表を持つ (`C1`) |
| 参照のある distinct 関数は 159 (F の集計) | **過少**。F は `call [VAR]` のみ数えた。実際は mac が `lea r,[VAR]; call [r]` 形、win(Delphi) が **`mov r,[slot]; call [r]` の二段間接** (.data の &VAR スロット 143 個, reloc 付) で呼ぶ。分類し直すと **win 225 (+関数ポインタ読出 4)=229 / mac x86_64 230(+4)=234 / mac arm64 234**、和集合 **239**。(私自身も最初は win=6 と誤判定し、llvm-objdump 線形掃引の独立検証で二段間接を発見して訂正した) |
| win64 の IPP 同梱は未確認 | `dsp_ippv2_x64.dll` **39,942,656B (block24356)** = 本物の Intel IPP。446 export, .pdata 50,529 エントリ (例外ディレクトリ 606,348B÷12; 検収で 50,560 から訂正 — 旧値は節の raw サイズ 606,720B÷12 でパディング込み), `.text`25.0MB+`IPPCODE`7.2MB, import は KERNEL32 のみ, 経路 index を 1 変数 (`[0x182541000]`) で切替 (6 経路)。x86 版 28.2MB (block24355) は 32bit FL 用で不要。win DLL は 420 名を**全て plain 名で**提供 (legacy90 不要) |
| FLEngine に _ipp 未定義なし (dlopen 経由?) | 正しい。mac: `_dlopen/_dlsym/_dlclose` import + UTF-16 リテラル。win: `LoadLibraryW/GetProcAddress`。ipp 未定義シンボル 0 (`C2`) |
| ildsp_x64.dylib | IPP ではない (Limiter/PitchShifter 等 10 `*_CreateInstance`, Accelerate 依存)。本チケット対象外 |

## 2. 読み込み経路 (ロード側コード読解) — FL 26.1.7

| | mac x86_64 FLEngine | mac arm64 FLEngine | win64 FLEngine |
|---|---|---|---|
| ローダ関数 | `0x5ba770` | `0x5e4f40` | `0x653f40` |
| LoadProc | `0x5bdcc0` (FPC `GetProcedureAddress`→dlsym) | `0x5e9870` | `0x653dd0` (GetProcAddress) |
| ライブラリ名 | UTF-16 `dsp_ippv2.dylib` に `_x64` を挿入 → `dsp_ippv2_x64.dylib` | 同左 | `dsp_ippv2.dll` → `dsp_ippv2_x64.dll` |
| 表の埋め方 | `lea rsi,[VAR]; lea rdx,[UStr名]; call LoadProc` を 420 回 | `adrp/add` 同 idiom 420 回 | `lea rdx,[VAR]; lea r8,[名]; call` 420 回 |
| 失敗時 | dlsym(name) → 無ければ dlsym(**"legacy90"+name**) → 無ければ **エラー報告を呼ぶ** (`IPP function not found: ` リテラルあり; 詳細未確認) | 同 → 無ければ **黙って False を返すだけ** (エラー文字列リテラル自体が無い) | GetProcAddress → `legacy90`+name → 無ければ **`OutputDebugStringW("IPP function not found: "+name)` して False** (例外ではない) |
| 戻り値の扱い | 呼出 4 箇所 (initialization 相当) | 呼出 4 箇所 | 呼出 3 箇所 — **いずれも戻り値を検査しない** |

- arm64 Mac で arm64 スライスが選ばれる件: dlopen のスライス選択は OS 挙動でコードには現れない。構造的裏付けのみ — FLEngine 自体が universal2 で arm64 スライスに**同じローダ**(420 名・同順)を持ち、142/143 モジュールが arm64 スライス保持 (`ilbridge` のみ thin x86_64 = Rosetta 橋渡し)。
- **arm64 版は未提供 163 名をそのまま nil のままにする** (ローダ読解 + 戻り値非検査からの推論。arm64 実機での起動は未確認)。そのうえ arm64 コードには未提供関数向けと思われる nil 判定(`ldr; cbz`)が 15 関数に検出された (x86/win は 0; ヒューリスティックなスキャナ値)。= FL 側が「arm64 は小さい実装」前提で作られている証拠。
- wasm shim への含意: 起動時に 420 名の GetProcAddress が引けることが必要 (win は引けなくても OutputDebugString のみだが、未実装関数を呼べば nil call で即死)。→ 未実装名は **名前入り fail-fast stub** にする (`gen_table.py`)。

## 3. arm64 スライスの正体 (0.4MB)

- 408,224B / `__text` 243,856B / 259 export。依存: libc++, libSystem, **Accelerate** (import: vDSP 56 + vImage 23 + vForce(`vv*`) 19 + LAPACK 2 + libc/libm 47)。x86_64 スライスは Accelerate 非依存の本物 IPP。
- FL が実際に使う 232 export の実装クラス (`data/arm64_ipp_map.json`): vDSP 71, vForce 36, vImage 27, libc/libm/LAPACK 38, **FL 自前 NEON 39, 自前 scalar 21**。例: `ippsAddC_32f`→`vDSP_vsadd` (13 命令, 戻り値常に 0, NULL/len 検査なし), `ippsExp_32f_A11`→`vvexpf`, `ippsSqrt_32f_A11`→`vvsqrtf`, `ippsMove_8u`→`memcpy`, `ippsConvert_32f32s_Sfs`→`ldexpf`+`vDSP_vfix(r)32`。
- **実 IPP との意味差を FL は許容している**: arm64 シムは NULL/len エラー戻り値なし、`MulC(0)`/`AddC(+0)` の ±0 短絡なし (§4)、A11 系は正確な `vv*`。それで出荷 = 厳密な bit 一致は FL の前提ではない (推定; 動的確認は E2E で)。
- 使用集合との包含 (`C5`): 使用 239 のうち arm64 export が **232 (97.1%)** を提供。欠落 7: `ippSetNumThreads`(Edison で nil 判定付き), `ippiFilterGauss_8u_C4R`/`ippiWarpBilinearQuad_8u_C4R`(FLEngine のビットマップ処理に**無条件 blr** = arm64 では到達すれば nil call; 到達しないか未発見の既知バグ), `ippsLog10_32f_A21`/`_64f_A50`/`_64f_A53`(14 の無関係モジュールに同数 12 呼出し = 共有ユニット残滓で dead と推定), `ippsSet_16s`(win のみ)。**arm64 提供集合 ≒ 必要十分条件の上界**という仮説は 97% で成立 (残り 3% は dead/未到達の疑い)。

## 4. 使用関数集合 (全モジュール静的) と実 IPP との差分テスト

方法: `scan_x64.py / scan_arm64.py / scan_win.py` — ローダ idiom から VAR を抽出し、**VAR 直参照 + `lea/mov→call [r]` + &VAR スロット二段間接**を capstone/命令語で `call / 関数ポインタ読出 / その他` に分類 (mac 143 モジュール×2 arch, win 150 モジュール)。「呼出箇所あり」は静的で、dead code を含みうる (Delphi は smart-link、FPC は共有ユニット残滓あり)。

| | mac x86_64 | mac arm64 | win64 |
|---|---|---|---|
| 使用関数 (呼出+ptr 読出) | 234 | 234 | 229 |
| FLEngine 本体のみ | 187 | 202 | **143** |
| PoC 実装済 (43 関数中) | 40 | 41 | 40 (本体 38) |

カテゴリ (和集合 239, 内 arm64 提供): FFT 14, FIR/IIR/conv/corr 17, complex/spectral 14, convert 14, imaging(ippi) 45, mem/fill 22, reduce 9, reorder/bit 14, signal gen 9, threshold 13, vector arith 24, vector math(精度等級付) 41, control 3。**FLEngine 本体の ippi 33 関数** は GUI 描画経路 (M7 関連)。FL 要求 420 名のうち **181 はどの platform も呼ばない**。

差分テスト基盤 (`ref/`): **win の実 `dsp_ippv2_x64.dll` を最小 PE ローダ (`pe_load.c`, 約 100 行) で Linux に VA 敷設し ms_abi で直接呼ぶ** (DllMain 不要、`ippSetCpuFeatures(mask)` だけで経路選択、KERNEL32 は 26 関数のみ実装、他は名前報告 trap。テスト中に trap した import は 0)。`m5` の VA 敷設方式の PE 版。arm64 スライスは Accelerate 依存でネイティブ実行不可 → 実 IPP をオラクルに採用 (こちらが lift 候補そのもの)。経路 idx0..5 = SSE2/SSSE3/SSE4.2/AVX/AVX2/AVX-512 を実測で確認。

| 24 関数 (n=1..4097, 位置ずれ 0/1/3, 特殊値 ±0/denormal/inf/NaN, 216 ケース・各 2.67M 要素を比較) | 結果 (AVX-512 経路との比較) |
|---|---|
| Move_8u/32f, Zero_8u/32f, Copy_32f, Set_32f/32s, Add_32f_I, Mul_32f(_I), AddC_32f(_I), MulC_32f(_I), SubCRev_32f(_I), Sqr_32f(_I), Threshold_GT/LT_32f_I, Convert_32f32s_Sfs | **21 関数 bit-exact** (戻りステータス含む。通常入力と特殊値のみ入力の両方, `C6/C7`)。ただし **両方 NaN の要素は仮数ペイロードの差を「一致」とみなす** (`nan_payload_diff` 別計上: 通常入力 AddC/MulC で各 42〜43 要素、特殊値入力 Add_I 826・Mul_I 817・AddC_I 201・MulC_I 189・AddC 206・MulC 214 要素 / 約 2.67M 中)。NaN 以外は全 bit 一致。NULL×len エラー格子 222 点も全一致 (`C8`) |
| `Sqrt_32f_A11` / `Exp_32f_A11` | 実 IPP は **A11 = 12〜14.5 bit 精度** (相対誤差 最大 4.4e-5〜2.6e-4 = 11.9〜14.5 bit)、自前は 24 bit。IPP 自身が **AVX-512 vs AVX2 で Sqrt 最大 4098 ulp / Exp 最大 1802 ulp 異なる** → bit 一致は定義不能。状態コード (overflow=12, underflow=17, 負引数=19) は一致 (Exp は overflow/underflow 境界の 71 ケースで不一致) |
| `VectorSlope_32f` | **(IPP-9 #276 で出力先が揃った場合、IPP-11 #473 で要素境界に揃った任意の出力先について bit 再現済み。`shim/REPORT_IPP9.md`・`shim/REPORT_IPP11.md`)** 以下は当時の記録: 実 IPP は **ブロック累積** (誤差が真値比で 100〜130 eps24 まで漂う; ISA 経路間の出力は同一) で bit 再現は未解決。自前は 1.8 eps24 (厳密に近い) |

実 IPP の発見済み癖 (bit-exact に必要で実装済): `MulC_32f(_I)` は val==±0 で **+0 全埋め** (x=inf/NaN/負でも)、`AddC_32f` は val==0 で copy (-0 が残る)、`AddC_32f_I` は val==0 で no-op、`Convert_32f32s_Sfs` の NaN は符号で飽和方向 (+NaN→INT_MAX, -NaN→INT_MIN)、len<1→-6/NULL→-8 (ippvm 系 Sqrt/Exp のみ len 検査が先)。

**実 IPP の ISA 経路間差** (`data/diff_results.json`): Exp/Sqrt_A11 (avx512↔avx2), Convert の NaN 入力 (avx↔avx2, ssse3↔sse4.2, sse2↔ssse3: 古い経路は 0、新しい経路は符号で INT_MIN/MAX), Threshold_GT/LT の NaN (avx↔sse4.2)。→ **IPP の bit は CPU 依存**で、ユーザ環境ごとに FL の出力が既に異なる。bit-exact 要件は A11 系・NaN 入力には課せない。

FFT (`ipp_fft.c`, 倍精度基数2 の素朴実装): ippsFFTGetSize/Init/Fwd_RToPack/Inv_PackToR/_I + RToCCS/CCSToR を 32f/64f で実装。order 1..16 × 全 flag(1/2/4/8) 128 ケース (ネイティブ build, `ipp_fft_ref`) で実 IPP との正規化 RMS 誤差 **32f 最大 1.5e-7, 64f 最大 6.6e-16**。wasm 版の突合 (`C11`) は golden 48 ケースで 32f 最大 1.3e-7 / 64f 最大 5.9e-16。Pack/CCS 形式・符号・スケール flag の意味が一致。

## 5. 判定: 案A/B/C 比較

| | 案A: x86_64 IPP を lift | 案B: arm64 スライスを lift | **案C: 必要関数のみ C 自前→emcc (推奨)** |
|---|---|---|---|
| 入力サイズ | mac x86_64 スライス 33.8MB (fat 全体 34.2MB; text 26.2MB) / win 39.9MB (.pdata 50,529 エントリ, 6 経路) | 0.41MB (text 244KB, 259 関数) | PoC 43 関数 = C 約 230 行 → wasm **46KB** (simd128 版 47KB) |
| 工数 (推定) | 最大。RetDec で 26MB text・巨大 closure・経路 dispatch 間接 jmp・AVX-512 経路を避ける pass が必要 | 中。arm64 リフタ要 (RetDec 5.0 は arm64 を名目サポート、未検証) **かつ Accelerate ~100 関数 (vDSP/vImage/vForce) の再実装が結局必要** → C より重い | 小〜中。残 ~190 関数 ≈ 2〜3 人週 (推定; vector 系は定型, imaging 45 と FIR/IIR が重め) |
| wasm サイズ | 数 MB 以上 (推定) | 小 + Accelerate 再実装 | 全 239 関数で 150〜300KB (推定: arm64 text 244KB 比) |
| 数値精度 | 選んだ 1 経路に対して bit-exact (ただし実機 CPU の経路とは別物) | arm64 シムの挙動 (vv* は高精度) | 21/24 bit-exact + A11 は 24bit (IPP 規格内)。差分テスト基盤で関数ごとに実測 |
| denormal/FTZ | IPP の `ippSetFlushToZero` は MXCSR 操作; wasm は FTZ 不可 | 同左 | **同左: wasm に FTZ/DAZ は無い**。FL win は ippSetFlushToZero を 1 回も呼ばない (本表でも未参照) ので影響小、Mac arm64 も同様 |
| bit-exact 可能性 | 高いが無意味 (CPU 依存) | 中 | 決定的な範囲は達成済 (21/24)。VectorSlope は未解決 |
| 配布・権利 (事実のみ) | Intel 第三者バイナリの派生物を同梱することになる。再配布条件は別途確認要 | FL (Image-Line) 製バイナリの派生 + Apple Accelerate 呼出が残る | 自前コード。FL バイナリ非依存 (オラクルはローカル検証専用で配布しない) |
| **採否** | 不採用 | 不採用 (仕様参照のみ) | **採用** |

案B の価値は「**仕様書**」としてのみ: `data/arm64_ipp_map.json` が各 export の実装クラスを与え、未知の癖 (NEON 自前 60 関数) を読むときの手がかりになる。

## 6. 成果物

| パス | 内容 |
|---|---|
| `ipp_e2e.sh` | 1 コマンド再現 (12 checks)。`e2e_check.py` が合否 |
| `fat_split.py` `ipp_names.py` `exports.py` `loader_evidence.py` | スライス分割 / ローダ表 420 名 / export 集合 / ロード側事実 |
| `discover.py` `scan_x64.py` `scan_arm64.py` `scan_win.py` `scan_all.py` `analyze_usage.py` | 使用関数集合の抽出・分類・集約 |
| `a64_map.py` | arm64 各 export が呼ぶ Accelerate/libc の対応表 |
| `xref.py` `a64_xref.py` | ローダ関数・リテラルの xref 探索 (§2 のアドレス特定に使用; arm64 は `llvm-objdump -d` 出力が入力) |
| `src/ipp_min.[ch]` `src/ipp_fft.c`[*] `src/gen/ipp_table.c` | 実装 43 関数 + 420 名 lookup 表 (`gen_table.py` 生成: 未実装 377 は fail-fast stub)。<br>[*] `src/ipp_fft.c` は CAB-139 で `shim/fft/` (pffft 版 28 関数) へ移設・削除。CAB-136 で `shim/impl/` に 35 関数追加 (型付き thunk 計 92 / stub 328, `shim/REPORT.md` §10) |
| `build_wasm.sh` | emcc (standalone wasm, 唯一の import は `emscripten_notify_memory_growth`) scalar / `EXTRA=-msimd128` |
| `ref/` | PE ローダ + 差分ハーネス (`ipp_ref.c` cmp/isa/gen/err, `ipp_acc.c` 精度, `ipp_fft_ref.c`, `ipp_bench.c`) と探索 probe 3 本 |
| `ipp_wasm_cmp.mjs` `ipp_wasm_fft.mjs` `ipp_wasm_bench.mjs` | wasm と golden(実 IPP 出力) の突合・性能 |
| `shim/impl/ipp_sig_fill3.c` `shim/test/fill3_oracle.c` `shim/test/fill3_oracle_run.sh` `shim/count_fill3.py` | **CAB-262**: 次層 29 関数の実装 + オラクル (native/wasm replay) + 独立再計算 (`shim/REPORT.md` §13) |
| `shim/test/sp57.c` `shim/test/sweep2.c` `shim/test/sweepv` | **CAB-261**: interp 4/5/6/7 の 1D 重み (H/V) をスパイク法で抽出 (`shim/REPORT.md` §14) |
| `shim/impl/ipp_resize.c` `shim/verify_cab274_kernel.py` | **CAB-274**: it=6/7 カーネルを Mitchell-Netravalli (it6=MN(0,0.5), it7=MN(0.5,0.3)=CUBIC2P_B05C03) と特定・実装 → オラクル it7 13.169%→**0.005%** / it6 9.768%→**0.000%** + 独立再計算 (`shim/REPORT.md` §15) |
| `data/` | `ipp_usage_summary.json`, `ipp_matrix.csv`(420 名×使用/提供/実装), `arm64_ipp_map.json`, `diff_results.json` |

## 7. 性能 (n=4096 float, ns/call。既知の問題として記録。単発測定でラン間ばらつきが大きい: 検収で 4 回測った範囲を括弧内に併記)

| 関数 | 実 IPP (AVX-512) | wasm scalar | wasm simd128 |
|---|---|---|---|
| Add_32f_I | 86 | 919 (11x) | 349 (4.1x; 再測 3.5〜4.5x) |
| MulC_32f_I | 85 | 530 | 246 (2.9x; 再測 3.1〜5.7x) |
| Move_8u (16KB) | 70 | 67 | 67 (同等) |
| Sqrt_32f_A11 | 114 | 5941 | 889 (7.8x; 再測 6.4〜9.5x) |
| Exp_32f_A11 | 333 | 9810 | 8612 (26x; scalar `expf`; 再測 32〜44x) |
| FFT Fwd 4096 (32f) | 1238 | 48971 (40x) | 39952 (32x; 再測 32〜50x) |

→ FFT は PoC の素朴実装なので **pffft 等 upstream SIMD 実装への差替え**が要る (方針「upstream からビルドできるものはビルド」に合致)。Exp/Log 系は A11 (12bit) 規格なので SIMD 多項式化の余地大。他の bit-exact 関数は simd128 化しても bit 不変 (`C10`)。

## 8. 未解決・リスク・ユーザ依頼

- **静的呼出 ≠ 動的実使用**。239 のうち dead code を含みうる (特に共有ユニット残滓)。確定は lift 済 FLEngine を fail-fast stub 付きで動かす E2E (名前が `ipp_unimpl_name()` に残る)。
- **呼出規約の橋渡し (最大の統合リスク)**: lift 後のコードは MS x64 ABI (xmm0–3 の float 引数) で `call [rax]` する。`MulC_32f_I(val→xmm0, ptr→rdx, len→r8)` 等、C の型付き関数と直結できない。m7/m8 の「f32 引数失落」と同型 → 署名ごとの thunk 生成が必要。
- Win の LoadProc は未解決名で OutputDebugString のみ。mac x86_64 の失敗時動作は未確認。
- VectorSlope の bit 再現 (ブロック累積方式) は未解決。Exp の overflow/underflow 境界 71 ケースで状態コード不一致。Rand/Tone/IIR/FIR の乱数列・状態更新の正確な再現は未着手 (オラクルで要検証)。
- 実 IPP 差分テストの前提: `ipp_ref` は win DLL をローカルで読むだけ (配布しない)。
- **ユーザ依頼**: (1) A11 系・NaN 入力は「IPP 規格内の高精度実装で bit 不一致を許容」でよいか (IPP 自身が CPU 依存のため推奨 yes)。(2) mac 版経路(FPC 製 FLEngine)も将来 lift する場合は arm64/x86_64 どちらを基準にするか。

## 9. 次タスク提案

1. **ipp-shim**: `LoadLibrary("dsp_ippv2")`/`GetProcAddress` を `ipp_lookup` に接続 + MS x64 ABI thunk 自動生成 (署名表は IPP ヘッダ由来)。
2. **ipp-fill**: `data/ipp_matrix.csv` の優先順 (win モジュール数降順) で残関数を実装し、`ref/ipp_ref.c` の FN 表に追加して差分テストを広げる。**CAB-136 で 35 / CAB-245 で 7 / CAB-262 で 29 関数を実施** (残 stub 292、使用集合 239 中 130 — `shim/REPORT.md` §13-7)。FLEngine 本体の ippi 33 関数 (GUI) は M7 と連携。3. **ipp-resize 残差**: it=7 の 31 px (|d|=1 丸め差) と it=16 (Lanczos, 6.913%) は未解明 (§15-6)。
3. **ipp-fft**: pffft 等で置換 (RToPack/CCS, 32f/64f)。
4. **ipp-profile**: lift 済 FLEngine で実呼出関数を採取 → 実使用集合の確定 (本 REPORT の 239 を絞る)。

## 10. 検収記録 (独立再計算)

- 420 名: FLEngine 3 種 (mac x86_64/arm64, win64) を UTF-16 正規表現で独立走査 → 同一 420 distinct 名 (x86_64=arm64 は同順)。export 集合も `llvm-objdump --exports-trie` と自前 PE export パーサで再計算し、win 446 export が 420 名全提供・arm64 257/420・x86_64 plain 369+legacy90 で 420 を確認。
- FLEngine 本体の使用関数: 別系統 (llvm-objdump 逐次逆アセンブル + rip 相対ターゲット解決; win は &VAR スロット 143 個) で mac x86_64 = 187、win64 = 143 を再現。
- オラクルは実 DLL の機械語をそのまま実行 (`pe_load.c` は PE 敷設・import 解決のみ。IPP 互換実装は経路に介在しない)。ただし KERNEL32 26 関数は自前スタブ。
- 訂正した点: .pdata 50,560→50,529、所要 25→約 40 秒、bit-exact の NaN ペイロード注記、「全 ISA 経路で決定的」の削除、FFT ケース数 (native 128 / wasm 48)、性能のラン間ばらつき。

## 11. ipp-shim (CAB-134) — ローダ接続 + 署名 thunk 自動生成 (追記)

詳細は `shim/REPORT.md`、再現 `bash tools/ipp/shim/shim_e2e.sh` (約 10 秒, 10 checks)。§9-1 の実施結果:
- 420 名の関数表 + `LoadLibraryW/GetProcAddress` 接続 (shimx 経由 420/420 解決)。実装済み 43 は型付き thunk、残 377 は fail-soft stub (0 戻し + 呼出カウンタ。STRICT で従来の fail-fast)。
- 署名 420/420 導出 (確度 A 43 / B+ 157 / B- 220)。win 全モジュール 19,018 呼出箇所で型・個数の矛盾 0。同クラス引数の順序は未検証 (B 系)。
- thunk 経路 (本物の MS x64 呼出 → レジスタブロック → dispatch) で §4 の 24 関数 5,184 ケースを再実行: 直呼び・既存 baseline と全統計一致、実 IPP に 21 関数 bit-exact (§0/§4 と同数)。wasm・FFT も同結果。
- 残: icall ブロックへ +0x48 (第 5 引数ポインタ) 追加、使用集合 239 のうち stub 198 (win 静的呼出 28.7% が stub 宛) は CAB-136 で実装。

## 12. 付録: VM 固定パス直書きの除去 (#3830)

- 対象 21 件 (`tools/ipp`・`tools/startup`・`tools/m2`) を `tools/shared` の `REPO_ROOT`・`FL_WIN64_DIR`・`FL_MAC_DIR` 経由へ置換。固定パスの grep (`tools/ipp tools/startup tools/m2 --exclude-dir=work`) は 0 件。既定値は `env.sh`・`paths.py` が従来値を保つ (`tools/shared/test_paths.sh` 4/4 PASS)。
- `shim/test/fl_dll_path.h` は既定値を持たず、`FL_WIN64_DIR` 未設定なら exit 2。呼び出し元 (`shim_e2e.sh` 系) は `env.sh` を source する。
- win 側 before/after (`resize_oracle`, fl-win64 `block24356_PE.bin`, `FL_WIN64_DIR` は runner の展開先): before (origin/main `68d5cb3c4`) と after で `cases.hash` が一致 (`cmp` 同一)。SUM `cases 82056, case_diff 359, byte_diff 55588` は両者で同一 (既存の差分で本変更の影響なし)。
- 未検証: `ipp_e2e.sh`・`startup.sh`・`m2` の全体 run は mac 素材 (`[MAC]`・#293) と Ghidra/emsdk (`docs/REFERENCES.md` の該当 ID) が runner に無いため実行せず。構文 (`bash -n`) と `py_compile` のみ確認。
