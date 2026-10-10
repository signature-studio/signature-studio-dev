# OTT (Xfer) — junk 根本原因の特定・修復 + native 実機械語 bit-exact 参照 (tools/ott)

## 0. 結論 (先出し)

- **`bash tools/ott/ott_e2e.sh` = PASS (約 14 秒)**。scenario matrix **89 本 / 50,236 cell が native 実機械語の出力と全 bit 一致
  (max_ulp = 0)、最終 heap/obj state の差 0 qword**。t1 標準 (512 cell) は **512/512 bit-exact、junk 0**
  (census: zero 5 / normal 507 / junkHi 0 / junkTiny 0 / NaN 0 / |max| 0.2516; 旧 chain は |max| 1.13e36)。
- **junk の根本原因は「RetDec lift 自体の構造欠陥」** で、M9/M10 が追った band-IIR 係数・exp 系 chain の個別破れは二次症状だった (§2)。
  特に (1) **間接 call (C++ 仮想呼出 / CFG dispatch) を RetDec が丸ごと脱落** (native 実行された 47 関数内の間接 call/jmp 54 箇所が RetDec IR では 0 件)、
  (2) **小さすぎる global 宣言** (20×f32 の既定値表が `[8 x i8]` → 範囲外読み)、(3) call site の r8/r9 引数脱落、
  (4) CRT 数学 (exp/log/tan/pow) を libm へ置換した hand port の ulp 差、(5) 欠落部を hand port した値の誤り (gate box 定数 10.0 等)。
- **修復**: RetDec 非依存の **自作 x86-64→C lifter `lift/x64c.py`** (capstone, 命令 1:1)。native 単歩 coverage で実行関数を決め
  (lift 対象 75 関数 / 5,790 命令)、間接 call は dispatch switch、CRT 数学は DLL 自身の機械語をそのまま lift → **bit-exact**。
  RetDec chain 側の局所修復 `passes/gvraw.py` (小 global 廃止) も残した (単独では junk 不変: §2 表)。
- **参照 (引継ぎ 3)**: 案 (a) を採用。**native OTT を Linux 上で実行できる** (旧 REPORT の「SEH 依存で不可」は誤り):
  PE を VA 0x180000000 に敷設し IAT を stub 化、MS x64 ABI trampoline で ctor/setParameter/resume/processReplacing を直接呼ぶ
  (`native/`)。wasm 側 alloc ログを再生して **heap アドレスまで一致** させ、bit・state 差分を機械判定する。
- 判定: **bit-exact (0 ulp) を基準**。`OTT_ULP_TOL=k` で ≤k ulp 許容 (他ホスト/FMA 版比較用)。FMA3 経路 vs SSE2 経路の
  差は実測 0 ulp (12 case / 18,432 cell, §4)。

## 1. 成果物 (tools/ott/)

| パス | 役割 |
|---|---|
| `ott_e2e.sh` | 1 コマンド検収 (native build → coverage 参照 → lift → matrix → INFO) |
| `native/` | `ott_native.c` PE 敷設+IAT stub+単歩 coverage+entry trace+alloc replay, `ms_call.S` MS ABI trampoline, `ottnat.py` ctypes |
| `lift/x64c.py` | 自作 lifter (capstone → C)。`data_gen.py` .rdata/.data/jump table 敷設, `mkentries.py`, `lift_build.sh` (emcc) |
| `rt/ott_cpu.{h,c}` `ott_glue.c` `ott_ovr.c` | CPU 状態+flag helper+import(HeapAlloc 他)+JS 入口+CRT 誤差報告 override 4 件 |
| `diff/matrix.py` | scenario matrix (89 本) 判定 = 本 PASS の本体。`scen2_*` 実行器, `fma_sens.py`, `old_census.mjs`, `perf.mjs` |
| `diff/cov_nat.py` `ref/cov_all.json` | native 単歩 coverage (194 scenario → 3,157 命令 / call target 45)。`OTT_RECOVER=1` で再取得 (約 90 秒) |
| `diff/{scen,cmp,trace_*,cmp_trace,transplant}.*` | 差分デバッグ資産 (stage dump 比較 / 関数 entry trace / 状態移植実験) |
| `ott_build.sh` `passes/{gvraw,trace_entry}.py` `rt/ott_{boot,rt,trace}.c` | 旧 RetDec chain の再ビルド (m6-m10 読取専用で出力は tools/ott/work) と診断 pass |

tools/m5..m10 は読取のみ (改変 0 行)。生成物は `tools/ott/work/` (gitignore)。

## 2. junk の根本原因 (実測)

