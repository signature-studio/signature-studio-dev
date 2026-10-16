# REPORT #5533 — `1046a30` の X・P の実行時値 trace (LD-277・親 #4749 の受入 2・3)

親: #4749。前提: #4676 (LD-237)。

## 1. 結論

- X・P の実行時値は**未取得**。判定 (`10479c7`) は**判定不能のまま**。`candidate_verdicts_277.jsonl` と `spill178_1161.tsv` は変えていない。
- **主因: survey 経路 (boot と 942 unit) で `function_1046a30` に到達しない** (§3b: `m11_wv_push` の呼出し 0 件)。値を記録する先をどう変えても、survey からは X・P を取れない。到達には unit の実行経路の変更が要り、計装の範囲を超える。
- 前 run (§3) の「固定リング `0x11FFF000` が boot 中の heap に上書きされる」は実測どおりだが、主因ではない。固定リング方式は捨てた (§2・§3b)。
- 現 IR は `M11_FIX_LD236=1`・`ir_sha256` `667bbb…` (§3b)。前 run の `c572d427…` とは生成経路の差分が未切り分け。この IR で `m11_gen_ir2.sh` → `m11_e2e.sh` が通り、#4676 と同じ survey 結果 (ok=875・miss=46・trap=20・clobber=0) に一致した。

## 2. 作ったもの (`tools/m11/ldfix/`・診断専用)

| ファイル | 役割 |
|---|---|
| `watch_ir_5533.py` | `function_1046a30` だけに観測フック `m11_wv(id, value)` を入れる。id 0 = 入口, 1 = `%359`, 2 = X (`%363`), 3 = P (`%491`), 4 = P の指す 4B (`%505`) |
| `watch_shim_5533.c` | `m11_wv(id, value)` を EM_JS で JS 配列 `globalThis.__m11_wv` に `[id, value]` として積む (上限 2000 件)。linear memory は使わない |
| `watch_survey_5533.mjs` | survey と同じ経路 (`_m11_set_survey(1)` → boot → 942 unit) で、unit ごとに `__m11_wv` を空にしてから実行し、積まれた値を読む |

## 3. 失敗の実測 (測定 commit は本 PR の最後の commit)

- watch build (`stage4.sh watch5533`) は link 成功 (`undefined symbol: 0`・`signature mismatch: 0`)。`m11_wv` は shim の `T` で解決している。
- 942 unit を走らせた結果、リングの count は全 unit で 0 (`WATCH_DONE units_with_hooks: 0`)。
- 原因の切り分け: boot 前に `0x11FFF000` へ `0xdeadbeef` を書くと、boot 後に `0` になる。boot 中に heap が `0x12000000` から `0x36d80000` まで伸び、このアドレスをプログラムが使う。`m11_image.bin` の中にもこのアドレスは無い。よって値は観測前に消えている。
- `function_407a50` の entry probe を入れた build は stage4 の結果が変わった (`stage4=false`・`reached_stage 3`)。フックの存在が boot を変えている。

## 3b. 再検証 (2 回目の run・診断計装を JS 配列方式に変更)

- 素材: `work-m11` を `tools/m11/work/` に展開 (tar の内部パスは `tools/m11/work/…` のため `-C tools/m11` では二重になる。展開先に注意)。`fl-win64` は `$RUNNER_TEMP/fl-win64`。
- 現 IR (`M11_FIX_LD236=1`・`m11_gen_ir2.sh` rc 0): `ir_sha256` `667bbb…` (前 run の `c572d427…` と異なる。生成経路の差分は未切り分け)。
- 同じ IR での `m11_e2e.sh`: survey ok=875・miss=46・trap=20・clobber=0 (前 run と一致)。gate の期待値 873 との不一致も同じ (既存の状態)。
- 計装を linear memory の固定リングから JS 配列 (`globalThis.__m11_wv`・EM_JS) に変更。shim は `obj/shim_*.o` として手で compile する必要がある (`stage4.sh` は `shim_*.o` を `emcc -c` しない)。
- watch build: 成功 (`signature mismatch: 0`・`undefined symbol: 0`)。入力は `work/boot_final3.ll` (`boot_final.ll` を入力にすると `duplicate symbol` で link が落ちる)。
- **survey 経路の観測**: `m11_wv_push` の呼出し回数は boot で 0・942 unit 全てで 0 (`total_calls 0 units 0`)。`function_1046a30` は survey の unit 実行中に一度も実行されない。

結論: 前 run の「heap による上書き」は誤りではないが、主因ではない。**主因は、survey 経路で `function_1046a30` に到達しないこと**。したがって、計装の記録先をどう変えても X・P の値は survey からは取れない。到達させるには unit の実行経路を変える必要があり、これは計装の範囲を超える。

## 4. 未達の受入

| 受入 | 状態 | 理由 |
|---|---|---|
| 1046a30 の X・P の実行時値を trace で取り、機械語 4 段と 10479c7 の P の一致を REPORT に書く | 未達 | リングが上書きされ、値が 1 件も取れない (§3) |
| 結果を受けて 10479c7 を判定し、candidate_verdicts_277.jsonl・spill178_1161.tsv を更新する | 未達 | 上の値が無いため判定を変えない (根拠なしに判定を変えない) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値の観測方式: 固定リングを使えない。boot の heap と衝突する。代替は heap 外の観測 (例: 呼出し先の戻り値経由・専用の別 region の mmap) | X・P の値が取れず、10479c7 が判定不能のまま | #4749 (親)・#5533 の続き |
| `function_1046a30` が survey 経路 (boot と 942 unit) で実行されない原因の特定 (到達させる unit・経路の選定) | 値を取る前提が立たない。X・P の観測は survey では不可能 | #4749 (親)・#5533 の続き |
| `0x11FFF000` の上書き元の特定 (前 run の観測。到達の問題より優先度は低い) | 固定リングの方式を捨てたので影響は小さい | 同上 |

## 6. 再現

```sh
cd tools/m11 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash m11_gen_ir2.sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash m11_e2e.sh   # survey ok=875 を確認
python3 ldfix/watch_ir_5533.py work/boot_final3.ll $RUNNER_TEMP/watch5533.ll
# stage4.sh は shim_*.o を compile しないため、shim を手で obj/ に置く (link は obj/*.o を読む)
mkdir -p ldfix/work/stage4/watch5533/obj
emcc -c ldfix/watch_shim_5533.c -o ldfix/work/stage4/watch5533/obj/shim_watch5533.o -O0 -g1
bash ldfix/stage4.sh $RUNNER_TEMP/watch5533.ll watch5533
S4_NAME=watch5533 node ldfix/watch_survey_5533.mjs   # WATCH_DONE units_with_hooks: 0 (§3)
```
