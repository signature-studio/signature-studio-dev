# REPORT_APPENDIX_5168 (PY-4877・patternCount 直接呼出し)

REPORT.md §14 の分割移動先。測定値・経緯はここ。

## 14. #5168 (PY-4877): boot 後に patternCount (0xd64d40) を直接呼ぶ driver

- **結論**: driver は動く (`fle_py_pattern_count` が boot 停止後に 0xd64d40 を `fle_run` で実行する)。boot 後の `patternCount` 呼出しで述語 0x12d8d30 が i=1..999 の順に呼ばれることを観測した (前回の「述語は boot 中に呼ばれない」は boot 中の話で、boot 後の呼出しでは届く)。ただし `patternCount` 内の間接呼出し (call site ret=0xd64d7a) が icall-miss (`dispatch(0)` → 戻り値 0) になり、`patternCount` の戻り値 0 は実行結果として信用できない。受入 1 (E[1..999] の実測) は未達。

| 項目 (測定 commit `8613de75b`) | 結果 |
|---|---|
| 1 回目 (`py4877_pred_e_probe.sh`・外側 110 秒上限) | rc 124 (build 完了後、boot の途中で時間切れ)。次の 580 秒の実行は `head` で打ち切られ rc 141 (SIGPIPE・boot 本体は無関係) |
| 2 回目 (`py4877_pred_e_probe.sh` の既定 run・`work/boot/run_py4877_probe.log`) | `FLEBOOT_PY4877_PRE` 非 0 行 0 → `FLEBOOT_PY4877_CALL {"ret":0,"threw":null}` → `FLEBOOT_PY4877_POST` 非 0 行 0 |
| 述語 0x12d8d30 | `[PY4877-PC]` n=999 (ecx=i が 1..999 の順・run_py4877_probe.log) |
| 間接呼出し | `[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss 揃え, call site ret=0xd64d7a)` |
| boot 本体 | units_run 895・`boot_threw` exit (既存の KPI と同じ・変化なし) |

- **読み**: 呼出し前後とも `E[1..999]` は全 0 で、述語は 999 回呼ばれたが、`patternCount` の戻り値は icall-miss による 0 である。0 は「999 件を数えた」でも「0 件」でもなく、観測不能。E の内容が実起動で崩れるかは、この icall-miss を解消してから判定する。
- 未解決: icall-miss (0xd64d7a の間接呼出し先) の解消 → 親 #5168 の残件。boot 本体の KPI は変えていない。

### 14-2. icall-miss の原因 (測定 commit `48d217792`・`py4877_pred_e_probe.sh` の ICALL 行)

- 0xd64d78 の `call qword ptr [rax]` は `rax = [0x15e4280]` (`.data`) を経由する。`[0x15e4280] = 0x16b8298` (`.bss`) で、PE の静的値どおり。
- 実行時 (呼出し直前・n=1): `[ICALL] n=1 slot=16b8298 [slot]=0`。`[slot]=0` のため、`0x16b8298` は関数ポインタの格納先と推定される。どの API を指すかは未測定。`dispatch(0)` → 戻り値 0 になる。
- 同じ boot で `0x12d8d30` は 999 回呼ばれ (`[PY4877-PC]` n=999)、`0xd64d40` 入口も 1 回発火。boot 本体は units_run 895 (既定 mode 3・`fle6_measure.sh` の `FLE_BOOT_RUNS=default` で再現)。
- 読み: 戻り値 0 は「999 件を数えた」でも「0 件」でもなく、観測不能。スロットが未初期化と推定されるため、呼出しが成功していない可能性がある (未確定)。E の内容は呼出し前後とも全 0 のまま (`FLEBOOT_PY4877_PRE`・`POST` の nonzero_rows = 0)。
- 残件 (仮説・未検証): `0x16b8298` を埋める箇所は GetProcAddress 結果の格納先と推定される。特定し、既定経路で埋まるか確認する。埋めると boot の挙動が変わるため、KPI 影響を測ってから判定する。

### 15. f_c395a0 (束縛関数) の既定経路での到達 (測定 commit `3b081a0f9`)

- **結論**: 既定経路 (FLE_IPP 未指定・mode 3) で、`0x16b8298` を書く `f_c395a0` の入口 (`c395a0`)・格納直前 (`c396c5`)・唯一の直接呼出元 (`c3b3a2`) は 0 件だった。したがって `0x16b8298` が 0 のままなのは、この束縛関数が既定 boot で走らないためと読める。受入 1 (E[1..999] の実測) は未達のまま。
- 測定: `tools/flelift/boot/c395_entry_probe.sh` (lift 生成 C に `dbg_lift.py` で 4 点を挿入し、`build.sh plain` → `fle_boot.mjs --boot-only`)。
- 挿入の確認: `[C395-entry]` は `fle_lifted_s0.c` の `f_c395a0` 冒頭、`[C395-STORE]` は `c396c5` の直前 (`s0.c:258322`)、`[C395-resolver]` は `f_4235f0` 冒頭 (`s7.c:36080`) に入った。probe 機構は動く (resolver は既定経路で 16 件以上発火)。

| 項目 | 結果 (`3b081a0f9`) |
|---|---|
| `[C395-callsite]` / `[C395-entry]` / `[C395-STORE]` | 0 / 0 / 0 件 |
| `[C395-resolver]` (4235f0 入口) | 16 件 (上限 16 で打ち切り・戻り番地 `44b80f` … `653e0d`) |
| boot (probe 付き) | units_run 895 / 942・`boot_threw` = `oob memory access out of bounds` (rc 0・1m41s) |
| boot (probe 無し・同条件の基準) | units_run 895 / 942・`boot_threw` = `exit` (fle6 default と一致) |

- **副作用の注意**: probe 付きだけ `boot_threw` が `oob` になる。units は 895 で同じだが、probe が boot の終わり方を変えている。`0xc395a0` 0 件の読みは、この変化を前提に「既定の挙動で走らない」とは断定しない。probe 無しの run で同じ入口を直接数える手段は今回無い。
- 読み (仮説): `0x16b8298` の書込み元 `f_c395a0` は既定 boot の units 1〜895 の中で呼ばれていない。`patternCount` の icall-miss (`dispatch(0)`) はこれと整合する。
- 未確定: (a) `oob` が probe 挿入に由来するか (挿入無しで同じ unit 895 の終わり方か)。(b) `f_c395a0` を起動する上位経路 (`c3b3a2` の呼出元 `f_c3b340` の呼出元)。次の一手は、probe 無しで `f_c3b340` 入口だけを数えて、上位経路まで辿ること。

#### 実行手順 (再現)

```
FL_WIN64_DIR=<fl-win64 展開先 [WIN64]> SS_EMSDK_ENV=<emsdk_env.sh [EMSDK]> FLE_BOOT_RUNS=default bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先 [WIN64]> SS_EMSDK_ENV=<emsdk_env.sh [EMSDK]> bash tools/flelift/boot/c395_entry_probe.sh
```
