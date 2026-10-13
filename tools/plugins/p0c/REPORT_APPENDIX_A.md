# tools/plugins/p0c REPORT 付録 A (§8〜§9)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。

## 8. P0c-2 追記 (CAB-241): f80→f64 lowering pass の実装と検証

作成: 2026-10-10 / 担当 dir: tools/plugins/p0c のみ (新規 5 ファイル、既存記述は本節のみ追記)

### 8.0 結論 (先出し)

1. **f80→f64 lowering pass を実装** (`f80_lower.py`): k80.lift.ll の x86_fp80 968 token → **0**、
   **llvm-as 通過・冪等 (2 回適用 byte 一致)・wasm32 バックエンド通過** (101,150 B; emcc_base.log の 20 error 全解消)。
2. **ARG pass 再適用** (`k80_argfix.py`): RetDec が落とす xmm 引数 46 site と spill 初期化落ち 27 件を
   機械語 ABI 走査 (`k80abi.py`) と突合して再接続。冪等。引数は**末尾追記** (m7 ir7 同規約)。
3. **差分試験ハーネス** (`k80_diff.py`, fork 隔離): 実機械語 vs lowering+ARG 適用 IR を同一入力で突合。
   **f32 mul 系 0x5df210/0x5df240 は出力バッファ bit-exact**、0x5e0760/0x5e0bb0/0x5e0b70/0x5e1590/
   0x5e1780 も bit-exact。i64 系: 0x5e0330 は IR が i64 完結で構造的 bit-exact、0x5de3e0 は
   `llvm.rint.f64` 挿入で RC=nearest を再現 (実機 native==rint **100%** / trunc 74.1% を実測。検収再現: rint 100% (0/200k)、trunc 一致率は入力分布依存 — 音響 k/1000 50.4% / f64 全エントロピー 98.7%)。
4. **既存 lift IR の x87 スタック模型欠陥を検出** (RetDec 起源・本 pass と独立): fld→演算→fstp 型
   (0x5de820/0x5dedf0/0x5dfb60/0x5dfd30 + rc_chop 3 本) で fstp 読出が st(1) になり (0x5de820 の出力が
   定数 c2 に化ける)、loop 末尾 TOP も +2 ずれる。§3 f80_micro (C model) では bit-exact だった面。
5. 既存 e2e は両方完走 (`p0c_e2e.sh` exit=0 / `p0c2_e2e.sh` exit=0)。

### 8.1 pass 仕様 (f80_lower.py — §3.4 の 4 点の実装)

| # | 変換 | k80 実測 |
|---|---|---|
| 1 | `x86_fp80`→`double` 型置換 (define/declare/alloca/load/store/算術/fcmp/select/call/frontend_reg 署名) — **f80 spill slot 排除はこの帰結** (alloca 3 件 16B→8B) | 968→0 |
| 2 | f80 定数 `0xK`→f64 bits (Fraction で正確な最近接丸め; bare 位置は `0xH` のみ) | 14 |
| 3 | `@llvm.*.f80`→`.f64` + 重複 declare 除去 | 13 |
| 4 | same-type 化した `fpext/fptrunc double→double` を RAUW 消去 (連鎖収束; f64→f80→f64 往復は -0.0/NaN 含め恒等) | 24 |
| 5 | `i3`→`i32` (wasm legalization; add の wrap は &7 で整合) | 813 |
| 6 | chop 区間外の `fptosi double→iN` に `llvm.rint.f64` 挿入 (`--chop-funcs` で rc_chop 3 本は trunc 保持)。冪等性は「%v が既に rint 結果なら挿入しない」 | 4 |
| 7 | `sitofp i64→double` 直後 `fptosi double→i64` (中間 def 無し) を恒等畳み込み = **i64 保持**。k80 は RetDec 既 i64 化のため適用例 0 (framework 向け) | 0 |

### 8.2 ARG pass 再適用 (k80_argfix.py)

