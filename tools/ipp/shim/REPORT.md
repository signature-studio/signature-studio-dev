# tools/ipp/shim — dsp_ippv2 ローダ shim + 署名 thunk 自動生成 (CAB-134)

再現: `bash tools/ipp/shim/shim_e2e.sh` (前提 `tools/ipp/ipp_e2e.sh` の成果が `work/` にあること。無ければ自動実行。前提ありで約 10 秒、exit 0 = 10 checks PASS)。大物は `tools/ipp/work/shim/` (gitignore)。数値はすべて実測、推定は「推定」と明記。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 420 名の関数表 + ローダ | **完了**。`LoadLibraryW("…dsp_ippv2_x64.dll")` → `GetProcAddress(420 名)` を shimx 経由で 420/420 解決 (絶対パス・`legacy90` 接頭辞も可)。取得値は cookie (表要素のアドレス) |
| thunk | **92 件 (型付き thunk)** = 実装済み全部 (CAB-134 43 + CAB-139 FFT 14 + CAB-136 優先順上位 35)。残 **328 件は fail-soft stub** (eax=0 / xmm0=0 を返し、関数別カウンタと初回順を記録。STRICT モードで trap) |
| 署名 | **420/420 導出 (不明 0)**。確度 A 92 / B+ 129 / B- 199 (CAB-136/139 完了時点。§2 の導出監査時は A 43 / B+ 157 / B- 220 — 実装済み 92 関数は A に繰り上げ)。呼出箇所実績 (win 145 モジュール 19,018 箇所) との**型・個数の矛盾 0** |
| thunk 経路の回帰 | 既存オラクル **24 関数 × 216 ケース (5,184)** を「実 MS x64 呼出 → asm トランポリン → dispatch → thunk → 実装」で再実行し、**直呼び・既存 baseline (`work/cmp_avx512.json`) と全統計が完全一致、実 IPP に対し 21 関数 bit-exact** (通常/特殊値入力とも)。エラー格子 222 点一致。wasm (scalar/simd128) の golden 突合も同じ 21 bit-exact、FFT 48 ケース NRMS 32f 1.34e-7 / 64f 5.87e-16 (thunk 経由) |
| 「最大の統合リスク」(呼出規約の橋渡し) | **thunk 側は解消、lift 側との接点が残る** (§6): レジスタブロック契約を icall の memory-ABI と同一配置で定義し、`stk`(第 5 引数以降) ポインタ +0x48 の追加が **icall 側に 1 点必要** |
| 実装の穴 (重要) | 使用集合 239 のうち stub は **166 関数** (CAB-136 完了時点; 実装済 73)。残る上位は `ippiResizeSqrPixel_8u_{C1,C3,C4}R` (143 モジュール)・`ippsThreshold_GT_32s_I` / `ippsSub_32f_I` / `ippsCopy_32s` / `ippsAtan_32f_A11` (125) ほか (§10-6) |

## 1. 成果物

| パス | 内容 |
|---|---|
| `sigscan.py` | win64 全モジュールの IPP 呼出箇所から引数レジスタ書込実績を採取 → `data/callsite_evidence.json` (217 関数) |
| `sigs.py` | 署名導出 (規則 + 明示表)。C 仮引数列で記述。ABI プローブ 6 本 (`PROBES`) |
| `gen_shim.py` | 署名検算 + 生成: `gen/ipp_proto.h` `gen/ipp_shim_tab.c` `data/ipp_sigs.json` `data/sigs_summary.json` `test/gen/probe_thunks.c` |
| `src/ipp_shim.[ch]` | ローダ/dispatch/fail-soft 本体 (C, 依存なし)。`src/ipp_shim_shimx.c` = shimx 結合グルー |
| `build_native.sh` `build_wasm.sh` `shim_e2e.sh` `shim_check.py` | native/wasm ビルド、1 コマンド e2e、合否判定 (`data/shim_results.json`) |
| `test/` | `shim_selftest.c` (ABI/ローダ/stub)、`shim_ref.c` (実 DLL オラクル vs thunk)、`tramp_x86_64.c` (手書き asm: 本物の MS x64 呼出 → ブロック)、`ipp_shim_wasm.mjs` (golden 突合)、`shimx_glue_test.c`、`proto_check.c` |
| `impl/README.md` | CAB-136 以降の実装追加契約 (置くだけで stub → 型付き thunk に自動切替) |