### 2.1 診断手順 (旧 RetDec chain, tools/ott/ott_build.sh で再現)

1. native 参照を作り (§3)、wasm の alloc ログを再生して同一 heap 配置で stage (ctor/setParameter/resume/process) ごとに全 heap を byte 比較。
2. 標準 sequence (ctor → setParameter 0..18 = 0.5 → resume → process) では **旧 chain は出力が全 0** (`obj+0x326`=1 で
   processReplacing 先頭の `cmp byte [rcx+0x326],0; jne` が早期 return)。M8–M10 が `U8[obj+0x326]=0`/setParameter(19,0)
   を harness に入れて junk 経路へ入っていたことが判明 (それが「junk」の観測条件)。
3. 原因: ctor の `setParameter(i, table[i])` ループ (20 回) の既定値表 `0x18025f530` を RetDec が
   `@global_var_3025f530 = constant [8 x i8]` (2 要素分) と宣言 → `rsi += 4` で範囲外 (隣接 global) を読み、param19 既定が非 0 → `0x326`=1。
   `passes/gvraw.py` (400 個の名前付き global を生アドレス参照へ置換) で ctor 直後の obj 差分は 15→4 qword に減る (残 4 = D3/D4)。
4. 状態移植実験 (`diff/transplant.mjs`): 旧 chain の resume 後に native の差分 state 59 qword (box/SVF 含む) を全部上書きしても
   **出力 junk は不変 (258/512 一致, junkHi 252)** → 初期化だけでなく **lift 済み processReplacing 本体の破れ** と確定。
   n=4 の単発で出力 L[3] から乖離 (native 2e-06 / wasm -0.0)、n=8 で -181.2 / 222.5 に発散。

### 2.2 欠陥一覧 (すべて native 比較で確認)

| # | 欠陥 | 実測証拠 |
|---|---|---|
| D1 | **間接 call/jmp の脱落** (RetDec は `call [rax+0x38]` 等を IR に出力しない) | 実行された 47 関数内の間接 call/jmp **54 箇所** (ctor 22 / de50 18 / resume 4 ほか; `call [rax+0x50]`, `call rdx`, `jmp [rax+0x28]` 等) が IR で **0 件** (IR 全体で `call %reg` 形 0)。ctor の gate box ループ (`call [vt+0x38]`/`[vt+0x80]`) は空ループ化 (raw RetDec 出力 `full_t1.drc.ll` でも同じ)。M9 が box 系を hand port したが定数が誤り (D5) |
| D2 | 小さすぎる global (範囲外読み) | 既定値表 20×f32 が 8B。400 global 中 256 個が `[8 x i8]`、`load i128` 32 箇所は 8B global から 16B を読む |
| D3 | call site の引数 reg 脱落 | `function_180127550(this,0,r8=1,r9=0x14)` を IR は 1 引数で呼ぶ → obj+0x20/0x58/0x80 が 0 (native 1/0x14/2) |
| D4 | CRT 数学を libm 置換 (exp/log/tan/pow) | SVF 係数 8 ブロックの f32 が 1–2 ulp ずれ (`0x3bce1fa2` vs `…fa3`; ctor 直後)。native は DLL 自身の SSE2 実装 |
| D5 | hand port の値誤り | gate box +0x28 が native 7.17/3.36/2.025 (box 毎) に対し wasm は全 box 10.0 固定 (ほか +0x8/+0x30/+0x48/+0x50 も差) |
| D6 | lift 済み processReplacing 本体/SVF 呼出し層の破れ (**個別の命令までは未特定**) | resume 後の差分 state を native 値に揃えても junk 不変 (2.1-4)。n=4 単発で出力 L[3] から発散 |

M10 の「±2^65/×1.0043 の exp 系 chain」「[0x248]=1 の denormal x cell」は D1–D6 の下流で現れた症状で、個別に直す対象ではなかった。
RetDec 出力は構造的に不完全 (間接呼出) なため、局所 pass の積み上げでは bit-exact に到達しない。

### 2.3 census (同一 harness = M10 e2e_check、標準入力 N=256)

| build | [0x248] | zero | normal | junkHi | junkTiny | NaN | \|max\| |
|---|---|---|---|---|---|---|---|
| 旧 RetDec chain (M10 と完全一致を再現) | 0 | 132 | 69 | 175 | 136 | 0 | 1.67e20 |
| 同上 | 1 | 4 | 254 | 252 | 2 | 0 | 1.13e36 |
| **自作 lifter (本回)** | 0 / 1 | 5 | 507 | **0** | **0** | 0 | 0.2516 |

