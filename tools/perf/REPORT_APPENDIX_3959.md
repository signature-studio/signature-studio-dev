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

## 3c. 子 #4392 の原因切り分け (Node・同期・`tools/perf/p15/ctor_data_overlap.mjs`)

測定 commit: `95f2351e5` (`ctor_data_overlap.mjs` を追加した commit = コードの最後の変更)。HEAD との差分: `git diff 95f2351e5 HEAD -- tools/perf/p15 tools/ott` は 0 行 (測定コードに差分なし)。`-- tools/perf` は本 REPORT の文言修正 (`docs(perf)` commit 60efc8c36) の 19 行のみ。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を展開して測定。
本 fix run では素材が展開されず (`$ARTIFACTS_DIR` は `fl-win64` のみ) 再測定していない。下表は実装 run (測定 commit `95f2351e5`) の値。

| 測定 | 結果 |
|---|---|
| `node node_init_sweep.mjs --m 145,146 --timeout 15000` (HEAD) | M=145 ok・M=146 timeout (15 s)。`setup_ms` は生ログ (`$RUNNER_TEMP`) のみで commit に無いため載せない |
| `ctor_data_overlap.mjs 145` ×2 | 2/2 同一: `data_changed_during_ctor_at=-1` (145 回の ctor で data 不変)・heap 起点 `0x1038d528`・1 回目の data 領域への確保 `0x301d3068` (malloc 10 回目, k=9)、その malloc の前後で data hash `b396a36c3521` → `27928e2cfb77` |
| 対照: `ctor` 145 回後の heap 先頭 | `0x2ff93079` (ctor 1 回あたり約 3.67 MB 進む) |

結論 (測定で確認した範囲):
- ctor の呼び出し自体は data を書き換えない。145 回までの ctor で data の hash は不変。
- heap の確保は `GLOBAL_BASE=0x10000000` の静的データの後ろから伸び、約 145 回で image data 領域 (`0x301e2000`〜`0x30284124`) に届く。届いた確保の後で data の内容が変わる。
- (→ §3d。この段落の仮説は §3d で棄却できなかった。)
- **ただし 146 回目の ctor が止まる箇所 (どの関数・どのループ) は未特定**。data 書換え → 停止の因果は直接示していない。

未確定: 146 回目の ctor で止まる関数の特定 (`ott_run` の trace で確認が必要)。修正 (`GLOBAL_BASE` を data 領域より上へ移す、または data の配置を heap と分ける) は lift 全体の再ビルドと harness の object 配置 (`0x31000000` 以降) の変更を伴うため、本 run では行わない。

## 3d. 子 #4392 の因果確認 (Node・同期・`tools/perf/p15/ctor_restore_data.mjs`)

測定 commit: `491700c5d` (`ctor_restore_data.mjs` を追加した commit = コードの最後の変更)。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を展開して測定。

| 測定 | 結果 |
|---|---|
| `RESTORE=0` M=145 | 145 返る・data 不変 (`data_changed_during_ctor_at=-1`) |
| `RESTORE=1` M=145 | 145 返る・data 不変 |
| `RESTORE=1` M=146 (3 run) | 3/3 とも 146 回目で戻らない (timeout 40 s) |

- 仮説「data 領域の書き換えが 146 回目の停止の原因」を試した。各 ctor の直前に data 領域を `ott_data_install` 直後の内容へ戻しても、M=146 は 3/3 で止まった。
- **交絡のため仮説の棄却はできない**: data 領域には allocator のメタデータも重なる可能性があり、書き戻しは allocator の状態も巻き戻す。そのため「書き換えが無い状態で 146 回を通す」条件を作れていない。
- 3 run は同じ決定的スクリプトの反復であり、独立した再現としての重みは小さい。
- heap を data 領域より上へ逃がす実験 (SKIP) は、wasm メモリ (0x36000000、約 864 MB) に 145 回分 (約 532 MB) が収まらず、M=10 でも止まったため無効。成果物には含めない。

## 3e. 子 #5403 (PERF-P28) の trace: 146 回目の ctor は仮想呼び出しで壊れ、ログ出力が止まらない (Node・同期)

測定 commit: `4266ebfd1` (`ctor_loop_trace.mjs` と `instr_loops.py` を追加した commit)。素材 `work-m6-ott` の `tools/ott/work/lift/ottl.wasm` (sha `e8fb06203811ff1f`) を使い、`wasm2wat` → `instr_loops.py` (loop 先頭 209 箇所に実行回数カウンタと budget) → `wat2wasm` で計装した (生成物は `tools/ott/work/` 配下のみ・commit 外)。