## 2. 署名: 導出・確度・検算

**IPP ヘッダ現物はこの環境に無い**ため (チケット記載の「ヘッダ由来」は不可)、命名規則 (`ipps<Stem>_<型>[_I|_Sfs|_A<等級>]`) + 公開 API の知識で `sigs.py` に C 仮引数列として記述し、**呼出箇所実績で独立に検算**した。

| 確度 | 件数 | 意味 |
|---|---|---|
| **A** | 43 | 実装済み。生成プロトタイプを `src/ipp_min.h` と同一 TU に入れて `-Werror` でコンパイル → **型衝突 0** (規則出力が実装宣言と一致)。うち 24 関数は実 IPP と実行比較 |
| **B+** | 157 | 規則/明示 + 呼出実績が一致。内訳: 完全一致 137 / weak 20 (型は矛盾しないが一部引数が実績で未観測) |
| **B-** | 220 | 実績なし。内訳: 使用集合 239 内 41 (mac のみ呼出 or 低サンプル) / どの platform も呼ばない 179 |

- 由来別 (A 除く 377): 規則導出 242 / 手書き 135 (ippi 71・FIR/IIR 17・未実装 FFT 14・信号生成 9・複素 Set 9・その他 15)。手書きのうち使用集合 239 内で実績確認が無いもの 15: `ippiFilterRoundGetBufSize32f_8u_C1R` `ippiFilter_Round32f_8u_C1R` `ippiMirror_8u_C3IR/C4IR/C4R` `ippiMulC_8u_C4RSfs` `ippiResizeCenter_8u_C3R/C4R` `ippiRotateCenter_8u_C4R` `ippsEqual_8u` `ippsIIR64f_32f_I` `ippsIIRGetStateSize64f_BiQuad_32f` `ippsIIRInit64f_BiQuad_32f` `ippsSet_32fc` `ippsTone_Direct_32fc` → **実装前に要確認リスト**。
- 検算の中身 (`sigscan.py`): 各呼出箇所の直前 ≤160B を逆アセンブルし、MS x64 引数レジスタ (rcx/rdx/r8/r9, xmm0-3, `[rsp+0x20…]`) への書込を集計。期待 (署名) と比較し、半数近い箇所で観測 = 在り。**判定できるのは「どのスロットが GPR か XMM か」「引数個数の下限」まで**で、**同クラスの引数同士の順序 (ポインタ 2 本の src/dst 入替等) は検算できない**。FIR/IIR の `pState` 位置、`ippsFIRSetTaps` の引数順 (記憶では taps が先)、`Equal_8u` の意味などは B 止まり。
- 実績の妥当性確認: 既知署名で試すと `Move_8u`=rcx/rdx/r8、`MulC_32f_I`=xmm0,rdx,r8、`Threshold_GT_32f_I`=rcx,rdx,xmm2、`VectorSlope_32f`=rcx,rdx,xmm2,xmm3、`Convert_32f32s_Sfs` スタック 1 語、`ippiResizeSqrPixel_8u_C4R` スタック 9 語 (= 13 引数。ダブル 4 個がスタック) と署名どおりに出る。
- 初回実行で `ippsFFTFwd_RToCCS_32f_I` / `ippsFFTInv_CCSToR_32f_I` が「slot3 に書込あり」で矛盾判定 → 姉妹関数 `RToPack_32f_I` (50 箇所) は slot3 なし、当該は 2〜4 箇所のみ、実 IPP 実行比較 (3 引数) で正しい → 低サンプル (<5) の矛盾は weak 扱いにした (判定規則をデータ側に合わせたのではなく、サンプル数の下限規則)。
- 全 420 名の署名 (引数ごとの ABI クラス・レジスタ・確度・根拠) は `data/ipp_sigs.json`。IR pass・CAB-136 実装者はこれを参照。

