# tools/ipp/shim — dsp_ippv2 ローダ shim + 署名 thunk 自動生成 (CAB-134)

> 正本: `tools/ipp/shim/REPORT.md`。
> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

再現: `bash tools/ipp/shim/shim_e2e.sh` (前提 `tools/ipp/ipp_e2e.sh` の成果が `work/` にあること。無ければ自動実行。前提ありで実測 21.3〜22.5 秒 (§15 参照・負荷依存)、exit 0 = **13 checks PASS** [CAB-262 で S13 追加])。検証起点 commit: `b8e762d` (HEAD, 自分の起点)。大物は `tools/ipp/work/shim/` (gitignore)。数値はすべて実測、推定は「推定」と明記。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 420 名の関数表 + ローダ | **完了**。`LoadLibraryW("…dsp_ippv2_x64.dll")` → `GetProcAddress(420 名)` を shimx 経由で 420/420 解決 (絶対パス・`legacy90` 接頭辞も可)。取得値は cookie (表要素のアドレス) |
| thunk | **128 件 (型付き thunk)** = 実装済み全部 (CAB-134 43 + CAB-139 FFT 14 + CAB-136 優先順上位 35 + CAB-245 7 + CAB-262 29)。残 **292 件は fail-soft stub** (eax=0 / xmm0=0 を返し、関数別カウンタと初回順を記録。STRICT モードで trap) |
| 署名 | **420/420 導出 (不明 0)**。確度 A 92 / B+ 129 / B- 199 (CAB-136/139 完了時点。§2 の導出監査時は A 43 / B+ 157 / B- 220 — 実装済み 92 関数は A に繰り上げ)。呼出箇所実績 (win 145 モジュール 19,018 箇所) との**型・個数の矛盾 0** |
| thunk 経路の回帰 | 既存オラクル **24 関数 × 216 ケース (5,184)** を「実 MS x64 呼出 → asm トランポリン → dispatch → thunk → 実装」で再実行し、**直呼び・既存 baseline (`work/cmp_avx512.json`) と全統計が完全一致、実 IPP に対し 21 関数 bit-exact** (通常/特殊値入力とも)。エラー格子 222 点一致。wasm (scalar/simd128) の golden 突合も同じ 21 bit-exact、FFT 48 ケース NRMS 32f 1.34e-7 / 64f 5.87e-16 (thunk 経由) |
| 「最大の統合リスク」(呼出規約の橋渡し) | **thunk 側は解消、lift 側との接点が残る** (§6): レジスタブロック契約を icall の memory-ABI と同一配置で定義し、`stk`(第 5 引数以降) ポインタ +0x48 の追加が **icall 側に 1 点必要** |
| 実装の穴 (重要) | 使用集合 239 のうち stub は **130 関数** (CAB-262 完了時点; 実装済 109)。残る上位は `ippsExp_32f_I` (50 モジュール)・`ippsSum_32f` / `ippsSin_64f_A50` / `ippsMulPack_32f` / `ippsConvert_32f24s_Sfs` / `ippsConvert_16s32f_Sfs` (49)・`ippsLn_32f_A11` (39)・`ippsLog10_32f_A11` (37) ほか (§13-7)。interp 7/6 のカーネルも残 (§14) |

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
| `verify_cab261_kernel.py` `test/verify_cab262_quirks.c` | **検収の独立再計算** (§13-8/§14-6): spike ログと数式モデルの突き合わせ (`work/resize/sw5.txt`・`sw7.txt` が必要・再生成コマンドは docstring) / quirk を実装を参照せず実 DLL だけで確認する probe |
| `count_fill3.py` | CAB-262 の stub 充填の独立再計算 (nm ベース・実装側) |

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

## 5. 検証 (`shim_e2e.sh` の 13 checks, 実測)

| # | 内容 | 結果 |
|---|---|---|
| S1 | 420 名の署名・thunk 件数 | 不明 0 / 型付き 43 / stub 377 |
| S2 | 呼出実績との矛盾 | **0** (agree 173 / weak 24 / nodata 223) |
| S3 | native 自己検査 (ABI プローブ 6・420 名解決・legacy90・LoadLibraryW 名 8 形・stub 全数を呼んで fail-soft/カウンタ/初回順) | 1,441 checks 失敗 0 (CAB-262 後の stub 292×2 実測。CAB-134 当初は 377 stub で 1,611) |
| S4/S5 | 実 DLL オラクル (AVX-512 経路) vs thunk、通常入力/特殊値入力: thunk 統計 = 直呼び統計 = 既存 baseline JSON、バッファ全語・状態コードの thunk-直呼び差 0 | 24 関数 5,184 ケース ×2 入力種、不一致 0 |
| S6 | thunk 経由でも実 IPP に bit-exact | **21 関数** (NaN 仮数ペイロード差は既存と同じ扱い・同じ件数) |
| S7 | NULL×len エラー格子 | 222 点、実 IPP との不一致 0 |
| S8 | wasm scalar / simd128 (150,523 / 193,502 B): golden を ABI ブロック経由 (JS 側で署名から MS ABI 配置を再現、上位 32bit ゴミ) | 21 bit-exact・fail 0、FFT 48 ケース NRMS 32f 1.34e-7 / 64f 5.87e-16、stub fail-soft |
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

### 10-6. 残 stub (使用集合 239 中 166 → CAB-245 で 159 → CAB-262 で **130**) と次タスク
CAB-136 時点の上位: `ippiResizeSqrPixel_8u_C1R/C3R/C4R` (143 モジュール) ほか。以下 CAB-245 §12 と CAB-262 §13 で実施。**CAB-262 後の残 stub 上位は §13-7**。