A: movd-from-zero — `%Z = xor i128 0,0` が `__asm_movX*(i128 %Z)` 専用のとき機械語 xmm slot を
`i64 %in.xmmN.bits` 引数で追加し `zext(trunc)` に置換 (46 site / 26 kernel)。B1: orphan spill —
load のみの alloca に引数+entry store (1)。B2: reg2mem 初期化落ち — `%rcx.0.reg2mem` 等に
slot 名から引数追加 (26)。abi json は `k80abi.py` (read-before-write + copy 逆向き伝播)。

### 8.3 検証結果

**(a) pass 品質**: llvm-as OK / 冪等 OK (両 pass) / wasm32 compile OK。k80.final.ll・kall.final.ll
にも同一変換計数で適用可能。

**(b) 差分試験 (2000 case/kernel)**: bit-exact 7 (§8.0-3)。RetDec x87 模型欠陥による不一致 7
(§8.0-4)。SSE 系の差分は pass 非干渉 (f80 無し kernel は変換 0) で lift 品質由来。crash 4
(ABI 推定の harness 限界, fork 隔離)。Group B 12 kernel (Delphi RTL / x87 helper 外部呼出) は
数値差分対象外 — framework 統合時に翻訳単位ごと。

**(c) model level 回帰**: f80_micro を N=2,000,000 で再実行し §3.2 と同値 (P1/P2=0, P3=1/2M,
P4=±1ulp 0.018%, K5e0330 native vs LD=0) — lowering 設計前提は不変。

### 8.4 CAB-194 (framework lift) への統合手順

1. `fw_f80.py` を `f80_lower.py` に置換 (`--chop-funcs` に rc_chop 分類)。fadd 0.0 近似 (73 site) は
   RAUW 消去に、0xK 定数は正確な最近接丸めに改善。
2. 引数末尾追記: `%in.xmmN.bits` (i64) / `%in.xmmN` (float/double) を呼出側 (dispatch/ir8) で末尾追加。
   site 計数は `k80_argfix.py --report` を流用。ABI json は `k80abi.py` を PE 毎に実行。
3. wasm 化は triple/datalayout を wasm32 に置換してから emcc (p0c2_e2e.sh [5])。
4. x87 模型欠陥 (§8.0-4) は framework 側にも同型発生が見込まれる — liftdiff (CAB-121) への分類追加を推奨。

### 8.5 限界

- fstp dword の chop 区間内 f32 丸めは nearest のまま (tie ~2^-25/case、実測未観測)。
- fistp overflow→indefinite / NaN→real-indefinite 正規化 (§3.4 (4)) 未実装 — 極端値域で
  native=indefinite vs IR=0 の差分 (rc_chop 系で観測)。
- RetDec x87 スタック模型欠陥 (fstp off-by-one / TOP 破綻) は本 pass scope 外 — 7 kernel 不一致の原因。
- 差分試験の入力は音響レベル (f32 指数 2^-17..2^7)。ABI 推定はヒューリスティック (crash 4 kernel は fork 隔離)。

### 8.6 再現手順 / 次タスク提案

再現: `bash tools/plugins/p0c/p0c2_e2e.sh 2000` (約 3 分) / 既存 e2e 回帰: `p0c_e2e.sh`。

次タスク (下流チケット案):

1. **[P0c-3] RetDec x87 スタック模型修復 pass** — fstp off-by-one / TOP 更新の機械的修復
   (transform C)。0x5de820 系 7 kernel の bit-exact 化見込み (欠陥様式と実機正解は確定済み)。
2. **[P0c-4] ARG pass の ABI 推定強化** — mid-function push のある rsp 相対 frame と
   movd site↔xmm slot の機械語主導対話で crash 4 kernel を救済。
3. CAB-194 framework への f80_lower 適用 (§8.4) + frontend_reg C 実装の共有化。
4. liftdiff (CAB-121) への「x87 fstp off-by-one」欠陥分類追加。

