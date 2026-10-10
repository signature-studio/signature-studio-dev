# KH-4: KH 共通基盤 lift (CAB-246) — 分類 / 112 関数 lift / D15 [icall] / 数学 lib powf

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/snapins/` (大物は `work/`, gitignore)
- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (既存 10 本 + **khbase** + Path A 対照 + libm 単体。キャッシュ有り 2〜3 分)
- Linear: CAB-246 (parent CAB-53, milestone アプリケーション完成)。計画段の CAB-56 ([KH-4] parent CAB-13) と関連付け — SnapinMasterDsp ホストハーネス構築は CAB-56 側のスコープとして残置

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 共通基盤の分類 | 事前解析の infra 188 関数 (≥8 snap-in が DSP root から到達, 53,010B) を実測分類: **(a) process 経路で到達 135 関数 / 34,373B (lift 対象)**、(b) Editor/Controller root のみ到達 21 / 4,898B、(c) 未到達 32 / 13,739B (残り 32 snap-in の lift 時に到達見込み)。判定根拠 = 既存 10 snap-in の process VA からの直接 call closure (callgraph.pkl 全域 sweep) + RTTI vtable root 別到達 |
| (a) の lift | (a) のうち既存 lift 済 22 を除く **新規 113 関数のうち 112 を lift (khbase エントリ, 22,391B — CRT atexit ランナ 0x180fe2508 の 1 個は D15+trampoline 連鎖で KH-6 へ残置)**。kh_lower 現行 pass セット (flags/mov128/store128/storelow/merge/callret/vshift/rdata_window) + **新規 [icall] pass (D15 修復)** + **[gs] pass** (addrspace(256) = セグメントアクセスのエミュレート) |
| 検証 | **khbase ctx-fuzz 200/200 trial・10,500/10,500 call bit-exact (seed 1) + 1,000/1,000・52,500/52,500 bit-exact (seed 7)**。native oracle = 実機 9950X (アリーナ ms_abi 直接 call)。近似命令なし = bit-exact 判定 |
| 数学 lib | **UCRT powf (0x180fc3640, 3,782B, FMA3/SSE2 二系統) 3,000/3,000 + 15,000/15,000 bit-exact**。内部 chain (0x180fdb804 → 0x180fd8bd4 → 0x180fd8988) も含め lift。rdata_window 8192 が必須 (窓 2048 で 4/3000 の O(1) 差分 = D14 同型の第 3 例) |
| 新規 lift 欠陥 | **D15**: stage-0 がメモリ間接 call (`call qword [reg+N]`, vtable dispatch) を**空ブロックとして丸ごと欠落** (khbase 113 関数中 5 関数・65 site)。kh_lower **[icall] pass** で修復 (kh_icall 間接 dispatch + arena vtable 実値読み取り) |
| 既存 10 snap-in | **無変更で維持** — run_all.sh exit 0、既存 10 本の RESULT 行は baseline (run_all.final.log) と 1 行も差分なし |
| 主要な達成 | **allocator (operator new/delete/calloc → HeapAlloc/HeapFree IAT)・std::vector push_back (realloc+memmove)・shared_ptr move-assign (vtable dispatch) が wasm で bit-exact 動作** — KH-6 (Tier-M snap-in) と SnapinMasterDsp ホストハーネス (CAB-56) の前置 |

## 1. 分類表 (実測)

方法: `scripts/khbase_classify.py` (新規)。infra 188 = `tools/targets/kilohearts/work/closures_sets.pkl` (事前解析 CAB-25 の ≥8 snap-in 共有集合)。
(a) = infra ∩ (既存 10 snap-in の process VA 起点直接 call closure ∪ lift セット ∪ stub 宣言集合)。
(b) = infra − (a) のうち Editor/EditorModel/Controller vtable root から到達。 (c) = 残り。

| 分類 | 関数数 | バイト | 内容 (代表) |
|---|--:|--:|---|
| (a) process 到達 — lift済 | 22 | 9,129B | libm closure (sincos_a/b, k_dfdb0, m_* 14種), biquad 0x180bac490, interp 0x180006500, dly 0x180020e70 |
| (a) process 到達 — **KH-4 で新規 lift** | **113** (lift 112 + 残置 1) | **22,391B** (lift 分) | **powf 0x180fc3640 (3,782B FMA3)** + 内部 chain, **operator new/delete/calloc (0x180f878e0 / 0x180fd4f30 / 0x180fd51cc / 0x180fd66a0)**, **vector push_back 0x18004cf20**, **shared_ptr move-assign 0x180050bb0 + release walker 群 (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980)**, CRT 数学 helper 群 (0x180fd2xxx〜0x180fe5xxx), _chkstk 0x180f87cd0, strtol core 0x180fd8aac |
| (b) Editor/Controller のみ | 21 | 4,898B | 0x180fc6d70 (1,782B FMA 数学), 0x180fc6870 (1,279B FMA 数学) 等 — UI/エディタ層の lift (KH-7) で到達 |
| (c) 未到達 | 32 | 13,739B | 0x180fc4590 (5,777B FMA 数学 = exp/pow 系と推定), 0x180fcce40 / 0x180fcc450 (FMA 数学) 等 — Tier-M (Delay/Phaser 等) の lift 時に到達見込み |

- 分類 JSON: `work/khbase/classify.json` (全 188 関数の cat/via/lifted/stub/fma/iat/indir 付き)。
- (a) のうち memmove/memset (0x181384040/0x1813846e0) は既存 shim 運用を維持 (lift 対象外)。
- (a) 新規 113 のうち **0x180fe2508** (CRT atexit/terminate ランナ) は `call reg → jmp [rip] trampoline → jmp rax` 連鎖で native oracle 単独実行が不可 (CRT 初期化前提の遅延バインド) → KH-6 へ残置 (fail-fast stub のまま)。

## 2. lift 関数表 (khbase: 112 関数 / 22,391B → wasm 1,319,920B, undefined import 1 (env.exit = fail-fast 経路のみ))

| 群 | 関数 (VA) | 検証 |
|---|---|---|
| 数学 lib | powf 0x180fc3640 (float,float→float, FMA3) + 0x180fdb804 + 0x180fd8bd4 + 0x180fd8988 | **直接差分 3,000/3,000 + 15,000/15,000 bit-exact** (r==0..6 の 7 導入クラス: 通常域 / 負底+整数指数 / 桁落ち境界 / 非正規境界 / オーバーフロー境界)。rdata_window 8192 必須 |
| allocator | op_new 0x180f878e0 / op_delete 0x180fd4f30 / calloc 0x180fd51cc / heap_alloc_wrap 0x180fd66a0 / 0x180fc61dc / 0x180fd662c | **直接差分 1,600/1,600 + 8,000/8,000 bit-exact** (op_new→HeapAlloc IAT shim, malloc→calloc(elem,count) 2 引数 ABI 実測) |
| vector | push_back (realloc helper) 0x18004cf20 | **直接差分 2,300/2,300 + 11,500/11,500 bit-exact** — ABI 実測 (rcx=vec, rdx=end, r8=&value)。毎 push realloc = op_new + memmove shim 経路を毎回発火 |
| shared_ptr (D15 icall) | move-assign 0x180050bb0 / addref 0x180fd2c10 / release 0x180fd2c90 | **直接差分 400/400 + 2,000/2,000 bit-exact** (arena 内 fake vtable + lift 関数 target)。destroy 分岐の全経路実働は KH-5/6 host harness に残留 (ablation 差 0 = 本 scenario の判定力外) |
| CRT 数学/errno helper | 0x180fd2fcc / 0x180fd3144 / 0x180fd320c / 0x180fd2ba0 / 0x180fd62dc / 0x180fd6320 ほか ~20 | **直接差分 43〜45/45 bit-exact** (generic prober: 2 段 pointer chain を満たす fake object + IAT shim) |
| dint/fint | 0x180fbdd78 / 0x180fbdef4 | 直接差分 45/45 (既存 shim 実装の再検証) |
| probe 対象外 (lift のみ) | vtable dispatch 4 種 (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980 — 計 10,278B), _chkstk 0x180f87cd0 (rax=framesize を do_call ABI で与えられない), gs/PEB プローブ 2 種 (0x180fd0a98 / 0x180fe027c — 実機 PEB 依存), MXCSR flag 依存 4 種 (0x180fd5bf4 / 0x180fd662c / 0x180fe5ef0 / 0x180fd8d24), delay-load/raise 経路 ~15 種, 0x180fd8aac (strtol core, delay 経路含む) | lift + build 通過。stub fail-fast により未coverage経路の発火は検出可能。**KH-6 の host harness で検証** |

- IAT shim (新設, `gen_stubs_sigs.py` IMP_SHIM): HeapAlloc (循環 bump アロケータ, 状態はアリーナ+0x100 に置き trial 毎 reset = native/wasm 同一進行・16B 整列・ゼロ充填), HeapFree/GetLastError/SetLastError (ret 0), Enter/LeaveCriticalSection (no-op), FlsGetValue/FlsSetValue/TlsGetValue (アリーナ scratch 0x04000200 — errno 書込み先の NULL 解消), IsProcessorFeaturePresent/IsDebuggerPresent/GetCurrentProcess (定数), RaiseException/TerminateProcess (ret 1), GetModuleHandleW/GetProcAddress/FreeLibrary/LoadLibraryExW/GetModuleHandleExW (ret 0/1)。**native 側は scenario が同一意味の ms_abi shim を IAT slot へ patch** し native oracle を成立させた。
- 新規 helper (gen_simd): paddq/psubq/psrad (+VEX 別名 15 種: vcvtdq2pd/vcvtsd2ss/vpshufd/vldmxcsr 等) — すべて厳密演算 = exact。cvtsi2ss/cvtsi2sd の 2 引数 (dest-merge) 形に対応。
- kh_lower 拡張: **[icall]** (D15), **[gs]** (gs:[0x10]/[0x60] の addrspace(256) を @kh_gs エミュレートへ), wrapper の ret i32 対応, named import の declare 出力。

## 3. D15: stage-0 のメモリ間接 call 欠落 (新規欠陥 → [icall] pass で修復)

- **症状**: `call qword ptr [rax+8]` (vtable dispatch) の IR ブロックが空 (pc store のみ)。vtable load と `mov rcx,obj` は残るため、call だけが無言で消える。`call reg` は解決済 (D15 はメモリ間接のみ)。
- **実測**: khbase 113 関数中 5 関数・65 site (0x18004f350×42 / 0x18004df70×11 / 0x180050860×7 / 0x18004d980×3 / 0x180050bb0×2)。全て shared_ptr/notify 系の vtable dispatch。
- **修復**: kh_lower [icall] pass — 空ブロックの機械語を capstone で読み (reg, disp) を復元 → `%slot = @reg + disp` → `call i64 @kh_icall(i64 %slot)` (callret fixup 付き)。kh_icall (C, 自動生成) は slot < 0x10000000 (アリーナ) なら実値を読み lift 済 callee へ switch、PE .rdata vtable slot は build 時逆引き map、未知は fail-fast。
- **検証**: SP_MOVE (0x180050bb0) の arena fake vtable unit-diff **400/400 bit-exact**。destroy 分岐の全経路実働は KH-5/6 host harness に残留 (§2 のとおり)。
- **意義**: KH-6 以降の snap-in (vtable dispatch を含む) と SnapinMasterDsp ホストハーネス (CAB-56) の必須前提。CAB-55 検出器への「空ブロック × メモリ間接 call」機械チェック追加を推奨 (DEFECTS.md)。

## 4. rdata_window の第 3 実例 (powf) と自動推定

- powf は 2^t 分解表 (log2 仮数→index) を可変 index で読む。**窓 2048 で 4/3000 が O(1) 差分 (want 11.98 got 7.29 等)、窓 8192 で 3,000/3,000 bit-exact** — D14 (sincos 256) / KH-1c (log10f 2048) と同型の第 3 実例。wasm は 644KB → 1,320KB (+676KB = 窓拡大分)。
- **自動推定 pass は未実装** (設計案): kh_lower が stage-0 時点で各 lift 関数の機械語を既に持つため、(1) `lea reg,[rip+X]` (X = 表 base) を収集、(2) 同一関数内の `movdqa/movdqu/movq/movd/movss [reg+disp]` で reg が base 由来のものの disp 最大値を機械語から集計、(3) `cmp reg,imm` / `and` による index 上限 (例: powf の仮数 8bit → 255×8B) と掛けて窓を確定、(4) 決まらない場合は PE の次シンボル境界まで。実装コストは kh_lower 内 ~80 行と推定。**検出器 (CAB-55) 系の下流チケット案** (D11/D14/powf の 3 実例で必要窓は 256/2048/8192 と関数により桁違い — 手動設定は破綻の温床)。

## 5. 検証結果まとめ (実測)

| 実施 | 結果 |
|---|---|
| khbase 200 trial seed 1 | **200/200 trial・10,500/10,500 call bit-exact** (powf 3,000 / allocator 1,600+844+800 / vector 2,300 / shared_ptr 400+200+200 / probe 群 45×N) |
| khbase 1,000 trial seed 7 | **1,000/1,000 trial・52,500/52,500 call bit-exact** (powf 15,000 / vector 11,500 / SP_MOVE 2,000) |
| 既存 10 snap-in (run_all.sh) | **exit 0、RESULT 行 baseline と完全一致** (matrix/gain/haas/clipper/gate/quickeq = bit-exact 200/200, resonator/stereo = 許容誤差 exceed 0, disperser/formant = bit-exact, Path A 対照 = clipper 0/200 負の対照も不変, qemath/qebig = 4,800/4,800) |
| khbase ablation (--skip icall) | SP_MOVE swap+refcount 経路は差分 0 (= 本 scenario の判定力外)。destroy 分岐の全経路実働は KH-5/6 に残留 |
| native oracle | 実機 AMD Ryzen 9 9950X・IAT を同意味 ms_abi shim へ patch して直接実行 (HeapAlloc 等を含む allocator 経路も native で実行可能に) |

## 6. 制限 / 未達

1. **vtable dispatch 4 種 (10,278B) の直接差分なし** (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980): lift + [icall] 適用済だが、実オブジェクト契約 (param mapper の vtable slot 群) の scenario 構築が未着手。CAB-56 の SnapinMasterDsp ホストハーネスで実オブジェクトを渡す形で検証するのが筋。
2. **MXCSR exception-flag 非追跡**: native は FP 演算で MXCSR flag が蓄積し、CRT matherr/MXCSR 変換 helper (0x180fd5bf4 / 0x180fd662c / 0x180fe5ef0 / 0x180fd8d24) がそれを参照。wasm は定数 0x1f80 を返す shim のため 4 関数は probe 対象外。flag 追跡は lift 語彙の拡張 (下流)。
3. **CRT 初期化前提の遅延バインド (UCRT encoded-pointer 機構)**: `__crt_state` の cookie デコード (0x180fe27b0 等) は CRT init で再エンコードされるため native 単独実行が不可。0x180fe2508 を含む ~15 関数は lift のみ (fail-fast stub)。 KH-6 で CRT init を shim する際に再訪。
4. **gs/PEB**: [gs] pass はゼロ初期化エミュレート (StackLimit=0 → probe 不発 = 実機と分岐一致)。PEB を読む CRT OS プローブ 2 関数 (0x180fd0a98 / 0x180fe027c) は実機依存のため probe 対象外。
5. **undefined import 1 (env.exit)**: fail-fast (abort) 経路のみで到達。既存 10 本の undefined 0 に対し khbase のみ 1 — fail-fast の即終了が設計通りのため許容。
6. **直接差分 34 関数 / 間接 78 関数**: khbase 112 のうち直接 fuzz は 34 (powf/allocator/vector/shared_ptr/CRT helper 群)。残りは lift + build 通過 + 呼び枝経由で発火 (powf chain / alloc chain / SP chain) — 個別 coverage 測定は未実施 (関数カウンタ埋め込みは下流案)。

## 7. ユーザ依頼事項

なし (素材・認証とも不要)。

## 8. 成果物 (追加・変更)

`scripts/khbase_classify.py` (新規: 分類)、`snapins.json` (khbase エントリ: lift 112 + abi + shims + rdata_window 8192)、`harness/scen_khmath.h` (新規: khmath 統合 scenario = powf/alloc/vec/icall/probe + native IAT patch + arena ヒープ shim)、`harness/scenarios.c` (khbase 群登録)、`harness/compare.mjs` (ret i64 undefined ガード — 既存挙動不変)、`lift/kh_lower.py` (**[icall]** / **[gs]** pass, ret i32 wrapper, named import declare, kh_icall/kh_icfail 生成)、`lift/gen_stubs_sigs.py` (named-import shim 群 + arena ヒープ)、`lift/gen_simd.py` (paddq/psubq/psrad/VEX 別名 15 種 + cvtsi2 系 dest-merge 形 + mxcsr)、`lift/build.py` (icall.c を emcc 入力に追加)、`scripts/make_table.py` (khbase 行)、`run_all.sh` ([4c] khbase ステップ)、`DEFECTS.md` (D15 + D14 窓実績の追記)。`work/khbase/` (gitignore: stage-0 / classify.json / vectors / compare.json / デバッグスクリプト)。

## 9. Tier-M (Delay/Phaser 等) への引き継ぎ

1. **khbase の使い方**: snapins.json に新 snap-in を追加し、lift に process + 固有 closure を書くだけ。共通基盤 (powf/allocator/vector/notify) は khbase 実績の pass セットがそのまま適用される。vtable dispatch を含む関数は [icall] が自動修復する (空ブロック検出は自動)。
2. **heap**: allocator IAT shim はアリーナ+0x100 を状態に使い trial 毎 reset — 新 scenario も冒頭で `A(0x110)` して cell を確保する慣習を踏襲すること (scen_khmath.h の trial_khmath 冒頭を参照)。vector/realloc はこの上で bit-exact 済み。
3. **notify/dirty 経路**: 0x18004df70 (dirty notify) / 0x18004d980 (param map) は lift 済だが unit-diff 未実施。CAB-56 ホストハーネス (SnapinMasterDsp) で実オブジェクト契約ごと検証するのが次手。
4. **MXCSR flag / CRT init / PEB**: §6 の 3 制限はホストハーネス設計 (CAB-56) と KH-6 の lift 語彙拡張に持ち越し。
5. **rdata_window 自動推定** (§4 の設計案) を先に実装すると、Tier-M の数学関数 (exp/pow 系, (c) の 0x180fc4590 等) で同型の窓破綻を未然に防げる。
6. **CAB-53 進捗**: KH-1a/1b/1c (snap-in 10 本) + KH-2b (D14) + KH-4 (共通基盤 112 関数) 完了。次は KH-6 (Tier-M snap-in) と CAB-56 (ホストハーネス)。