## 12. CAB-245 (IPP-5 ipp-fill-2): ResizeSqrPixel + GetBufSize 実測式 + 125 モジュール群 4 関数 (2026-10-10)

**結論**: 対象 7 関数 (+ GetBufSize 2 関数の実測式版) を実装し **typed thunk 92 → 99** (stub 328 → 321)。`shim_e2e.sh` は **12 checks PASS** (S10/S11 を新設)。オラクル (実 DLL vs 自前実装, **80,256 ケース**) で **status 格子全一致**・**GetBufSize 74,468 ケース完全一致**・信号 3 関数 **bit-exact** (Atan_32f_A11 は A11 規格内の許容差, §12-1)、Resize カーネルは **NN 0.000% / Cubic 0.027% / Linear 0.101% / Super 0.643% / Lanczos 6.913%** の画素差率 (実測、§12-5)。wasm replay **1,728 レコード mismatch=0** (可搬 sin / round により native と bit 一致)。実装は `impl/ipp_resize.c` + `impl/ipp_sig_fill2.c` (+ `impl/ipp_img_fill.c` から Resize 系 GetBufSize を移設)。

### 12-1. 実装関数
| 関数 | 内容 | 検証 |
|---|---|---|
| `ippiResizeSqrPixel_8u_C1R/C3R/C4R` | 13 引数 + interp {1,2,4,5,6,7,8,16} (5/6/7 は 4 と同一視, 6 のみ H-pass 重み回帰で一致確認) | NN bit-exact / Cubic 0.027% / Super・Lanczos §12-5 |
| `ippiResizeGetBufSize` | **実測式** (§12-3) | **74,468 ケース完全一致** (dw,dh ≤ 600 拡張ランダム含む) |
| `ippiResizeSqrPixelGetBufSize` | **常時 -8・書込なし** (実 DLL が `mov eax,-8; ret` のスタブ — 逆アセ + 4,000 ケース実測) | 完全一致 |
| `ippsThreshold_GT_32s_I` / `ippsSub_32f_I` / `ippsCopy_32s` | 信号 3 関数 | **bit-exact** (オラクル 160 ケース) |
| `ippsAtan_32f_A11` | atanf 版 | bit 差 59.8%, **maxulp 3728 = A11 規格内** (spec 2^-11 ≈ 8200 ulp @ π/4, CAB-141 暫定方針 — メイン暫定決定・ユーザ最終確認待ち) |

### 12-2. 座標系の確定 (B+/B- 引数順序の実装前確認 — callsite_dump.py / 逆アセ)
- 13 引数の ABI 配置は署名どおり (rcx=pSrc, rdx=srcSize 値渡し, r8=srcStep, r9=srcRoi 16B 構造体ポインタ, stk0..8)。win FLEngine 呼出実績 3 箇所で確認。
- **FL は `ippiResizeGetBufSize`(5 引数) → malloc → `ippiResizeSqrPixel_*R` の順で呼ぶ** (block00031 0x6c0bda/0x6c0c80 実測) — lift 側の fail-fast は GetBufSize 実測式実装により解消。
- **座標系 (実測で確定)**: `u = (x_abs + 0.5 − xShift)/xFactor − srcRoi.x` (x_abs = dst 絶対座標)。書込条件は `0 ≤ u ≤ srcRoi.w` かつ v 同様 — **範囲外の dst は未書込のまま** (probe5/6 実測)。書込可能画素が 1 つも無ければ status 1 で無操作。タップは **ROI 相対 index で画像絶対座標をフェッチ** (画像範囲でクランプ, ROI 外の隣接画素も読む — CAB-136 FilterBox と同様)。
- 位相パイプライン: **NN index は Q16 固定小数点** (`inv16 = trunc(65536/fx)`, `idx = (u16−1)>>16`) — double だと fx=0.7/0.9 で index が ±1 ずれるを実測。重み位相は double (§12-5)。
- エラー格子 (52 ケース × 4 interp): NULL→-8 / 寸法<1→-6 / interp 無効→-22 / factor≤0・Super+拡大→-23 — **全一致**。

### 12-3. ippiResizeGetBufSize 実測式 (受入条件)
密グリッド (dw ≤ 96 × dh ≤ 48 × ch ∈ {1,3,4} × interp 5 種 = 34,560 点) でフィットし、**拡張ランダム dw,dh,sw,sh ≤ 600 (40,000 点) で完全一致** を確認。b = ブロック数。
- NN(1): `144 + 64·(c16(dw)−1) + 64·(c16(dh)−1)` (ch 非依存), c16(x)=⌈x/16⌉
- Linear(2): `1168 + 64·(16·⌊(bw−1)/4⌋ + [0,1,6,7][(bw−1)%4]) + 64·(8·⌊(bh−1)/4⌋ + (bh−1)%4) + (ch−1)·256·(2+⌊(dw−1)/32⌋)`, bw=c16(dw), bh=c16(dh) — 初期の二次式フィットは dw>96 で破綻 (4 ブロック周期の線形が正, dense2 実測)
- Cubic(4): `2448 + 64·(20·⌊(bw8−1)/4⌋ + [0,2,9,11][(bw8−1)%4]) + 64·(12·⌊(bh8−1)/4⌋ + [0,2,5,7][(bh8−1)%4]) + (ch−1)·256·(4+⌊(dw−1)/16⌋)`, bw8=c8(dw)
- Super(8): `16 + 128·ch·c16(sw)` (srcRoi 幅のみ依存, dst 非依存)
- Lanczos(16): `2704 + 64·(28·⌊(bl−1)/6⌋ + [0,4,8,13,17,21][(bl−1)%6]) + 64·(16·⌊blh−1)/6⌋ + [0,2,4,7,9,11][(blh−1)%6]) + (ch−1)·128·(bl+5)`, bl は 5/5/6px ブロック番号
- ch=2 → **-53** (実測), dstRoi 寸法 < 1 → **-6** (実測; CAB-136 時の -5 仮定を修正)