## 9. P0c-3 追記 (CAB-251): RetDec x87 スタック模型修復 pass

作成: 2026-10-10 / 担当 dir: tools/plugins/p0c のみ / 新規: x87fix.py, p0c3_e2e.sh

### 9.0 結論 (先出し)

1. **x87 スタック模型修復 pass を実装** (`x87fix.py`): RetDec が生成する fpr[] 配列 +
   fpu_stat_TOP 変数模型の欠陥 (fstp 読出 off-by-one / fld 書込先ずれ / 演算 operand 絶対
   slot ずれ / loop 末尾 TOP 更新過大 / fisub 零化 / fxch 対象ずれ / 初期 TOP store 欠落) を
   IR のみから機械検出し、真の TOP シミュレーションで全 fpr アクセスの絶対 slot を再導出して
   書替える。**0x5de820 / 0x5dedf0 / 0x5dfb60 の 3 kernel が k80_diff.py で bit-exact** (buf_diff=0)。
2. **0x5dfbe0 / 0x5dfc90 / 0x5dfdb0 / 0x5dfd30 の構造も修復** (fist overflow→0x80000000 化、
   fstp f32 の chop 丸め、frac/index の構造) し、残差を桁で圧縮 (下表)。残差の原因は
   **x87 64-bit mantissa (ext) と double 53-bit の演算精度差** であり論理欠陥ではない (§9.4)。
3. **k80_diff.py の driver bug を修復**: ir 引数式が mslot index (4..7) を value slot として
   使い stack 引数が未初期化 vI[4..7] を渡していた (正は sidx 8..11)。これにより 0x5dfb60 の
   差分が消えた (P0c-2 の §8.0-4 での「b60 不一致」の実体はこの harness bug だった)。
4. p0c_e2e.sh / p0c2_e2e.sh exit 0 (回帰なし)、x87fix 冪等 (2 回適用 byte 一致)、
   llvm-as + wasm32 通過。`bash tools/plugins/p0c/p0c3_e2e.sh` で 1 コマンド再現。

### 9.1 x87 模型と欠陥の機構

RetDec 模型: `st(i) = fpr[(TOP+i)&7]`、fld=`store.fpr(TOP-1)`+`TOP:=TOP-1`、fstp/fist=`load.fpr(TOP)`(+pop)、entry TOP=0。
欠陥: 翻訳中の内部 TOP 追跡が loop 内で破綻し (D1) fstp 読出 st(1) 化、(D2) 第2 fld 書込先 +1、
(D3) 演算 operand 絶対 slot ずれ、(D4) loop 末尾 TOP 更新 +1/+2、(D5) fist 直後 fisub が
`fsub %X,%X`(=0)、(D6) fxch 対象ずれ、(D7) 初期 TOP store 欠落。0x5de820 では fstp が定数 c2 を読む。

### 9.2 修復規則 (x87fix.py — 機械検出+機械的書替え)

| # | 規則 | 欠陥 | 実装 |
|---|---|---|---|
| R1 | emission パターン (push/dup/binop dest-st0,st1+pop/memarith/fstp_mem/fist/fstpst0/fxch/fisub) を復元し真 TOP で全 index を `add i32 <block先頭TOP>, <真slot-先頭TOP>` 正準形へ再導出 | D1/D2/D3 | process_function |
| R2 | fpu_stat_TOP store を真 delta へ (平衡 loop = 0) | D4 | simulate |
| R3 | fisub 零化: `fsub %X,%X` → `fsub %X, sitofp(fptosi(%X))` (fpr/devirtualized 両方) | D5 | composite / fix_fsub_zero_global |
| R4 | 初期 TOP store 補完 | D7 | process_function |
| R5 | fst/fist/fstp st(0) の pop 有無は 2^k 組合せを試し back-edge TOP 平衡が一意な組合せのみ採用 (非平衡/複数解はスキップ) | D1 | simulate |
| R6 | chop 区間の fstp f32 store を RC=toward-zero 化 (nearest が真値を跨いだら nextafterf で 1 つ戻す。符号ゲート付) | fstp chop RC | fix_chop_f32 |
| R10 | fist/fistp overflow → 0x80000000: fptosi 入力を \|v\|≥2^31 で -2^31 へ clamp (poison 解消) | fist overflow | fix_fist_overflow |

