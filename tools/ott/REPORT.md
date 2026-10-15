# OTT (Xfer) — junk 根本原因の特定・修復 + native 実機械語 bit-exact 参照 (tools/ott)

## 0. 結論 (先出し)

- **`bash tools/ott/ott_e2e.sh` = PASS (約 15〜20 秒 warm / 初回 約 40 秒)**。scenario matrix **89 本 / 50,236 cell が native 実機械語の出力と全 bit 一致
  (max_ulp = 0)、最終 heap/obj state の差 0 qword**。t1 標準 (512 cell) は **512/512 bit-exact、junk 0**
  (census: zero 5 / normal 507 / junkHi 0 / junkTiny 0 / NaN 0 / |max| 0.2516; 旧 chain は |max| 1.13e36)。
- **junk の根本原因は「RetDec lift 自体の構造欠陥」** で、M9/M10 が追った band-IIR 係数・exp 系 chain の個別破れは二次症状だった (§2)。
  特に (1) **間接 call (C++ 仮想呼出 / CFG dispatch) を RetDec が丸ごと脱落** (native 実行された 47 関数内の間接 call/jmp 55 箇所が RetDec IR では call として 0 件; 検査 `diff/count_icall.py`)、
  (2) **小さすぎる global 宣言** (20×f32 の既定値表が `[8 x i8]` → 範囲外読み)、(3) call site の r8/r9 引数脱落、
  (4) CRT 数学 (exp/log/tan/pow) を libm へ置換した hand port の ulp 差、(5) 欠落部を hand port した値の誤り (gate box 定数 10.0 等)。
- **修復**: RetDec 非依存の **自作 x86-64→C lifter `lift/x64c.py`** (capstone, 命令 1:1)。native 単歩 coverage で実行関数を決め
  (lift 対象 75 関数 / 5,790 命令)、間接 call は dispatch switch、CRT 数学は DLL 自身の機械語をそのまま lift → **bit-exact**。`i_rcr` の flags 規則は #3125 で flelift 版と揃えた (実機 rcr と 4004/4004 一致・e2e PASS。詳細 `REPORT_APPENDIX_3125.md`)。
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
| `diff/cov_nat.py` `ref/cov_all.json` | native 単歩 coverage (194 scenario → 3,157 命令 / call target 45; params 全 0.0 の 2 scenario は native が CRT 未初期化で落ちる想定内 FAIL)。`OTT_RECOVER=1` で再取得 (+約 100 秒) |
| `diff/count_icall.py` | D1 の独立検査: 実行済み命令の間接 call/jmp を capstone で数え, RetDec IR と突合 |
| `diff/{scen,cmp,trace_*,cmp_trace,transplant}.*` | 差分デバッグ資産 (stage dump 比較 / 関数 entry trace / 状態移植実験) |
| `ott_build.sh` `passes/{gvraw,trace_entry}.py` `rt/ott_{boot,rt,trace}.c` | 旧 RetDec chain の再ビルド (m6-m10 読取専用で出力は tools/ott/work) と診断 pass |
| `f7eval/` | CAB-238 評価 driver。`cab238_eval.py` (site/group 別 build + e2e + bitcmp + 無限ルーブ probe, 既定 34 tag), `run_eval.sh`, `cab238_bitcmp.mjs` (2 module の出力 bit 比較), `cab238_outhash.mjs` (SHA プロトコル, DROP 対応), `cab238_probe.mjs` (任意 combo の停止判定), `outhash_gate.sh` (SHA gate), `REPORT.md` |

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
| D1 | **間接 call/jmp の脱落** (RetDec は `call [rax+0x38]` 等を IR に出力しない) | 実行された 47 関数内の間接 call/jmp **55 箇所** (IAT 経由 import call 2 は除く; ctor 22 / de50 18 / resume 4 ほか 11; `call [rax+0x50]`, `call rdx`, `jmp [rax+0x28]` 等) を capstone で数え `!insn.addr` で IR と突合: 45 = 命令ごと消失, 1 = `br` のみ, 8 = `jmp`→`ret` 化, 1 = `call rdx` が `call @function_1801d2750()` (CFG thunk; 真の target 喪失)。**レジスタ/メモリ経由の間接 call は IR 全体で 0 件** (`full_t1.drc.ll`, `ott_memfix1.ll` とも)。ctor の gate box ループ (`call [vt+0x38]`/`[vt+0x80]`) は空ループ化 (raw RetDec 出力 `full_t1.drc.ll` でも同じ)。M9 が box 系を hand port したが定数が誤り (D5) |
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
- 速度: bit-exact 検証と同一の `ottl.wasm` (-O1), 256 sample block 192 µs → **実時間の約 30 倍** (node 24.19; node 26 では 175 µs / 33 倍; `MOD=work/lift/ottl.cjs node diff/perf.mjs`, params 0.5・正弦入力)。

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
6. 旧 REPORT 群 (m6–m10) の記述は下記 §6.1 の通り誤りだが、tools/m6..m10 は読取専用・状態表はメイン (PM) 担当ゆえ未改訂 (T6)。

