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
| 修復 ON の hang (`+0x4c` の初期 store) と OOB (`+0x70` の書込み) の原因の切り分け。親の loop 変数 `-28` / `-32` の SSA 分解との整合 | 修復 pass を既定にできない | `[SHX-T40]` の子 issue (本 PR の未解決表で追跡する) |
| 301 site の真偽 (真の D23 か、通常の rbp 渡しの局所参照か) | 修復範囲の決定 | 同上 |
| D23 の「修復」列の更新 | 修復が未達のため未更新 | 同上 |