**適用範囲**: 以下は Node・同期・`fd_write` stub の下でだけの観察。Chrome (AudioWorklet) の M=146 無応答は本節では測っておらず、同じ原因かは未確認。

**測定の状態**: 下表の計装 wasm の値は本 fix の測定 (HEAD `545bec77b`・素材 `work-m6-ott` の `ottl.wasm` sha `e8fb06203811ff1f`・wabt を npm で一時導入・`instr_loops.py` → `wat2wasm` → `ctor_loop_trace.mjs`)。計装なしの `node_init_sweep` は本 run では未再測定。

| 測定 (head `545bec77b`) | 結果 |
|---|---|
| `node tools/perf/p15/node_init_sweep.mjs --m 145,146 --timeout 15000` (計装なし) | 未再測定 (前 run: M=145 ok (setup 783 ms)・M=146 timeout) |
| `ctor_loop_trace.mjs 145` (計装 wasm) ×1 | 完走 (`completed: 145`・trap なし)。ctor 145 直後の `budget_left` = 406,505,799 |
| `ctor_loop_trace.mjs 146` (計装 wasm) ×3 | 3/3 とも ctor 146 で `RuntimeError: unreachable`。ctor 146 の loop 170 = 399,163,510 回 (3/3 で同値)。ctor 1〜145 の loop 170 の合計は 0。ctor 146 の loop-head 総数 402,834,282 回のうち loop 170 が 99.09%。trap 時 `budget_left` = 0 |
| `PERF_FD_WRITE=1` `ctor_loop_trace.mjs 146` ×3 | 3/3 とも `Error: abort` (`_abort_js`)。`fd_text` = `[ott] call to UNLIFTED function 0 (shifted VA; RVA 0xffffffffd0000000) ret=0x3011d9fc\n`。ctor 146 の loop 170 = 2 回 (loop-head 総数 3,670,778 回)・trap 時 `budget_left` = 399,163,504。同 M=145 は完走 |

`budget_left` の定義: `perCtor[k].budget_left` は「ctor k の直後」の残り budget (2e9 から通算で減る)。ctor 145 直後は 406,505,799、trap 時は 0。ctor 145 直後から trap までに減った 406,505,799 は、ctor 146 の loop-head 総数 402,834,282 と、ctor 145 の後続 `run` 呼び出し (ctor 間の処理) の loop-head 3,671,517 の和。後者は各 ctor 間で同じ 3,671,517 回ずつ出ており、`perCtor[k].delta` には入らない (`delta` は ctor 呼び出しの前後だけを測るため)。

分かったこと (Node・同期・`fd_write` stub 下。`fd_write` 書込み版の 3 run を含む):
- **loop 170 は wasm func 92 内の loop** (`ottl.wat` の loop 出現順 170 番。`func (;92;)` の内側)。stdio 書き込みと推定する根拠は、`PERF_FD_WRITE=1` で `fd_write` が `nwritten` を書くと、同じ loop が 2 回で抜けて `fd_text` のエラー文言が出ること。stub (`return 0`・`nwritten` を書かない) の下では loop が抜けず、399M 回回って budget を使い切る。Node の M=146 の timeout は、この stub の下でエラー文言の出力が終わらない結果と読める。
- 上の 2 点は、loop 170 が「ctor 146 の loop-head 回数の 99% を占める」ことまでしか数値で言えない。loop 170 が stdio 書き込みであることは、`fd_write` 書込み版の 2 回抜けで裏付けるが、関数の対応は推定。
- **146 回目の ctor で、ctor `0x18011d400` 内の仮想呼び出し** (`tools/hostbridge/evidence/ott_ottprocessor_ctor.asm` の L303: `18011d9f9: CALL qword ptr [RAX + 0x38]`。直前は L300〜302 で `MOV RCX,[RDI]`・`MOV RAX,[RCX]`) が、VA `0` (shifted RVA `0xffffffffd0000000`) を呼ぶ。`ott_unlifted` が中断する (前 run の `fd_write` 書込み版の出力)。
- 146 の上限は、「heap が data 領域に届いた後で vtable が壊れる」ことで起きる、と読むのが自然な仮説。ただし、どの確保が vtable を書き換えたかは未確定。§3d の交絡 (allocator メタデータ) と同じ問題が残る。

