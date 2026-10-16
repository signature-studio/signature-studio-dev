# REPORT #5533 — `1046a30` の X・P の実行時値 trace (LD-277・親 #4749 の受入 2・3)

親: #4749。前提: #4676 (LD-237)。

## 1. 結論

- X・P の実行時値は**未取得**。trace の計装は作ったが、値が一度も記録されなかった。判定 (`10479c7`) は**判定不能のまま**。`candidate_verdicts_277.jsonl` と `spill178_1161.tsv` は変えていない。
- 失敗の原因: 固定アドレスのリング `0x11FFF000` が boot 中のプログラム自身の書込みで上書きされる。実測は §3。REPORT_942 の方式 (固定リング) は、この build では成立しない。
- 検証済みの事実: 現 IR (`M11_FIX_LD236=1`、`ir_sha256` `c572d427…`) で `m11_gen_ir2.sh` → `m11_e2e.sh` が通り、#4676 と同じ survey 結果 (ok=875・miss=46・trap=20・clobber=0) に一致した。

## 2. 作ったもの (`tools/m11/ldfix/`・診断専用)

| ファイル | 役割 |
|---|---|
| `watch_ir_5533.py` | `function_1046a30` だけに観測フック `m11_wv(id, value)` を入れる。id 0 = 入口, 1 = `%359`, 2 = X (`%363`), 3 = P (`%491`), 4 = P の指す 4B (`%505`) |
| `watch_shim_5533.c` | リング (`0x11FFF000`) に (id, value) を書く `m11_wv` |
| `watch_survey_5533.mjs` | survey と同じ経路 (`_m11_set_survey(1)` → boot → 942 unit) で unit ごとにリングを読む |

## 3. 失敗の実測 (測定 commit は本 PR の最後の commit)

- watch build (`stage4.sh watch5533`) は link 成功 (`undefined symbol: 0`・`signature mismatch: 0`)。`m11_wv` は shim の `T` で解決している。
- 942 unit を走らせた結果、リングの count は全 unit で 0 (`WATCH_DONE units_with_hooks: 0`)。
- 原因の切り分け: boot 前に `0x11FFF000` へ `0xdeadbeef` を書くと、boot 後に `0` になる。boot 中に heap が `0x12000000` から `0x36d80000` まで伸び、このアドレスをプログラムが使う。`m11_image.bin` の中にもこのアドレスは無い。よって値は観測前に消えている。
- `function_407a50` の entry probe を入れた build は stage4 の結果が変わった (`stage4=false`・`reached_stage 3`)。フックの存在が boot を変えている。

## 4. 未達の受入

| 受入 | 状態 | 理由 |
|---|---|---|
| 1046a30 の X・P の実行時値を trace で取り、機械語 4 段と 10479c7 の P の一致を REPORT に書く | 未達 | リングが上書きされ、値が 1 件も取れない (§3) |
| 結果を受けて 10479c7 を判定し、candidate_verdicts_277.jsonl・spill178_1161.tsv を更新する | 未達 | 上の値が無いため判定を変えない (根拠なしに判定を変えない) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値の観測方式: 固定リングを使えない。boot の heap と衝突する。代替は heap 外の観測 (例: 呼出し先の戻り値経由・専用の別 region の mmap) | X・P の値が取れず、10479c7 が判定不能のまま | #4749 (親)・#5533 の続き |
| `watch5533` の ring 上書きの原因の確定 (`0x11FFF000` を使う他の書込み元の特定) | 方式の選択に必要 | 同上 |

## 6. 再現

```sh
cd tools/m11 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash m11_gen_ir2.sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash m11_e2e.sh   # survey ok=875 を確認
python3 ldfix/watch_ir_5533.py work/boot_final3.ll $RUNNER_TEMP/watch5533.ll
bash ldfix/stage4.sh $RUNNER_TEMP/watch5533.ll watch5533
S4_NAME=watch5533 node ldfix/watch_survey_5533.mjs   # WATCH_DONE units_with_hooks: 0 (§3)
```