### 12-4. 補間カーネル (実測フィット)
- **Cubic**: 4-tap `f(d)=0.5d³−d²−0.5d+1 (d≤1)`, `f(d)=−(1/6)(d−1)(d−2)(d−3) (1<d≤2)` — 全位相で partition of unity (fit13)。スパイク+回帰で A=−0.5 Keys ではないことを確認 (負ローブの分布が異なる)。
- **Super**: 面積平均。footprint `[start, start+1/fx)`, `start=(x−sx)/fx`。**ROI 外の面積は最近接エッジ画素へ fold してから総面積で正規化** (spike 重み表 fx=0.3/0.5/0.75 × sx 4 種と全一致)。
- **interp 5/6/7** (`CUBIC2P_*` 系と推定): ~~H-pass 重み回帰で 6 のみ cubic と一致~~ **[CAB-274 で訂正: 誤り。it=6 の H-pass 重みも cubic とは不一致 (d=0.25 で 221 vs 209、最大 12/255)。回帰が「一致」としたのは近似の分解能不足]**。5/6/7 はすべて Mitchell-Netravalli (B,C) カーネル (§15-1) — **CAB-274 で完全再現**。

### 12-5. 残差 (許容差の根拠 — 受入条件の「bit-exact または許容差」)
オラクル 74,456 resize ケース (591 万画素) の画素差率: **NN 0.000% / Cubic 0.027% / Linear 0.101% / Super 0.643% / Lanczos 6.913%**。差分は **|d|≤1 の丸め境界差** (Lanczos big8=16/72.9 万 = 0.002%)。
- 原因: 実 DLL は重みを内部固定小数点経路で算出し、`255·w` が厳密に 0.5 に乗る位相 (±0.006 帯域) で +1/−1 が手計算と逆になる (spike 313 ペアで分離検証 — fit15〜21)。例: a=1/6 で (213,42) vs (213,43)。
- 影響は ±1/画素のみ (NN/Cubic はこの帯域をほぼ回避) — リサイズ用途の実害は限定的。完全一致は DLL の重み算出経路 (Q16 逆算+独自丸め) の解明が前提で **IPP-6 (候補) へ**。
- wasm 差異: libm sin と lround のプラットフォーム差を可搬実装 (テイラー 11 項の sin_pi + round-half-up) で排除 → **wasm replay mismatch=0**。

### 12-6. 更新物
- `impl/ipp_resize.c` (新規 351 行) / `impl/ipp_sig_fill2.c` (新規 47 行) / `impl/ipp_img_fill.c` (Resize 系 GetBufSize を移設) / `test/resize_oracle.c` + `test/resize_oracle_run.sh` (新規, オラクルハーネス) / `shim_e2e.sh` (S10/S11 追加) / `shim_check.py` / `test/ipp_shim_wasm.mjs` (stub 抽出サンプルを WARP 系へ — ResizeSqrPixel が型付き化したため)
- 検証ハーネスの開発過程物 (probe1〜10, fit1〜21, callsite 解析) は `work/resize/` (gitignore)

## 13. CAB-262 (IPP-7 ipp-fill-3): 残 stub 次層 29 関数の静的優先順充填 (2026-10-11)

**結論**: win 呼出モジュール数降順の上位 **29 関数** (すべて使用集合 239 内) を実装し **typed thunk 99 → 128** (stub 321 → 292)。`shim_e2e.sh` は **13 checks PASS** (S13 を新設、S1〜S11 維持)。オラクル (実 DLL vs 自前実装, **727 ケース / 297 ハッシュレコード**) で **status 不一致 0** (データ + エラー格子の 61 検証エントリすべて)・wasm replay **297 レコード mismatch=0**。実装は `impl/ipp_sig_fill3.c` のみ (契約どおり `gen_shim.py` が自動 thunk 化)。**オラクルでデータ比較したのは 29 関数のうち 28 関数** (`ippsCplxToReal_32fc` は未比較) で、そのうち **27 関数が byte 単位で bit-exact**、`ippsWinKaiser_32f_I` は許容差 (max abs err 2.444e-06)、`ippsVectorSlope_64f` は 9 ケース中 7 ケースが不一致 (§13-5)。検収の独立再計算は §13-8。

### 13-1. 実装関数と優先順根拠 (独立再計算: `python3 shim/count_fill3.py`)
win_modules 降順 (data/ipp_matrix.csv)。全 29 関数が used239=True。