## 3. thunk と ABI 契約

**レジスタブロック `IppBlk`** (配置は `tools/icall/icall_rewrite.py` の memory-ABI ブロックと同一。`static_assert` で固定):

| off | 内容 | off | 内容 |
|---|---|---|---|
| +0x00 | target (GetProcAddress が返した値) | +0x28..0x40 | xmm0..3 (下位 64bit; float は下位 32bit) |
| +0x08..0x20 | rcx rdx r8 r9 | **+0x48** | **stk = call 時点の rsp+0x20 (第 5 引数スロットのアドレス) ← icall に無い拡張** |
| +0x80 | rax (戻り: IppStatus=eax, ポインタ=rax) | +0x88 | xmm0 (戻り; IPP は常に 0) |

- 引数 i の位置は**位置のみで決まる** (i<4 → rcx/rdx/r8/r9 または xmm0-3、i≥4 → スタック語 i-4)。型は署名が決める: float/double → xmm、整数・ポインタ・**8B 以下の値渡し構造体 (`Ipp32fc` `IppiSize` `IppiPoint`) → GPR (ビット列のまま memcpy)**、**16B 構造体 (`IppiRect` `Ipp64fc`) → 呼出側コピーへのポインタ** (thunk が deref して値渡し)。32bit 整数/float のレジスタ上位は未定義として読む (テストは 0xDEADBEEF を詰めて検証)。
- ゲストポインタ ↔ ホストポインタは `IPP_GUEST_PTR(w)` / `IPP_TO_GUEST(p)` マクロ (既定は恒等 = ゲスト番地が wasm32 リニアメモリ番地。lowbase 方式のベースオフセットがあるなら `-D` で差替え)。
- 検証した ABI 特殊ケース (`shim_selftest.c`, **本物の MS x64 呼出で**): 狭い整数 (u8/s16/u32/s64)、スタック上の double/float、xmm0-3 と GPR の位置混在、8B 構造体 GPR・4B 構造体スタック・16B 構造体参照、13 引数 (ippiResizeSqrPixel 形)、ポインタ戻り。**mutation 検査**: thunk の xmm/stack 読出しを故意に壊すと 5/6 プローブが FAIL することを確認 (テストが実効的)。

## 4. ローダ (`src/ipp_shim.h`)

| API | 役割 |
|---|---|
| `ipp_shim_getproc(name)` / `ipp_shim_find` / `ipp_shim_cookie(i)` | 420 名の解決 (二分探索、`legacy90` 接頭辞は剥がして同じ関数)。未知名・NULL → 0 |
| `ipp_shim_load_library_w` / `ipp_shim_get_proc_address` | `dsp_ippv2[_x64][.dll\|.dylib]` (パス・大小無視) を判定する LoadLibraryW/GetProcAddress 相当 (shimx 非依存の単体利用) |
| `ipp_shim_install_shimx()` | shimx に擬似モジュール `dsp_ippv2_x64.dll` + 420 名を登録 (`shimx_module_register` / `shimx_proc_register` のみ使用) |
| `ipp_shim_dispatch(IppBlk*)` | `b->target` が cookie なら実行して 1、他は 0 (b 不変)。実装済み → 型付き thunk、未実装 → fail-soft |
| `ipp_shim_set_mode` | SOFT (既定) / STRICT (未実装で `__builtin_trap`)。従来の fail-fast は STRICT で再現 |
| `ipp_shim_calls(i)` `ipp_shim_stub_first(k)` `ipp_shim_stub_distinct()` `ipp_shim_last_stub()` | 実使用の採取 (**CAB-37 の ipp-profile 用**: 起動〜操作後に呼ばれた stub の初回順を取得)。カウンタは原子的 |

