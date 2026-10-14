# tools/flelift/boot — #2719 (WIN-8) x64c 寛容起動: 942 unit の逐次試行と CreateFruityInstance の観測

> 正本の要約は `tools/flelift/boot/REPORT.md` §11。本書は詳細 (工程・結果表・skip 一覧・survey との差・リスク評価)。
> 測定 commit: **a55cb0d5** (`fle_boot.c` / `fle_boot.mjs` / `build.sh` / `fle6_measure.sh` を変えた最後の commit)。
> 既知類型との関係: 寛容起動で見えた clobber (units 配列・InitContext・unit 先頭 8B の 0 化) は、#3060 の `f_6a7b70` 広域ゼロ埋めと同じ現象と推定 (未実測の推定)。`docs/DEFECTS.md` D1a〜D23 のどれにも直接は当たらない (推定)。

## 0. 結論

- x64c の寛容起動を足した (`FLE_TOLERANT=1` 寛容 / `FLE_TOLERANT=2` 診断)。**既定 (未指定) の数値は不変** (209 / GetMem 1,890 / FreeMem 776 / 停止 unlifted `0x6a7b70`)。
- **942 unit を最後まで試行した** (mode 1・mode 2 とも 942)。ただし mode 1 は unit 245 (VA `0x733090`・dispatch 209 番目) の ExitProcess の後に units 配列を含む InitContext が 0 になり、695 unit が clobber で走れなかった。
- mode 2 (診断: 失敗 unit の後で InitContext・InitTable・units 配列・unit 先頭 8B を起動時の値へ戻す) では 942 unit が走り、ok 811 / empty 46 / exit 19 / oob 65 / noproc 1。ただし mode 2 は補修であり、状態の欠落を消すものではない (§6)。
- **CreateFruityInstance (0x1375990) には到達しなかった**。両 mode とも呼出しは `oob` で即 trap し、API (RegisterClassW・CreateWindowExW を含む) は 1 件も呼ばれなかった (`soft_called` 空)。trap 地点は CFI 本体 (または直接呼出し先) 内と推定 (未特定)。残件は #3077 [WIN-16] (CFI の trap 地点と CS 0x12bd390 の登録経路) に寄せる。
- 寛容 mode 1 の dispatch は 209 (unit 245 で ExitProcess)。mode 2 は 895 dispatch (試行 942 のうち)。

## 1. 測定条件