未確定:
- ctor 146 の loop 別実行回数は測定済み (上表)。loop 170 が 99.09%、次点は loop 9 (2,097,152 回) と loop 7 (1,572,864 回) で、残りの loop の合計は約 367 万回。`BUD` は通算の budget (2e9) で、trap は loop 170 だけの条件ではないが、ctor 146 の予算の大半は loop 170 が使っている。「loop 170 が原因」とは言えず、「ctor 146 の loop-head 回数の 99% を占める」までを言う。
- 壊れた vtable を書いた store の特定 (watchpoint 相当の計装が必要)。
- wasm 関数番号と VA `0x18011d400` の対応表。`ottl.wasm` に name section が無く、`ott_run` の dispatch から関数番号を取り出す作業は本 run で完了していない。対応の一次証跡は `tools/hostbridge/evidence/ott_ottprocessor_ctor.asm`。
- 「`fd_write` 書込み版で M=146 が 3/3 `_abort_js` で停止する」「`call to UNLIFTED function 0` の出力」は、本 commit の `PERF_FD_WRITE=1` で再現済み (上表)。
- `fd_write` の stub は `tools/perf/p15` の harness 8 件 (`ctor_data_overlap.mjs`・`ctor_heap_probe.mjs`・`ctor_restore_data.mjs`・`node_init_sweep.mjs`・`web/shared_worker.mjs`・`web/shared_worklet.js`・`web/worker.mjs`・`tools/perf/p8/real/web/real_worker.mjs`) と、新規の `ctor_loop_trace.mjs` (`PERF_FD_WRITE` 未指定時) に入る。`chrome_worklet.mjs` と `chrome_shared.mjs` は `fd_write` stub を含まない。Chrome 側 146 の無応答が同じ原因かは本 run で未確認。

再現コマンド (素材 `work-m6-ott` 展開後。`tools/ott/work/` 配下に出力):

```sh
wasm2wat tools/ott/work/lift/ottl.wasm -o tools/ott/work/lift/ottl.wat
python3 tools/perf/p15/instr_loops.py tools/ott/work/lift/ottl.wat tools/ott/work/lift/ottl_lc.wat
wat2wasm tools/ott/work/lift/ottl_lc.wat -o tools/ott/work/lift/ottl_lc.wasm
node tools/perf/p15/ctor_loop_trace.mjs tools/ott/work/lift/ottl_lc.wasm 146 $RUNNER_TEMP/perf/trace146.json
PERF_FD_WRITE=1 node tools/perf/p15/ctor_loop_trace.mjs tools/ott/work/lift/ottl_lc.wasm 146 $RUNNER_TEMP/perf/trace146_fdw.json
```

出力 JSON の `fd_text` に `fd_write` の書込み内容 (最大 4000 字) が入る。`perCtor` は完走した ctor と trap した ctor (`trapped: true`) の loop 別回数と `budget_left` を持つ。

## 3f〜3h (前 run までの vtable 窓・memory.fill・calloc)

全文は `REPORT_APPENDIX_5403.md` に分割移動した (250 行上限)。要点: func 23 が vtable `0x30203BD0` を 0 にする `memory.fill` (func 75) の dest `0x301d3e40` は、func 75 の引数ではなく `malloc` (f119) の戻り値で、146 回目の ctor の中だけ image 内の領域を返す (§3i の機構の結果)。

## 3i. 子 #5403 (PERF-P28) の停止原因: sbrk の break が image 基底を越える (Node・同期・`fd_write` nwritten 版)

測定 commit: `320bb129a` (`tools/perf/p15/ctor_brk_trace.mjs` を追加した commit。`tools/perf/p15` の既存ファイルは §3h の `7156a4b3e` から変更なし)。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を計装なしで使った。harness は `ctor_calloc_image.mjs` と同じく `fd_write` が `nwritten` を書く版。

wasm func 123 は sbrk 相当で、break 値を線形メモリ `269004816` (`0x1008AFD0`) の i32 に持つ。初期値は `0x1038D520` (global 0 と同じ)。image (`0x30000000`〜`0x30284124`) は線形メモリの固定位置にあり、break の上限は `memory.size` だけで見て image を避けない。

| 測定 (HEAD `320bb129a`) | 結果 |
|---|---|
| `ctor_brk_trace.mjs 146` ×3 | 3/3 同一。ctor 1〜145 完走・break は単調増加。146 で `Error: abort`。145 完走後の break `0x2ff94000` (image 基底の手前)、trap 時 `0x30314000` (image 基底を超える) |
| ctor ごとの break 増分 | 最小 3670016 B・最大 3674112 B (3670016 = 14 × 262144。差 4096 B は割り当て境界の差と読める)。ctor 1〜145 の全増分がこの範囲 |
| `ctor_brk_trace.mjs 146 33554432` (shift 32 MiB) ×1 | trap は ctor 137 (completed 136)。break 最後 `0x3000b000`、image 内に入った完了 ctor は 136 のみ |
| 同 shift 64 MiB ×1 | trap は ctor 128 (completed 127)。completed 127 は image 内 (`0x30083000`) |
| 同 shift 128 MiB ×1 | trap は ctor 109 (completed 108)。break は image の手前 (`0x2fdf1000`) で止まる |

