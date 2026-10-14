# KH-4: KH 共通基盤 lift (CAB-246) + KH-6 (CAB-258) Tier-M 3 本 + CAB-56 SnapinMasterDsp ホストハーネス

- 解析日: 2026-10-11 / 担当 dir: `tools/targets/kilohearts/snapins/` (大物は `work/`, gitignore) / Linear: CAB-246 (KH-4) / CAB-258 (KH-6, parent CAB-53) / CAB-56 (KH-4b, parent CAB-13) / CAB-273 (§15, parent CAB-53)
- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (13 snap-in + **khbase** + Path A 対照 + libm 単体 + **CAB-56 ホストハーネス**。実測秒 + load average は §13-5・§15)。1000 trial / seed 7 は `TRIALS=1000 SEED=7 bash .../run_all.sh` (全 13 本 + khbase + ハーネスが 1000 trial になる)。§9/§10 の 1000 trial 数値はこの形で取得
- 既知類型 (DEFECTS.md): **D14 修復 (CAB-242) / D15 修復 (CAB-246) / D16 検出器 (CAB-258) が該当**、D2/D3/D7/D8/D9/D11 は非該当 (§15 も非該当)。検収 (=§14) も独立再計算・別アルゴリズム・ネガコン・baseline diff を実施
- 本報は KH-4 (§1〜§8) と KH-6 (§9, §11) と CAB-56 (§10) の合本。**第 2 弾 = §13** (rcpps/rsqrtps 実機近似表で Resonator/Stereo/Delay が bit-exact 化, D16 検出器化)、**第 3 弾 = §15** (CAB-273: tol gate 撤去)。既存 10 snap-in (KH-1a/1b/1c) と KH-2b (D14 修復) の詳細は前版 (git log fe57c01) を参照

## 0. 結論 (先出し)

**KH-4 (CAB-246)**: infra 188 関数 / 53,010B を実測分類 → (a) process 到達 **135 / 34,373B**、(b) Editor/Controller のみ **21 / 4,898B**、(c) 未到達 **32 / 13,739B**。(a) から既存 22 を除く新規 113 のうち **112 を lift** (khbase, KH-4 時点 24,263B。CRT atexit ランナ 0x180fe2508 は D15+trampoline 連鎖で残置)。検証 = khbase ctx-fuzz **200/200・10,500/10,500 call** (seed 1) + **1,000/1,000・52,500/52,500** (seed 7)、**UCRT powf 3,000/3,000 + 15,000/15,000**。**D15 (新規欠陥)**: stage-0 がメモリ間接 call を空ブロックとして丸ごと欠落 (5 関数・65 site) → **[icall] pass で修復**。主要な達成 = allocator / vector push_back / shared_ptr move-assign が wasm で bit-exact 動作。本改修で khbase 112 → **116 関数** (判定行は完全不変、wasm +9,634B)。

**KH-6 (CAB-258) + CAB-56**: Tier-M 3 本 — Phaser (80 fn/17,955B)・Limiter (108 fn/22,580B) = **bit-exact**、Delay (141 fn/37,914B) は当時 許容誤差 exceed 0 (§13 で bit-exact 化 → §15 で tol gate 撤去)。**(c) 32 関数中 5 関数 / 8,018B (58%) に到達・lift** (最大 0x180fc4590 double pow 5,777B)。**CAB-56**: vtable dispatch 4 種 (7,395B) を実オブジェクト契約で unit-diff → khmrel/khmaster/khmring すべて 200/200 + 1000/1000 bit-exact・D15 destroy 分岐 (class A/B) 全経路発火。**[rdataest] pass**: delay 24 base の per-VA 窓を推定、最大 cap 8192。**D16 (新規欠陥)** → 64B 既定を併用して修復。**回帰**: run_all.sh exit 0、RESULT 行 baseline と 1 行も差分なし、lic_check 70/70。**§15 (CAB-273)**: tol gate を撤去し比較を tolerance なし完全一致に統一 = 14 snap-in 全本が bit-exact 表記・1 bit 改変を FAIL 検出。

## 1. 分類表 (実測)

方法: `scripts/khbase_classify.py` (新規)。infra 188 = `tools/targets/kilohearts/work/closures_sets.pkl` (事前解析 CAB-25 の ≥8 snap-in 共有集合)。(a) = infra ∩ (既存 10 snap-in の process VA 起点直接 call closure ∪ lift セット ∪ stub 宣言集合)、(b) = infra − (a) のうち Editor/EditorModel/Controller vtable root から到達、(c) = 残り。

| 分類 | 関数数 | バイト | 内容 (代表) |
|---|--:|--:|---|
| (a) process 到達 — lift済 | 22 | 9,129B | libm closure (sincos_a/b, k_dfdb0, m_* 14種), biquad 0x180bac490, interp 0x180006500, dly 0x180020e70 |
| (a) process 到達 — **KH-4 で新規 lift** | **113** (lift 112 + 残置 1) | **22,391B (当時報 / .pdata extent 再計算では 24,263B)** | **powf 0x180fc3640 (3,782B FMA3)** + 内部 chain, **operator new/delete/calloc (0x180f878e0 / 0x180fd4f30 / 0x180fd51cc / 0x180fd66a0)**, **vector push_back 0x18004cf20**, **shared_ptr move-assign 0x180050bb0 + release walker 群**, CRT 数学 helper 群 (0x180fd2xxx〜0x180fe5xxx), _chkstk 0x180f87cd0, strtol core 0x180fd8aac |
| (b) Editor/Controller のみ | 21 | 4,898B | 0x180fc6d70 (1,782B FMA 数学), 0x180fc6870 (1,279B FMA 数学) 等 — UI/エディタ層 (KH-7) で到達 |
| (c) 未到達 | 32 | 13,739B | 0x180fc4590 (5,777B FMA 数学 = exp/pow 系と推定), 0x180fcce40 / 0x180fcc450 (FMA 数学) 等 — Tier-M の lift 時に到達見込み |