fail-soft の注意 (**サイレントに誤る**): stub は status 0 (=成功) を返し出力バッファを触らない。`Init/Alloc/GetSize` 系 10 関数 (`ippsFIRInitAlloc*` `ippsFIRMRInitAlloc*` `ippsIIRInit64f_BiQuad_32f` `ippsIIRGetStateSize…` `ippiResize*GetBufSize` `ippiFilterBoxBorderGetBufferSize` `ippiFilterRoundGetBufSize32f_8u_C1R`) は出力ハンドル/サイズ未更新のまま 0 戻りになる → 後続は NULL state で stub を呼ぶ連鎖 (クラッシュはしない設計)。**統合後の初回 E2E は STRICT で回して踏む stub を洗い出す**ことを推奨。

## 5. 検証 (`shim_e2e.sh` の 10 checks, 実測)

| # | 内容 | 結果 |
|---|---|---|
| S1 | 420 名の署名・thunk 件数 | 不明 0 / 型付き 43 / stub 377 |
| S2 | 呼出実績との矛盾 | **0** (agree 173 / weak 24 / nodata 223) |
| S3 | native 自己検査 (ABI プローブ 6・420 名解決・legacy90・LoadLibraryW 名 8 形・stub 全数を呼んで fail-soft/カウンタ/初回順) | 1,513 checks 失敗 0 (CAB-136/139 後の stub 328×2 実測。CAB-134 当初は 377 stub で 1,611) |
| S4/S5 | 実 DLL オラクル (AVX-512 経路) vs thunk、通常入力/特殊値入力: thunk 統計 = 直呼び統計 = 既存 baseline JSON、バッファ全語・状態コードの thunk-直呼び差 0 | 24 関数 5,184 ケース ×2 入力種、不一致 0 |
| S6 | thunk 経由でも実 IPP に bit-exact | **21 関数** (NaN 仮数ペイロード差は既存と同じ扱い・同じ件数) |
| S7 | NULL×len エラー格子 | 222 点、実 IPP との不一致 0 |
| S8 | wasm scalar / simd128 (83,467 / 84,488 B): golden を ABI ブロック経由 (JS 側で署名から MS ABI 配置を再現、上位 32bit ゴミ) | 21 bit-exact・fail 0、FFT 48 ケース NRMS 32f 1.34e-7 / 64f 5.87e-16、stub fail-soft |
| S9 | shimx 結合 (wasm): `LoadLibraryW`(裸名・絶対パス) → `GetProcAddress` 420/420 → MulC_32f_I を FL 同様のレジスタ配置で実行 → stub fail-soft | PASS |

非 bit-exact 3 関数 (Sqrt/Exp_A11, VectorSlope) は既存 REPORT §4 のとおり (実 IPP 自身が CPU 依存/低精度) で、thunk 経由でも同一統計。

## 6. M11/lift 結合手順書 (今回は未結合)

**シンボル命名**: 公開は `ipp_shim_*` (C リンケージ、接頭辞なし)。実装関数は IPP 名そのまま (`ippsAddC_32f` …) で lifted 側の `function_<VA>` / Win32 名 (shimx) と衝突しない。per-function thunk は `static blk_<IPP名>` (非公開)。複数 DLL 同居で接頭辞化する場合も `ipp_shim_*` は 1 つだけ持てばよい。