- 素材: `fl-win64` を `docs/WORKFLOW.md` §11 の手順で展開し、`FL_WIN64_DIR` に指定。`[EMSDK]` は既存 (`docs/REFERENCES.md` §4)。4 core・RAM 15.6GB。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FLE_BOOT_RUNS="tol tol2" FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh` (lift → clang 8 shard → link → boot)。既定経路は `FLE_BOOT_RUNS=default FLE_EXTRA_ROOTS=`。
- 寛容 mode 1 = `FLE_IPP=1` + `FLE_TOLERANT=1`、mode 2 = `FLE_IPP=1` + `FLE_TOLERANT=2`。shim 有は #3062 の shim 行 (209 / 2,314 / 1,199) と同じ条件。

## 2. 工程 (測定 commit a55cb0d5・実測)

| 工程 | 秒 | ピーク RSS | 備考 |
|---|--:|--:|---|
| gen-A | 6 | - | |
| lift (root 0x6a7b70・0x1375990) | 62〜65 | 609MB | functions 29,937 / insns 1,564,587 (root 0x6a7b70 のみの #2702 は 29,908 / 1,557,903) |
| clang plain (8 shard) | 57〜72 | 2,260〜2,630MB/shard (1 回目) | link mismatch 0 / undefined 0 / duplicate 0 |
| boot mode 1 | 18〜19 | - | |
| boot mode 2 | 17〜19 | - | |
| 既定経路 (root 無し) | lift 62 | 609MB | 既定の数値は #2702 と一致 |

## 3. 結果 (942 試行・n=1)

| 経路 | 試行 | ok | empty | noproc | clobber | exit | oob | dispatch (units_run) | GetMem / FreeMem | 停止 | CFI |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|---|
| 既定 (root 無し) | (停止) | - | - | - | - | - | - | 209 | 1,890 / 776 | unlifted `0x6a7b70` | 未実行 |
| 寛容 mode 1 | 942 | 208 | 37 | 1 | 695 | 1 | 0 | 209 | 2,314 / 1,199 | unit 245 の ExitProcess (`0x412a12` 系) | oob 即時 |
| 寛容 mode 2 (診断・補修あり) | 942 | 811 | 46 | 1 | 0 | 19 | 65 | 895 | 2,320 / 1,200 | 全 942 試行の後 ExitProcess (exit 20) | oob 即時 |

- mode 1 の clobber 695 は unit 246〜941 (proc の先頭 8B が 0 = 起動時は非 0 だった)。InitContext (`0x15eac90`) のポインタ自体が 0 になっていた (`fle_unit_proc` が全て 0 を返す)。
- mode 2 の補修 84 回 (`restored`) は、skip の各 unit の後に InitContext 16B・InitTable 16B・units 配列・unit 先頭 8B を起動時の値へ戻した回数。mode 1 の補修前は同じ 942 のうち 246 以降が 0 化されていた。
- mode 2 の empty 46 は隔離 survey (`results/survey.json`) の empty 46 と一致。noproc 1 も一致。
- 寛容 mode 1 の最初の 209 dispatch は、#3062 の shim 行 (units 209 / GetMem 2,314 / FreeMem 1,199) と一致する。

## 4. skip 一覧 (mode 2・84 件)

形式: `unit VA 種類` (unit は InitTable の添字・VA は proc)。種類: `exit` = ExitProcess (JS 例外化)・`oob` = wasm の範囲外アクセス。

```text
245 0x733090 exit
254 0x76c410 oob
265 0x7a7360 exit
272 0x7f5350 oob
275 0x80e170 oob
276 0x80f980 oob
279 0x8136d0 oob
280 0x816010 exit
283 0x81e040 oob
291 0x832660 exit
296 0x846130 exit
302 0x86d240 oob
304 0x883140 exit
307 0x8b2080 oob
308 0x8b43f0 oob
311 0x8cb690 oob
313 0x8d8840 oob
314 0x8e48a0 exit
327 0x8f7070 oob
328 0x902960 oob
365 0x977100 oob
369 0x981550 oob
415 0x9b6180 oob
421 0x9cefd0 oob
424 0x9d95f0 oob
426 0x9dac90 oob
427 0x9db1d0 exit
429 0x9df8a0 oob
432 0xa31210 oob
477 0xabfd60 oob
484 0xad0680 oob
492 0xad5700 oob
493 0xad9ba0 oob
503 0xaee5a0 exit
509 0xb39ca0 oob
513 0xb654c0 oob
519 0xb76a70 oob
520 0xb76bf0 oob
547 0xbd6a00 oob
555 0xbf2500 exit
584 0xc1c7f0 exit
585 0xc217b0 oob
589 0xc21a00 exit
597 0xc2eff0 oob
604 0xc44460 exit
615 0xc620b0 oob
616 0xc63d20 oob
647 0xc97ac0 oob
649 0xc9c620 oob
652 0xcaa5b0 oob
659 0xceaa30 oob
661 0xcf06e0 oob
666 0xd0eee0 oob
669 0xd33480 oob
712 0xdc4e60 oob
719 0xddb790 oob
745 0xebb3b0 oob
766 0xf55b10 oob
770 0xf8cba0 oob
800 0xfdfb20 oob
806 0x102b010 oob
829 0x10c3210 oob
830 0x10d50d0 oob
838 0x10e6230 oob
850 0x1102fb0 oob
864 0x11562a0 oob
865 0x11573e0 oob
873 0x1251210 oob
876 0x1253c20 oob
880 0x1263540 oob
882 0x1266a60 oob
884 0x1268010 oob
885 0x1274ed0 oob
888 0x12aea40 exit
890 0x12bf9b0 oob
891 0x12c69f0 exit
894 0x12cbeb0 exit
895 0x12ddfe0 exit
898 0x1306110 exit
907 0x13314e0 oob
917 0x134c760 oob
923 0x136c660 exit
935 0x1374350 oob
936 0x1375000 oob