| win_modules | 関数 | 内容 | 検証 |
|---|---|---|---|
| 61 | `ippsRealToCplx_32f` | re/im interleave | **bit-exact** (格子 32 点も全一致。dst NULL 優先・len 次・片方 src NULL は書込のみ — §13-3) |
| 61 | `ippsCplxToReal_32fc` | re/im split | **bit-exact** |
| 55 | `ippsCopy_8u` | memcpy | **bit-exact** (エラー格子 10 点一致) |
| 51 | `ippsZero_32s` | 0 充填 | **bit-exact** |
| 50 | `ippsMinMax_32f` | min/max | **bit-exact** |
| 50 | `ippsConvert_16s32f` | (int16)→(float) 変換 | **bit-exact** |
| 49 | `ippsWinKaiser_32f_I` | Kaiser 窓 | **max abs err 2.4e-06** (140 (len,alpha) 組合せ、式は §13-2) |
| 49 | `ippsVectorSlope_64f` | 直線生成 | **±1 ULP** (§13-5 未解決) |
| 49 | `ippsThreshold_LT_64f_I` | 閾値 | **bit-exact** |
| 49 | `ippsMinMax_16s` | min/max | **bit-exact** |
| 49 | `ippsInterleave_32f` / `_16s` | channel interleave | **bit-exact** (nch 1..4) |
| 49 | `ippsDeinterleave_32f` / `_16s` | channel deinterleave | **bit-exact** (nch 2..4) |
| 38 | `ippsRound_32f` | round-half-away | **bit-exact** (§13-3 丸め規則) |
| 38 | `ippsPowerSpectr_32fc` | re²+im² | **bit-exact** |
| 38 | `ippsMin_16s` / `ippsMax_16s` | 単極 min/max | **bit-exact** |
| 38 | `ippsCopy_64s` | memcpy | **bit-exact** |
| 38 | `ippsAddProductC_32f` | dst += val·src | **bit-exact** (§13-3 double 精度) |
| 37 | `ippsThreshold_LT_32s_I` | 閾値 | **bit-exact** |
| 36 | `ippsSwapBytes_32u_I` | byte swap | **bit-exact** |
| 33 | `ippsFlip_32f_I` / `ippsFlip_16u_I` | 要素反転 | **bit-exact** |
| 30 | `ippsSwapBytes_16u_I` | byte swap | **bit-exact** |
| 27 | `ippsZero_64s` | 0 充填 | **bit-exact** |
| 26 | `ippsAbs_32f` | 絶対値 | **bit-exact** |
| 25 | `ippsSet_64f` | 定数充填 | **bit-exact** |
| 24 | `ippsThreshold_LTValGTVal_32f_I` | 双閾値 | **bit-exact** |

### 13-2. `ippsWinKaiser_32f_I` の実測式 (kaiser_fit.py / probe_u,probe_kap3,kap4)
実測 (n, alpha) 全組合せ 140 点のフィット:
- `beta = alpha·(len−1)/2`、`r_i = 2i/(len−1) − 1`、`w[i] = I0(beta·√(1−r²)) / I0(beta)`
- **I0 は級数 60 項** (beta=37.5 まで必要。24 項だと beta=30 で最大 2.6e-04・beta≈37.5 で最大 6.5e-03 の誤差 — 検収実測 `test/verify_cab262_quirks.c`)
- **beta ≥ 38 では実 DLL が -39 を返し書込しない** (probe_kap3/kap4 で境界を実測: beta=38.0 は -39、37.975 は 0。検収が N=256 で 0.00005 刻みに細分: beta=37.995 は 0・38.001 は -39)
- 典型値: len=16, alpha=2 → w[0]=2.944e-06, w[15]=0.9683 (実測と max abs err 2.4e-06)
- self-check: `t ≤ 0` のとき `I0(0)/I0(beta)` を書く (0 ではなく — probe_kap5 で発見)

### 13-3. エラー格子で確定した quirk (オラクル error grid、23 エントリ・254 点すべて一致)
- **`ippsRealToCplx_32f`**: dst NULL → -8 が**最優先**、次に len<1 → -6。len≥1 では re/im の**片方 NULL はエラーにならず**その成分だけ書込 (書けない側は 0 充填)、両方 NULL のときだけ -8 (probe_q/r2c 実測)。
- **`ippsAddProductC_32f`**: IPP は **double で乗算・加算してから float に丸める** (= `fmaf(val,src,dst)`)。float のままだと 1 ULP 差 (apcz fit で全 8 ケース確認。検収が 180 組合せで「モデル A (float 2 段丸め) と B (double 1 段丸め) が不一致になる 7 組合せ」を抽出 → DLL は **7/7 で B に一致**)
- **`ippsRound_32f`**: round-half-**away**-from-zero。±0 は符号保存。`|結果| ≥ 2^31` では入力をそのまま返す (float はその域で全て整数値)。
- **Interleave/Deinterleave**: nCh<1 → **-53** (ptr 検査より先)、pSrc NULL → -8、len<1 → -6、pDst NULL → -8。

### 13-4. 検証 (S13, 実測)
```
SUM {"fns":61,"cases":727,"st_mis":0,"case_diff":7,"byte_diff":4757}
dump records=297
wasm replay: records=297 mismatch=0 -> PASS
```
- 61 = 検証エントリ数 (**データ比較 38** エントリ + **エラー格子 23** エントリ)。データ比較 38 = case_diff 比較 37 行 + WinKaiser 許容差 1 行 (うち reorder 系 14 行は nch 別)。エラー格子 23 エントリ = 254 点。ケース数 727 = データ 473 + エラー格子 254。`st_mis=0` が status 不一致 0。`case_diff=7` は §13-5 の VectorSlope_64f の 7 ケース。
- 再現: `bash shim/test/fill3_oracle_run.sh` (native + wasm replay)
- 独立再計算: `python3 shim/count_fill3.py` (nm で実装シンボルを直接数えて data/ipp_sigs.json の impl 集合と照合、差 0 を assert)