1. **同一 wasm モジュール/同一リニアメモリにリンクする** (必須)。IPP に渡るポインタは FL のバッファそのもの。別 instance にすると deref 不能。`m11_build.sh` の `cc` 群に次を追加: `ipp/shim/src/ipp_shim.c`, `ipp/shim/gen/ipp_shim_tab.c`, `ipp/src/ipp_min.c`, `ipp/shim/fft/ipp_fft_pffft.c` + `ipp/shim/fft/pffft/*.c` (CAB-139 以降。旧 `ipp/src/ipp_fft.c` は移設済), `ipp/shim/impl/*.c` (CAB-136 以降), (shimx 経由なら) `ipp/shim/src/ipp_shim_shimx.c` (`-I tools/shimx/src`)。**IPP 実装 2 本は `-ffp-contract=off -fno-fast-math` 必須** (m11 の `CF` は `-O0 -g1` のみ。bit-exact 前提が崩れる)。M11 の `-sERROR_ON_UNDEFINED_SYMBOLS=0` / `--export-all` でも衝突しない。
2. **起動順**: shimx 初期化後・FL の IPP ローダ (win64 `0x653f40`、呼出 3 箇所) より前に `ipp_shim_install_shimx()` を 1 回。FL は `dsp_ippv2.dll` に `_x64` を挿入した名で `LoadLibraryW` → `GetProcAddress`×420 → 戻り値は検査されない。shimx を使わない場合は、lift 側の `LoadLibraryW`/`GetProcAddress` 実装から `ipp_shim_load_library_w` / `ipp_shim_get_proc_address` を呼ぶ。
3. **間接 call の接続**: FL は VAR に取得値を保持し `mov r,[slot]; call [r]` で呼ぶ (win)。`icall_rewrite.py` が target と rcx/rdx/r8/r9/xmm0-3 をブロックへ store し `__icall_dispatch(site_va)` に落とすので、**その先頭で `if (ipp_shim_dispatch(blk)) return;`** を入れる (cookie 以外は 0 で素通り)。戻り値はブロック +0x80/+0x88 から icall 側が既に load する。x64c (`ott_dispatch`) でも CPU 状態 `R[]` から同じブロックを組めば同様。
4. **icall への要望 (CAB-134 範囲外・要依頼)**: ブロックに **+0x48 = call 時点の rsp+0x20** を追加 (`lea` 1 命令)。無いと第 5 引数以降を持つ関数が使えない — 実装済みでは `Convert_32f32s_Sfs`・`FFTGetSize_R_32f/64f`・`FFTInit_R_32f/64f` の 5 関数、stub では 90 関数 (うち win が呼ぶもの 45。`ippiResize*` は 10〜13 引数) が該当。≤4 引数の IPP 呼出はこれ無しで動く。
5. **ポインタ**: m11 (LVA=RVA+GLOBAL_BASE)・lowbase (LB_BASE=0x10000) ともゲストポインタ = wasm32 リニア番地なので恒等で正しい。ゲスト VA にオフセットを持つ構成になった場合のみ `-DIPP_GUEST_PTR/IPP_TO_GUEST` を差替え。
6. **採取**: 結合後の最初の実機走行は `ipp_shim_set_mode(IPP_SHIM_STRICT)` か `ipp_shim_stub_first()` 列挙で「実際に踏まれた stub」を取る → 使用集合 239 の確定 (REPORT §8 の未解決項目) と CAB-136 の優先順に直結。

## 7. リスク (「最大の統合リスク」への回答)

