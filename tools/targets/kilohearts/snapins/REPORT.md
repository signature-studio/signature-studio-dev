# Kilohearts snap-in 易 6 本の一括 lift (CAB-53 / KH-1)

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/snapins/` (大物は `work/`, gitignore)
- 1 コマンド再現: `bash tools/targets/kilohearts/snapins/run_all.sh` (キャッシュ有り 1〜2 分 / 初回 + RetDec 約 3 分。`ABLATE=1` で ablation 全数、`TRIALS=1000 SEED=7` で試行数変更)
- 前提: `../work/winpkg/HeartCore.core_64` (無ければ run_all.sh が `../scripts/extract_installer.sh` で再抽出)

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 判定 | **Channel Mixer / Gain / Haas / Clipper / Gate / 3-Band EQ の 6 本すべて、RetDec lift → wasm が実機 x86 機械語と bit-exact** (ctx-fuzz 200 trial 全一致、seed 7 の 1000 trial でも 6/6 全一致 = 計 31,746 call) |
| 方式 | **Path B = RetDec の decode 直後 IR (stage-0) を自前 lowering (`kh_lower.py`)**。RetDec 最終 IR を後から直す Path A (`kh_passes.py`) は 3 本 (Channel Mixer/Gain/Haas) で成立するが **Clipper で原理的に不可能** (§3) |
| 最重要の発見 | RetDec は `ucomiss/comiss` が EFLAGS を更新しない → 直前の `xor r,r` 等の *定数フラグ* を jcc が読み LLVM が分岐を畳み込む → **skip 側コードが IR から消える** (Clipper の soft-knee 計算全体)。最終 IR からは復元不能。stage-0 で fcmp 結線すれば解決 |
| ctx-fuzz | PoC の 6 ブロック固定ベクタを、乱数のバッファ・パラメータ・状態 × 複数 call の差分ハーネスに汎化 (§2)。修復を 1 本外すと 0〜57/200 に落ちる (ablation §4)。PoC の固定 6 ブロックが同じ欠陥を検出できたかは未検証 |
| 欠陥類型 | 13 類型 (`DEFECTS.md`; CAB-55 の silent-miscompile 検出器入力)。既知 3 (P1/F7/F2 同型) + 本タスクで新規 10。出力バッファに現れず ABI 検査でしか見えない型 (D2 の xmm6-15 破損) を含む |
| 未達 | Resonator / Stereo / Disperser は未着手 (§6)。CRT 例外系 6 関数は stub (有限・正常入力では未到達 = 200+1000 trial で abort 0 件)。性能最適化 (レジスタのメモリ経由) は未実施 |

## 1. 一覧表 (実測, Path B, 200 trial seed 1)

| snap-in (id) | process VA | process B | lift fn 数 / 合計 B | wasm B | undefined import | bit-exact trial | bit-exact call | 必要な修復 (発火数) | shim / 未 lift stub |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| Channel Mixer (kscm) | 0x1804f41a0 | 257 | 3 / 275 | 23,206 | 0 | 200/200 | 1149/1149 | mov128×3, flags×1, merge×2 | 0 / 0 |
| Gain (ksgn) | 0x1804b0380 | 609 | 1 / 609 | 23,054 | 0 | 200/200 | 999/999 | merge×2, flags×1, store128×1 | 0 / 1 (vector realloc) |
| Haas (ksha) | 0x1804d0280 | 1175 | 5 / 1,606 | 35,967 | 0 | 200/200 | 1100/1100 | store128×4, storelow×1, merge×5, flags×5 | 0 / 0 |
| Clipper (kclp) | 0x180884b30 | 1683 | 3 / 1,743 | 37,457 | 0 | 200/200 | 1100/1100 | mov128×10, merge×8, flags×10, store128×4, callret×1 | 0 / 0 |
| Gate (ksgt) | 0x1804c2f50 | 1703 | 3 / 2,532 | 45,754 | 0 | 200/200 | 999/999 | callret×12, mov128×11, flags×9, merge×2, store128×1 | 2 (memmove/memset) / 1 |
| 3-Band EQ (ksqe) | 0x18035fb10 | 1754 | 24 / 11,512 | 186,285 | 0 | 200/200 | 999/999 | mov128×43, flags×30, merge×13, store128×11, callret×49, jumptable×1 | 2 (`_dint`/`_fdint`) / 6 (CRT 例外系) |

- lift した関数 (config `lift`): Channel Mixer = process + reset(slot15) + slot7(float 引数); Gain = process; Haas = process + 無音ブロック(slot13) + reset + slot17 + latency(slot19, int 戻り); Clipper = process + peak-hold callee(xmm2/xmm3 引数) + reset; Gate = process + lookahead delay 2 関数 (sidechain 経路); 3-Band EQ = process + 設計/libm/CRT 23 関数。
- 「lift fn 数 / 合計 B」= lift した関数 (process + 必要な closure + reset 等) の数と機械語バイト (`fnscan.py` の extent)。**process B は REPORT.md (親) の「固有 B」より大きい**: 親の leaf 関数サイズ推定は末尾分離ブロックを落とす (Channel Mixer process 186B → 実 257B, §5 D13)。
- 3-Band EQ の closure = process + 係数設計 (`180362700`/`180bac490` = 8 type の biquad 設計 switch) + **FMA3 libm** (`180fcd690`/`180fce0d0` = sin/cos, `180fcde58` = exp 系 double, `180fbc1f4` = float exp 系) + CRT 補助。libm 4 関数は単体でも **4800/4800 call bit-exact** (`qemath` scenario)。
- wasm サイズは Path B がレジスタをグローバル (メモリ) 経由で持つため大きめ (Path A の Gain 17KB / Channel Mixer 17KB に対し 23KB)。register localization (mem2reg 相当) は未実施の最適化余地。
- undefined import 0: 未 lift callee は fail-fast stub (abort) か C shim で解決済み。stub に到達した trial は 0。
- wasm サイズ・fn 数は `work/table_s0.json` (`scripts/make_table.py`)。

## 2. 方式

### 2.1 native 参照 = ctx-fuzz (`harness/`) — lift 側と循環しない
- `native_ref.c`: HeartCore の x86-64 機械語を ImageBase 0x180000000 に VA 敷設し、**ms_abi 直接 call** (インライン asm トランポリン: rcx/rdx/r8/r9 + xmm0-3 を設定、rax/xmm0 を回収)。m5 `native_fx` 方式を踏襲。
- **アリーナ方式**: this / ctx / AudioBuffer / リングバッファ等を固定 0x04000000 の 8MB アリーナに構築 (wasm 側も同アドレス) → ポインタ値込みでバイト一致を比較できる。各 call の「scenario が書いた差分 (patch)」「引数 (整数 4 + xmm 4)」「call 後アリーナ全体」「戻り値 (i32/f32/f64/i64)」を `vectors.bin` に記録。複数 call を連続再生 (wasm 自身の状態を引き継ぐ) ので最初の乖離 call が特定できる。
- scenario (`scen_*.h`) は逆アセンブル + Ghidra decompile (`work/ghidra/decomp.txt`) から起こした **this / ctx / AudioBuffer レイアウト** に従い、乱数 (RFSPECIAL = 0/±lo/±hi/非正規数含む) でパラメータ・状態・入力・call 順 (reset / process / 補助 slot) を振る。NaN を作る入力は避ける (NaN ペイロードは wasm と x86 で異なるため)。
- `compare.mjs`: wasm を同手順で再生し **アリーナ全バイト + 戻り値**を突合、不一致は region 名 (self/P/ring/buf…) + offset で報告 (`--v` で差分語列挙・wasm スタック)。
- **ABI 検査** (wrapper に内蔵): callee-saved (rbx rbp rsi rdi r12-15, xmm6-15) を非自明な定数で汚してから call し、戻り後に不変であることを確認 → 不一致は `unreachable`。xmm6-15 の spill/restore 破損は出力バッファに現れないため、これでのみ検出できる (Clipper の mov128 ablation: 検査無し 200/200 → 有り 0/200)。

### 2.2 lift パイプライン (`lift/`)
- **Path B (本編)** `build.py --path s0`: RetDec `--select-ranges … --print-after-all` の **最初のダンプ (Input binary to LLVM IR decoding = stage-0 IR)** だけ採取して打ち切る (≈7 s/本) → `kh_lower.py` (レジスタ=グローバルのまま frontend 欠陥だけ局所修復) → `ir_normalize.py` (m2) → `gen_simd.py` (declare 駆動 SSE/VEX/FMA helper 生成) + `gen_globals.py` (DLL 実データ窓) + `gen_stubs_sigs.py` (stub/shim/sigs) → `emcc -O1` → wasm。入口 wrapper が ms_abi (rcx..r9 / xmm0-3 / 戻り rax・xmm0) とスタックを提供 (F2 = xmm 引数落ちが ABI 仕様で消える)。
- **Path A (対照)** `--path a`: RetDec 最終 IR → `kh_passes.py` (機械語 = capstone を `!insn.addr` で照合する修復: flags / branches / f7 / f2 / mov128 / storelow / trace 報告) → ir5_patch (m5 継承) → 同上。
- SIMD helper は **名前ではなくシグネチャ** (`i128/i64/i32` 引数形 + 戻り型) から生成 (`__asm_*` の `.N` 接尾はバイナリごとに変わる)。EQ で必要だった VEX-128 / FMA3 (`vfmadd{132,213,231}sd`、`fma()` = 単一丸め)・`cvttpd2dq`・`psrldq` 等を含め 87 helper を自動生成、未対応 0。
- shim (CRT 置換, config `shims`): `memmove`/`memset` (Gate)、`_dint`/`_fdint` (ImageBase 相対の mask 表を引くため lift 不能 → 同一意味の C 実装。差分試験で検証: `qemath`/EQ 全体)。switch jump table は config `jumptables` で `switch` に復元 (EQ 1 箇所)。

## 3. Path A vs Path B (Clipper が分けた)

| snap-in | Path A (最終 IR + kh_passes) | Path B (stage-0 + kh_lower) |
|---|---|---|
| Channel Mixer / Gain / Haas | 200/200 (1149/999/1100 call) | 200/200 |
| Clipper | **0/200** (全 pass を入れても) | 200/200 |
| Gate / 3-Band EQ | 未試行 (同根の欠陥: ucomis 直前が定数フラグ) | 200/200 |

Clipper の `ucomiss xmm; ja/jbe` は直前が `xor ecx,ecx; … ucomiss; setb cl` で、stage-0 では jcc が **@cf=0,@zf=1 の定数**を読む → LLVM が `ja` を恒偽に畳み込み、soft-knee 計算ブロック (`180884f40…`) が **dead code として削除**される。最終 IR にはもう存在しない (`kh_passes` の `branches` pass は "region empty" を報告するのみ)。stage-0 は機械語命令ごとに区切られた最適化前の IR なので、`ucomis` を `fcmp` で @cf/@zf/@pf に結線すれば CFG が保存される。

## 4. ablation (修復を 1 本外した時の bit-exact trial 数 / 200)

Path B (数字 = 外した時の一致 trial。`/200` 全一致が基準):

| 外した pass | Channel Mixer | Gain | Haas | Clipper | Gate | 3-Band EQ |
|---|--:|--:|--:|--:|--:|--:|
| flags (ucomis→fcmp) | 1 | 1 | 9 | 1 | 0 | 0 |
| mov128 (movaps sext) | 0 | 200 (不使用) | 200 (不使用) | **0 (ABI 検査のみ検出)** | 0 | 0 |
| store (movups/movlps store 復元) | 200 (不使用) | 57 | 11 | 30 | 54 | 0 |
| callret (戻り番地 push/pop) | 200 | 200 | 200 | 200 | **100** | **0** |
| merge (cvt/sqrt dest 上位 lane) | 200 | 200 | 200 | 200 | 200 | 200 |
| rdata (DLL 実データ窓) | 0 | 0 | 2 | 0 | 0 | 0 |
| jumptable (switch 復元) | – | – | – | – | – | 異常終了 (abort/無限) |
| 全部外す | 0 | 1 | 0 | 0 | 0 | 0 |

Path A (kh_passes; 外した pass 毎, trial/200):

| 外した pass | Channel Mixer | Gain | Haas |
|---|--:|--:|--:|
| flags (P1) | 1 | 1 | 16 |
| branches (消えた jcc 復元) | 200 | 200 | 43 |
| f7 (`mov r,[r8]` deref 復元) | 0 | 0 | 3 |
| f2 (xmm 引数) | 150 (set7 0/50) | 200 | 200 |
| mov128 | 0 | 200 | 200 |
| storelow (movlps 等 store) | 200 | 200 | 42 |
| 全部外す | 0 | 0 | 2 |

読み: **flags/f7/mov128/store/callret/rdata は必須、merge は 6 本とも無影響** (MSVC が cvt 前に xorps で上位を 0 化するため。防御的に残す)。`flags` を外すと 0〜9/200 に落ち、PoC (Gain 6 block) で通っていた経路でも ctx-fuzz は検出する。

## 5. 新規欠陥類型 (詳細は `DEFECTS.md`)

D1 ucomis/comis が EFLAGS 未更新 → 古いフラグを jcc/setcc が読む (a: 古い symbolic = 誤分岐 / b: 古い *定数* = 分岐削除+dead code 消滅) /
D2 `movaps/movups [m],xmm` が `call i64 @__asm_movaps` + `sext i64→i128` で上位 64bit 符号拡張 (xmm6-15 spill 破損) /
D3 メモリ宛 SSE store (movups 128 / movlps・movsd・movq 64) が `call void @__asm_X(old_load, val)` に化け store 消失 (128bit は m5 S1a が救済、64/32bit は未救済) /
D4 `mov r64,[r8]` (disp=0, 引数 reg) の deref 脱落 = F7 (最終 IR 段で発生、stage-0 は正しい) /
D5 xmm 引数落ち (F2): 最終 IR で bogus な `sext %arg1` / 未初期化 alloca が xmm1 の代わりになる /
D6 merge 型 scalar 変換 (cvtsi2ss/cvtss2sd/sqrt…) の helper が dest を落とす /
D7 stage-0 の `call` は戻り番地を push/pop しない → callee の `[rsp+8+…]` (スタック引数/shadow) が 8B ずれる /
D8 stage-0 の `call` は `store callee_ret, @rax` を後置 → callee を `ret 0` にすると実 rax を潰す /
D9 `jmp reg` (switch jump table) が `ret i64 undef` に化け、case ブロックは到達不能のまま残る /
D10 ImageBase 相対 mask 表を引く CRT (`_dint`/`_fdint`) は VA 窓では lift 不能 /
D11 PE VA リテラル (`i64 0x18…`) の wasm32 切り捨て → OOB (rdata 窓が必須)。
D12 (harness) 出力バッファ比較だけでは xmm6-15/callee-saved の破損が不可視 → ABI 毒入れ検査を追加。
D13 (調査精度) 親 REPORT の leaf サイズ推定が過小 (257B を 186B)。

検出器の入力として使える信号: **jcc の IR 痕跡欠落** (`insn.addr` 無し = D1b)、**メモリオペランド命令の IR 痕跡欠落** (`trace` = D4)、`call i64 @__asm_mov*` + `sext` (D2)、`call void @__asm_mov*(iN old, i128 v)` (D3)、`ret` 直前の `jmp reg` (D9)。

## 6. 未解決 / ブロッカー / 次

- **未着手**: Resonator / Stereo / Disperser (余力枠)。**Resonator は `rcpps`、Stereo は `rsqrtps` を process 内で使う** — 逆数/逆平方根の *近似* 命令 (相対誤差 ≤ 1.5·2^-12) で結果は CPU 実装依存 (Intel/AMD で異なる)。native 参照 (本機 = AMD Ryzen 9 9950X) と bit-exact を取るには AMD 表の再現が必要で、他 CPU 上の本物とは一致しない → bit-exact の定義自体が CPU 依存。wasm 側は IEEE の `1/x`, `1/sqrt(x)` との許容誤差 (≤ 2^-11 相対) 判定にするか、特定 CPU の近似表を移植する方針判断が要る。Disperser は近似命令無しだが `180316d90`/`1803172a0`/`1803172f0`/`180006500` 等の追加 lift + this レイアウト起こし (7 段 biquad の状態 ≈ 0x4a0B) が必要 (scenario 作成が律速)。
- stub のまま (到達 0): Gain/Gate の `std::vector<int>` 再確保 `0x18004cf20` (通知 vector が満杯の経路)、EQ の CRT 例外系 6 関数 (NaN/Inf/domain error 用)。**NaN・Inf 入力は未試験** (NaN ペイロード差のため意図的に除外)。
- 性能: Path B はレジスタ=グローバルで -O1 のまま (wasm 23〜186KB)。register file の局所化 (関数内 alloca 化 → mem2reg) で縮む見込み (推定)。
- ライセンス層・GUI・間接 call (vtable) 経由の closure 拡張は対象外 (親 REPORT §7)。

### liftlib 移行時の差分 (`tools/liftlib/` は別 subagent が作成中・読取のみ)
liftlib 現状 (`passes/{base,p1,f7,f2,dataimage,remap}.py`, `simd/gen.py`, `harness/diff.py`) は **RetDec 最終 IR を直す Path A 系**。
- 取り込み推奨: ① `harness/native_ref.c`+`compare.mjs` のアリーナ/patch/ABI 毒入れ検査 (liftlib の diff harness と統合可)、② `lift/gen_simd.py` の VEX/FMA 追加分 (vfmadd*, cvttpd2dq, psrldq, movhlps…)、③ `kh_passes.py` の `branches`/`storelow`/`mov128` (最終 IR 用)、④ **`kh_lower.py` = stage-0 経路そのもの** (Path A で救えない D1b/D7/D8/D9 を解決)。
- 衝突する点: liftlib の P1/F7/F2 は最終 IR 上の名前パターン (`%cf.N`, `add …, %arg3`)、`kh_passes` は `!insn.addr` + capstone 照合。`!insn.addr` は ir5_patch A7 が除去するので **機械語ガイド pass は A7 より前に走らせる**必要がある。
- config 分離: lift VA 群 / abi / shims / jumptables は `snapins.json` に集約済み (liftlib の `specs/*.json` へ写像可能)。

## 7. ユーザ依頼事項
なし (素材・認証とも不要)。ライセンス層の方針判断 (親 REPORT §7-1) は引き続き保留。

## 8. 成果物
`snapins.json` (lift 対象/ABI/shim/jumptable/scenario)、`run_all.sh`、`harness/{ctxfuzz.h,native_ref.c,scenarios.c,scen_*.h,compare.mjs}`、`lift/{build.py,kh_lower.py,kh_passes.py,khmach.py,gen_simd.py,gen_globals.py,gen_stubs_sigs.py,ir_normalize.py,ir5_patch.py(m2/m5 継承コピー),msimd6_core.h}`、`scripts/{fnscan.py,vtslots.py,pe_dis.py,make_table.py,ablate.py,dbg_trap.sh}`、`DEFECTS.md`、`work/` (gitignore: RetDec 出力 / stage-0 / 各 tag の wasm・IR・vectors / ablation.json)。