### 6.1 旧説の訂正 (m6–m10 REPORT / README / 旧状態表の M9・M10 記述に対して)

| 旧記述 | 訂正 (本回の実測) |
|---|---|
| M9: junk 175 cell の由来 = band IIR 係数の pole (≈2..4, [0x88]/[0x90]) | 誤り。band 係数は M10 で bit 一致済みでも junk は不変。junk は RetDec lift の構造欠陥 (D1–D6) の結果 |
| M10: junk の出生 = exp/log chain (±2^65/±2^-63, ×1.0043/sample) | 誤り (二次症状)。chain の個別修復は不要で、間接 call 脱落・小 global・引数脱落・libm 置換の下流で現れた値。旧 chain は [0x248]=0/1 とも junkHi 175/252 のまま |
| M10→M11 引継: 「[0x248]=1 の x cell denormal 入力 deref 欠落」 | 同上 (二次症状)。lifter 版は [0x248]=0/1 とも native と 512/512 bit 一致 |
| M8–M10 harness の `U8[obj+0x326]=0` / setParameter(19,0) 経由で junk 経路に入る | 標準 sequence の旧 chain は出力全 0。上記操作で処理経路へ入っていた (観測条件の人為性, §2.1-2) |
| bit-exact 参照は native 不可 (SEH 依存) / mac AU 等が必要 | 誤り。DLL 機械語を Linux に敷設して直接実行可能 (§3) |
| 旧状態表 (現 `docs/STATUS.md`): bit-exact 判定は junk-free 確保後 / native poly tan ulp マージ留保 | 解消: 0 ulp 達成 (tan/exp/log/pow も DLL 自身の機械語を lift) |
| M10 の junk 閾値 (\|v\|≥4) | 目安に過ぎない: params=1.0 では正当出力が 472 まで出る。junk = native と bit が異なる cell と再定義 |

## 7. 下流チケット案

- **T1 (高)**: FL 本体 (FLEngine, M11) の RetDec lift に D1 (間接 call 脱落) が無いか全数点検。`call [reg+off]` を capstone で数え、
  IR の間接 call 数と突合する検査を `tools/m11` 側 e2e に追加 (本 lifter の `x64c.py` を PE/Mach-O 両対応にして流用可)。
- **T2**: lifter の汎用化 (PE x64 全般): Delphi (FLEngine) の VMT/RTTI 間接呼出、SEH `.pdata`、`rep` 系、x87、TLS/gs を段階対応。
  native 実機械語参照 + alloc 再生 + 差分 matrix の枠組みは FL 本体 (M11) の関数単位検証にもそのまま使える。
- **T3**: AVX/FMA 命令 (vfmadd*/vmovsd/vroundsd ほか 64 種) の lift と FMA 経路の bit-exact 化 (musl `fma()`)、ldmxcsr/FTZ/DAZ の扱い。
- **T4**: OTT の他 entry (getParameter/Display/setSampleRate/chunk/UI 非依存部) を coverage に追加し、VST2 プラグインとして
  AudioWorklet から駆動する wasm ABI (`ott_run` → 型付き export) を M7/M8 (オーディオパス) に接続。
  → **入口 lift 拡張は実施済み** (CAB-137): `tools/ott/entry/` — VST entry 41 関数を lift し native 実機械語と 85 scenario 全突合 (REPORT 同梱)。AudioWorklet ABI 結線は別チケット (CAB-122 系)