| リスク | 状態 |
|---|---|
| 呼出規約の橋渡し (xmm 引数の失落/誤配置, m7/m8 と同型) | **thunk 側は解消**: 型は署名表で位置別に確定、実 MS x64 呼出で検証 (float/double/構造体/スタック)。lift 側は xmm を raw bits で保持するため失落しない前提 (icall ブロックが `movsd` で xmm0-3 を store する設計に依存)。**残るのは icall ブロックの +0x48 追加 (§6-4) と、IR が xmm 値を SSA に持っていること** (m7: 呼出直前 `__asm_movss` に残る) |
| 署名誤り → 実装時の引数取り違え | B+/B- (377) の引数**順序**は未検証 (§2)。CAB-136 は実装前に呼出側逆アセンブルで順序確認。型衝突はコンパイラ (`proto_check`) が防ぐ。クラス/個数は実績検算済み |
| stub のサイレント失敗 | 198 関数 (使用集合) が stub で、呼ばれても 0 戻り。ippi 描画 45 は FLEngine 本体の GUI 経路 (M7 関連)。STRICT/採取で可視化できるが、**機能欠落は CAB-136 まで残る** |
| リニアメモリ分離 | 同一モジュール必須 (§6-1)。別 wasm にすると全 IPP 呼出が壊れる |
| スレッド | 採取カウンタのみ原子的。実装本体 (ippMalloc 以外) は状態を持たない。FFT spec/FIR state は呼出側保持で再入可 (既存実装の性質; FIR/IIR 実装時に要注意) |
| mac FPC 版 | 本 shim は win64 呼出規約 (MS x64)。mac FLEngine を lift する場合は SysV (rdi,rsi,rdx,rcx,r8,r9 / xmm0-7) のブロック版が別途必要 (未着手) |

## 8. 未解決・制約

- 署名の根拠にヘッダ現物が無い (B 系は規則 + 呼出実績)。引数順序は未検証 (§2)。
- 呼出実績は 1 モジュール 1 関数あたり先頭 3 箇所・直前 160B・ヒューリスティック (レジスタ再利用で未観測の weak が 24)。
- thunk 検証の実 IPP オラクルは既存 24 関数 + FFT のみ (実装済み 43 のうち残りは FFT の別 flag・in-place 等)。stub 377 には比較対象の実装がまだ無い。
- 実 FLEngine lift との結合・実機能確認は未実施 (依頼どおり)。

## 9. 次タスク提案

1. **CAB-136 (ipp-fill)**: **実施済み (§10)** — 優先順 (win 呼出モジュール数降順) 上位 35 関数 + Init/Alloc/GetSize 10 関数 (エラーコード返却) を実装。元リスト: `ippiCopy_8u_C3AC4R` `ippiAddC/SubC_8u_C3/C4IRSfs` `ippsOrC_32u_I` `ippiSet_8u_C3R` `ippiCopy_8u_C3R/C4R/C1C4R/AC4C3R` `ippiCopyManaged_8u_C1R` `ippiAlphaPremul_8u_AC4IR` `ippiFilterBox_8u_C3IR/C4IR` `ippiAlphaCompC_8u_C3R/C4R` `ippsThreshold_GT_32f` `ippsSet_64s` … (いずれも 143〜145 モジュールが呼ぶ)。手順: `shim/impl/*.c` に追加 → `gen_shim.py` が自動で thunk 化 → `test/shim_ref.c` の FN 表に追加して実 IPP 差分。実装前に B 系の引数順序を逆アセンブルで確認。
2. **CAB-139 (ipp-fft)**: **実施済み** (`shim/fft/REPORT.md` — pffft 差替え、FFT 28 関数 stub 0)。`impl/` か FFT 実装 TU を置き換えるだけで `shim_e2e.sh` の S8 (FFT 48 ケース) が回帰テストとして機能する設計は維持。
3. **icall 側 (別チケット案)**: ブロックに +0x48 (stk) 追加と `__icall_dispatch` 先頭の `ipp_shim_dispatch` フック。これが無いと第 5 引数以降を持つ IPP 関数が結合後に使えない。
4. **ipp-profile**: 結合後に STRICT/採取で実使用集合を確定 → 239 を絞る (REPORT §9-4)。
5. mac 版 FLEngine を lift する場合の SysV ブロック版 shim (任意)。

## 10. CAB-136 (ipp-fill): 優先順上位 stub の実装 (2026-10-10)

**結論**: win 呼出モジュール数降順の上位 25 関数 (ippi 21 + ipps 4) を**実 IPP DLL と bit-exact・状態コード一致**で実装、Init/Alloc/GetSize 系 10 関数を**エラーコード返却** (CAB-134 検収決定の適用) で実装。合計 **35 関数** (typed thunk 43→78、CAB-139 分と合算し 92)。回帰 `shim_e2e.sh` **10 checks PASS 維持**。実装は `impl/ipp_img_fill.c` + `impl/ipp_sig_fill.c` のみ (契約どおり `gen_shim.py` が自動 thunk 化)。