パターン外は関数単位で未変更スキップ (安全側)。適用スコープは `--funcs` (+`--chop-f32-fns`)。

### 9.3 検証結果 (k80_diff.py, 2000 case/kernel, fork 隔離)

| kernel | 修復前 buf_diff | 修復後 | 判定 |
|---|---:|---:|---|
| 0x5de820 | 5,136,704 | **0** | bit-exact |
| 0x5dedf0 | 2,571,305 | **0** | bit-exact |
| 0x5dfb60 | 758,431 (harness bug) | **0** | bit-exact |
| 0x5dfbe0 | 790,341 | 288,922 | 構造修復 / 残差 §9.4 |
| 0x5dfc90 | 757,178 | 52,323 | 構造修復 / 残差 §9.4 |
| 0x5dfd30 | 2,552,059 (ret 1518) | 38,099 (ret 59) | 構造修復 / 残差 §9.4 |
| 0x5dfdb0 | 2,454,776 (ret 1712) | 841,305 (ret 79) | 構造修復 / 残差 §9.4 |

回帰: 既修復 0x5df210/0x5df240/0x5e0760/0x5e0b70/0x5e0bb0/0x5e1590/0x5e1780 (+0x5e0330/0x5de3e0)
すべて buf_diff=0 維持。f80_lower/argfix 冪等性・llvm-as・wasm32 (101,539 B) 通過。

### 9.4 残限界 (ext 精度 — 据置と [P0c-4] 引継)

修復後も be0/c90/d30/db0 に ±1-8 f32 ulp が残る (cell 比率 14%/2.5%/1.9%/41%)。
原因は論理ではなく **x87 64-bit mantissa (ext) と double 53-bit の演算精度差**:
(1) frac = p - trunc(p) の精度が \|p\| の整数部ビット数分圧縮される (p~1e9 で frac 粒度
1.2e-7、ext では 7.5e-12)。(2) interp/積鎖の各段の丸めが 53-bit。(3) harness の入力分布が
f6/f7 最大 2^116 級の極端スケールを含み、frac の微小差が f32 下位 bit に増幅する。
対処には x87 ext 演算の double-double/64-bit-grid エミュレーション (fma 鎖で各段の丸め剰余を
伝搬) が必要 — 試作 (fma 補正) は compiled-IR の FMA 収縮と干渉し悪化したため未採用。
f32 音響出力への影響は ±1ulp 時点で実質無視できるが、bit-exact 完走には上流の
f80_lower に ext-emulation mode を追加するのが正しい設計位置。

### 9.5 [P0c-4] への引き継ぎ

1. **ARG pass ABI 推定強化** (本チケット繰越): mid-function push のある rsp 相対 frame、
   movd site↔xmm slot 対話、crash 4 kernel (0x5de710/0x5df610/0x5e05b0/0x5e0d80, sig11) 救済。
2. **x87 ext-precision emulation** (§9.4): f80_lower の mode 追加 (frac/interp 鎖の
   double-double 化)。bit-exact 完走の前提。
3. liftdiff (CAB-121) への分類追加候補: 「x87 fstp/fld index ドリフト」「fisub 零化」
   「fpu_stat_TOP loop 更新過大」「fptosi poison (fist overflow)」。
4. harness 注意: k80_diff.py の stack 引数 value-slot 対応修正済み (§9.0-3) —
   P0c-2 時点の sweep 数値とは driver 分だけ非互換 (改善)。