- **T5**: CRT 初期化を実行する経路 (DllMain → `__scrt_*` → static ctor) を native/wasm 双方で再現し、override 4 件を native 実測で置換。
- **T6 (docs)**: `docs/STATUS.md` / README の M10 記述に「junk 原因 = RetDec の間接 call 脱落ほか D1–D6、解決 = tools/ott の自作 lifter」を追記 (PM 担当・2026-10-12 再編で反映済み)。

## 8. 再現

```sh
bash tools/ott/ott_e2e.sh                # 約 15〜20 秒 (初回 約 40 秒)。--quick で matrix 縮小
OTT_RECOVER=1 bash tools/ott/ott_e2e.sh  # native 単歩 coverage から再取得 (全体 約 2 分, 並列 12)
python3 tools/ott/diff/count_icall.py    # D1 独立検査 (capstone 再計数 vs RetDec IR)
OTT_ULP_TOL=2 bash tools/ott/ott_e2e.sh  # 許容 ulp 指定
# 個別: python3 tools/ott/diff/matrix.py tools/ott/work/lift/ottl.cjs ; node tools/ott/diff/perf.mjs
# 前提: python3 (capstone, pefile), gcc/clang, emsdk 6.0.12 の emcc, node >= 22 (emsdk 同梱 24.19 可), setarch
```

## 9. CAB-238 — `ott --auto f7,p1` 既定化の評価 (詳細・全実測は `f7eval/REPORT.md`)

- liftlib `ott` コマンドの既定が auto f7,p1 に (実装は tools/liftlib 側 / LIFTLIB-2 スコープ, 本 dir は評価と文書を担当)。
  検証環境 = **a137396 (CAB-239 適用後) + CAB-238 既定化** の snapshot (`work/cab238/` と `f7eval/` が再現器)。
  検収実測: **checks 7/0・census junkHi 104≤104 (旧 175 より −71)・trap rc 0**。出力 SHA は旧既定 `--auto none`
  = m10 参照と **42/42 一致** (継続ゲート) / auto 既定は修復由来の変化が正のため突合を分離 — 実測 **40 combo 中 34 不一致**
  (一致 6 = param 0.0 の無音のみ)。
- 新規 F7 は **7 site** (チケットの 6 + 0x180120632)。junkHi 175→104 の全量は P1 tail 6 site の再構成,
  **F7 単独は census0 不変**。**F7@0x180120632 は例悪 (除外で census0 52 / census1 248→0, absmax 2.2e-3)** — 次の既定候補。
- 脱落分岐: 再構成 **19** / 残留 **30** (region join 8・bind xmm0 6・bind rcx 5・bind xmm1 2・bind xmm5 2・reg2mem 5・
  間接 call 1・live-out 1) を site リスト付きで再計上。関数帰属は実測 (processReplacing 内 14 / cvt 6 / tan 2 ほか)。
  bit 一致は x64c 参照に対し P1 再構成の有無で 765/3072→0/3072 (bit-parity は未達, x64c のみ bit-exact)。
- **未解決 (CAB-238 で新たに発見)**: 既定ビルドは params=0.9・[0x248]=1 の 2 combo で processReplacing が停止しない
  (無限ルーブ)。原因は P1 再構築 site **0x18012024b / 0x1801204b9** の単体再現 (f7eval §6 の bisect)。e2e gate は
  param 0.5 固定なので未検出 → 下流チケット (site 修正 or 白リスト) が必要。
- 回帰: `liftlib_e2e.sh` フル ALL PASS (FA 400/400・KH 366/366・regress 4 PASS・SIMD・inject 94/94・leafspec)、
  本 dir `ott_e2e.sh` PASS (89 scenario / 50,236 cell bit-exact, max_ulp 0)。メインツリーは LIFTLIB-2 未コミット WIP のため
  OTT auto ビルドが不能 (f7eval §1) — 着地時に同一ゲートで自動再検証される。

**検収 (別セッション, 2026-10-11): `ACCEPTANCE_CAB238_CAB135.md`** — 判定 = **受入 (PASS)**
(CAB-238 4 項目 + CAB-135 全条件を Clean HEAD snapshot で独立再現・独立再計算・ネガティブコントロール 3 件)。
ただし既定ビルドの**無限ルーブ 2 combo (params=0.9 / [0x248]=1) は未修**で、実運用 blocker として LIFTLIB-2 引継。

