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
| Chrome 155.0.8059.39・EPYC 9V45・素材 wasm (sha `e8fb…`)・`1dad02299` で測定 | 145 | 3 | 成功 3/3 | 472〜500 | `head_1dad02299_worklet_m145_146_init.jsonl` |
| 同 | 146 | 3 | 無応答 3/3 (`eval timeout` 30 s) | — | 同 |
| Chrome 154.0.8037.97・EPYC 7763・素材 wasm (sha `e8fb…`)・`9e0bbf7e7` の機械で再測定 | 145 | 3 | 成功 3/3 | 811〜834 | `rerun_20261015_e8fb_worklet_m145_146_init.jsonl` |
| 同 | 146 | 3 | 無応答 3/3 (`eval timeout` 30 s) | — | 同 |

- M=146 の結果は Chrome 154 (測定 commit `277307238`) と Chrome 155 (測定 commit `1dad02299`・素材 wasm) と本 run の Chrome 154 (`9e0bbf7e7`) の 3 つで、どれも無応答。
- 測定 commit: 154 の行は `277307238`、155 の行 (1・130) は `e4d2d1799`。155 の HEAD 再現 (`rerun_20261015_worklet_*.jsonl`) は `ab6466296`。
- HEAD 測定 (`1dad02299`・Chrome 155 の行): **素材 wasm での測定**。素材 `work-m6-ott` の `tools/ott/work/lift/ottl.wasm` (sha256 `e8fb06203811ff1f42ea563f9647ef290ca93abfe4cc0b7e68660b680eac664e`) を使った。この wasm は `tools/ott/.gitignore` の `work/` 配下で commit に入らない。**HEAD の lift/rt から wasm を再生成していない** (emcc と Windows DLL `OTT_vst2_win64.dll` が本 run の環境に無い)。よって HEAD の lift・rt の差分 (下記) が測定値を変えないことは示せていない。HEAD で作った wasm の測定は子 #4392 に残す。
- 154 の run (`277307238`) で使った wasm の sha は未記録のため、154 と HEAD の wasm が同一かは確認できない。
- 本 run の再測定 (`9e0bbf7e7`・Chrome 154.0.8037.97・EPYC 7763・素材 wasm の sha `e8fb…` 一致): M=145 は 3/3 成功 (setup 811〜834 ms)、M=146 は 3/3 無応答 (`eval timeout` 30 s)。生データ: `tools/perf/p15/results/rerun_20261015_e8fb_worklet_m145_146_init.jsonl`。Chrome 155 の HEAD 測定とは版・CPU が違う。
  - 再現コマンド (素材展開後):

```sh
node tools/perf/p15/chrome_worklet.mjs --init-only --m 145,146 --runs 3 --timeout 30000 --out tools/perf/p15/results/head_1dad02299_worklet_m145_146_init.jsonl
node tools/perf/p15/chrome_worklet.mjs --init-only --m 145,146 --runs 3 --timeout 30000 --out tools/perf/p15/results/rerun_20261015_e8fb_worklet_m145_146_init.jsonl
```
- 再現コマンド (154 の行。素材 `work-m6-ott` 展開後):

```sh
node tools/perf/p15/chrome_worklet.mjs --init-only --m 145,152,148,146,160 --runs 3 --timeout 30000 --out $RUNNER_TEMP/perf/worklet_range_init.jsonl
node tools/perf/p15/chrome_worklet.mjs --init-only --m 146 --runs 1 --timeout 150000 --out $RUNNER_TEMP/perf/worklet_range_long.jsonl
```

**測定 commit から HEAD までの差分** (`git diff --stat 277307238 1dad02299 -- tools/perf/p15 tools/perf/harness tools/ott`): 9 files / 459 insertions / 18 deletions。`tools/ott` の lift (`x64c.py`・`rcr_emit_check.py`)・rt (`ott_x87.h`)・native (`ott_native.c`) と、`tools/perf/p15/node_init_sweep.mjs` (新規) を含む。`chrome_worklet.mjs` と `tools/perf/harness` は差分 0。HEAD (`1dad02299`) の Chrome 測定は上の表の 155 の行 (M=145・146、各 3 run) に記録した。HEAD の lift コードで wasm を再生成していないため、この差分が測定値を変えたかは本 run では分離していない。

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