- 分類 JSON: `work/khbase/classify.json` (全 188 関数の cat/via/lifted/stub/fma/iat/indir 付き)。memmove/memset (0x181384040/0x1813846e0) は既存 shim 運用を維持 (lift 対象外)。(a) 新規 113 のうち **0x180fe2508** (CRT atexit/terminate ランナ) は `call reg → jmp [rip] trampoline → jmp rax` 連鎖で native oracle 単独実行が不可 → fail-fast stub のまま。

## 2. lift 関数表 (khbase: KH-4 時点 112 関数 / 24,263B → wasm 1,304,576B。**CAB-56/KH-6 後 = 116 関数 / 24,609B → wasm 1,314,210B** = 本章の数値は §10 の増員分を未反映。undefined import は全 13 snap-in + khbase で 0)

| 群 | 関数 (VA) | 検証 |
|---|---|---|
| 数学 lib | powf 0x180fc3640 (float,float→float, FMA3) + 0x180fdb804 + 0x180fd8bd4 + 0x180fd8988 | **直接差分 3,000/3,000 + 15,000/15,000 bit-exact** (r==0..6 の 7 導入クラス: 通常域 / 負底+整数指数 / 桁落ち境界 / 非正規境界 / オーバーフロー境界)。rdata_window 8192 必須 |
| allocator | op_new 0x180f878e0 / op_delete 0x180fd4f30 / calloc 0x180fd51cc / heap_alloc_wrap 0x180fd66a0 / 0x180fc61dc / 0x180fd662c | **直接差分 1,600/1,600 + 8,000/8,000 bit-exact** (op_new→HeapAlloc IAT shim, malloc→calloc(elem,count) 2 引数 ABI 実測)。※ 旧規約 (切り詰め・循環) の下での値。0 返却規約での再測定は #1116 |
| vector | push_back (realloc helper) 0x18004cf20 | **直接差分 2,300/2,300 + 11,500/11,500 bit-exact** — ABI 実測 (rcx=vec, rdx=end, r8=&value)。毎 push realloc = op_new + memmove shim 経路を毎回発火 |
| shared_ptr (D15 icall) | move-assign 0x180050bb0 / addref 0x180fd2c10 / release 0x180fd2c90 | **直接差分 400/400 + 2,000/2,000 bit-exact** (arena 内 fake vtable + lift 関数 target)。destroy 分岐の全経路実働は §10 (CAB-56) で完了 |
| CRT 数学/errno helper | 0x180fd2fcc / 0x180fd3144 / 0x180fd320c / 0x180fd2ba0 / 0x180fd62dc / 0x180fd6320 ほか ~20 | **直接差分 43〜45/45 bit-exact** (generic prober: 2 段 pointer chain を満たす fake object + IAT shim) |
| dint/fint | 0x180fbdd78 / 0x180fbdef4 | 直接差分 45/45 (既存 shim 実装の再検証) |
| probe 対象外 (lift のみ) | vtable dispatch 4 種 (0x18004f350 / 0x180050860 / 0x18004df70 / 0x18004d980 — 計 7,395B = .pdata extent 実測, 旧 "10,278B" は誤記), _chkstk 0x180f87cd0, gs/PEB プローブ 2 種 (実機 PEB 依存), MXCSR flag 依存 4 種, delay-load/raise 経路 ~15 種, 0x180fd8aac (strtol core) | lift + build 通過。stub fail-fast により未 coverage 経路の発火は検出可能。**CAB-56 の host harness で検証** (§10) |

