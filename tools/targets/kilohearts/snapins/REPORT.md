# KH-4: KH 共通基盤 lift (CAB-246) + KH-6 (CAB-258) Tier-M 3 本 + CAB-56 SnapinMasterDsp ホストハーネス

- 解析日: 2026-10-11 / 担当 dir: `tools/targets/kilohearts/snapins/` (大物は `work/`, gitignore)
- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (13 snap-in + **khbase** + Path A 対照 + libm 単体 + **CAB-56 ホストハーネス**。キャッシュ有り 5〜6 分)。1000 trial / seed 7 は `TRIALS=1000 SEED=7 bash .../run_all.sh` (全 13 本 + khbase + ハーネスが 1000 trial になる)。§9/§10 の 1000 trial 数値はこの形で取得
- Linear: CAB-246 (KH-4) / CAB-258 (KH-6, parent CAB-53) / CAB-56 (KH-4b ホストハーネス, parent CAB-13)
- preflight: RULES_SHA=ff4999169333
- 本報は KH-4 (§1〜§8) と KH-6 (§9, §11) と CAB-56 (§10) の合本。**第 2 弾 = §13** (rcpps/rsqrtps 実機近似表で Resonator/Stereo/Delay が bit-exact 化, D16 検出器化)。既存 10 snap-in (KH-1a/1b/1c) と KH-2b (D14 修復) の詳細は前版 (git log fe57c01) を参照 — run_all.sh の RESULT 行は前版 baseline と完全一致

## 0. 結論 (先出し)

### 0-1. KH-4 (CAB-246) — 前版の判定を再確認 (200 trial seed 1 / 1000 trial seed 7)

- **分類**: infra 188 関数 / 53,010B を実測分類 → **(a) process 到達 135 / 34,373B** (lift 対象)、(b) Editor/Controller のみ 21 / 4,898B、(c) 未到達 32 / 13,739B。根拠 = 既存 10 snap-in の process VA 起点直接 call closure (callgraph.pkl 全域 sweep) + RTTI vtable root 別到達
- **lift**: (a) のうち既存 22 を除く新規 113 関数のうち **112 を lift** (khbase, KH-4 時点 24,263B。CRT atexit ランナ 0x180fe2508 は D15+trampoline 連鎖で残置)。pass セット = flags/mov128/store128/storelow/merge/callret/vshift/rdata_window + **新規 [icall]** (D15 修復) + **[gs]**
- **検証**: khbase ctx-fuzz **200/200・10,500/10,500 call bit-exact** (seed 1) + **1,000/1,000・52,500/52,500** (seed 7)。**UCRT powf (3,782B, FMA3) 3,000/3,000 + 15,000/15,000 bit-exact** (窓 2048 で 4/3000 の O(1) 差分 = D14 同型の第 3 例)
- **D15 (新規欠陥)**: stage-0 がメモリ間接 call を**空ブロックとして丸ごと欠落** (113 関数中 5 関数・65 site) → [icall] pass で修復
- **主要な達成**: allocator (new/delete/calloc→HeapAlloc IAT)・vector push_back (realloc+memmove)・shared_ptr move-assign (vtable dispatch) が wasm で bit-exact 動作
- **本改修での変更**: khbase lift 112 → **116 関数** (interp/ring driver/getshared/route map get)。判定行は完全不変、wasm +9,634B

### 0-2. KH-6 (CAB-258) + CAB-56 (KH-4b) — 新規成果 (前ラウンド)。本弾 (§13) で Delay も bit-exact 化

- **Tier-M 3 本**: Phaser (80 fn/17,955B)・Limiter (108 fn/22,580B) = **bit-exact**、Delay (141 fn/37,914B) = 当時 許容誤差 exceed 0。200 (seed 1)・1000 (seed 7) trial とも green
- **(c) 32 関数中 5 関数 / 8,018B (58%) に到達・lift** — 最大 0x180fc4590 (double pow 5,777B)。単体差分 pow 5,012・tan 6,011 ケース bit 一致
- **CAB-56 ハーネス**: vtable dispatch 4 種 (7,395B) を実オブジェクト契約で unit-diff → khmrel/khmaster/khmring すべて 200/200 + 1000/1000 bit-exact。D15 の destroy 分岐 (class A/B) 全経路を発火
- **[rdataest] pass**: delay 24 base の per-VA 窓を推定、最大 cap 8192。**D16 (新規欠陥)**: map 非該当 VA の窓が型サイズまで縮小 → 64B 既定を併用して修復
- **Delay の当時の許容誤差**: rcpps 4 箇所のみ。gate 超過 185 / 1,271,000 word (0.015%)・絶対誤差 1 ULP で頭打ち → absFloor 1e-6 で exceed 0
- **回帰**: run_all.sh exit 0、RESULT 行 baseline と 1 行も差分なし、lic_check 70/70

