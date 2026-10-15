# SHX-T40 (#3234): 入れ子手続 function_448490 の親 object を callee の view に合わせる修復 pass (D23)

## 1. 結論

- 修復 pass `tools/m11/ldfix/fix_shx_t40.py` を追加した。`M11_FIX_SHX_T40=1` の opt-in でだけ適用し、既定 (OFF) の IR と build は変えない。
- 実測では、この pass は効かなかった。修復 ON の実 boot は unit 18 で停止せず 120 s 以上応答しなかった (hang)。`+0x70` の書込みだけを入れた版は `memory access out of bounds` で停止した。修復を既定にする根拠は無い。
- 受入条件 2 (修復前後の `units_run ≥ 18`・`VirtualAlloc` 不発・`MessageBoxA` 不発) は満たさなかった。受入条件 3 (301 site の切り分け) と 4 (D23 の「修復」列) は未実施。残りは子 issue に移す (§6)。

## 2. 測定条件

- 基底: `origin/main` (de2aa64f7 相当)。作業ブランチ `3234-shx-t40-nested-frame-repair`。
- 素材: `work-m11.tar.zst` と `fl-win64.tar.zst` (`extracted/block00031_PE.bin`) を展開。`toolchain-emsdk` は runner 既存。
- 手順: `m11_gen_ir2.sh` → `m11_build.sh` → `shimx_link/build.sh --trace --soft` → `run_trace.mjs` (`SHIMX_TRACE_FILE=/ftrace.jsonl`)。
- 負荷: 測定中の 1 分平均 load は 0.8〜1.0 (nproc 4)。

## 3. 実測

| 条件 | IR 生成 | build / shimx | 実 boot (`run_trace.mjs`) |
|---|---|---|---|
| baseline (修復なし・既定) | rc 0 | rc 0・mismatch 0・undefined 0 | rc 0・`units_run=17`・`dllmain_done=true`・`total_calls=106` |
| 修復 ON (`+0x70`・`+0x4c`・120 B) | rc 0 | rc 0・mismatch 0・undefined 0 | **rc 124 (120 s timeout)**・ログ 0 行。プロセス残留なし |
| 修復 ON・`+0x4c` の初期 store を外す (`+0x70` のみ・120 B) | rc 0 | rc 0・mismatch 0・undefined 0 | rc 0・`units_run=17`・`init_count_var=18`・`dllmain_done=false`・`threw="memory access out of bounds"`・`total_calls=103` |
| 既定 (修復 OFF・opt-in フラグ後) | rc 0 | rc 0・mismatch 0・undefined 0 | baseline と一致 (`units_run=17`・`total_calls=106`) |

- 修復 pass の入力 (生成段階の IR) は `%stack_var_-104 = alloca i64` (8 B)。最初の測定で見た `[6 x i64]` は、`m11_build.sh` 内の `alloca/m11_alloca.py` (R8 escape gap) が拡幅した後の形だった。pass は両方の形を受けるようにした。
- 修復 pass の対象は `function_448490` の 1 関数 (`ALLOCA_RE` と entry の anchor が 1 件であることを assert する)。

## 4. 解釈

- `+0x70` の書込みだけで OOB になるのは、親の `%arg1` を object に入れた後で callee が別の経路 (`+0x70` を object の値として読む) を辿り、alloca 外を触るため。生成段階の alloca 拡幅 (120 B) と、後段 `m11_alloca.py` の R8 拡幅の整合を取り切れていない可能性が高い。
- `+0x4c` の初期 store を足すと hang する。callee の `+0x4c` は loop 変数 (`-28`) の書換えに使われ、初期値 1 で親の loop が回り続けると推測する (未確認)。
- 機構の確定 (真の D23 か、通常の rbp 渡しか) は未実施。REPORT_SHX-T28 §4 の 301 site と同じく site 単位の突合が要る。

## 5. 再現

```
cd tools/m11
FL_WIN64_DIR=<fl-win64 展開先> bash m11_gen_ir2.sh          # 既定 (shx_t40=not-applied)
FL_WIN64_DIR=<fl-win64 展開先> M11_FIX_SHX_T40=1 bash m11_gen_ir2.sh   # 実験 (shx_t40=applied)
FL_WIN64_DIR=<fl-win64 展開先> bash m11_build.sh
(cd shimx_link && bash build.sh --trace --soft)
SHIMX_TRACE_FILE=/ftrace.jsonl node shimx_link/run_trace.mjs work/shimx_link/m11_sx_trace_soft.cjs --out work/shimx_link/trace
```

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復 ON の hang (`+0x4c` の初期 store) と OOB (`+0x70` の書込み) の機序の確定 (§7) | 修復 pass を既定にできない | [SHX-T45] #4459 (修復 pass の実装と OFF/ON 実測) |
| 301 site の真偽 (真の D23 か、通常の rbp 渡しの局所参照か) | 修復範囲の決定 | [SHX-T44] #4189 |
| D23 の「修復」列の更新 | 修復が未達のため未更新 (§7 で理由を残す) | [SHX-T45] #4459 |