## 10. #450 — 固定パス (/home/ubuntu) の環境変数化 (親 #294 / 報告 #440)

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみ・lift 出力は不変)。

- 対象 8 ファイルのうち、`tools/liftlib/tests/test_unit.py` / `tools/liftlib/xmm0_ret_census.py` は #427 (2db928d) で
  `liftlib.env.OTT_DLL` (= `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll`) 参照済みで本件の変更なし。
  残り 6 ファイルを `tools/shared/{env.sh,paths.py}` 経由に置換:
  `ott/avx/build_avx.sh`・`ott/crtinit/lift_crt.sh` (DLL → `$PLUGINS_DIR`、emsdk → `${EMSDK_DIR:-/opt/emsdk}`)、
  `ott/accept/acc_crt_table.py`・`ott/avx/unsup_scan.py`・`m9/m9_tablebind.py` (DLL → `PLUGINS_DIR`)、
  `shimx/scripts/import_scan.py` (プラグイン → `PLUGINS_DIR`、`/home/ubuntu/work/webstudio/...` → `REPO_ROOT`)。
- 既定値の不変: 環境変数未設定時の `PLUGINS_DIR` = `/home/ubuntu/work/analysis/plugins` (paths.py 既定のまま)。
  `import_scan.py` の webstudio 側は `REPO_ROOT` (git toplevel) になる — 作業用 VM の webstudio checkout と同一 repo を指す前提。
- 検証 (Actions runner, 2 vCPU load average 0.27–1.06): 置換前 = origin/main (11f0561) の対象 6 ファイルの固定パスだけを
  `$HOME/analysis` / worktree 絶対パスに sed 置換した基準 worktree、置換後 = 本 branch。同一入力 (`ANALYSIS_DIR=$HOME/analysis`) で比較。

| 対象 | 比較方法 | 結果 |
|---|---|---|
| `acc_crt_table.py` | stdout の sha256 | 一致 (104b771c…, rc 0) |
| `m9_tablebind.py` | stdout + 生成 `m9_tables.c` の cmp | 一致 (62cee537…, 4096 B, rc 0) |
| `unsup_scan.py` | 出力 JSON の cmp (1.65 s / 1.54 s) | 一致 (c839ab44…, sites 0) |
| `import_scan.py` | 変数 (FLE/PLUGINS) の解決値を ROOT 相対で比較 + 実行 | 解決値一致。実行は FLEngine 素材 (tools/startup/work, tools/m2/work) が runner に無く旧新とも同一の FileNotFoundError → **範囲外** |
| `build_avx.sh` / `lift_crt.sh` | gcc/emcc/python3 を記録 shim に差し替え、呼出引数列を比較 | 一致 (4 行 / 6 行。`--pe` は OTT DLL を指す)。実 emcc ビルドは未実行 → **範囲外** |

- ネガティブコントロール: `PLUGINS_DIR=/nonexistent` で `m9_tablebind.py` / `acc_crt_table.py` / `unsup_scan.py` が
  `/nonexistent/ott/binaries/OTT_vst2_win64.dll` の FileNotFoundError で失敗する (3/3) = 変数が実際に効いている。
- 参考 (変更なしの確認): `xmm0_ret_census.py` = 分母 169・検出 103・別算法 103・一致 YES (6.3 s)。
  `liftlib/tests/test_unit.py` は FreshAir SlateCore 素材 (work-liftlib-targets) が無く T1 で FileNotFoundError → 範囲外 (本件は当該行を変更していない)。
- 再現: `ANALYSIS_DIR=<analysis> python3 tools/m9/m9_tablebind.py out.c` 等を origin/main と本 branch で実行して cmp。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `test_unit.py` の `T = ../..` 相対 (FA_PE 等) は `REPO_ROOT` 化していない | 固定パスではなく挙動不変のため据え置き | #294 にコメント |
| `import_scan.py` / `build_avx.sh` / `lift_crt.sh` の実素材での通し実行 | 本 run は素材 (FLEngine, emcc ビルド) 未実行 | #294 にコメント |

## 13. x64c ia32 front-end (#896 / #1094 fix 再実測, 3d1ff740)