## 1. 分類表 (実測)

方法: `scripts/khbase_classify.py` (新規)。infra 188 = `tools/targets/kilohearts/work/closures_sets.pkl` (事前解析 CAB-25 の ≥8 snap-in 共有集合)。
(a) = infra ∩ (既存 10 snap-in の process VA 起点直接 call closure ∪ lift セット ∪ stub 宣言集合)。
(b) = infra − (a) のうち Editor/EditorModel/Controller vtable root から到達。 (c) = 残り。

| 分類 | 関数数 | バイト | 内容 (代表) |
|---|--:|--:|---|
| (a) process 到達 — lift済 | 22 | 9,129B | libm closure (sincos_a/b, k_dfdb0, m_* 14種), biquad 0x180bac490, interp 0x180006500, dly 0x180020e70 |
| (a) process 到達 — **KH-4 で新規 lift** | **113** (lift 112 + 残置 1) | **22,391B (当時報の値 / 現行の .pdata extent 再計算では 24,263B)** | **powf 0x180fc3640 (3,782B FMA3)** + 内部 chain, **operator new/delete/calloc (0x180f878e0 / 0x180fd4f30 / 0x180fd51cc / 0x180fd66a0)**, **vector push_back 0x18004cf20**, **shared_ptr move-assign 0x180050bb0 + release walker 群 (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980)**, CRT 数学 helper 群 (0x180fd2xxx〜0x180fe5xxx), _chkstk 0x180f87cd0, strtol core 0x180fd8aac |
| (b) Editor/Controller のみ | 21 | 4,898B | 0x180fc6d70 (1,782B FMA 数学), 0x180fc6870 (1,279B FMA 数学) 等 — UI/エディタ層の lift (KH-7) で到達 |
| (c) 未到達 | 32 | 13,739B | 0x180fc4590 (5,777B FMA 数学 = exp/pow 系と推定), 0x180fcce40 / 0x180fcc450 (FMA 数学) 等 — Tier-M (Delay/Phaser 等) の lift 時に到達見込み |

- 分類 JSON: `work/khbase/classify.json` (全 188 関数の cat/via/lifted/stub/fma/iat/indir 付き)。memmove/memset (0x181384040/0x1813846e0) は既存 shim 運用を維持 (lift 対象外)。
- (a) 新規 113 のうち **0x180fe2508** (CRT atexit/terminate ランナ) は `call reg → jmp [rip] trampoline → jmp rax` 連鎖で native oracle 単独実行が不可 (CRT 初期化前提の遅延バインド) → KH-6 へ残置 (fail-fast stub のまま)。

## 2. lift 関数表 (khbase: KH-4 時点 112 関数 / 24,263B → wasm 1,304,576B・undefined 0。**CAB-56/KH-6 後は 116 関数 / 24,609B → wasm 1,314,210B・undefined 0 = 本章の数値は §10 の増員分を未反映**。undefined import は全 13 snap-in + khbase で 0)

| 群 | 関数 (VA) | 検証 |
|---|---|---|
| 数学 lib | powf 0x180fc3640 (float,float→float, FMA3) + 0x180fdb804 + 0x180fd8bd4 + 0x180fd8988 | **直接差分 3,000/3,000 + 15,000/15,000 bit-exact** (r==0..6 の 7 導入クラス: 通常域 / 負底+整数指数 / 桁落ち境界 / 非正規境界 / オーバーフロー境界)。rdata_window 8192 必須 |
| allocator | op_new 0x180f878e0 / op_delete 0x180fd4f30 / calloc 0x180fd51cc / heap_alloc_wrap 0x180fd66a0 / 0x180fc61dc / 0x180fd662c | **直接差分 1,600/1,600 + 8,000/8,000 bit-exact** (op_new→HeapAlloc IAT shim, malloc→calloc(elem,count) 2 引数 ABI 実測) |
| vector | push_back (realloc helper) 0x18004cf20 | **直接差分 2,300/2,300 + 11,500/11,500 bit-exact** — ABI 実測 (rcx=vec, rdx=end, r8=&value)。毎 push realloc = op_new + memmove shim 経路を毎回発火 |
| shared_ptr (D15 icall) | move-assign 0x180050bb0 / addref 0x180fd2c10 / release 0x180fd2c90 | **直接差分 400/400 + 2,000/2,000 bit-exact** (arena 内 fake vtable + lift 関数 target)。destroy 分岐の全経路実働は KH-5/6 host harness に残留 (ablation 差 0 = 本 scenario の判定力外) |
| CRT 数学/errno helper | 0x180fd2fcc / 0x180fd3144 / 0x180fd320c / 0x180fd2ba0 / 0x180fd62dc / 0x180fd6320 ほか ~20 | **直接差分 43〜45/45 bit-exact** (generic prober: 2 段 pointer chain を満たす fake object + IAT shim) |
| dint/fint | 0x180fbdd78 / 0x180fbdef4 | 直接差分 45/45 (既存 shim 実装の再検証) |
| probe 対象外 (lift のみ) | vtable dispatch 4 種 (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980 — 計 7,395B。.pdata/ extent の実測, 旧 "10,278B" は誤記), _chkstk 0x180f87cd0 (rax=framesize を do_call ABI で与えられない), gs/PEB プローブ 2 種 (0x180fd0a98 / 0x180fe027c — 実機 PEB 依存), MXCSR flag 依存 4 種 (0x180fd5bf4 / 0x180fd662c / 0x180fe5ef0 / 0x180fd8d24), delay-load/raise 経路 ~15 種, 0x180fd8aac (strtol core, delay 経路含む) | lift + build 通過。stub fail-fast により未coverage経路の発火は検出可能。**KH-6 の host harness で検証** |

