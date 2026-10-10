# RetDec lift の silent miscompile 類型 (CAB-55 検出器入力) — Kilohearts snap-in 6 本で観測

- 凡例: **既知** = Gain PoC / M5〜M9 で既出と同型、**新規** = 本タスクで初観測。層: `fe` = RetDec frontend (capstone2llvmir; stage-0 で既に欠陥) / `opt` = RetDec 内部最適化 (stage-0 は正しい) / `ours` = 我々のパイプライン/ハーネス。
- 検証: 各行の「証拠」は `work/<snap-in>/abl_*` の ablation (200 trial, 一致 trial 数)。

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D1a | fe | 既知 (P1 同型) | jcc が *無関係な直前 cmp* の cf/zf を読み誤分岐 | `ucomis{s,d}`/`comis{s,d}` は `call void @__asm_ucomiss` + `store i64 undef, @rflags` のみで @cf/@zf/@pf を更新しない | Channel Mixer/Gain: flags 無し 1/200 | `__asm_(u)comis*` の後続 jcc の br 条件が comis 由来でない | `fcmp` で CF=lt∨uno, ZF=eq∨uno, PF=uno (`kh_lower` [flags]) |
| D1b | fe→opt | **新規** | jcc が IR から消え、skip 側ブロックが **dead code として削除** (Clipper soft-knee) / 無条件実行 (Haas) | D1a の古いフラグが `xor r,r`/`test` 由来の *定数* → LLVM が br を畳み込む (Clipper は stage-0 で `xor ecx,ecx` 由来の cf=0,zf=1 を確認。Haas は同型と推定) | Clipper Path A 0/200 (全 pass でも) / Haas branches 無し 43/200 | 機械語 jcc に対応する IR `br` (insn.addr) が無い。skip 領域が空 (region empty) | 最終 IR からは **復元不能** → stage-0 で D1a を直す |
| D2 | fe | **新規** | `movaps [m],xmm` の上位 64bit が符号拡張 (xmm6-15 spill/restore で callee-saved 破損) | `call i64 @__asm_movaps(i128)` → `sext i64→i128` → `store i128` | Channel Mixer 0/200, Gate 0/200, EQ 0/200。**Clipper は ABI 検査でのみ検出** (出力バッファは一致) | `call i64 @__asm_mov(aps\|ups\|dqa…)` に `sext … to i128` が続く | `trunc`/`or %x,0` で 128bit 恒等 ([mov128]) |
| D3 | fe | **新規** (128bit は M5 S1a 既知) | メモリ宛 store が消える (`movups`/`movlps`/`movsd`/`movq`/`movss`) | `%old = load iN,%p` + `call void @__asm_X(iN %old, i128 %v)` でポインタが load 側にしか残らない | Gain 57/200, Haas 11/200, Clipper 30/200, Gate 54/200 | `call void @__asm_mov*` (戻り void, 第1引数が直前 load) | load の ptr へ `store` ([store]) |
| D4 | opt | 既知 (F7) | `mov r64,[r8]` (disp=0, 引数 reg) の deref 脱落 → `rD := r8` | stage-0 は正しい。最終 IR 段で `[r8]` が address 扱い | Gain 0/200, Channel Mixer 0/200, Haas 3/200 (Path A) | 機械語のメモリ命令に IR 痕跡 (`insn.addr`) が無い (`kh_passes` trace) | consumer に `load i64,%argN` 挿入 (f7)。stage-0 では不要 |
| D5 | opt | 既知 (F2) | float/double 引数 (xmm1…) が落ち、`sext i64 %arg1` や未初期化 alloca が代役 | RetDec ABI 解析が xmm 引数を整数 reg と取り違え | Channel Mixer set7 0/50 (Path A) | 関数入口 live-in の xmm0-3 (CFG 上 read-before-write) | 引数追加 (f2) / wrapper ABI 仕様 (Path B) |
| D6 | fe | 新規 (影響未観測) | `cvtsi2ss/cvtss2sd/cvtsd2ss/sqrtss/sd` の dest 上位 lane が 0 化 | helper シグネチャが dest を持たない | 6 本とも ablation 差なし (MSVC は直前に `xorps`) | merge 型命令の直前に zero idiom が無い | old dest と merge ([merge]、防御的) |
| D7 | fe | **新規** | callee が読むスタック引数/shadow space が 8B ずれる | stage-0 の `call` は戻り番地を push せず `ret` も pop しない | Gate 100/200 (sidechain 経路), EQ 0/200 | callee が `[rsp+8+…]` を読む (stack 引数 / `movss [rsp+8],xmm0`) | call 前後で rsp -=8/復元 ([callret]) |
| D8 | fe | **新規** | callee の rax 戻り値が消える | stage-0 の `call` は `store i64 <callee ret>, @rax` を後置。callee が `ret i64 undef` を `ret 0` にすると潰す | EQ `_dtest` 系 (180fd27a8) | call 後に rax を読む | callee は `load @rax; ret` |
| D9 | fe | **新規** | switch (`jmp rax`) が `ret i64 undef`、case ブロックは No predecessors で残る → type switch が無効 | 間接 jmp を return として翻訳 | EQ (180bac559) jumptable 無し → abort/無限 | `jmp reg` 命令 + 直前 `lea reg,[rip+tbl]; mov eax,[reg+idx*4]; add rax,reg` | table を PE から読み `switch` 復元 ([jumptable]) |
| D10 | ours/CRT | **新規** | `_dint`/`_fdint` が 1.0 等の固定値を返す | `lea rcx,[ImageBase]` + `[rcx+rax*2+0x227ffc0]` 表。VA 窓は ImageBase 近傍 64B しか持たない | EQ libm (180fcde58) 失敗 → shim で解消 | 定数 ImageBase を base にした大 disp のメモリ参照 | C shim (`dint`/`fint`) で置換、単体差分で検証 |
| D11 | ours | **新規** | PE VA リテラル (`i64 0x18…`) が wasm32 で切り捨て → OOB | 絶対 VA がそのまま IR 定数 | 全 snap-in で rdata 無し 0〜2/200 | `i64 6.4e9…6.5e9` の定数 | `global_var_<VA>` 窓 + PE 実データ ([rdata]) |
| D12 | ours (harness) | **新規** | 出力バッファだけ比較すると callee-saved 破損が不可視 | レジスタ状態が比較対象外 | Clipper mov128 ablation: 検査無し 200/200 → 有り 0/200 | wrapper の ABI 毒入れ検査 | 毒入れ + 事後不変チェック |
| D13 | 調査 | **新規** | leaf 関数サイズ推定の過小 (Channel Mixer process 186B → 実 257B) | callgraph.py の終端ヒューリスティック (最後の前方分岐先後の ret) | 親 REPORT の難度表は下限 | `.pdata` 無し関数の BB 走査結果との差 | `scripts/fnscan.py` (BB 走査 + .pdata) |

## 検出器設計メモ (CAB-55)
1. **機械語 jcc ↔ IR br 対応表**: capstone の jcc 全件について `!insn.addr` を持つ `br` が存在するか。D1b は jcc 痕跡欠落として決定的に検出できる (偽陽性: RetDec が select/switch に畳む場合)。
2. **メモリオペランド命令の IR 痕跡**: `kh_passes.py` の `trace` が D4 の deref 脱落を全件検出 (Channel Mixer 2 件 / Gain 1 件 / Haas 2 件 — いずれも後続の誤動作と一致)。
3. **ヘルパ呼出しパターン**: D2 (`call i64 @__asm_mov*` → `sext`)、D3 (`call void @__asm_mov*(iN, i128)`)、D9 (`ret` 直前に `jmp reg`)。
4. **動的**: ctx-fuzz + ABI 毒入れ (D12) は静的検出が効かない欠陥の最終防衛線。ablation (1 pass ずつ外す) で検出力を定量化できる。