### 10-1. 実装関数と優先順根拠 (`data/ipp_matrix.csv` win_modules 降順)
- **145 モジュール群**: `ippsOrC_32u_I` `ippiSet_8u_C3R` `ippiCopy_8u_C3R/C4R/C1C4R/C3AC4R/AC4C3R` `ippiCopyManaged_8u_C1R` `ippiAlphaPremul_8u_AC4IR` `ippiFilterBox_8u_C3IR/C4IR` `ippiAddC_8u_C3IRSfs/C4IRSfs` `ippiSubC_8u_C3IRSfs/C4IRSfs`
- **143 群**: `ippsSet_64s` `ippsSqrt_32f_A21` `ippsThreshold_GT_32f` `ippiAlphaCompC_8u_C3R/C4R` `ippiMulC_8u_C3IRSfs` `ippiCopyConstBorder_8u_C3R/C4R` `ippiCopyReplicateBorder_8u_C3R/C4R`
- **Init/Alloc/GetSize 10** (エラーコード返却): `ippsFIRInitAlloc_32f/64f_32f` `ippsFIRMRInitAlloc_32f/64f_32f` `ippsIIRInit64f_BiQuad_32f` `ippsIIRGetStateSize64f_BiQuad_32f` `ippiResizeGetBufSize` `ippiResizeSqrPixelGetBufSize` `ippiFilterBoxBorderGetBufferSize` `ippiFilterRoundGetBufSize32f_8u_C1R`
- FFT 系は **CAB-139 が pffft で実装済み** (FFT stub 残 0) — 本チケットでは未着手 (要件どおり)。

### 10-2. 引数順序の確認 (実装前・win 呼出実績)
`work/fill/callsite_dump.py` で各関数の呼出箇所 (直前 ≤160B + call) を逆アセンブルし引数スロットの型クラスと即値を確認: `ippiAddC_8u_C3IRSfs` (value=rcx/pSrcDst=rdx/step=r8d/roiSize=r8 値渡し/sfs=stk 即値 0, block00031 0x6c77b0)・`ippiAlphaCompC_8u_C3R` (alpha2=0xff 即値・**alphaType=0 即値**, 0x6c001b)・`ippsOrC_32u_I` (val=0xff000000 即値, 0x6c71b2)・`ippiFilterBoxBorderGetBufferSize` (dataType=1 即値) ほか全対象。B- (実績なし) の 5 関数は win 呼出箇所が存在しないため実績確認不可 → IPP 標準引数順のまま (エラーコード返却ゆえ順序依存は NULL 検査のみ)。