- IAT shim (新設, `gen_stubs_sigs.py` IMP_SHIM): HeapAlloc (循環 bump アロケータ, 状態はアリーナ+0x100・trial 毎 reset = native/wasm 同一進行・16B 整列・ゼロ充填)、HeapFree/GetLastError/SetLastError (ret 0)、Enter/LeaveCriticalSection (no-op)、FlsGetValue/FlsSetValue/TlsGetValue (アリーナ scratch 0x04000200)、IsProcessorFeaturePresent/IsDebuggerPresent/GetCurrentProcess (定数)、RaiseException/TerminateProcess (ret 1)、GetModuleHandleW/GetProcAddress/FreeLibrary/LoadLibraryExW/GetModuleHandleExW (ret 0/1)。**native 側は scenario が同一意味の ms_abi shim を IAT slot へ patch** し native oracle を成立させた。新規 helper (gen_simd): paddq/psubq/psrad (+VEX 別名 15 種: vcvtdq2pd/vcvtsd2ss/vpshufd/vldmxcsr 等、すべて厳密 = exact) と cvtsi2ss/cvtsi2sd の 2 引数 (dest-merge) 形。kh_lower 拡張: **[icall]** (D15)、**[gs]**、wrapper の ret i32 対応、named import の declare 出力。

## 3. D15: stage-0 のメモリ間接 call 欠落 (新規欠陥 → [icall] pass で修復)

- **症状**: `call qword ptr [rax+8]` (vtable dispatch) の IR ブロックが空 (pc store のみ)。vtable load と `mov rcx,obj` は残るため、call だけが無言で消える。`call reg` は解決済 (D15 はメモリ間接のみ)。
- **実測**: khbase 113 関数中 5 関数・65 site (0x18004f350×42 / 0x18004df70×11 / 0x180050860×7 / 0x18004d980×3 / 0x180050bb0×2)。全て shared_ptr/notify 系の vtable dispatch。
- **修復**: kh_lower [icall] pass — 空ブロックの機械語を capstone で読み (reg, disp) を復元 → `%slot = @reg + disp` → `call i64 @kh_icall(i64 %slot)` (callret fixup 付き)。kh_icall (C, 自動生成) は slot < 0x10000000 (アリーナ) なら実値を読み lift 済 callee へ switch、PE .rdata vtable slot は build 時逆引き map、未知は fail-fast。
- **検証**: SP_MOVE (0x180050bb0) の arena fake vtable unit-diff **400/400 bit-exact**。destroy 分岐の全経路実働は §10/CAB-56 で解消 (class A 500+520, class B 54 hit = §13)。**意義**: KH-6 以降の snap-in (vtable dispatch を含む) と SnapinMasterDsp ホストハーネス (CAB-56) の必須前提。CAB-55 検出器への「空ブロック × メモリ間接 call」機械チェック追加を推奨 (DEFECTS.md)。

## 4. rdata_window の第 3 実例 (powf) と自動推定

- powf は 2^t 分解表 (log2 仮数→index) を可変 index で読む。**窓 2048 で 4/3000 が O(1) 差分 (want 11.98 got 7.29 等)、窓 8192 で 3,000/3,000 bit-exact** — D14 (sincos 256) / KH-1c (log10f 2048) と同型の第 3 実例。wasm は 644KB → 1,320KB (+676KB = 窓拡大分)。
- ~~**自動推定 pass は未実装** (設計案)~~ → **§9-2 で実装済み**。設計: (1) `lea reg,[rip+X]` の表 base 収集、(2) base を使う load の到達幅 (`disp + mask×scale + opsize`) 集計、(3) `cmp reg,imm`/`and` の index 上限、(4) 決まらない場合は PE の次シンボル境界まで。D11/D14/powf の 3 実例で必要窓は 256/2048/8192 と関数により桁違い = 手動設定は破綻の温床。

## 5. 制限 / 未達