### 13-5. 未解決 (起票先付き)
> **更新 (IPP-9 #276)**: 下表の VectorSlope_64f/_32f の bit 不一致は、出力先が揃った場合について解消した (算法・検証・残課題は `shim/REPORT_IPP9.md`)。出力先が揃わない場合も IPP-11 #473 で解消した (`shim/REPORT_IPP11.md`)。以下は #263 時点の記録として残す。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ippsVectorSlope_64f` が実 DLL と bit 不一致 (オラクル 9 ケース L={1,2,3,7,16,17,33,1000,4097} の計 **5,176 要素中 4,757 要素 = 91.9%**。ULP 距離は大半が 1〜数 ULP だが n=4097 では最大 52 ULP、最大絶対差 5.912e-12・最大相対差 5.77e-15 を検収が実測。実装は `offset + (double)i*slope` の 1 行)。実 DLL は SIMD ブロック累積経路で値を生成していると推定されるが、block8/16/32 × mul/fma × 直接積の 14 通り (work/fill7/vs*.c, vs4.txt) および増分累積 (検収の B=1..64 総当たり) を試しても n=7 は一致するが n>=16 で不一致。`ippsVectorSlope_32f` も同種で bit 再現未解決 (REPORT §4)。 | 64f の厳密 bit 一致。相対 1e-15 帯で絶対値は 1e-12 以下、FL の呼出は 49 モジュールだが音階生成用途のため実害は限定的 (推定)。 | 本チケット §13-5 に記録。win カーネル逆アセ (CPU dispatch 込み) で解明する子チケットを提案 |

### 13-6. ネガティブコントロール (規則 41)
`impl/ipp_sig_fill3.c` の `ippsAddProductC_32f` の `+1.0` を 1 行追加 → オラクルが検出:
```
(破壊前) SUM {"fns":61,"cases":727,"st_mis":0,"case_diff":7,"byte_diff":4757}
(+1.0)  SUM {"fns":61,"cases":727,"st_mis":0,"case_diff":16,"byte_diff":9933}
```
→ case_diff 7→16, byte_diff 4757→9933 で FAIL を確認 (オラクルが実効的)。

### 13-7. 残 stub (使用集合 239 中 130) と次タスク
上位: `ippsExp_32f_I` (50)・`ippsSum_32f` (49)・`ippsSin_64f_A50` (49)・`ippsMulPack_32f` (49)・`ippsConvert_32f24s_Sfs` (49)・`ippsConvert_16s32f_Sfs` (49)・`ippsLn_32f_A11` (39)・`ippsLog10_32f_A11` (37)。`ippsSin_64f_A50` は実 DLL 自体が Segv するため要調査 (probe_k で n=1 でも Segv を実測)。

| S13 | CAB-262 オラクル (実 DLL vs 自前実装, native + wasm replay): 次層 29 関数のデータ + エラー格子 61 関数分 | **727 ケース status 不一致 0**、wasm replay **297 レコード mismatch=0** (§13) |

## 14. CAB-261 (IPP-6): interp 5/7 (CUBIC2P 系) カーネル再現 — it5 は 3 次 B-スプラインで解決、it7 は spike 行列を記録 (2026-10-11)

**結論 (部分達成)**: it=5 のカーネルを**3 次 B-スプライン**と特定し実装 → オラクルの画素差率 **14.541% → 0.021%** (受入条件「1% 未満」を達成、pxdiff 109,741 → 159 画素)。it=7 は 1D 重みを位相 64 点で完全に抽出し**対称 3 タップ核**であることを実測確定したが、closed form のフィットは近似誤差 1e-2 に留まり未確定 (後続チケットへ)。it=6 は従来の cubic 代用のまま (9.768%、§12-4)。`shim_e2e.sh` は **13 checks PASS 維持**、wasm replay **1,728 レコード mismatch=0**。

### 14-1. スパイク法による重み抽出 (test/sp57.c + test/sweep2.c)
src の 1 バイトだけ 255・他 0 → `dst = 255·w_k(x)` (整数) を得る。it=4/5/6/7 × fx ∈ {2,1.5,1.25,1,0.75,0.5,0.3,0.25} × sx ∈ {0,±0.25,±0.5,±0.75,1} で H/V 分離採取 (`work/resize/sp57.log`、8,192 レコード)。位相 64 点のスイープは `test/sweep2.c` (`work/resize/sw4..sw7.txt`)。

### 14-2. it=5 = 3 次 B-スプライン (確定・実装済)
- `u = (x + 0.5 − xShift)/xFactor − srcRoi.x − 0.5` (px)、4 タップ窓 `[⌊px⌋−1, ⌊px⌋+2]`
- `w_t = bspl3(px − (base+t))`、**和で正規化** (分離路の `clamp_u8` は round-half-up で 0..255)
- `bspl3(d) = 2/3 − d² + d³/2 (|d|<1)`、`(2−|d|)³/6 (1≤|d|<2)`、`0 (|d|≥2)`
- 1D spike で **64/64 位相が完全一致** (ゲイン 255·5/6 = 212.5 を掛けた整数比較)
- 残差は `px` が**半整数**のときの ±1 丸め差のみ (REPORT §12-5 の `255·w` が 0.5 に乗る帯域と同根)

### 14-3. it=7 の抽出結果 (closed form 未確定・後続へ)
dst_x=6, taps by src k の**未正規化**重み (|d|=px からの距離):

| d | 0 | 0.125 | 0.25 | 0.375 | 0.5 | 0.625 | 0.75 | 0.875 | 1.0 | 1.125 | 1.25 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| w | 195 | 189 | 173 | 151 | 123 | 94 | 65 | 39 | 19 | 6 | 0 |

- 完全に対称 (`w(d)=w(−d)`)、サポートは `|d| ≤ 1.2031`、3 タップ窓
- 正規化ピーク: 0.8369, 0.8077, 0.7269, 0.6163, 0.5 (d=0..0.5)
- `(1−d²/R²)^p` 系の最適フィットでも近似誤差 ~9.5e-3 (R=1.799, p=6.42) → closed form 不一致
- 3 次多項式 (|d| の) では maxerr 2.0 → bit 再現に届かず

### 14-3b. ネガティブコントロール (規則 41)
it=5 の 4 タップ正規化重みの `w[0] += 0.02; w[3] -= 0.02` (1 行) を追加 → オラクルが検出:
```
(破壊前) it5: px=754704 pxdiff=159   (0.021%) big8=134   SUM byte_diff=220396
(+0.02)  it5: px=754704 pxdiff=91175 (12.081%) big8=135  SUM byte_diff=311412
```
→ pxdiff 159 → 91,175 で FAIL を確認 (bspl3 カーネルが実効的)。

### 14-4. 未解決 (起票先付き)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| it=7 (`CUBIC2P_*` 系) の closed form が未確定。1D 重みは完全抽出済み (spike 行列 `work/resize/sw7.txt`・上表) なので、数表 (33 エントリ × 線形補間 or Q16 テーブル) での実装が可能。 | it7 の画素差 13.169% (big8 44,279) が残る。FL の呼出は work/resize の fuzz で it7 を含む。 | 本チケットに記録。子チケット「IPP-8: interp 7 数表実装」を提案 ( spike → テーブル → wasm replay まで) |
| it=6 も cubic 代用のまま (9.768%)。H-pass 重み回帰は cubic と一致 (§12-4) なので V-pass または丸め経路の差と推定。 | it6 の画素差。 | 同チケットで対応 |
| it=5 の残差 159 画素 (0.021%) は `px` 半整数の ±1 丸め差。IPP の内部固定小数点重み算出経路 (Q16 + 独自丸め) の解明が前提。 | 厳密 bit-exact。実害は ±1/画素。 | REPORT §12-5 に統合 (CAB-261 の完了条件「1% 未満」は達成) |

### 14-5. 更新物
- `impl/ipp_resize.c`: `ker_bspl3` + `mode 35` (interp_base(5)=35、`interp_base(6/7)=4` は従来どおり)
- `test/sp57.c` (新規, スパイク採取) / `test/sweep2.c` (新規, 位相スイープ)
- `shim/REPORT.md` 本节。spike 行列・フィット過程物は `work/resize/` (gitignore)

### 14-6. 検収の独立再計算 (2026-10-11 検収 subagent・別アルゴリズム)

実装 (impl) を一切リンクせず、実 DLL の spike ログ (`work/resize/sw5.txt`・`sw7.txt`) と数式モデルを突き合わせた。再現: `python3 shim/verify_cab261_kernel.py` (ログは `./work/resize/sweep2 <it> > work/resize/sw<it>.txt` で再生成可)。

| 検算した数値 | 独立再計算 | 結果 |
|---|---|---|
| it=5 = 3 次 B-スプライン・64/64 位相一致 | `sw5.txt` の位相 64 点 × 4 タップを `px = (dst_x + 0.5 − sx) − srcRoi.x − 0.5`、`w_t = bspl3(px − k)`、`round(255·(5/6)·w_t)` と比較 | **256 点不一致 0** → §14-2 の「64/64 位相」「ゲイン 255·5/6=212.5」を確認 |
| it=7 の未正規化重み 195,189,173,151,123,94,65,39,19,6,0 | `sw7.txt` の dst_x=6・位相 0,8,16,…,56 のタップ値から距離 d=0,0.125,…,1.125 の重みを抽出 | 表と**全数一致**。正規化ピーク 195/233=0.8369・189/234=0.8077・173/238=0.7269・151/245=0.6163・123/246=0.5 も一致。サポート: 位相 13 の tap4 (距離 1.203125) が最後の非ゼロ → **|d| ≤ 1.2031** を確認 |
| closed form 不確定 | 11 点の表に対して `(1−d²/R²)^p` と 3 次多項式を min-max / 最小二乗で当てる | min-max 最適 (R=1.483, p=3.81) でも max err **8.9e-03**、3 次多項式で 6.3e-03 (=255 換算 ~1.6)。closed form での bit 再現不可を確認 (最適パラメータは当時の fit とは異なるが誤差の位数は一致) |
| 14.541% → 0.021% | `work/negc261/` のコピーで `interp_base(5)` を 35 → 4 (bspl3 を cubic に戻す) にしてオラクル再実行 | `it5: px=754704 pxdiff=109741 (14.541%)` を**再現**。SUM も `byte_diff=329978` (破壊前 220396)。§14-3b の `w[0] += 0.02; w[3] -= 0.02` についても同じ方法で `pxdiff=91175 (12.081%)`・`byte_diff=311412` を再現 |
## 15. CAB-274 (IPP-8): interp 6/7 カーネル特定と実装 — it7 13.169%→0.005% / it6 9.768%→0.000% (2026-10-11)

**結論**: it=7・it=6 のカーネルを **Mitchell-Netravalli 2 パラメータ三次カーネル** (CUBIC2P) と特定し closed form で実装。オラクル画素差率 **it7 13.169% → 0.005%** (受入 <1% 達成)、**it6 9.768% → 0.000% (bit-exact)**。it=5 = 0.021% 不変、it=4 = 0.027% 不変。`shim_e2e.sh` 13 checks PASS、wasm replay **1,728 records mismatch=0**。

検証起点 commit: `2f8e79c` (feat 本体) / `23aa4be` (本注記)。クリーン HEAD 検証 (規則 45): `git archive HEAD -- tools/ipp` を `work/verify_head/` に展開し、`work/` の gitignore データ (spike ログ・golden・baseline) をコピーして同一 e2e を再現。5b の `tools/shimx` 参照のみ symlink)。`bash shim/shim_e2e.sh` 実測 **21.3〜22.5 秒** (n=3: 21.29 / 22.47 / 22.11 秒。負荷依存値: load average 開始 3.22〜3.44、3 本目直後の uptime = 3.44 / 2.87 / 2.59。nproc=16・他セッションと共有)。クリーン HEAD 再実行結果: **13 checks PASS / SUM 同一 (px_diff=55588, cases=82056) / wasm replay 1,728 records mismatch=0**。