```

mode 1 の skip は 696 件 (unit 245 の `exit` 1 件 + unit 246〜941 の `clobber` 695 件 + 起動時 proc 0 の `noproc` 1 件は skip に数えず)。

## 5. 隔離 survey (`results/survey.jsonl`) との差 (unit 番号)

- 隔離 survey: ok 888 / oob 2 / unlifted 5 / empty 46 / noproc 1 (942)。
- 寛容 mode 2: ok 811。**survey で ok だったのに寛容で ok にならなかった unit は 77 件** (oob 62・exit 15)。逆方向 (survey で非 ok → 寛容で ok) は 0 件。
- 77 件の unit 番号 (survey ok → 寛容で非 ok): 245 254 265 272 275 276 279 283 291 302 304 307 308 311 313 314 327 328 365 369 415 421 424 426 427 429 432 477 484 492 493 503 509 513 519 520 547 555 584 585 589 597 604 615 616 647 649 652 661 669 712 719 745 766 770 800 806 829 838 850 864 865 873 876 880 882 884 885 888 890 891 894 907 917 923 935 936
- 解釈 (推定を含む): 逐次起動では、先行する unit が作った状態 (と失った状態) を後続 unit が引き継ぐ。survey は unit を 1 本ずつ新 stack・同じ状態で走らせるため、この差は状態依存を示す。m11 の寛容起動 (#2714) でも同じ型の差 (ok 872 → 874) が出ている。

## 6. silent miscompile のリスク評価 (リスクの一覧。正しさの証明ではない)

| # | リスク | 根拠 (実測) | 影響 |
|---|---|---|---|
| R1 | 補修 (mode 2) で戻した範囲の外に、ゼロ埋めされた状態が残る | mode 2 の補修は InitContext・InitTable・units・unit 先頭 8B のみ。`f_6a7b70` の広域ゼロ埋め (#3060) の全域は未確認 | mode 2 の ok 811 は欠落の上に成り立つ。補修を外した mode 1 は 695 unit が走れない |
| R2 | ok と数えた unit が、実行中に icall-miss (dispatch(0)) で fail-soft に戻っている | mode 2: unit 12 (4 回)・501 (2)・592 (2)・833 (1) | 呼出先が未解決のまま ok に入る。出力が静かに違う可能性 (候補) |
| R3 | 逐次起動の ok が、隔離 survey の ok と一致しない | 77 件 (§5) | 「その unit は動く」の判定は実行順序に依存する |
| R4 | skip 84 件 (mode 2) の途中書込み | oob は途中までの書込みが残る。exit は RunError 経路 (#3060) | skip した unit の副作用が後続に残る。個別の状態は未測 |
| R5 | IPP 判定が使えない | mode 2 でも終了時 0x15F34A0 = 0 (root 有の既知現象 #3060) | ippsZero_8u 登録の有無を寛容起動では確かめられない (判定は測定のみ) |
| R6 | ExitProcess を skip として続行する | 本来の FL では ExitProcess で終了する | 続行の結果は実機の挙動ではない。最初の fatal は unit 245 (#3060 の RunError 経路) |

## 7. CreateFruityInstance (0x1375990) の観測

- lift: root に追加 (`FLE_EXTRA_ROOTS=0x6a7b70,0x1375990`)。増分は関数 29 (root 0x6a7b70 のみの 29,908 → 29,937)。
- 呼出し: 寛容起動の後で `fle_run` を 1 回 (mode 1・mode 2 とも)。結果は `oob` (memory access out of bounds)。`longjmp` 0・`exit` 0・soft 呼出し 0。
- dispatch リング末尾 4 件: `0x1375170` → `0x13751b0` → `0x13751d0` → `0x1375990`。trap は CFI 本体 (または直接呼出し先) で起きた。直接呼出しは dispatch 記録に出ないため、trap の関数は未特定。
- S12〜S22 の到達: 0 (API が呼ばれていない)。`RegisterClassW` / `CreateWindowExW` の自然到達: 0。
- trap 地点の特定は #3077 [WIN-16] の範囲。本 issue では観測までに留める。

## 8. 製品 KPI の前後 (PR 本文の表と同じ値)

| KPI | 前 (#3062 の寛容前) | 後 (本測定 a55cb0d5) |
|---|---|---|
| x64c の逐次起動の unit 進行 | dispatch 209 / 完走 208 (停止 unlifted `0x6a7b70`) | 寛容 mode 1: 試行 942・dispatch 209・ExitProcess (unit 245) / 寛容 mode 2 (補修あり): 試行 942・dispatch 895・ok 811・skipped 84 |
| `CreateFruityInstance` 到達の有無 | 無し | 無し (oob 即時) |
| 最終到達ステップ (S12〜S22) | S12 未達 (推定) | 到達なし (API 呼出し 0 件) |
| `RegisterClassW`/`CreateWindowExW` の自然到達 | 0 | 0 |
| 既定経路の回帰 | 209 / GetMem 1,890 / FreeMem 776 | 209 / 1,890 / 776 (不変) |

起動 KPI (最初のウィンドウ) は未達。窓は描けていない。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CFI (0x1375990) の trap 地点と、CS 0x12bd390 の登録経路 | 最初のウィンドウ未達。S12〜S22 の到達なし | #3077 [WIN-16] (既存・重複起票せず) |
| unit 245 (VA 0x733090) の ExitProcess (RunError 経路) の原因と、`f_6a7b70` の広域ゼロ埋めの範囲 | 寛容起動が 245 で fatal 扱いになる。clobber 695 の原因 | #3060 [FLE-11] (既存) |
| 補修 (mode 2) の妥当性。戻す範囲の外の欠落 (R1) | mode 2 の ok 811 の確度 | #3060 (受入に追加済み) |
| x64c の寛容起動レコードを `tools/startup/boot_metric.json` に追加 | 受入 6 (WIN-2 と同一スキーマ) | #3147 [WIN-17] |

## 10. 再現

```sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FLE_BOOT_RUNS="tol tol2" FLE_EXTRA_ROOTS=0x6a7b70,0x1375990 bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FLE_BOOT_RUNS="default" FLE_EXTRA_ROOTS= bash tools/flelift/boot/fle6_measure.sh
```

結果の JSON: `tools/flelift/boot/results/boot_summary_fle6_tol.json` (mode 1)・`..._tol2.json` (mode 2)・`..._default.json`。`tolerant.units` の各要素は `[i, 種類, VA, GetMem 増分, FreeMem 増分, dispatch(0) 回数]`。