1. ~~**vtable dispatch 4 種 (7,395B) の直接差分なし**~~ → **§10 (CAB-56) で解消**: 実オブジェクト契約をアリーナ上に構築し 3 scenario で 200 + 1000 trial bit-exact。destroy 分岐 (class A/B) も全経路発火済み。
2. **MXCSR exception-flag 非追跡**: native は FP 演算で MXCSR flag が蓄積し CRT matherr helper (0x180fd5bf4 / 0x180fd662c / 0x180fe5ef0 / 0x180fd8d24) がそれを参照。wasm は定数 0x1f80 を返す shim のため 4 関数は probe 対象外 (flag 追跡は lift 語彙の拡張 = 下流)。
3. **CRT 初期化前提の遅延バインド (UCRT encoded-pointer 機構)**: `__crt_state` の cookie デコード (0x180fe27b0 等) は CRT init で再エンコードされるため native 単独実行が不可。0x180fe2508 を含む ~15 関数は lift のみ (fail-fast stub)。GH-6 で CRT init を shim する際に再訪。
4. **gs/PEB**: [gs] pass はゼロ初期化エミュレート (StackLimit=0 → probe 不発 = 実機と分岐一致)。PEB を読む CRT OS プローブ 2 関数 (0x180fd0a98 / 0x180fe027c) は実機依存のため probe 対象外。
5. **直接差分 34 関数 / 間接 78 関数**: khbase 112 のうち直接 fuzz は 34 (powf/allocator/vector/shared_ptr/CRT helper 群)。残りは lift + build 通過 + 呼び枝経由で発火 — 個別 coverage 測定は未実施 (関数カウンタ埋め込みは下流案)。~~**rcpps 完全エミュレート未実装**~~ → **§13 で達成** (142 関数中 4 箇所・すべて 0x180289ea0 内。実機表 3 × 4,096 で bit-exact)。native oracle = 実機 AMD Ryzen 9 9950X・IAT を同意味 ms_abi shim へ patch して直接実行。
6. **undefined import 0 (訂正)**: 旧版は「khbase のみ env.exit 1」としていたが、実測では **khbase / phaser / delay / limiter すべて undefined import 0** (fail-fast stub 化で env.exit への import が消えた)。旧 values (112 fn 時点) は wasm 1,319,920B / undefined 1 だった。

## 6. ユーザ依頼事項: なし (素材・認証とも不要)。
## 7. 成果物 (追加・変更)

`scripts/khbase_classify.py` (新規: 分類)、`snapins.json` (khbase エントリ: lift 112 + abi + shims + rdata_window 8192 — KH-6/CAB-56 で **116 + phaser/delay/limiter 3 エントリ + delay tol**)、`harness/scen_khmath.h` (新規: khmath 統合 scenario = powf/alloc/vec/icall/probe + native IAT patch + arena ヒープ shim)、`harness/scenarios.c` (khbase 群 + phaser/delay/limiter 登録)、`harness/scenarios_kh.c` (新規: CAB-56 ハーネス登録 khmrel/khmaster/khmring)、`harness/compare.mjs` (ret i64 undefined ガード — 既存挙動不変)、`lift/kh_lower.py` (**[icall]** / **[gs]** / **[rdataest]** pass, ret i32 wrapper, named import declare, kh_icall/kh_icfail 生成, rdata_window_map 出力)、`lift/gen_stubs_sigs.py` (named-import shim 群 + arena ヒープ)、`lift/gen_simd.py` (paddq/psubq/psrad/VEX 別名 15 種 + cvtsi2 系 dest-merge 形 + mxcsr + **sqrtps/sqrtpd/pcmpeqd/pcmpeqq/vpcmpeqq/pcmpgtd/pmovsxdq**)、`lift/gen_globals.py` (**--window-map (per-VA 窓)** + D16 修復), `lift/build.py` (icall.c を emcc 入力に追加, --window-map 分岐), `scripts/make_table.py` (13 本 + khbase 行), `run_all.sh` ([2] 13 本 + [4c] khbase + **[4d] CAB-56 ハーネス**), `scripts/leafscan.py` (新規・読取専用: leaf getter 発見), `DEFECTS.md` (D15 + D14 窓実績 + **D16**)。`work/khbase/` (gitignore: stage-0 / classify.json / vectors / compare.json / デバッグスクリプト)。

## 8. Tier-M への引き継ぎ状況 — 3/5/6 は解消済み