matrix 全体 (89 scenario × 出力 50,236 cell) の native bit 一致: 旧 chain **4,791 (9.5%)**、旧 chain+gvraw 17,805 (35%, junkHi 21,011)、
**lifter 50,236 (100%)**。なお M10 の junk 閾値 (|v|≥4) は目安に過ぎない: params=1.0 では正当な出力が 472 まで出る
(native と bit 一致)。**本回の junk 定義 = native と bit が異なる cell**。

## 3. 参照実装 (native 実機械語) の仕組み

- `native/ott_native.c`: `OTT_vst2_win64.dll` を ImageBase 0x180000000 に mmap (再配置不要)、375 import は名前付き fail-fast thunk、
  実使用の HeapAlloc/GetLastError/CS 系のみ実装。CRT 初期化 (DllMain) は **走らせない** → wasm 側と同じ `.data` 静的初期状態を共有。
- `ms_call.S`: rcx/rdx/r8/r9 + xmm0-3 + stack を設定して任意 VA を呼ぶ。f32 引数は xmm2 に載せる (setParameter)。
- 差分デバッグ機構 (すべて native 側で成立): ① 単歩 coverage (TF + SIGTRAP) ② 関数 entry trace (INT3 差替+単歩再挿入)
  ③ **alloc 再生** (wasm の `{ptr,size}` 列を native の HeapAlloc に再生 → heap アドレス完全一致 → 全 heap を byte 比較)
  ④ SIGSEGV 時の stack 内 image RIP 表示。ASLR は `setarch -R` で固定 (brk が 0x108xxxxx と衝突するため)。
- 引継ぎ (3) の案 (b) mac AU / (c) JS 移植は不要になった: DLL 自身の機械語を実行する (a) が最強の参照 (同一 CRT・同一丸め)。
- 旧 REPORT の「native は SEH 依存で不可」は誤認だった: ctor/setParameter/resume/processReplacing は SEH も UI も通らず、
  未解決 import は 0。唯一の不成立は CRT 数学の**エラー経路** (log(0) → `_handle_error`) で、未初期化 CRT のため native 自身が SIGSEGV
  (params 全 0.0 の 2 scenario)。lifter 側は override で UCRT 意味 (返値=渡された retval) に置換 (§6)。

## 4. 判定定義 (tolerance 含む)

- **PASS (exit 0)** = matrix の全 scenario で ①出力 cell が native と ulp 距離 ≤ `OTT_ULP_TOL` (既定 0 = bit-exact)、②最終 obj/heap の
  qword 差 0 (tol>0 の時は②を免除)、③alloc 再生が完全一致 (サイズ不一致 0)。
- scenario (89): ctor 既定 / 全 param 0.5・0.1・0.25・0.75・1.0 / 各 param 単独 0.9 / p4=0,1 (= [0x248]) / bypass(p19) /
  N=1,3,4,5,7,31,64,255 / 3 block 連続 / SR 22.05k–192k / 入力 zero・DC・impulse・square・noise・非正規数域・減衰 / 乱数 24 本。
  各々 [0x248]=0/1 (SVF 路線 / per-sample 路線) を含む。
- **FMA3 経路との差** (`diff/fma_sens.py`): CRT の `__use_fma3` 相当 flag (`0x18026c50c`) を 1 にすると exp/log/tan/pow は
  AVX/FMA 実装に分岐する。native で SSE2 経路と比較: **12 case / 18,432 cell で差 0 (max_ulp 0)**。実ホストで FMA 経路が
  選ばれても本参照と一致する見込み (全入力域の保証ではない)。k ulp 許容が必要になるのは別 CPU/別 CRT との比較時のみ。

## 5. lifter 設計 (lift/x64c.py)

- 状態: `R[16]`, `X[16]` (128bit union), flag 5 個 (global)。関数 = `void f_<va>(void)`。call は return address を guest stack に
  push → `f_xxx()`、`ret` は rsp+=8 して return。image VA は 0x30000000 へ shift し、data は m6 と同じ規約で
  同アドレスに敷設 (`.reloc` DIR64 を補正; MSVC jump table は .text 内 data として窓敷設)。
- 実行時に fail-fast: 未対応命令 `ott_unsup` / 未 lift callee `ott_unlifted` / 未実装 import `ott_missing_import` / 不正 jump。
- 関数集合: native coverage の call target (jmp 経由 CFG thunk・メモリ operand の tail `jmp [vt+x]` を含む) + root 4 + closure 深さ 2。
- 浮動小数: C の float/double 演算 (`-ffp-contract=off`)、`cvt*`/`comis*`/`cmpXXsd`/`min/max` は x86 意味 (第 2 operand 返し等) を
  helper 化。SSE パックは 128bit union で lane 展開。MXCSR は既定固定 (ldmxcsr は fail-fast)。