- 入力: `block22434_PE.bin` (fl-win64 素材 `extracted/`)、roots = `0x10007ca0` (`main`)。
- `--arch ia32 --closure 0` → `functions 1, insns 30, unsup {}, unlifted callees 2`。`--closure 2` → `functions 8, insns 301` (closure 範囲の差)。
- 生成 C (`--closure 0`) を `cc -c -O1 -I tools/ott/rt ott_lifted.c` → rc=0。`emcc` は runner に無く `emcc -c` は未実行。
- `--arch x64` + ia32 PE → `fail-fast` (exit 1)。
- 未解決 (ia32 の関数境界・x87・jump table 実データ) は #1098 / #1099 / #1117。

## 14. ia32 jump table の実データ検証 (#1117, 測定 commit f1b4ea4c)

- 入力: `block22434_PE.bin` (sha256 84b64c43…de724a9、fl-win64 素材)。 再現: `FL_PE=<同ファイル> python3 tools/ott/lift/verify_ia32_jt.py <ott_lifted.c>` (gate) / 末尾 `neg` (ネガコン)。
- 受入 1 の対象: issue 本文の export `main` (0x10007ca0, 30 命令) には jump table が無い (`call esi` の間接 call のみ)。 jump table を持つ関数は opcode dispatcher **0x10001300** (`cmp eax,0x18` / `ja 0x1000149c` / `jmp dword ptr [eax*4+0x100014a4]`)。 検証はこちらで行った。
- 修正 (前は `jmp [idx*4+tbl]` が解決されず実行時 `ott_dispatch` に落ちていた): `x64c.py` の `descend` / `jump_table` が ia32 のメモリ間接 jmp (scale 4・base 0・絶対 disp) を読むようにした。 x64 の経路は分岐条件 (`IA32 and` / `REG` のみ) で不変。
- 実測 (f1b4ea4c):

| 項目 | 実測 |
|---|---|
| lift (`--arch ia32 --closure 0`, root 0x10001300) | functions 1, insns 171, unsup `fmul` 1 (case 内の x87), unlifted callees 1 (0x10009bc4), jt_ranges 1 (0x100014a4 / 104 B) |
| switch | 21 case (表 25 entry・重複 target あり) + default。 遷移先ラベルは全て case 値の VA に存在 |
| gate `verify_ia32_jt.py` | `[jt] OK`: case 値集合 == PE 表データ (100 B)、rc 0 |
| ネガコン (表の 1 entry を 1 bit 破壊) | `[jt] FAIL` (only-in-C 0x10001388 / only-in-PE 0x10001398)、rc 1 |
| 間接 jmp・call の読み | `LD32((R[0]*4 + 0x100014a4ULL))`・`LD32((R[0] + 0x1cULL))` (PTR=4 B) |
| `cc -c -O1 -I tools/ott/rt ott_lifted.c` | rc 0 |
| `emcc -c -O1 -I tools/ott/rt ott_lifted.c` (toolchain-emsdk 6.0.12) | rc 0 (wasm object 7,512 B) |
| 回帰: ia32 closure 2 (root 0x10007ca0, 8 関数, 301 insn) の生成 C・lift_meta | origin/main と HEAD で `cmp` 一致 (差 0) |
| 所要 (lift, 単独実行) | wall 139 ms・load 1 分 0.00 |

- x64 の回帰は**未実測**: fl-win64 素材に x64 の PE が無く、plugins-ott の展開物にも OTT DLL が無い (インストーラのみ)。 変更は ia32 でのみ成立する条件 (`IA32 and ...`) で、x64 の出力は構造上不変と推定。 差分確認は OTT DLL 素材で行うこと。
- 未解決: (1) 0x10001300 の case 内 x87 `fmul` 1 件 (unsup)。 (2) 受入 1 の「main」(0x10007ca0) は jump table を持たない (`call esi` のみ) ため、main 自体は表の検証対象にならない。 PM が受入の対象関数を再定義する必要あり。 (3) x64 の回帰は OTT DLL 素材が無く未実測。

## 15. #1200 — 相対化 (OTT_RELOC=1): N=16 別 base で署名 6b1696f0 一致 (測定 commit 2b1f0288)。詳細 `tools/ott/REPORT_APPENDIX_1200.md`