## 3b. 子 #4392 の一次切り分け (Node・同期・`tools/perf/p15/ctor_heap_probe.mjs`)

測定 commit: `daea2d06f` (プローブを追加した commit。コードの最後の変更)。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb…`) を展開して測定。

| 測定 | 結果 | 出典 |
|---|---|---|
| `node node_init_sweep.mjs --m 145,146 --timeout 15000` | M=145 成功 (setup 788 ms)・M=146 timeout | 本 run のローカル出力 |
| `ctor_heap_probe.mjs 146` 3 run (HEAD) | 3/3 とも 146 回目の ctor 前 (`before_call` 145) で戻らず (25 s で打ち切り) | 本 run のローカル出力 (未 commit) |
| `ctor_heap_probe.mjs 145` (対照) | 完了 (wall 1 s)・`bytes_per_ctor` 3673793 | 同上 |

観察 (本 run で確認した数値):
- ctor 1 回で wasm heap の先頭が約 3.67 MB 進む (`bytes_per_ctor` 3673793)。`ctor` は `operator new` (`f_1801a04d0`・`f_1801a7794`) で `0x40000` などを 6〜14 回確保する (commit 済みの根拠: `tools/hostbridge/evidence/ott_ottprocessor_ctor.asm` の 172〜196 行、`MOV ECX,0x40000` / `CALL 0x1801a7794`)。
- 145 回後の heap 先頭は `0x2ff93020`。次の 3.67 MB の確保範囲が image の data 領域 (`0x301e2000`〜`0x30284124`) と重なる。
- `ott_data_install` が敷く rdata・data の領域 (`0x301e2000`〜`0x30284124`) は、wasm heap の伸びる範囲と重なる。heap 側の確保は `imp_HeapAlloc` が確保ごとに `memset(0)` する (`tools/ott/rt/ott_cpu.c` 76 行。ただし `HeapAlloc` のゼロ化は確保した領域だけに効く)。
- heap を 64 MiB ずらすと (`malloc` を先に呼ぶ)、止まる位置が `before_call` index 145 (146 回目) から index 127 (128 回目) へ早まる。index で 18 回早まる。64 MiB ÷ 3.67 MB (`bytes_per_ctor` 3673793 B) ≈ 18.3 回と整合する。Node・1 run のみ・`work/` で実施 (commit 外)。

**未確定 (この節の結論ではない)**: 「heap が data 領域に届いた確保が、data の内容を変えて ctor を戻らなくする」という機構は**仮説**。実測したのは次の 2 点だけ: (a) 145 回目までの ctor では data 領域の hash が不変 (Node・1 run。プローブは commit 外で、コミット済みの再現は未整備)、(b) 146 回目の ctor が戻らないこと (HEAD で 3/3)。146 回目の確保直後に data が変わることの直接確認と、どの関数で戻らなくなるかは未了。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ctor (`0x18011d400`) が同一 instance で 146 回目に戻らない原因 | 上限 145 の意味が未確定。M=146 を通す修正方針が立たない | #4392 [PERF-P26] |
| Chrome の M=147・149〜151・153〜159 と M=2〜129・131〜144 の成否 (単調性) | 成功最大 145 と失敗最小 146 の範囲外は未確認 | #4392 (コメントで追加) |
| Node 掃引の再測定と生データの commit (§1) | 掃引の数値が根拠にならない | #4392 (コメントで追加) |
| §3b の監視プローブ (145 回までの data hash 不変・`next_span_overlaps_data`) が commit 外・再現未整備 | §3b の (a) は再現できない。`ctor_heap_probe.mjs` の 3673848 (`next_span_overlaps_data` の判定定数) と観測 `bytes_per_ctor` 3673793 の 55 B 差は判定に影響しないが、由来は未記録 | #4392 (次の run で commit) |
| 154 の run の wasm sha が未記録 (§2) | 154 と HEAD の wasm が同一かを示せない。HEAD の 155 測定 (M=145・146) は素材 wasm で再現済み | #4392 (コメントで追加) |
