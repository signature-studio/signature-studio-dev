# PERF-P25 (#3959): AudioWorklet 上の M=146 以上の instantiate 無応答と、M の成否の掃引

親: #2988 (PERF-P21)。REPORT の正本は `tools/perf/REPORT_P15.md` §9。本付録は §9 の未解決 2 件 (M=146 の原因・146 超と未測 M の成否) の実測。

**結論**: 1 instance (Memory 1 本) に OTT obj を畳む instantiate は、**M=2〜145 が全て成功、M=146〜160 が全て失敗** (Node 掃引 15 点、Chrome 実測 12 点)。成功最大 M = 145、失敗最小 M = 146 で、単調性は M=2〜160 の範囲で確認した (M=1 は成功)。原因は **未特定** (子 issue で切り分け)。M=146 の無応答は、同一 instance で 146 回目の `ctor` (`0x18011d400`) 呼び出しが戻らないことまでは確定した。

## 1. 掃引 (Node・同期 setup。ctor・setParam 19 個・resume・入力設定)

測定 commit: `513bb2b02` (`tools/perf/p15/node_init_sweep.mjs` の追加のみ)。HEAD 再現も同じ commit で行った。

| 項目 | 結果 |
|---|---|
| 測定点 | M = 2〜160 の全 159 点 (1 点ずつ別プロセス・timeout 15 s) |
| 成功 | M = 2〜145 の 144 点 (全て `ok`) |
| 失敗 (timeout) | M = 146〜160 の 15 点 (全て無応答) |
| 成功最大 M / 失敗最小 M | 145 / 146 |
| 再現 | HEAD `513bb2b02` で同一 (成功 144・失敗 15) |
| setup_ms (M=145) | 795 ms (`loadavg` 0.43)、M=1: 23 ms |

Node の掃引は `$RUNNER_TEMP/perf/p25_node_sweep.jsonl` (HEAD 再現は `p25_head_node.jsonl`) に出力される (生データは commit していない)。

## 2. Chrome 実測 (AudioWorklet・`chrome_worklet.mjs --init-only --timeout 30000`)

Chrome は `Chrome/155.0.8059.39` (§9 の 154 とは版が違う。行の `runtime` で確認できる)、CPU AMD EPYC 7763 (4 vCPU)。

| M | 結果 |
|---|---|
| 145 | 成功 (setup 804 ms、1 run) |
| 146 | 無応答 3/3 (`Error: eval timeout`、30 s) |
| 147・149・150・151・153・154・155・156・157・158・159 | 無応答 1 run ずつ (11 点) |

掃引 (Node) と Chrome は同じ境界 (145 成功・146 以上失敗) を示す。

## 3. 原因の切り分け (Node・同一 wasm・ログ付き)

| 観察 | 結果 |
|---|---|
| M=146 の止まる位置 | obj 145 (基底 `0x33440000`) の `ctor` の呼び出し直前で止まる (setParam・resume は obj 144 まで完了) |
| obj 145 を単独で ctor | 成功 (新しい instance なら通る) |
| 同一 obj アドレス `0x31000000` の ctor を 146 回連続 | 146 回目で無応答。アドレスと配置に依存しない |
| 各 ctor の所要 | 約 3.5 ms で一定。途中で伸びない |
| スタックポインタ (`emscripten_stack_get_current`) | 146 回の呼び出しで不変 (`0x1038d520`)。スタック伸長ではない |
| `malloc(0x2000)` を 400 回 | 成功 (戻り値が単調増加し NULL なし)。ヒープ枯渇ではない |
| `resume` (`0x180120800`) を同一 obj に 200 回 | 成功 |
| `setParam` (`0x180120af0`) を同一 obj に 200 回 | 成功 |
| stride 0x30000 の ctor 146 回 | 無応答 (stride 非依存) |

**分かったこと**: 無応答は「配置の境界」ではなく、**同一 instance 内での ctor の呼び出し回数**に結びつく。`resume` と `setParam` は同回数でも止まらないため、`ctor` (`0x18011d400`) の内部に 146 回目で戻らなくなる条件 (カウンタ・テーブル・状態の蓄積) がある可能性が高い。原因の具体 (どのループ・どのテーブルか) は未確定。

**未確認**: 「146 回目の ctor で何が起きるか」を lift 側 (`ott_run` の ctor 関数) で確定するには、ctor の逆アセンブルかトレースが要る。本 run では時間内に完了しなかった。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ctor (`0x18011d400`) が同一 instance で 146 回目に戻らない原因 (ループ・テーブル・カウンタのどれか) | 上限 145 の意味 (メモリ限界か、状態の蓄積か) が未確定。M=146 を通す修正方針が立たない | 子 issue (本 PR で起票) |