### 10-3. オラクル検証 (実 IPP DLL vs 自前実装, `work/fill/fill_oracle.c`)
再現: `gcc -O1 -I ../../src -o fill_oracle fill_oracle.c ../../ref/pe_load.c ../../shim/impl/ipp_*.c -lm && ./fill_oracle` (DLL は pe_load でネイティブ実行)。**25 関数中 22 関数が bit-exact + 状態コード一致** (ランダム + 境界ケース 約 2,000 ケース: 寸法 1..64、step 余滋、SIMD 境界 15/16/17/31/32/33、特殊値)。
- **全数グリッド**: `ippiAddC/SubC/MulC_8u_C3IRSfs` sfs -4..6 × val,src 全組合せ **720,896 ケース ×3 = 不一致 0** (丸めは 3 関数とも**偶数丸め** round-half-to-even — float+cvtps 系カーネルと整合)。`ippiAlphaPremul_8u_AC4IR` (v,a) 全組合せ **131,072 = 0** (`(v*a+127)/255`)。
- **ippiAlphaCompC**: alphaType 0..5 の 6 モード式を fit2/fit5 で特定し全数 grid **4,718,592 ケース中不一致 5,956 (0.13%)** — type 0 は融合有理式 `(255·s1·a1 + s2·a2·(255−a1))/65025` で **134/786k (0.017%)** まで (残りは実カーネルの float 中間丸め差。type 1..5 の残差は数式近似の限界)。FL の呼出実績は type=0 のみ。
- **ippiFilterBox_8u_C3IR/C4IR**: 出力 = `floor(窓和/面積)` (丸めなし, fit7 実測)、in-place は ROI + 左ハロを元値参照、**実 IPP quirk** (H == mh+1 かつ ay == mh-1 で縦ウィンドウが row0 に凍結, 3x3 は例外 — fit10/fit11 で発見・実装) を再現。mask≤5×5 全 anchor グリッド **C3IR 675 ケース不一致 0 / C4IR 6**。
- **ippsSqrt_32f_A21**: 実 IPP は IEEE sqrtf と **±1 ulp 差が 12.6%** (1,048,576 サンプル実測, maxulp=1, ほぼ対称) — A21 多項式の固有差で規格内。A11 と同じ扱い。
- **エラー格子 (image)**: NULL × サイズ 0 の **126 点すべて状態コード一致** (NULL→-8, サイズ→-6, 境界コピーは dstRoi < srcRoi+(top,left) で -6 を実測・再現)。
- **Init/Alloc/GetSize 10 関数**: 実 IPP は正常引数で 0 を返すが、**検収決定どおり ours は非 0 を返す**: NULL 出力 → -8 (実 DLL 観測と一致)、不正サイズ (tapsLen<1 / numBq<1) → -5 (arm64 dsp_ippv2 逆アセンブルで実測の IPP 挙動)、正常引数 → **-22** (実 DLL が Resize 系「未対応モード」で返すコード, probe 実測)。state/size は書き換えない (fail-fast)。

### 10-4. wasm 突合
`fill_oracle.c` を `emcc -DWASM_REPLAY` (wasm32) でビルドし、native 実行時に記録した全 **1,920 ケースの出力ハッシュ (FNV1a64) と wasm 実行結果を突合 → 不一致 0** (同一入力生成は決定論 RNG 再現)。これにより impl 35 関数の wasm32 挙動が native と bit 等価、かつ native オラクル経由で実 IPP parity を満たす。初回は halo 読みの隣接メモリ差で 7 ケース不一致 → halo 512→2048B に拡大して解消。

### 10-5. 既知差分 (残課題)
- `ippiFilterBox_8u_C*IR` の in-place: 実カーネルの内部読み順 (ROI 端・隣接行オーバーラップ分) を完全には再現できず、特定形状で最大 ~24%/ケースの画素差が残る (fit13 マップ: 200 構成中 156 が 2〜48 画素差)。一般的な blur 用途 (H≫mh) への実害は限定的。**win カーネル逆アサ (CPU dispatch 込み) による読み順完全再現**を残課題に。
- `ippiAlphaCompC` type 1..5: 数式フィットの残差 0.15% (type 0 は FL 実績どおり最優先で 0.017%)。

### 10-6. 残 stub (使用集合 239 中 166) と次タスク
上位: `ippiResizeSqrPixel_8u_C1R/C3R/C4R` (143 モジュール, 13 引数 + 補間 + pBuffer — `ippiResizeSqrPixelGetBufSize` がエラーコード返却のため lift 側は fail-fast になる) / `ippsThreshold_GT_32s_I`・`ippsSub_32f_I`・`ippsCopy_32s`・`ippsAtan_32f_A11` (125) / `ippsRealToCplx_32f`・`ippsCplxToReal_32fc` (61) / `ippsCopy_8u` (55) / `ippsZero_32s` (51)。次善: `ippiResizeSqrPixel` 群 (線形/NN 補間) と 125 モジュール群の 4 関数。