### 15-1. カーネル特定 (1D spike + 2D インパルス応答の2系統で確定)

| interp | カーネル | 同定根拠 |
|---|---|---|
| it=4 | `0.5d³−d²−0.5d+1` (線形項付き cubic、MN ではない) | 従来実装のまま (0.027%) |
| it=5 | MN(B=1, C=0) = 3次 B-スプライン | CAB-261 で確定 (§14-2) |
| it=6 | **MN(B=0, C=0.5)** = Catmull-Rom | 1D spike `sw6.txt` の 13 点と MN 予測が **diff 0** |
| it=7 | **MN(B=0.5, C=0.3)** = CUBIC2P_B05C03 | 1D spike `sw7.txt` の 19 点と MN 予測が **diff 0** |

- 2D インパルス応答 (`work/resize/ksw4..7.txt`、1 画素スパイクの 3x3 応答、シフト 1/64 刻み 64 点) から (B,C) を
  最小二乗フィット (別アルゴリズム): it=5 → (1.000, −0.002)、it=6 → (0.000, 0.504)、it=7 → (0.502, 0.300)。
  採用した closed form の 3x3 応答予測は **it6/it7 で 576 点中不一致 0** (負ローブは最終 clamp で 0 — 分離モデル+clamp で完全一致)。
- 数表 (Q16/float 33 エントリ) は不要になった (closed form が同一)。ticket の「数表実装」要件は closed form で充足。
- MN は partition of unity (窓の重み和 = 1、任意位相) → **per-pixel 正規化不要**。flat image (128/200/255) の
  through を実測で確認 (probe274/flat2.c: 全 interp で入力値一致)。