分かったこと:
- 停止の機構: ctor 1 回ごとに break が約 3.5 MiB (増分 3670016〜3674112 B) 押し上げられ、解放は break に戻されない (break は単調増加)。145 回目の終わりで break は image 基底 `0x30000000` の直前まで来る。増分が 14 × 262144 B と一致するのは算術上の一致で、割り当て個数は未計数 (推測)。146 回目の ctor 内で break が image に入り、calloc が image 内の領域を返す (§3h の 10 件。§3g・§3h の本文は `REPORT_APPENDIX_5403.md` に分割移動した)。その 8 番目 `0x301d3e40` の 262144 B が vtable `0x30203BD0` を覆って 0 にする (§3g)。vtable が 0 になった後で `call [rax+0x38]` (`18011d9f9`) が VA 0 を呼び、abort する (§3e)。
- 機構の鎖は、break が image に届く → calloc が image 内を返す → 0 埋めで vtable が壊れる → 間接呼び出しが 0 へ飛ぶ、で閉じる。
- 起動直後の break 押し上げ量と trap する ctor 番号が直線的 (shift 0 / 32 / 64 / 128 MiB で 146 / 137 / 128 / 109)。shift との差を trap 番号の差 (9 / 18 / 37 ctor) で割ると 1 ctor あたり 3.56 / 3.56 / 3.46 MiB で、1 ctor あたり約 3.5 MiB と概ね整合する (trap 番号は整数のため、厳密な一致ではない)。
- 「146 で止まる」は ctor の番号の性質ではなく、break と image 基底の残余 (`0x30000000 − 0x2ff94000` = 442368 B = 約 0.42 MiB) の結果と読める。残余が 1 ctor の増分 (約 3.5 MiB) より小さいため、146 回目の ctor の中で break が image に入る。

未確定:
- 1 ctor が約 3.5 MiB を解放せず積む理由 (割り当ての個数・解放経路は未計数。ctor 側の leak か、同一 instance に繰り返し呼ぶ harness の前提の違いかは未確定)。実機 (Chrome・AudioWorklet) で同じ積み上げが起きるかは未確認。
- image が固定 `0x30000000` に置かれ、heap の上限検査がそれを避けない点は、lift の配置の問題。修正方針 (image を heap の上に置く・break の上限を image 基底にする・ctor の解放を入れる) は本 run では選んでいない。
- VA `0x18011d400` ↔ wasm 関数番号: ctor は func 16 (`REPORT_APPENDIX_5403.md` §3j)。全 case の対応は未完。

再現コマンド (素材展開後。`tools/ott/work/lift/` 配下に出力):

```sh
wasm2wat tools/ott/work/lift/ottl.wasm -o tools/ott/work/lift/ottl.wat
node tools/perf/p15/ctor_brk_trace.mjs tools/ott/work/lift/ottl.wasm 146
node tools/perf/p15/ctor_brk_trace.mjs tools/ott/work/lift/ottl.wasm 146 33554432
```

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ctor (`0x18011d400`) が同一 instance で 146 回目に戻らない原因 | §3i で機構 (break が image 基底 `0x30000000` を越える) を特定。未確定は、1 ctor が 14 個の 262144 B を解放しない理由と、Chrome で同じ積み上げが起きるか。§3g の vtable 0 化の store (func 75 の memory.fill) はこの機構の結果 | #4392 [PERF-P26] |
| Chrome の M=147・149〜151・153〜159 と M=2〜129・131〜144 の成否 (単調性) | 成功最大 145 と失敗最小 146 の範囲外は未確認 | #4392 (コメントで追加) |
| Node 掃引の再測定と生データの commit (§1) | 掃引の数値が根拠にならない | #4392 (コメントで追加) |
| §3b の監視プローブ (145 回までの data hash 不変・`next_span_overlaps_data`) が commit 外・再現未整備 | §3b の (a) は再現できない。`ctor_heap_probe.mjs` の 3673848 (`next_span_overlaps_data` の判定定数) と観測 `bytes_per_ctor` 3673793 の 55 B 差は判定に影響しないが、由来は未記録 | #4392 (次の run で commit) |
| 154 の run の wasm sha が未記録 (§2) | 154 と HEAD の wasm が同一かを示せない。HEAD の 155 測定 (M=145・146) は素材 wasm で再現済み | #4392 (コメントで追加) |
