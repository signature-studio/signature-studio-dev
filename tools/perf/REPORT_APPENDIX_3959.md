# PERF-P25 (#3959): AudioWorklet 上の M=146 以上の instantiate 無応答

**#3959 の受入の正本はこの付録**。`tools/perf/REPORT_P15.md` §9 は要約と本付録への参照だけを持つ。親: #2988 (PERF-P21)。

**結論**: Chrome 154.0.8037.97 (AMD EPYC 7763) の AudioWorklet で、1 instance (Memory 1 本) に畳んだ OTT obj は、**M=145 が 3/3 成功、M=146 が 3/3 無応答** (30 s。1 run は 150 s でも戻らない)。M=148・152・160 も 3/3 無応答。原因は未特定 (子 #4392)。

**未確定**: Chrome の M=147・149〜151・153〜159 と M=2〜129・131〜144 は、コミット済みのデータが無く成否を言えない。Node 掃引 (§1) は生データが無く、本 run では再現していない。§3 の ctor 切り分けは単発の観察。

## 1. Node 掃引 (未再現)

前回の記録は「M=2〜160 の掃引で成功 144 点 (M=2〜145)・失敗 15 点 (M=146〜160)」だったが、生データ (`$RUNNER_TEMP/perf/p25_node_sweep.jsonl`) が commit されておらず、本 run では `tools/ott/work/lift/ottl.wasm` が無いため再実行できなかった。この数値は本付録の根拠にしない。

掃引の再現 (素材 `work-m6-ott` を展開した後。既定の `--timeout` は 20000):

```sh
export PERF_TMP=$RUNNER_TEMP/perf
node tools/perf/p15/node_init_sweep.mjs --m $(seq -s, 2 160) --timeout 15000 --out $RUNNER_TEMP/perf/p25_node_sweep.jsonl
```

## 2. Chrome 実測 (AudioWorklet・`chrome_worklet.mjs --init-only`)

| 版・CPU | M | run | 結果 | setup_ms | 出典 (jsonl) |
|---|---|---|---|---|---|
| Chrome 154.0.8037.97・EPYC 7763 | 145 | 3 | 成功 3/3 | 799〜828 | `worklet_range_init.jsonl` (commit `277307238`) |
| 同 | 146 | 3 | 無応答 3/3 (`eval timeout` 30 s) | — | 同 |
| 同 | 146 | 1 | 無応答 (`eval timeout` 150 s) | — | `worklet_range_long.jsonl` |
| 同 | 148・152・160 | 各 3 | 無応答 3/3 (30 s) | — | `worklet_range_init.jsonl` |
| 同 | 145 (署名) | 3 | 署名 145/145 一致 (`sig_ok=true`) | 806〜868 | `worklet_range_sig.jsonl` |
| Chrome 155.0.8059.39・EPYC 9V45 | 1・130 | 3 | 成功 (M=130 の setup 446〜465) | 17〜22・446〜465 | `worklet_init_limit.jsonl` (commit `e4d2d1799`) |
| 同 | 160・176・192・256・288・320・352 | 各 3 | 無応答 (`eval timeout`。timeout 値は未記録) | — | 同 |

- Chrome 155 の行は M=146 を含まない。M=146 の結果は Chrome 154 のみ。
- 測定 commit: 154 の行は `277307238`、155 の行は `e4d2d1799`。155 の HEAD 再現 (`rerun_20261015_worklet_*.jsonl`) は `ab6466296`。
- 再現コマンド (154 の行。素材 `work-m6-ott` 展開後):

```sh
node tools/perf/p15/chrome_worklet.mjs --init-only --m 145,152,148,146,160 --runs 3 --timeout 30000 --out $RUNNER_TEMP/perf/worklet_range_init.jsonl
node tools/perf/p15/chrome_worklet.mjs --init-only --m 146 --runs 1 --timeout 150000 --out $RUNNER_TEMP/perf/worklet_range_long.jsonl
```

**測定 commit から HEAD までの差分** (`git diff --stat 277307238 820b0ee95 -- tools/perf/p15 tools/perf/harness tools/ott`): `tools/ott` の lift・rt・native に計 459 行の変更がある。wasm (`ottl.wasm`) の生成元が変わっており、上の 154 の行は HEAD の wasm では再測定していない。HEAD での再測定は未実施 (#4392 に記録)。

## 3. ctor 切り分け (単発の観察・再現スクリプト未コミット)

| 観察 | 結果 |
|---|---|
| M=146 の止まる位置 | obj 145 (基底 `0x33440000`) の `ctor` (`0x18011d400`) の途中で戻らない (ログ上 `obj 145 ctor` が最後) |
| obj 145 を単独で ctor | 成功 (新しい instance なら通る) |
| 同一 obj アドレス `0x31000000` の ctor を 146 回連続 | 146 回目で無応答 |
| 各 ctor の所要 | 約 3.5 ms で一定 |
| スタックポインタ (`emscripten_stack_get_current`) | 146 回で不変 |
| `malloc(0x2000)` を 400 回 | 成功 (NULL なし) |
| `resume` (`0x180120800`) を同一 obj に 200 回・`setParam` (`0x180120af0`) を 200 回 | 成功 |
| stride 0x30000 の ctor 146 回 | 無応答 |

この表の再現スクリプトは repo に無い。本 run では再現していない。**分かったことは「配置の境界ではなく、同一 instance 内での ctor の呼び出し回数に結びつく可能性」まで**。原因 (どのループ・どのテーブルか) は未確定。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ctor (`0x18011d400`) が同一 instance で 146 回目に戻らない原因 | 上限 145 の意味が未確定。M=146 を通す修正方針が立たない | #4392 [PERF-P26] |
| Chrome の M=147・149〜151・153〜159 と M=2〜129・131〜144 の成否 (単調性) | 成功最大 145 と失敗最小 146 の範囲外は未確認 | #4392 (コメントで追加) |
| Node 掃引の再測定と生データの commit (§1) | 掃引の数値が根拠にならない | #4392 (コメントで追加) |
| `tools/ott` の差分 (459 行) を含む HEAD での再測定 (§2) | 154 の値が HEAD の wasm の値ではない | #4392 (コメントで追加) |