### 15-2. it=6 の 9.768% 原因特定 (ticket 要件2: V-pass spike)

`work/resize/sweepv.c 6 > swv6.txt` で垂直 1D spike を採取 → **H-pass (`sw6.txt`) と V-pass は同一カーネル (13 点不一致 0)**。
したがって背景の推定「H-pass 回帰一致なので V-pass/丸め差」は**誤り**で、原因は **カーネル自体の差**:

| d | 0 | 0.125 | 0.25 | 0.375 | 0.5 | 0.625 | 0.75 | 0.875 | 1.0 |
|---|---|---|---|---|---|---|---|---|---|
| it=6 spike | 255 | 246 | 221 | 186 | 143 | 99 | 58 | 23 | 0 |
| cubic (=旧実装) | 255 | 235 | 209 | 178 | 143 | 107 | 70 | 34 | 0 |
| 差 | 0 | +11 | +12 | +8 | 0 | −8 | −12 | −11 | 0 |

重み差 8〜12/255 が画素差 9.768% (76,293 px) に拡大。MN(0,0.5) 実装後は **0 px (bit-exact)**。

### 15-3. オラクル結果 (native + wasm replay)

| interp | 変更前 pxdiff | 変更後 pxdiff | 変更前% | 変更後% |
|---|---|---|---|---|
| it=4 | 233 | 233 | 0.027% | 0.027% (不変) |
| it=5 | 159 | 159 | 0.021% | 0.021% (不変) |
| it=6 | 76,293 | **0** | 9.768% | **0.000%** |
| it=7 | 88,546 | **31** | 13.169% | **0.005%** |
| it=8 / it=16 | 4,004 / 50,390 | 同左 | 0.643% / 6.913% | 不変 (対象外) |

- 定義: pxdiff = native 実 DLL と自前実装の出力が異なる dst バイト数、px 分母 = 当該 interp の比較总バイト数
  (oracle.log の `it<n>: px=.. pxdiff=..`) 。wasm replay 1,728 records mismatch=0。
- it=7 の残差 31 px は all |d|=1 (丸め差)。it=6 は完全一致。

### 15-4. GetBufSize の it=5/6/7 (副作用修正)

実 DLL は **it=5/6/7 のバッファサイズが cubic (4) と同一** (work/resize/gbs.log: interp 別 96 ケースずつ全 CUBIC 一致)。
旧実装は it=5 が mode 35 で Lanczos 式に落ちており**不一致だった** (潜在バグ: 過大サイズ)。本章で 5/6/7 → 4 に修正し、
オラクルの GetBufSize 族に it=5/6/7 (dw 1..96/dh 1..48/ch∈{1,3,4} = 1,800 ケース) を追加して **mismatch=0** を確認。

### 15-5. ネガティブコントロール (規則 41)

`work/negc274/` と `work/negc274b/` のコピーに1行だけ破壊を入れ、オラクルを再実行:

| 破壊 | it6 pxdiff | it7 pxdiff |
|---|---|---|
| 破壊前 | 0 (0.000%) | 31 (0.005%) |
| it=7 の B を 0.5 → 0.52 | 0 (不変) | **37,037 (5.509%)** |
| it=6 の C を 0.5 → 0.54 | **51,445 (6.587%)** | 31 (不変) |