1. **khbase の使い方**: snapins.json に新 snap-in を追加し lift に process + 固有 closure を書くだけ。共通基盤 (powf/allocator/vector/notify) は khbase 実績の pass セットがそのまま適用される。vtable dispatch を含む関数は [icall] が自動修復する (空ブロック検出は自動)。
2. **heap**: allocator IAT shim はアリーナ+0x100 を状態に使い trial 毎 reset — 新 scenario も冒頭で `A(0x110)` して cell を確保する慣習を踏襲すること (scen_khmath.h の trial_khmath 冒頭を参照)。
3. ~~**notify/dirty 経路** の unit-diff 未実施~~ → **§10 で解消済み** (khmaster/khmring 実オブジェクト契約)。
4. **MXCSR flag / CRT init / PEB**: §5 の 3 制限はホストハーネス設計 (CAB-56) と KH-6 の lift 語彙拡張に持ち越し。
5. ~~**rdata_window 自動推定**~~ → **§9-2 の [rdataest] pass で実装済み** (per-VA 窓)。§13-2 で固定点超過反復化。
6. ~~**CAB-53 進捗**~~ → KH-1a/1b/1c (10 本) + KH-2b + KH-4 + **KH-6 (3 本) + CAB-56 ハーネス** 完了。残りは CAB-60 の中位〜難 snap-in (§11)。

## 9. KH-6 (CAB-258): Tier-M snap-in 3 本 (Phaser / Delay / Limiter) — 新規 lift 329 関数・(c) 到達 5 関数

- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (既定 200 trial / seed 1)。1000 trial / seed 7 は `TRIALS=1000 SEED=7 bash .../run_all.sh`
- Linear: CAB-258 (parent CAB-53)。前提 = KH-4 (commit 9e175e8) + [icall]/[gs] pass。

| snap-in (id) | process VA | B | lift fn / 合計B | wasm B | undefined | 200 trial | 1000 trial (seed 7) | 判定 |
|---|---|--:|--:|--:|--:|---|---|---|
| Phaser (ksph) | 0x1807270d0 | 2172 | 80 / 17,955 | 345,220 | 0 | 200/200・1,100/1,100 call | **1000/1000・5,500/5,500** | **bit-exact** |
| Delay (ksdl) | 0x1802ed7f0 | 3291 | 141 / 37,914 | 3,585,984 | 0 | 200/200・1,299/1,299 call | **1000/1000・6,499/6,499** | 許容誤差 (§9-4) |
| Limiter (kslt) | 0x1804e8500 | 1980 | 108 / 22,580 | 438,170 | 0 | 200/200・1,100/1,100 call | **1000/1000・5,500/5,500** | **bit-exact** |

- **scenario は slot13 (prepare) / slot14 (process) / slot15 (reset) の 3 エントリを混在させる** (Delay は setfs/delay-line 確保・Limiter/Phaser は sync/bands 変化で ramp 再計算)。通知 vector・dirty フラグ・AudioBuffer (L/R/n + f64 sample rate) も bit 突合対象。
- Delay は 0x1802ed640 (dl_prepare) が `op_new[]` で delay line 2 本を確保 (fs=8000 固定 → cap 65,536 × 4B = 256KB × 2)、tap_add 0x1802ecfc0 が obj+0x198 を加算先にする実オブジェクト契約を scenario で再現。**vec push の満杯 realloc 経路 (0x18004cf20)** も end を 0..64 slot に散らして発火。

### 9-1. (c) 未到達 32 関数の到達・lift (KH-4 §1 の (c) 解消の第 1 例)

| 関数 | B | 内容 | 到達経路 (静的 call 辺) / 動的確認 |
|---|---:|---|---|
| **0x180fc4590** | **5,777** | **double pow (FMA 14)** = `pow(1-x, n)` 形の平滑化 | limiter slot13 0x1804e8340 / delay slot13 0x1802ed790 (各 555 / 1,000 回) |
| 0x180fcce40 | 1,459 | double tan (biquad 設計の `tan(f/fs)` 引数) | delay process 0x1802ed7f0 (3,999 回・分岐 n>0 で常通) |
| 0x180fcd400 | 472 | tan の内部 | 0x180fcce40 から (同行) |
| 0x180fdb6e0 | 292 | pow 内部 (strtol thunk 0x180fd8aac への分岐) | 0x180fc4590 から (同上) |
| 0x180fdc858 | 18 | 0x180fcce40 の tail | 0x180fcce40 から (同行) |
| 計 | **8,018** | (c) 13,739B の **58%** | |

- **単体差分**: pow (0x180fc4590) 5,012 ケース・tan (0x180fcce40) 6,011 ケースを native (実機 IAT 無し直接 call) と wasm で突合 → **両者 bit 一致** (`work/pow_in.txt` 等、負底・非整数指数・NaN・±0・指数 1e306 級を含む)。

### 9-2. rdata_window 自動推定 [rdataest] pass (KH-4 §4 設計案の実装 = 半自動)