## 7. SHX-T42 (#4121): hang と OOB の切り分け (commit `e9f8317f8` で測定)

### 7.1 測定 (commit `e9f8317f8`・`ir_sha256` は `m11_gen_ir2.sh` が出力したもの)

| 条件 | `shx_t40` | IR 生成 / build / shimx | 実 boot (`run_trace.mjs`, 上限 150 s) |
|---|---|---|---|
| OFF (既定) | not-applied (`64a0e5dc…`) | rc 0 / 0 / 0 | rc 0・`units_run=17`・`init_count_var=0`・`dllmain_done=true`・`total_calls=106`・`va_calls=2` |
| ON (`+0x70`・`+0x4c`・120 B) | applied (`90cd1ed4…`) | rc 0 / 0 / 0 | **rc 124 (150 s timeout)**。trace 出力なし |
| `+0x70` のみ (`+0x4c` の初期 store を外す) | applied-70only (`638ff7d4…`) | rc 0 / 0 / 0 | rc 0・`units_run=17`・`init_count_var=18`・`dllmain_done=false`・`threw="memory access out of bounds"`・`total_calls=103`・`va_calls=1` |

- 測定時の負荷: 1 分平均 0.75〜1.00 (nproc 4)。3 条件の合計は実測 real 5 分 14.5 秒 (foreground 1 本で実行。ON の run のみ timeout 150 s に達した)。
- 3 条件とも REPORT §3 の値と一致した (再現性あり)。
- ON / OFF の stderr の差: OFF でも `[m11][VA] #1 addr=0 size=1989214208 (0x76910000)` (1.9 GB の `VirtualAlloc`) が出て OOM (NULL)、`MessageBoxA` (`Runtime error 0 at 00000000102A0410`) で止まる。つまり **OFF の `units_run=17` の停止原因も、この `VirtualAlloc(0x76910000)` の OOM である**。受入条件の「VirtualAlloc 不発・MessageBoxA 不発」は OFF の時点で満たしていない。ON はこの前段で止まる (hang)。

### 7.2 IR で確認した事実 (`function_448490` / `function_4483f0` / `function_448430`)

- `function_4483f0` (Append) は `this` (= 親 `%stack_var_-104`) の `+0x4c` (`%5 = this+76`) を **読んで +1 して書き戻す**。`+0x48` (`this+72`) も同様に +1 する。`+0x4c` は書込み位置 index として使われる。
- `function_448430` も `this+0x4c` を読み、`this+0x4c` に `rsi` を加算して書き戻す。
- 親 IR では、ループ変数は `%stack_var_-32.*.reg2mem` (SSA の reg2mem) で、object の `+0x4c` / `+0x48` と結び付いていない。このため、親の `-32` の値と callee が見る `this+0x4c` が一致しない。
- `+0x4c` に `1` を入れると、callee が毎回 index を +1 する状態が親の loop に入り、回り続ける (hang)。ただし、回り続ける機序 (どの loop がどの条件で抜けないか) は IR の静的な読みに留まり、trace での確認はしていない。
- `+0x4c` の初期 store を外すと OOB になる。`+0x70` の arg1 を object の値として読む callee の経路で alloca 外を触るが、どの store が alloca 外かは未確定。

### 7.3 修復を既定にできない理由 (受入条件 4)

- 修復 ON は実 boot で hang する (§7.1)。`+0x70` のみでも OOB で `dllmain_done=false` になり、OFF より前に進まない。
- OFF の `units_run=17` は `VirtualAlloc(0x76910000)` の OOM が原因で、修復 pass はこれを解消していない。
- よって既定 OFF のまま。D23 の「修復」列は、修復が効かないため更新しない (§6 の起票先で追跡)。

### 7.4 ネガコン用のコード変更

- `ldfix/fix_shx_t40.py` に `--only-70` を追加し、`m11_gen_ir2.sh` に `M11_FIX_SHX_T40=70` を追加した。既定 (未設定 / 0 / 1) の IR は変わらない (`shx_t40=not-applied` の既定 IR sha256 は §7.1 のとおり)。
- 測定のコード変更は commit `e9f8317f8` のみ。

### 7.5 未了 (受入条件)

- 受入条件 1 (hang の機序を IR と機械語で確定): 静的な IR の読みまで。trace で loop の抜けを確認していないため未了。
- 受入条件 2 (OOB の機序を alloca 単位で確定): 未了。
- 受入条件 3 (修復 ON で `units_run ≥ 18`・`VirtualAlloc` / `MessageBoxA` 不発): **未達** (ON は hang)。
- 受入条件 4 (既定の変更、または理由): 理由を §7.3 に残した。
- 受入条件 5 (commit 済み HEAD で再現): §7.1 のとおり `e9f8317f8` で 3 条件を測定した。