→ 両カーネルが実効的であることを数値で確認 (壊すと FAIL、触らない方は不変)。

### 15-6. 独立再計算 (規則 37)・検証範囲外

`python3 shim/verify_cab274_kernel.py` (impl 非リンク・別アルゴリズム):
1D spike 予測 (it4/5/6/7) 不一致 0、2D インパルスからの (B,C) フィット、3x3 応答予測 576/576、
V==H (it=6)、cubic との差の定量化、GetBufSize 実測。

- **検証範囲外**: 他 interp (NN/linear/Super/Lanczos) のカーネル変更は行っていない。wasm は replay (ネイティブ出力との
  ハッシュ一致) のみで、wasm 側の単独テストはしていない。it=7 の残差 31 px の原因 (丸め経路) は未追跡 (it=5 と同種の ±1)。
- **未解決**: it=4 のカーネルが MN でない理由 (線形項付き) は未解明 — 影響なし (0.027%) で起票先なし (既存許容差)。
  GetBufSize の it=5/6/7 旧値 (Lanczos 式) を踏んでいた呼出元はなし (FL は ResizeSqrPixel 使用・§12-3)。
- **環境前提**: Emscripten (`[EMSDK]`・emcc)、実 DLL は `docs/REFERENCES.md` `[WIN64]` の `extracted/block24356_PE.bin` (pe_load が直接読む)、
  `tools/ipp/work/` の gitignore データ (golden・win_refs・baseline・spike ログ — `tools/ipp/ipp_e2e.sh` が生成)。
  TMPDIR は未指定 (ネイティブ gcc/emcc は小物のみ)。/tmp は tmpfs 3.7GB だが本節の産物はすべて `work/` (実ディスク)。
- **独立再計算の実行出力** (`python3 shim/verify_cab274_kernel.py`、impl 非リンク):
```
[1] 1D spike 予測 (S(d) = round(255*(K(1)+K(0))*K(d)), 負値 clamp)
   it=4 (ker_cubic(impl)): 15 点中 不一致 0 (最大 |diff| = 0) -> 一致
   it=5 (MN): 25 点中 不一致 0 (最大 |diff| = 0) -> 一致
   it=6 (MN): 15 点中 不一致 0 (最大 |diff| = 0) -> 一致
   it=7 (MN): 19 点中 不一致 0 (最大 |diff| = 0) -> 一致
[2] 2D インパルス応答からの (B,C) 最小二乗フィット (別アルゴリズム)
   it=5: fit B=1.000 C=-0.002 (rms=0.00159 max=0.00516 n=65)
   it=6: fit B=0.000 C=0.504 (rms=0.00274 max=0.01438 n=60)
   it=7: fit B=0.502 C=0.300 (rms=0.00209 max=0.00678 n=65)
[3] 2D インパルス応答 3x3 予測 (MN + 負値 clamp、分離モデル)
   it=6: 576 点中 不一致 0 (最大 |diff| = 0) -> 一致
   it=7: 576 点中 不一致 0 (最大 |diff| = 0) -> 一致
[4] it=6 の V-pass (swv6) vs H-pass (sw6)、cubic (it=4) との差: 不一致 0 点
[5] GetBufSize 実測 (gbs.log): it4/5/6/7 各 96 ケースすべて CUBIC 一致
```
- **並行セッション** (規則 46): 本セッション中に CAB-261/262 検収の別セッションが tools/ipp に staged WIP を持っていた。
  本コミットは一時インデックス (GIT_INDEX_FILE) で**自分のファイルのみ**を commit して巻き込みを防止した。
  ただし main の lost-commit recovery (reset) でその staged WIP は失われ、ファイル実体のみディスクに残存
  (`shim/impl/ipp_sig_fill3.c` 変更分・`shim/verify_cab261_kernel.py`・`shim/test/verify_cab262_quirks.c`)。
  shim/REPORT.md の §13-8/§14-6 加筆分はダングリング blob の可能性 (`git fsck --lost-found`)。

### 15-7. 更新物

- `shim/impl/ipp_resize.c`: `ker_mn(d,B,C)` 追加、`interp_base` で it=6→36 / it=7→37 のモード、GetBufSize の 5/6/7→4 修正
- `shim/test/resize_oracle.c`: GetBufSize 族に it=5/6/7 (1,800 ケース) を追加
- `shim/verify_cab274_kernel.py` (新規, 独立再計算)、`work/resize/probe274/` (flat/spk2d/imp2d/ksweep/gbs probe)
- spike ログ `work/resize/swv6.txt` (it=6 V-pass)、`ksw{4,5,6,7}.txt` (2D インパルス) は gitignore (再生成コマンドはスクリプト docstring)

> 注 (#3830): 本節と下の付録が書く「`$ANALYSIS_DIR` → VM 既定値」の fallback 連鎖は古い。現在は `FL_WIN64_DIR` を優先し、`fl_dll_path.h` は既定値を持たず未設定なら exit 2 (`tools/ipp/REPORT.md` §12)。

## 環境パス置換 (#364, 親 #294): 外部資産パスを tools/shared の env 定義へ

- `/home/ubuntu` 絶対パス 10 行を `FL_WIN64_DIR` (`docs/REFERENCES.md` `[WIN64]`) 経由に置換。既定値は従来と同一で、env 未設定の直接起動も従来どおり動く。
- 変更表・検証 (env なし直接起動 / 明示引数 / AVX-512 有無の実測)・未解決: [`REPORT_APPENDIX_364.md`](REPORT_APPENDIX_364.md) (本体から分割移動した全文)。