- IAT shim (`gen_stubs_sigs.py` IMP_SHIM): HeapAlloc (循環 bump アロケータ, 状態はアリーナ+0x100・trial 毎 reset = native/wasm 同一進行・16B 整列・ゼロ充填。※ この「循環」説明は旧規約の記述。現行は bytes 上限・領域超過で `return 0` (カーソル不変)。0 返却規約の再測定は #1116)、HeapFree/GetLastError/SetLastError (ret 0)、Enter/LeaveCriticalSection (no-op)、FlsGetValue/FlsSetValue/TlsGetValue (アリーナ scratch 0x04000200)、IsProcessorFeaturePresent/IsDebuggerPresent/GetCurrentProcess (定数)、RaiseException/TerminateProcess (ret 1)、GetModuleHandleW 以下 (ret 0/1)。**native 側は scenario が同一意味の ms_abi shim を IAT slot へ patch** して native oracle を成立。新規 helper (gen_simd): paddq/psubq/psrad (+VEX 別名 15 種、すべて厳密 = exact) と cvtsi2ss/cvtsi2sd の 2 引数 (dest-merge) 形。kh_lower 拡張: **[icall]** (D15)、**[gs]**、wrapper の ret i32 対応、named import の declare 出力。

## 3. D15: stage-0 のメモリ間接 call 欠落 (新規欠陥 → [icall] pass で修復)

- **症状**: `call qword ptr [rax+8]` (vtable dispatch) の IR ブロックが空 (pc store のみ)。vtable load と `mov rcx,obj` は残るため、call だけが無言で消える。`call reg` は解決済 (D15 はメモリ間接のみ)。
- **実測**: khbase 113 関数中 5 関数・65 site (0x18004f350×42 / 0x18004df70×11 / 0x180050860×7 / 0x18004d980×3 / 0x180050bb0×2)。全て shared_ptr/notify 系の vtable dispatch。
- **修復**: kh_lower [icall] pass — 空ブロックの機械語を capstone で読み (reg, disp) を復元 → `%slot = @reg + disp` → `call i64 @kh_icall(i64 %slot)` (callret fixup 付き)。kh_icall (C, 自動生成) は slot < 0x10000000 (アリーナ) なら実値を読み lift 済 callee へ switch、PE .rdata vtable slot は build 時逆引き map、未知は fail-fast。**検証**: SP_MOVE (0x180050bb0) の arena fake vtable unit-diff **400/400 bit-exact**。destroy 分岐の全経路実働は §10/CAB-56 で解消 (class A 500+520, class B 54 hit)。**意義**: KH-6 以降の snap-in (vtable dispatch を含む) と SnapinMasterDsp ホストハーネス (CAB-56) の必須前提。CAB-55 検出器への「空ブロック × メモリ間接 call」機械チェック追加を推奨 (DEFECTS.md)。

## 4. rdata_window の第 3 実例 (powf) と自動推定

powf は 2^t 分解表 (log2 仮数→index) を可変 index で読む。**窓 2048 で 4/3000 が O(1) 差分 (want 11.98 got 7.29 等)、窓 8192 で 3,000/3,000 bit-exact** — D14 (sincos 256) / KH-1c (log10f 2048) と同型の第 3 実例。wasm は 644KB → 1,320KB (+676KB = 窓拡大分)。~~**自動推定 pass は未実装**~~ → **§9-2 で実装済み**。設計: (1) `lea reg,[rip+X]` の表 base 収集、(2) base を使う load の到達幅 (`disp + mask×scale + opsize`) 集計、(3) `cmp reg,imm`/`and` の index 上限、(4) 決まらない場合は PE の次シンボル境界まで。D11/D14/powf の 3 実例で必要窓は 256/2048/8192 と桁違い = 手動設定は破綻の温床。

## 5. 制限 / 未達

1. ~~**vtable dispatch 4 種 (7,395B) の直接差分なし**~~ → **§10 (CAB-56) で解消**: 実オブジェクト契約をアリーナ上に構築し 3 scenario で 200 + 1000 trial bit-exact。destroy 分岐 (class A/B) も全経路発火済み。
2. **MXCSR exception-flag 非追跡**: native は FP 演算で flag が蓄積し CRT matherr helper (0x180fd5bf4 / 0x180fd662c / 0x180fe5ef0 / 0x180fd8d24) がそれを参照。wasm は定数 0x1f80 を返す shim のため 4 関数は probe 対象外 (flag 追跡は下流)。**CRT 初期化前提の遅延バインド** (UCRT encoded-pointer 機構): `__crt_state` の cookie デコード (0x180fe27b0 等) は CRT init で再エンコードされるため native 単独実行が不可。0x180fe2508 を含む ~15 関数は lift のみ (fail-fast stub)。
3. **gs/PEB**: [gs] pass はゼロ初期化エミュレート (StackLimit=0 → probe 不発 = 実機と分岐一致)。PEB を読む CRT OS プローブ 2 関数 (0x180fd0a98 / 0x180fe027c) は実機依存のため probe 対象外。
4. **直接差分 34 関数 / 間接 78 関数**: khbase 112 のうち直接 fuzz は 34。残りは lift + build 通過 + 呼び枝経由で発火 — 個別 coverage 測定は未実施 (関数カウンタ埋め込みは下流案)。~~**rcpps 完全エミュレート未実装**~~ → **§13 で達成** (142 関数中 4 箇所・すべて 0x180289ea0 内)。native oracle = 実機 Ryzen 9 9950X・IAT を同意味 ms_abi shim へ patch して直接実行。
5. **undefined import 0 (訂正)**: 旧版は「khbase のみ env.exit 1」としていたが、実測では **khbase / phaser / delay / limiter すべて 0** (fail-fast stub 化で消えた)。旧 values (112 fn 時点) は wasm 1,319,920B / undefined 1。

## 6. ユーザ依頼事項: なし (素材・認証とも不要) / §7. 成果物 (追加・変更)

`scripts/khbase_classify.py` (分類)、`snapins.json` (khbase lift 112→**116** + phaser/delay/limiter・rdata_window 8192)、`harness/scen_khmath.h` (khmath 統合 + native IAT patch + arena ヒープ shim)、`harness/{scenarios.c,scenarios_kh.c}`、`lift/kh_lower.py` (**[icall]/[gs]/[rdataest]**・ret i32 wrapper・named import declare・kh_icall 生成)、`lift/gen_stubs_sigs.py` (named-import shim + arena ヒープ)、`lift/gen_simd.py` (paddq/psubq/psrad/VEX 別名 15 種・cvtsi2 dest-merge・mxcsr・**sqrtps/sqrtpd/pcmpeq*/pcmpgtd/pmovsxdq**・**rcpps/rsqrtps 実機表**)、`lift/gen_globals.py` (**--window-map** + D16 修復・検出器)、`lift/build.py` (icall.c 入力追加)、`scripts/make_table.py` (13 本 + khbase、**§15 で判定を実測由来に変更**)、`run_all.sh` ([2] 13 本 + [4c] khbase + **[4d] CAB-56**)、`scripts/leafscan.py`、`DEFECTS.md` (D15 + D14 窓実績 + **D16**)。`work/khbase/` (gitignore)。**§15 (CAB-273) 追加分**: `harness/compare.mjs` (tol 撤去)、`scripts/{tol_removal_check.py, negcon_1bit.py, negcon_table.py, tol_negcon.sh}`、`scripts/acc_replay.mjs`・`acc_independent.sh`・`run_all.sh` の注記更新。

## 8. Tier-M への引き継ぎ状況 — 3/5/6 は解消済み

1. **khbase の使い方**: snapins.json に新 snap-in を追加し lift に process + 固有 closure を書くだけ。共通基盤 (powf/allocator/vector/notify) は khbase の pass セットがそのまま適用される。vtable dispatch を含む関数は [icall] が自動修復する (空ブロック検出は自動)。**heap**: allocator IAT shim はアリーナ+0x100 を状態に使い trial 毎 reset — 新 scenario も冒頭で `A(0x110)` して cell を確保する慣習を踏襲すること。
2. ~~**notify/dirty 経路** の unit-diff 未実施~~ → **§10 で解消済み** (khmaster/khmring 実オブジェクト契約)。~~**rdata_window 自動推定**~~ → **§9-2 の [rdataest] pass で実装済み**。§13-2 で固定点超過反復化。
3. **MXCSR flag / CRT init / PEB**: §5 の 3 制限はホストハーネス設計 (CAB-56) と lift 語彙拡張に持ち越し。~~**CAB-53 進捗**~~ → KH-1a/1b/1c (10 本) + KH-2b + KH-4 + **KH-6 (3 本) + CAB-56 ハーネス** 完了。残りは CAB-60 の中位〜難 snap-in (§11)。

## 9. KH-6 (CAB-258): Tier-M snap-in 3 本 (Phaser / Delay / Limiter) — 新規 lift 329 関数・(c) 到達 5 関数

1 コマンド再現 `bash tools/targets/kilohearts/snapins/run_all.sh` (既定 200 trial / seed 1)。Linear: CAB-258 (parent CAB-53)。前提 = KH-4 (commit 9e175e8) + [icall]/[gs] pass。

| snap-in (id) | process VA | B | lift fn / 合計B | wasm B | undefined | 200 trial | 1000 trial (seed 7) | 判定 |
|---|---|--:|--:|--:|--:|---|---|---|
| Phaser (ksph) | 0x1807270d0 | 2172 | 80 / 17,955 | 345,220 | 0 | 200/200・1,100/1,100 call | **1000/1000・5,500/5,500** | **bit-exact** |
| Delay (ksdl) | 0x1802ed7f0 | 3291 | 141 / 37,914 | 3,585,984 | 0 | 200/200・1,299/1,299 call | **1000/1000・6,499/6,499** | 許容誤差 (§9-4 → §13 で bit-exact 化 → §15 で tol 撤去) |
| Limiter (kslt) | 0x1804e8500 | 1980 | 108 / 22,580 | 438,170 | 0 | 200/200・1,100/1,100 call | **1000/1000・5,500/5,500** | **bit-exact** |

- **scenario は slot13 (prepare) / slot14 (process) / slot15 (reset) の 3 エントリを混在させる** (Delay は setfs/delay-line 確保・Limiter/Phaser は sync/bands 変化で ramp 再計算)。通知 vector・dirty フラグ・AudioBuffer (L/R/n + f64 sample rate) も bit 突合対象。Delay は 0x1802ed640 (dl_prepare) が `op_new[]` で delay line 2 本を確保 (fs=8000 → cap 65,536 × 4B = 256KB × 2)、tap_add 0x1802ecfc0 が obj+0x198 を加算先にする実オブジェクト契約を scenario で再現。**vec push の満倉 realloc 経路 (0x18004cf20)** も end を 0..64 slot に散らして発火。

### 9-1. (c) 未到達 32 関数の到達・lift (KH-4 §1 の (c) 解消の第 1 例)

| 関数 | B | 内容 | 到達経路 / 動的確認 |
|---|---:|---|---|
| **0x180fc4590** | **5,777** | **double pow (FMA 14)** = `pow(1-x, n)` 形の平滑化 | limiter slot13 0x1804e8340 / delay slot13 0x1802ed790 (各 555 / 1,000 回) |
| 0x180fcce40 (+内部 0x180fcd400 472B・tail 0x180fdc858 18B) | 1,949 | double tan (biquad 設計の `tan(f/fs)` 引数) | delay process 0x1802ed7f0 (3,999 回・分岐 n>0 で常通) |
| 0x180fbdb6e0 | 292 | pow 内部 (strtol thunk 0x180fd8aac への分岐) | 0x180fc4590 から (同行) |
| 計 | **8,018** | (c) 13,739B の **58.4%** | 残り 27 関数 / 5,721B |

- **単体差分**: pow (0x180fc4590) 5,012 ケース・tan (0x180fcce40) 6,011 ケースを native (実機 IAT 無し直接 call) と wasm で突合 → **両者 bit 一致** (負底・非整数指数・NaN・±0・指数 1e306 級を含む)。

### 9-2. rdata_window 自動推定 [rdataest] pass (KH-4 §4 設計案の実装 = 半自動)・9-3 新規 SIMD 語彙 (gen_simd)

kh_lower が各関数の機械語を持つことを利用し、(1) `lea reg,[rip+X]` の表 base 候識、(2) base を使う load の到達幅 (`disp + mask×scale + opsize`、`and idx,imm` から index 上限を取得)、(3) **call 辺を跨ぐ base 伝播** (arg reg への base 束縛を callee の `[rcx+idx*8]` 読出しに伝播) で per-VA 窓幅を推定。精密推定不能な base は「次参照 VA までの gap + 64B」に倒す。**9-3** sqrtps / sqrtpd (IEEE 正確, 4 lane / 2 lane)・pcmpeqd / pcmpeqq / vpcmpeqq / pcmpgtd (全 1 = mask)・pmovsxdq (符号拡張 2 dword → 2 qword)。いずれも厳密演算なので近似判定は不要。

### 9-4. Delay の許容誤差判定 (rcpps) — 数値根拠 (legacy: → §13 で bit-exact 化 → §15 で tol 撤去)

delay closure 142 関数の近似命令は rcpps 4 箇所のみ (すべて 0x180289ea0)。wasm 側が IEEE の 1/x だったため実機近似表との差が伝播し、純相対 gate 超過は 185 / 1,271,000 word (0.015%)、絶対誤差は 1 ULP (2⁻²²) で頭打ち。したがって snapins.json の delay `tol` に tap へ absFloor 1e-6 を設定して exceed 0 としていた。**§13 で実機近似表を移植したため approx 0 / bit-exact に移行。**

## 10. CAB-56: SnapinMasterDsp ホストハーネス — vtable dispatch 4 種の実オブジェクト契約 unit-diff

対象 = KH-4 で「直接差分なし = ホストハーネスで検証」と残置した 4 関数・7,395B (master オブジェクトをアリーナ上に構築)。scenario 登録は `scenarios_kh.c` に分離 (native_ref_kh バイナリ) — 既存 scenarios.c の行は不変。

| scenario | 対象 (VA) | 契約 | 200 trial | 1000 trial |
|---|---|---|---|---|
| **khmrel** | sp_release 0x18004f350 (小路線) + sp_destroy_walker 0x180050860 | dirty record 配列 (span<0x401 = ≤32 record / ≥0x401 = 大路線) + fake vtable | **200/200・600/600** | **1000/1000・3,000/3,000** |
| **khmaster** | dirty_notify 0x18004df70 + param_map_notify 0x18004d980 (interp driver 0x180006500 経由) | master (0x2e00) + 201 dirty record + route table 100 本 + ctrl block + obj2 | **200/200・400/400** | **1000/1000・2,000/2,000** |
| **khmring** | ring driver 0x1804faa80 | master + ring bank 5 本 (128 slot × 16B) | **200/200・200/200** | **1000/1000・1,000/1,000** |

- **D15 destroy 分岐の全経路**: ctrl block の vtable slot +8 = destroy / +0x10 = delete (op_delete 実物, HeapFree IAT shim) を dispatch。destroy は **class A (ctx_set2f 0x1800fb8f0, r9d でアリーナ内 +0x768/+0x780 に書込)** と **class B (0x180f87f24, r9 が野生ポインタ)** の 2 種を切替え、小路線 (A) と大路線後半 (B) の両方を発火。refcount/weakref 0〜7 を振って replace/remove/append を踏む。**native oracle は IAT patch 方式**: scen_khmaster.h が 20 種の IAT slot を同意味 ms_abi shim に差替え + 0x5000000 に 1MB ヒープ域を mmap + ARCH_SET_GS でゼロ TEB 設定 ([gs] の wasm ゼロ初期化と同一)。**wasm 側は patch 不要**。
- khbase lift 112 → **116 関数** (+2,218B、.pdata extent 実測: interp 145B / ring driver 163B / getshared 30B / route map get 8B)。**判定行は完全不変**、wasm 1,304,576 → **1,314,210 B (+9,634 B)**。0x1800065e0 (8B) は `scripts/leafscan.py` で HeartCore 全 .text から発見した leaf (KH-4 分類では (c) だったため同時に解消)。

## 11. 引継ぎ (次タスク) — §12 (V27 検収) は §14 に統合したため削除

~~**rcpps の完全エミュレート**~~ → **§13 で達成** (実機表 3 × 4,096 で 3 本が bit-exact 化、gate 未使用のまま解消)。~~**rdataest の精度向上 + D16 検出器化**~~ → **§13-2 で達成**。**CAB-60 の中位〜難 snap-in**: (c) 残り 27 関数 (5,721B) と Ladder / Slice EQ / Filter Table (AVX・FMA 427) は report §4 の難度表に従い未実施 (§13-4 起票先 = 親 CAB-53)。

## 12. KH-16 (#779): VEX-256 / FMA 語彙の実測 (語彙追加の前段)

語彙は推定で足さず、難 4 本の snap-in 固有 closure (`closures_sets.pkl` の unique) を capstone で全命令走査して決める。再現手順 (上流の順序・検証起点 commit `a44f819c`・すべて `tools/targets/kilohearts/` から実行): (1) installer 抽出で `work/winpkg/HeartCore.core_64` を作る (素材 = `plugins-kilohearts` の `Kilohearts Offline Installer.zip`。`scripts/extract_installer.sh` の `KH_SRC` 経由、Windows 側は `payload.dat` → `windows.zip/*` → `winpkg/`) → (2) `python3 scripts/rtti_walk.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json` → (3) `python3 scripts/callgraph.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json work/callgraph.pkl` → (4) `python3 scripts/closures.py work/callgraph.pkl work/rtti_vtables.json work/closures.json` (`work/closures_sets.pkl` を出力) → (5) `python3 snapins/scripts/vex256_census.py --json work/vex256_census.json` → (6) `python3 snapins/scripts/vex256_recount.py` (表の数え直し)。依存 = capstone・pefile・numpy。

- **数え方 (現行 filter)**: unique closure の各関数の全命令を走査し、(a) オペランドに `ymm` を含む命令、または (b) mnemonic が `v` で始まる VEX 符号化命令 (xmm 形を含む) を 1 件と数える。`vex256_census.py` の `total` は **snap-in ごとの重複を含む合計** (同じ VA が複数 snap-in の closure に入ると、その数だけ数える)。VA 一意数はその下の `vex256_recount.py` が出す (本 run は 673)。ymm 命令数 (`ymm-operand instructions`) は filter によらず `ymm` 判定のみで決まる。
- **測定 commit の表記**: 本節の生出力は commit `f354504c` の filter で取得した (2026-10-13 18:33 UTC・素材 `plugins-kilohearts` 付き run で再現)。`cf7b36a7`→`e0c79165`→`f354504c` の間で filter 条件 (`is_ymm` / `startswith('v')`) は変わっていない (`git show <commit>:…vex256_census.py` で確認)。census・recount・negcon の全生出力は [REPORT_APPENDIX.md](REPORT_APPENDIX.md)。
- **検証状況 (再現 HEAD `f354504c`・素材 `plugins-kilohearts`)**: `HeartCore.core_64` = 76,642,304 B (sha256 `d55ce8b4…1441e`) ・`rtti_walk` = typedescriptor 6,923 / vtable 付き class 6,307・`callgraph` = 120,856 関数 (7.1 秒)・`closures` = infra 188。`vex256_census.py` rc 0 (0.36 秒)・`vex256_recount.py` rc 0・`vex256_negcon.py` rc 0。closure の飛ばし件数は census・recount とも **0 件** (`skipped … total 0`)。
- **実測 (`f354504c` の filter・重複込み)**: mnemonic **54** / 合計 **917** / VA 一意 **673** (snap-in 間で共有 244)。ymm 形は **Convolver 40 / Filter Table 40 / Ladder 0 / Slice EQ 0** (計 80)。**vblend\*/vperm\* は xmm・ymm いずれも 0 件** (census の全 `v*` 走査・recount の `[]` で確認)。
- **ネガティブコントロール (f354504c で再現・素材不要・`snapins/scripts/vex256_negcon.py`)**: 既知の VEX 符号化 7 命令 (合成バイト列、capstone 5.0.7、全バイト消費を assert) に対し、現行 filter は 7 件検出、旧 filter は 3 件検出。旧 filter で漏れるのは `vblendps` xmm / `vblendvps` xmm / `vpermilps` xmm / `vaddps` xmm の 4 件 (新 filter のみ検出)。`vperm2f128` ymm と `vaddps` ymm は両方で検出。これにより「xmm 形 `vblend*` / `vperm*` は 0 件」の否定結果は、filter が当該命令を検出できることを前提に読む。
- 下表は `f354504c` の生出力 (`vex256_recount.py`) の転記。ymm 形の値 (旧 filter の表と同じ) であり、xmm 形は含まない。

| mnemonic | Convolver | Filter Table | Ladder | Slice EQ | 合計 |
|---|--:|--:|--:|--:|--:|
| `vmovaps` ymm (`ymmword`) | 20 | 20 | – | – | 40 |
| `vmulps` ymm | 8 | 8 | – | – | 16 |
| `vaddps` ymm | 6 | 6 | – | – | 12 |
| `vsubps` ymm | 6 | 6 | – | – | 12 |
| `vfmadd213sd` (xmm) | – | – | 7 | 3 | 10 |
| `vfmadd213ss` (xmm) | – | 3 | – | 3 | 6 |
| `vfmsub213ss` (xmm) | – | 2 | – | 2 | 4 |
| `vfmadd231sd` (xmm) | – | – | 2 | – | 2 |
| `vfmadd231ss` (xmm) | – | 1 | – | 1 | 2 |
| `vfnmadd231sd` (xmm) | – | – | 1 | 1 | 2 |
| `vfmadd132sd` (xmm) | – | – | 1 | – | 1 |

- **xmm FMA (`vf*`) 計 27 件** (Ladder 11 / Filter Table 6 / Slice EQ 10 = 上表の `vf*` 行の合計)。
- **語彙の対象 (f354504c の census 結果に基づく・PM 判断 2026-10-13 に従う)**: census で `vblend*` / `vperm*` は 0 件と確定したため、#779 の語彙追加対象から外し、**ymm (`vaddps` / `vmulps` / `vsubps` / `vmovaps`・Convolver と Filter Table のみ) と vfmadd 系 (xmm・scalar) に絞る**。
- **未解決**: ymm 命令の lift (RetDec が ymm を `i256` の `__asm_v*` として出すか、gen_simd の declare 駆動で扱えるか) は未確認。`gen_simd.py` の VEX 別名表は xmm 形のみで、ymm 形の意味 (`vaddps` 等の 8 lane・upper lane 規則) は未実装。`vfmadd*` の scalar 形は既存 `gen_simd.py` で対応済み。
- **受入条件の残り**: 語彙追加 (ymm)・既存 14 snap-in のハッシュ不変・語彙ごとの bit-exact テストとネガコン・run_all.sh 再実行は未実施。起票先 = #779 (ymm・bit-exact・ハッシュ不変は #779 に残す。#250 LIFTLIB には振らない)。後続: #709 (KH-14) は #779 完了後に着手 (PM が `blocked_by` 登録済み)。

### 12-1. ymm 語彙 vaddps / vsubps / vmulps の実装と単体検証 (#779 第 2 弾)

- **生成形 (実測)**: `retdec-decompiler -m raw -a x86-64 -e little` に `c5 f4 58 c2` (vaddps ymm0,ymm1,ymm2) を通すと `call i256 @__asm_vaddps(i256 src1, i256 src2)`。`gen_simd.py` は i256 宣言を `OUT.c.i256.ll` の LLVM IR 定義 (bitcast i256→`<8 x float>`・fadd/fsub/fmul・bitcast 戻し) で出す。C に i256 の正体型が無いため IR で定義し、呼出側と ABI を揃える。`build.py` は `.i256.ll` がある時だけ emcc 入力に加える。未対応の i256 宣言は `undefined` に報告する。
- **本検証** `python3 snapins/scripts/ymm_vocab_check.py 20000 1` (測定 commit `3d51fd7a`・oracle = ホスト AVX2 `_mm256_*_ps`・32B 全 bit 比較・NaN 含む): vaddps / vsubps / vmulps 各 20,000 call・160,000 lane **mismatch 0**。1.3 秒・load 0.21 0.29 0.22 (nproc=4)。
- **ネガコン**: (a) 語彙定義を外す → リンク失敗 (FAIL)。(b) vaddps の fadd を fsub に変える → mismatch **19,971 / 20,000** (FAIL)。
- **回帰**: i256 を含まない 9 宣言の入力で、旧 gen_simd と新 gen_simd の C 出力・report が `cmp` 一致。HEAD で build が通る 14 本は i256 宣言を含まない (旧版は i256 宣言で `KeyError` して落ちるため。推論)。**run_all.sh の 14 本ハッシュ照合は未実施**。
- **測定 commit `3d51fd7a` → HEAD のコード差分** (`git diff 3d51fd7a HEAD -- lift harness scripts`): 0 行 (以降の追記は REPORT.md のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 14 snap-in のハッシュ不変 (run_all.sh) 未実行 | 構造上は不変 (推論)・実測なし | #779 |
| ymm 語彙を snap-in の lift へ接続 (kh_lower の 256-bit 表現・vmovaps ymm・Convolver/Filter Table) | 難 snap-in は未 lift | #709 (KH-14) |
| vfmadd / vblend / vperm の ymm 形・vmovaps ymm の語彙 | 受入条件 1 の残り | #779 |

## 13. KH-6 第 2 弾 (CAB-258 続, 2026-10-11) — rcpps/rsqrtps 実機近似表で Resonator/Stereo/Delay が bit-exact 化

起点 `8efb7a0`。既知類型 (DEFECTS.md): **D16 該当** (§13-2)、D2/D3/D7/D8/D9/D11/D14 非該当。前提: rcpps/rsqrtps の結果は CPU 内蔵近似表で仕様 (SDM) は相対誤差 ≤1.5·2⁻¹² しか保束せず、旧 wasm 実装 (IEEE の 1/x) との差が CAB-224 以来の許容誤差 gate の原因だった。

| 対象 | 変更前 (legacy tol 判定, V27 検収) | 変更後 (本弾) |
|---|---|---|
| Resonator | 許容誤差 (legacy) approx 140,067 / maxrel 2.778e-1 | **approx 0 / maxrel 0.000e+0, 1000/1000・4,999/4,999** |
| Stereo | 許容誤差 (legacy) approx 827 / maxrel 2.894e-5 | **approx 0 / maxrel 0.000e+0, 1000/1000・4,999/4,999** |
| Delay | 許容誤差 (legacy) approx 3,052 / maxrel 3.591e-2 | **approx 0 / maxrel 0.000e+0, 1000/1000・6,499/6,499** |
| 既存 10 + Path A + qemath/qebig + khbase + CAB-56 | baseline | **1 行も差分なし** (limiter/phaser も 1000/1000・5,500/5,500)、lic_check **70/70** |

### 13-1. 近似表の構造 (実測) と検証

`rcpps : result = sign | ((253 - e) << 23) | T_rcp[m]` (253-e <= 0 → ±0) / `rsqrtps: result = sign | ((190 - ((e+1)>>1)) << 23) | T_rsq[odd/even][m]` (1/sqrt(2^k) で指数非線形 = √2 因子で 2 表)。特殊値 = ±0/非正規 → ±Inf / NaN → quiet NaN / ±Inf → ±0 / rsqrtps 負有限値 → NaN。e = exponent field, m = mantissa 上位 12bit (下位 11bit は実測 0/2048 differ = 無影響)。表 = **3 × 4,096 × 4B = 49,152 B**。

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
| 1000 trial seed 7 (個別 build の emcc_sec は §13-5) | 上表のとおり **すべて bit-exact**。wasm: resonator 65,787→**82,697 B** / stereo 111,574→**144,986 B** / delay 3,585,984→**3,602,863 B** |

成果物: `scripts/{approx_probe.c, extract_approx_tables.py, approx_tables.b64, verify_approx_helpers.c, d16_detector_check.py}` / `lift/gen_simd.py` (rcpps/rsqrtps 実機表ベース) / `lift/kh_lower.py` (固定点超過反復) / `lift/gen_globals.py` (D16 検出器)。

### 13-4. 未解決 (起票先付き) / 検証範囲外

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 近似表は **実機 CPU (9950X) 依存** | 別 CPU では表が違い bit-exact でない | 親 CAB-53 に次タスク提案コメント |
| ~~resonator/stereo/delay の snapins.json `tol` 残存 (exceed 0 で実質 gate 未使用)~~ → **§15 (CAB-273) で撤去済み** | gate 緩いまま判定が落ちる萌芽 | 解消 (CAB-273) |
| (c) 未到達 27 関数/5,721B のシナリオ拡張は未実施 (c) が 5 関数/8,018B のまま / run_all.sh 一括 1000 trial は globals.c 1.25GB で稀に SIGKILL | 個別 build の和で担保 | 親 CAB-53 にコメント |

### 13-5. 実行時間の実測 (規則 38: 実測秒 + load average・n を併記)

| 実施 | 実測秒 | load average (開始 → 終了, nproc=16) |
|---|---|---|
| run_all.sh 200 trial / seed 1 (n=2, キャッシュ有り) | **376・384** (min–max) | 2.39 2.33 5.98 → 4.06 3.67 5.34 / 1.52 3.50 3.60 → 11.50 5.91 4.42 |
| run_all.sh 1000 trial / seed 7 (n=1) | **453** | 8.83 6.54 4.76 → 17.22 11.73 7.36 |
| emcc 個別 build (n=3 min–max) | limiter **35.4〜46.3** / delay **37.4〜51.0** / khbase **34.7〜45.8** | — |
| baseline (\`8efb7a0\`) 200 trial (n=1) | **696** (HeartCore 抽出込み) | — |

## 14. 検収 (独立再計算, 2026-10-11・CAB-242/243/246/258 一括)

起点 `0d5117c` (HEAD と snapins ツリー同一・`git diff 0d5117c HEAD -- snapins` = 0 行)。既知類型 (DEFECTS.md): **D14 修復 (CAB-242) / D15 修復 (CAB-246) / D16 検出器 (CAB-258) が該当**、D2/D3/D7/D8/D9/D11 非該当。

**独立再計算 (規則 37)**: 自分で native oracle を生成 (`work/native_ref_acc`、vectors は **別人名 `myvec_*`** で作り直し = `build.py` の `vec_` キャッシュ非依存) + KHV2 を Python で解析 (`scripts/acc_khvec.py`) + 自分で replay・突合 (`scripts/acc_replay.mjs`)。`harness/compare.mjs` とは別実装で、**tol gate を持たない = 常に全バイト exact 比較**。実行 `bash scripts/acc_independent.sh [TRIALS] [SEED]` (既定 200 1)。結果 (firstDiff = null): **13 snap-in + khbase + CAB-56 の全 scenario が 200/1・1000/7 で全 call bit-exact**。khbase は seed 42 でも 52,500 call 一致、Formant は 1000/42 でも 4,999/4,999。

| チケット | 独立再計算結果 |
|---|---|
| CAB-242 | qebig (sincos_a + k_dfdb0) seed 1/7/42 × 200/1000 trial = **86,400 call 全 bit-exact** (主張の 52,800 を含む)。`sincos_a(x)` を Python `math.sin` と別比較 → 2,290/2,400 exact bits, 残りは全て ≤1 ULP = native oracle が junk でない実測 |
| CAB-243 | Formant 200/1・1000/7・1000/42 = 200/200・999/999 と 4,999/4,999 ×2, wasm **405,390 B** / undefined **0** |
| CAB-246 | 分類 **135 / 21 / 32** (188 関数 / 53,010 B)・khbase lift **116 関数 / 24,609 B**・powf **3,000/3,000 + 15,000/15,000**・ctx-fuzz **10,500 + 52,500 call**・[icall] **65 site**・op_new 8,000 / vector 11,500 / SP_MOVE 2,000 call bit-exact |
| CAB-258 | rcpps/rsqrtps 表 **49,152 B / 12,288 エントリ**・グリッド **1,040,384 + 乱数 500,000 不一致 0**・gen_simd 生成 C のホスト検証 **1,048,576 + 500,000 不一致 0**・rdataest **収束 2 ラウンド**・D16 検出器 + ネガコン PASS |

**ネガティブコントロール (規則 41・主因を 1 件ずつ壊す)**: ① quickeq の `rdata_window`/`rdata_est` を外して窓 64 B 相当に戻す (D14 再現) → qebig **0/200** (want `3fe1778cae83c69b` got `3fef179225980ce8`) = 窓が主因。② 窓 256 + `--skip vshift` → **4,800/4,800** = vshift は防御 (発火差 0)。③ 近似表 1 エントリ (`kh_at_rcp[100]` +1) → grid mismatch **391** (rcp) / rsqrt **0** = 表照合が実機に紐づいている。④ D16 修復を外す → `global_var[64]` → **`[16]`** に縮小を再現し検出器は同条件を検出。**baseline 差分 (CAB-258「1 行も差分なし」の検証)**: `git worktree add --detach work/wt_base_8efb7a0 8efb7a0` で親ツリーを展開し `run_all.sh` 200/1 を再実行 (exit 0, 696 s)。RESULT 行 23 本の diff = **ちょうど 3 行** — resonator / stereo / delay のみ (approx 140,067→0・827→0・478→0 + wasm 拡大分)。他の 20 行 (既存 10 本 + Path A + qemath/qebig + khbase + CAB-56) は **差分 0 行**。lic_check (license/ は読取のみ) **ok 70 / fail 0**・license/ 改変 0 行。

## 15. CAB-273 (2026-10-11) — tol gate 撤去: 比較を tolerance なし完全一致に統一

起点 `49f7dd4`。本改修 = commit `5d0d321` (初回 `e407a4f` は**他セッションの共有ワークツリーへの `git reset` で消えた**ため同内容を再コミット。差分は `git diff e407a4f 5d0d321 -- snapins` = 0 行で確認済)。既知類型 (DEFECTS.md): **該当なし** (lift/IR は不変 = ハーネス判定層のみの改修)。撤去 = ① `harness/compare.mjs` の `--tol` 相対誤差 gate (`|a-b| > 1.6·2⁻¹²·max(|a|,|b|) + absFloor`、CAB-224 由来)・② `snapins.json` の `tol` (resonator 5 region / stereo 4 / delay 5)・③ `lift/build.py` の tolarg/tol.json 生成・④ `scripts/make_table.py` の「`cfg['tol']` の有無 → 許容誤差/bit-exact」判定 (→ 実測に変更)。撤去後は比較が常に全バイト strict 一致 = 14 snap-in すべて `bit-exact` 表記 (§13-4 の tol 残存は解消)。

| 検証 | 実測 |
|---|---|
| `python3 scripts/tol_removal_check.py` | **OK**: `tol` キー **0** 件・`--tol` 解析 **0** 件・build.py tol 経路 **0** 件・make_table `c.get('tol')` **0** 件。HEAD の snapins.json との差分 = **tol キー削除のみ** (tol-stripped ツリー相等)。**[6] 独立再計算**: `work/<n>/s0/stat.json` 14 本の実測を数え直し = not-exact **0**・legacy tol タグ **0**・欠落 **0** |
| `bash run_all.sh` 200/1 (n=2) | exit 0・**413・423 s** (load 2.95 3.28 3.69 → 16.12 10.31 6.43、nproc=16 直列)。RESULT **23 本** の baseline (`49f7dd4`) との diff = **ちょうど 3 行** = resonator/stereo/delay の `[tolerance]` タグ消滅のみ (trial 200/200・call 999/999・1299/1299・wasm B は不変) |
| `TRIALS=1000 SEED=7 bash run_all.sh` (n=2) | exit 0・**400・423 s** (load 7.17 12.33 10.06 → 4.54 7.45 8.60)。13 snap-in + khbase がすべて 1000/1000 bit-exact (delay 6,499/6,499・khbase 52,500/52,500・qebig 4,800/4,800 = KH-2b sincos を含む)。Path A clipper のみ 0/1000 (消失コードの意図的負の対照) |
| lic_check (`license/` は読取のみ) | `cd ../license && node lic_check.mjs work` = **ok 70 / fail 0**・license/ 改変 0 行 |
| ネガコン (規則 41) `bash scripts/tol_negcon.sh` | **FAIL=0**。① 1 bit 改変 (`negcon_1bit.py`): 旧 tol 領域 1 byte の最下位 bit を XOR (改変バイト数 = 1) → strict は **exit 1 / trials 199/200** で FAIL 検出 (resonator `histR+0x0`・stereo `bufR+0x0`・delay `tap+0x20`)、未改変は exit 0。**同一改変を HEAD 版 `--tol` で再判定すると exit 0 = gate が吸収** (maxrel 7.365e-8・9.198e-8・**1.000e+0**、maxabs 1.192e-7・1.863e-9・**1.401e-45**): delay は tap の denormal 1.401e-45 の 1 bit 差 (相対誤差 100%) を absFloor 1e-6 で PASS していた。② `negcon_table.py`: 親 `8efb7a0` の実測 (approx 140,067/827/478) を埋めた snapshot → 判定列 `許容誤差(legacy)` (bit-exact と誤表示しない)。現行 14 本はすべて `bit-exact` |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| /tmp (tmpfs 3.7GB) の emscripten_temp が `Disk quota exceeded` で一括再実行が失敗 (TMPDIR=`work/tmp` で解消)・一括 1000 trial は globals.c 1.25GB で稀に SIGKILL | 個別 build の和で担保 | 親 CAB-53 にコメント |
| 検証範囲外: 別 CPU での strict 比較は未実施 (§13-4 の「wasm helper は C テーブル lookup・SIMD 近似命令不使用」も適用。legacy gate の再現は HEAD 版 compare.mjs を `work/` に展開する形・work/ は gitignore) | — | — |

### 1116 HeapAlloc 過大要求・領域超過の 0 返却 (未検証の残り)

- 変更: `lift/gen_stubs_sigs.py` の `HEAP_C` と `harness/scen_khmath.h` `n_HeapAlloc` / `scen_khmaster.h` `khb_HeapAlloc` を同じ規約 (1MiB 超・領域超過で `return 0`、cursor 不変) に揃えた。
- 実測 (HEAD 19cdf357、gcc -O0 x86_64 ホスト): `python3 tools/targets/kilohearts/snapins/harness/heap_alloc_diff.py` → `total=32 mismatches=0` (exit 0)。
- 未実施: `run_all.sh` による 13 本 + khmrel/khmaster/khmring の bit-exact 突合、RetDec lift、emcc 再ビルド。理由は素材不足 (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ = FL Studio インストーラー 1 本。`plugins-kilohearts` / `toolchain-retdec` / `toolchain-emsdk` 無し)。#1116 で継続。