- kh_lower が各関数の機械語を持っていることを利用し、(1) `lea reg,[rip+X]` の表 base 候識、(2) base を使う load の到達幅 (`disp + mask×scale + opsize`、`and idx,imm` からindex上限を取得)、(3) **call 辺を跨ぐ base 伝播** (arg reg への base 束縛を callee の `[rcx+idx*8]` 読出しに伝播・4 ラウンド不動点) で per-VA 窓幅を推定。精密推定不能な base は「次参照 VA までの gap + 64B」に倒す。
- 実測 (delay, 24 base): 8192 (cap 上限) = 0x181563298 / 0x180000000 (ImageBase 相対) / 0x1823e44d0 / 0x182868d70、4784 = 0x1822894d0、4012 = 0x18227f020、2128 = 0x182280e30〜0x182288ac0、940 = 0x184162358、672 = 0x18227edc0、576 = 0x1822892d0、440 = 0x1822871f8、416 = 0x18228a9d0、256/224/224/192 = 0x18436cc80 / 0x18228a920 / 0x18228ac50 (2/π) / 0x18436cc00、static disp = 68/72/88/96 (work/delay/s0/stat.json の `rdata_window_map` 全 24 エントリと一致)。limiter は 17 base (ImageBase 相対は 8192 で打切り)。
- **cap 8192 = powf 0x180fc3640 の検証済み最大窓**。limiter の ImageBase 相対パターン (`lea base,[rip+ImageBase]` + `[base+idx*2+0x227ffc0]`) は reach が 68,586,968B に爆発するが 8192 で打切り。snapins.json の `"rdata_est": true` は phaser/delay/limiter のみ (既存 10 本は `--window` 無し = 64B 既定に固定し baseline 不変)。
- **D16 (新規欠陥, ours)**: `--window-map` 経路で `window == 0` が falsy になり map 非該当 VA の窓が IR 型サイズ (1〜2B) まで縮み定数読みが壊れた。`n = max(n, window or 64, wmap)` で修復 (DEFECTS.md D16)。

### 9-3. 新規 SIMD 語彙 (gen_simd)

sqrtps / sqrtpd (IEEE 正確, 4 lane / 2 lane)・pcmpeqd / pcmpeqq / vpcmpeqq / pcmpgtd (全 1 = mask)・pmovsxdq (符号拡張 2 dword → 2 qword)。いずれも厳密演算なので近似判定は不要。

### 9-4. Delay の許容誤差判定 (rcpps) — 数値根拠 (→ §13 で bit-exact 化)

delay closure 142 関数の近似命令は rcpps 4 箇所のみ (すべて 0x180289ea0)。wasm 側が IEEE の 1/x だったため実機近似表との差が伝播し、純相対 gate 超過は 185 / 1,271,000 word (0.015%)、絶対誤差は 1 ULP (2⁻²²) で頭打ち。したがって snapins.json の delay `tol` に tap へ absFloor 1e-6 を設定して exceed 0 としていた。**§13 で実機近似表を移植したため approx 0 / bit-exact に移行。**

## 10. CAB-56: SnapinMasterDsp ホストハーネス — vtable dispatch 4 種の実オブジェクト契約 unit-diff

- 対象 (KH-4 §5-1 で「直接差分なし = ホストハーネスで検証」と残置した 4 関数・7,395B)。すべて master オブジェクトをアリーナ上に構築して実 machinery に通す。
- **scenario 登録は scenarios_kh.c に分離** (native_ref_kh バイナリ) — 既存 scenarios.c の既存 scenario 行は不変。

| scenario | 対象 (VA) | 契約 | 200 trial | 1000 trial |
|---|---|---|---|---|
| **khmrel** | sp_release 0x18004f350 (小路線) + sp_destroy_walker 0x180050860 | dirty record 配列 (span<0x401 = ≤32 record / ≥0x401 = 大路線) + fake vtable | **200/200・600/600** | **1000/1000・3,000/3,000** |
| **khmaster** | dirty_notify 0x18004df70 + param_map_notify 0x18004d980 (interp driver 0x180006500 経由) | master (0x2e00) + 201 dirty record + route table 100 本 + ctrl block + obj2 | **200/200・400/400** | **1000/1000・2,000/2,000** |
| **khmring** | ring driver 0x1804faa80 | master + ring bank 5 本 (128 slot × 16B) | **200/200・200/200** | **1000/1000・1,000/1,000** |

- **D15 destroy 分岐の全経路**: ctrl block の vtable slot +8 = destroy / +0x10 = delete (op_delete 実物, HeapFree IAT shim) を dispatch。destroy は **class A (ctx_set2f 0x1800fb8f0, r9d でアリーナ内 +0x768/+0x780 に書込)** と **class B (0x180f87f24, r9 が野生ポインタ = 引数無視)** の 2 種を scenario 制御で切替え、小路線 (A) と大路線/df70 後半 (B) の両方を発火。refcount/weakref 0〜7 を振って replace/remove/append を踏む。
- **native oracle は IAT patch 方式**: scen_khmaster.h が 20 種の IAT slot を同意味 ms_abi shim に差替え + 0x5000000 に 1MB ヒープ域を mmap + ARCH_SET_GS でゼロ TEB 設定 ([gs] の wasm ゼロ初期化エミュレートと同一)。**wasm 側は patch 不要**。
- khbase lift 112 → **116 関数** (+2,218B、.pdata extent 実測: interp 145B / ring driver 163B / getshared 30B / route map get 8B)。**判定行は完全不変**、wasm 1,304,576 → **1,314,210 B (+9,634 B)**。0x1800065e0 (8B, `lea rax,[rcx+0x1b30]; ret`) は `scripts/leafscan.py` (新規・読取専用) で HeartCore 全 .text から発見した leaf (KH-4 分類では (c) だったため本改修で同時に解消)。