- 速度: -O1, 256 sample block 201 µs → **実時間の約 29 倍** (node 24, `diff/perf.mjs`)。

## 6. 未解決・制約

1. **AVX/FMA 版 CRT 経路は未 lift** (未対応 mnemonic 64 種 473 箇所、全て未実行経路; 到達すれば `ott_unsup` で停止)。
   SSE2 経路は bit-exact。FMA 経路は `fma()` 実装で追加可能 (ticket T3)。
2. **override 4 件は native 検証不能** (`ovr_handle_error_{d,f}` = 1801c8c00/c8cb8, `ovr_sqrt_{d,f}` = 1801a9a6c/b38): native の CRT 未初期化では
   エラー経路が落ちる。UCRT 仕様 (返値 = 呼出側 retval, sqrt(<0) = -nan(ind)) と dsm (xmm0←xmm6←xmm1) から導出。params 全 0.0 でも wasm は有限値を返す
   (無音 0.0×512) が、この経路の bit 正解は未取得。
3. **lift 対象は ctor/setParameter/resume/processReplacing と callee のみ**。getParameter/表示/chunk/setSampleRate 呼出/プログラム/UI は未 lift
   (SR は harness が `obj+0x18` を直接書く)。native coverage 外の経路で未 lift callee 17 (CRT 誤差報告・lock) に入ると fail-fast。
4. DllMain (CRT 初期化・static ctor) は実行しない。`__use_fma3`/`__isa_available` 等は DLL 静的値 (0) のまま。lock は no-op (単スレッド)。
5. NaN の符号・payload は engine 依存 (x86 sqrtsd の default NaN は負符号)。有限値出力に影響しない。
6. 旧 REPORT 群 (m6–m10) の「band pole / exp chain / [F8] 係数」議論は本診断で二次症状と判明したが、ファイルは読取専用のため未改訂
   (README/MILESTONES の M10 記述の更新はメイン担当へ提案: 下記)。

## 7. 下流チケット案

- **T1 (高)**: FL 本体 (FLEngine, M11) の RetDec lift に D1 (間接 call 脱落) が無いか全数点検。`call [reg+off]` を capstone で数え、
  IR の間接 call 数と突合する検査を `tools/m11` 側 e2e に追加 (本 lifter の `x64c.py` を PE/Mach-O 両対応にして流用可)。
- **T2**: lifter の汎用化 (PE x64 全般): Delphi (FLEngine) の VMT/RTTI 間接呼出、SEH `.pdata`、`rep` 系、x87、TLS/gs を段階対応。
  native 実機械語参照 + alloc 再生 + 差分 matrix の枠組みは FL 本体 (M11) の関数単位検証にもそのまま使える。
- **T3**: AVX/FMA 命令 (vfmadd*/vmovsd/vroundsd ほか 64 種) の lift と FMA 経路の bit-exact 化 (musl `fma()`)、ldmxcsr/FTZ/DAZ の扱い。
- **T4**: OTT の他 entry (getParameter/Display/setSampleRate/chunk/UI 非依存部) を coverage に追加し、VST2 プラグインとして
  AudioWorklet から駆動する wasm ABI (`ott_run` → 型付き export) を M7/M8 (オーディオパス) に接続。
- **T5**: CRT 初期化を実行する経路 (DllMain → `__scrt_*` → static ctor) を native/wasm 双方で再現し、override 4 件を native 実測で置換。
- **T6 (docs)**: MILESTONES/README の M10 記述に「junk 原因 = RetDec の間接 call 脱落ほか D1–D6、解決 = tools/ott の自作 lifter」を追記 (メイン担当)。

## 8. 再現

```sh
bash tools/ott/ott_e2e.sh                # 約 14 秒。--quick で matrix 縮小
OTT_RECOVER=1 bash tools/ott/ott_e2e.sh  # native 単歩 coverage から再取得 (+約 90 秒, 並列 12)
OTT_ULP_TOL=2 bash tools/ott/ott_e2e.sh  # 許容 ulp 指定
# 個別: python3 tools/ott/diff/matrix.py tools/ott/work/lift/ottl.cjs ; node tools/ott/diff/perf.mjs
# 前提: python3 (capstone, pefile), gcc/clang, emsdk 6.0.12 の emcc, node >= 22 (emsdk 同梱 24.19 可), setarch
```