## 11. 引継ぎ (次タスク) — 1・3 は本弾 (§13) で解消

1. ~~**rcpps の完全エミュレート**~~ → **§13 で達成**。実機表 3 × 4,096 エントリで Resonator/Stereo/Delay が bit-exact 化。baseline 不変の制約 (§9-4 の警告) は、gate 未使用 (exceed 0) のまま 3 本が bit-exact になったことで解消。
2. **CAB-60 の中位〜難 snap-in**: (c) 残り 27 関数 (5,721B) と Ladder / Slice EQ / Filter Table (AVX・FMA 427) は report §4 の難度表に従い **未実施** (§13-4 起票先 = 親 CAB-53)。
3. ~~**rdataest の精度向上 + D16 検出器化**~~ → **§13-2 で達成** (固定点超過反復・収束 2 ラウンド実測・D16 検出器 + ネガコン)。

## 12. 検収 (独立再計算, 2026-10-11) — 本チケットの確定値

- **① vtable dispatch 4 種の実働 / ② D15 destroy 分岐 (class A/B)**: native oracle に gdb bp を置き hit 数を実測 (`work/native_ref_kh CORE <scen> 200 1`) → 0x18004f350 **637** / 0x180050860 **605** (khmrel), 0x18004df70 **400** / 0x18004d980 **1,100** (khmaster, interp driver 経由)、class A (ctx_set2f) **500**+**520** (khmaster/khmring), class B **54** (khmrel), op_delete = 150/15/160 — 4 種すべて unit-diff 対象・全経路発火
- **③ Tier-M 判定**: phaser/limiter = **bit-exact** (200/200・1000/1000), delay = 許容誤差 exceed 0 (1000 trial: approx 3,052 / 1,271,000 word, maxrel 3.591e-2, maxabs 2.384e-7), khmaster 1000/1000。tap の absFloor を外すと exceed **185** = §9-4 の "185 word (0.015%)" (as-is は 0)
- **④ (c) 未到達 32 関数 / ⑤ rdata_window**: `work/khbase/classify.json` + snapins.json の lift 集合 → **5 関数 / 8,018B (58.4%)** が delay/limiter に lift 済 (0x180fc4590 / 0x180fcce40 / 0x180fcd400 / 0x180fdb6e0 / 0x180fdc858)、残り 27 関数 / 5,721B。窓の使い分け = quickeq/stereo/disperser 256 / formant 2048 / delay・khbase 8192 / phaser・limiter は rdata_est 自動推定 (delay 24 base の推定値は §9-2 と全一致)
- **⑥ baseline 不変 / khbase**: 親コミット (504678c) のツリーを `work/headminus1/` に展開し再実行 → RESULT 行 10 本が**完全一致**。khbase 112 fn/24,263B/wasm 1,304,576B → 116 fn/24,609B/wasm 1,314,210B と増加したが判定行 (10,500/10,500, by-fn) は不変。seed 1 200/200・10,500/10,500、seed 7 1,000/1,000・52,500/52,500 bit-exact。lic_check **ok 70 / fail 0**、license/ 改変 0
- **誤記修正** (`.pdata` / `fnscan.extent` 実測): vtable dispatch 4 種 = **7,395B** (旧 "10,278B"), khbase 増員 = **+2,218B** (旧 "+24,609B"), khbase undefined import = **0** (旧 "1"), delay の static disp 推定 = 68/72/88/96 (旧 "72〜96")

---

## 13. KH-6 第 2 弾 (CAB-258 続, 2026-10-11) — rcpps/rsqrtps 実機近似表で Resonator/Stereo/Delay が bit-exact 化

起点 `8efb7a0`。既知類型 (DEFECTS.md): **D16 該当** (§13-2)、D2/D3/D7/D8/D9/D11/D14 非該当 (新規 miscompile なし)。前提: `rcpps`/`rsqrtps` の結果は CPU 内蔵近似表で仕様 (SDM) は相対誤差 ≤1.5·2⁻¹² しか保束せず、旧 wasm 実装 (IEEE の 1/x) との差が CAB-224 以来の許容誤差 gate の原因だった。

| 対象 | 変更前 (V27 検収) | 変更後 (本弾) |
|---|---|---|
| Resonator | 許容誤差 approx 140,067 / maxrel 2.778e-1 | **approx 0 / maxrel 0.000e+0, 1000/1000・4,999/4,999** |
| Stereo | 許容誤差 approx 827 / maxrel 2.894e-5 | **approx 0 / maxrel 0.000e+0, 1000/1000・4,999/4,999** |
| Delay | 許容誤差 approx 3,052 / maxrel 3.591e-2 | **approx 0 / maxrel 0.000e+0, 1000/1000・6,499/6,499** |
| 既存 10 + Path A + qemath/qebig + khbase + CAB-56 | baseline | **1 行も差分なし** (limiter/phaser も 1000/1000・5,500/5,500)、lic_check **70/70** |

### 13-1. 近似表の構造 (実測) と検証

```
rcpps : result = sign | ((253 - e) << 23) | T_rcp[m]                    (253-e <= 0 → ±0)
rsqrtps: result = sign | ((190 - ((e+1)>>1)) << 23) | T_rsq[odd/even][m]  (1/sqrt(2^k) で指数非線形 = √2 因子で 2 表)
特殊値: ±0/非正規 → ±Inf / NaN → quiet NaN (s|0x7f800000|(man|0x400000)) / ±Inf → ±0 / rsqrtps 負有限値 → NaN
```
e = exponent field, m = mantissa 上位 12bit (下位 11bit は実測 0/2048 differ = 無影響)。表 = **3 × 4,096 × 4B = 49,152 B**。

| 検証 (規則 37・41) | 結果 |
|---|---|
| `approx_probe.c verify` (全グリッド 1,040,384 + 乱数 500,000) | 不一致 **0** (両命令) |
| `verify_approx_helpers.c` (**生成 C** をホスト検証, grid 1,048,576 + rand 500,000) | 不一致 **0** |
| closed form `round(1/(1+m/4096))` の再現度 | **0/4096** (max ULP 差 4,421) = 式では再現不可 = 表抽出が唯一 |

### 13-2. rdata_est 固定点超過反復 + D16 検出器化

- **[rdataest]**: `range(4)` → **収束まで超過反復** (`range(64)` + `if not changed: break`)。旧 4 ラウンドは V27 指摘の recall 不足 (call 5 段以上で到達幅過小)。収束ラウンド数を rep 出力 → **実測 2 ラウンド** (limiter)
- **D16 検出器** (`gen_globals.py`): `--window-map` 経路で map 非該当 VA の IR 型 > 8B を集計出力。**ネガコン** (`d16_detector_check.py`): 修復を外すと `global_var_<VA>[64]` → `[16]` に縮小を再現、検出器は修復有無に関わらず同条件を検出

### 13-3. 検証結果 (実測) と成果物

| 実施 | 結果 |
|---|---|
| run_all.sh 200 trial seed 1 | **exit 0**。resonator/stereo/delay が `approx 0 / maxrel 0.000e+0`、他は baseline と 1 行も差分なし |
| 1000 trial seed 7 (個別 build: limiter 37.2s / delay 46.5s / khbase 40.1s emcc) | 上表のとおり **すべて bit-exact**。wasm: resonator 65,787→**82,697 B** / stereo 111,574→**144,986 B** / delay 3,585,984→**3,602,863 B** |

成果物: `scripts/approx_probe.c` (構造推定・表抽出・全グリッド検証) / `scripts/extract_approx_tables.py` (表 base64 化+検証) / `scripts/approx_tables.b64` (3 表 49,152 B) / `scripts/verify_approx_helpers.c` (生成ヘルパ独立検証) / `scripts/d16_detector_check.py` (D16 ネガコン) / `lift/gen_simd.py` (rcpps/rsqrtps 実機表ベース) / `lift/kh_lower.py` (固定点超過反復) / `lift/gen_globals.py` (D16 検出器)

### 13-4. 未解決 (起票先付き) / 検証範囲外

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 近似表は **実機 CPU (9950X) 依存** | 別 CPU では表が違い bit-exact でない | 親 CAB-53 に次タスク提案コメント |
| resonator/stereo/delay の snapins.json `tol` 残存 (exceed 0 で実質 gate 未使用) | gate 緩いまま判定が落ちる萌芽 | 親 CAB-53 にコメント (撤去は別チケット) |
| (c) 未到達 27 関数/5,721B のシナリオ拡張は未実施 | (c) が 5 関数/8,018B のまま | 親 CAB-53 に次タスク提案コメント (要件 1 は次弾) |
| run_all.sh 一括 1000 trial は limiter/khbase/delay globals.c 1.25GB で emcc ピークメモリ大・稀に SIGKILL | 個別 build の和で担保 | 親 CAB-53 にコメント |
| 検証範囲外: wasm helper は C テーブル lookup で wasm SIMD 近似命令は未使用 (= CPU 非依存厳密実装) | — | — |
