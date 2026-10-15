# M11 REPORT 付録 #134 [M11-N5] (REPORT.md §14・§18 の本文)

親の [REPORT.md](REPORT.md) §14 と §18 の本文を移した (250 行上限のため分割移動。Git 履歴に残す)。

## 14. #134 [M11-N5]: unit 23 の IntToStr 表構築 OOB を解消 (通常起動 22→53 unit), judge を Halt0 早期終了と分離

既知類型: DEFECTS.md D4 (1 段 deref 脱落) 2 件 = 414ad0 `_LStrSetLength` (`[rbx]`) / 43a3f0 IntToStr 書込み (`mov r8,[rbx]`)。D15 の 467c40 間接 call は 4c3baa4 で復元 (#490)。
**起点** `13e8962` (= origin/main `8d883c3` + 本 PR)。4 vCPU, PE=`FL_WIN64_DIR` の block00031_PE.bin, work-m11 展開, capstone+pefile venv, node v22.23.3。

| 構成 | units_run | 停止 | survey ok/trap(oom)/miss/noproc | 所要 s / load |
|---|---|---|---|---|
| main + PE パス修正のみ (n=1) | 22 | unit 23 例外→Halt0 | 864/31(1)/46/1 | 45.2 / 0.33→0.76 |
| + 4c3baa4 + BSTR 割当 (n=1) | 22 | OOB 414ad0←43a3f0←467c40 | 864/31(1)/46/1 | 26.7 |
| `6654322` (+414ad0・43a3f0 転記, n=3) | **53** | unit 57 (0x16fde0) 後に Halt0 | **866/29(2)/46/1** | 26.3–26.9 / 0.39→0.98 |
| `6654322` 再測 (n=1, gen_ir2・boot5 lift 込み) | 53 | 同 | 866/29(2)/46/1 | 84.7 / 0.35→0.97 |
| `de50ffa` (指摘対応 3 点, n=1, 増分 build) | 53 | 同 | 866/29(2)/46/1 (不変) | 32.5 / 0.16→0.69 |
| NC: `6654322` から 2 転記を IR 版へ | 22 | OOB (boot threw) | 未測 | — |

**数え方** (`m11_ov.c` `function_4120c0`): `units_run` は Init が例外も間接 call miss も無く完了した unit 数。miss が 1 回でも出た unit は `units_skipped` に入り `units_run` には入らない (その unit の init は呼ばれている)。Halt0 までに実行を終えた unit は `units_run + units_skipped` = 53 + 3 = **56**、停止したのは 1-based で 57 番目 (VA 0x16fde0)。

**units_skipped = 3 の内訳**: `icall_miss_targets` は `0xfa9390` の 1 種 (`icall_miss=3`)。unit 30・39・40 の Init 値が 0xfa9390 で、呼出し site は `InitUnits` の `ICALL_AT(0x412126)`。0xfa9390 は PE `.text` (RVA 0xba9390) の関数先頭ではなく、直前の `jg rel32` の直後にある中間アドレス (先頭 bytes `00 44 2b f0`)。closure 外のため miss → ret 0 で skip される。関数名は未特定。PE の .data/.rdata に同じ 8B 値のポインタは無く (LE 検索 0 件)、この値の出所は未確認 (未解決)。

**stage 6 の `skip 0`**: judge は `units_skipped` が非 0 なら 6 にしない (`m11_judge.py` の stage 6 条件)。Halt0 が無くても本 HEAD は skip 3 のため未達。

機構: 43a3f0 は `call 414ad0` の後 `mov r8,[rbx]` で `*s` を読むが, IR は deref を落として `r8=&s` とし, 桁を変数自身 (a[0]) に書いた。次反復で文字列本体を文字列ポインタとして読み, `Move` が長さ -2012213261 で OOB。414ad0 も rcx=&s の `[rbx]` 脱落。機械語を 1 命令ずつ突合し C 転記 (桁ペア表 PE 0x13aaa68 の 100 entry は "00".."99" と一致)。BSTR は faee5b6 の m11_win.c 部分のみ採用 (m11_ov.c 部分は main の 417b70/409470 と重複のため不採用)。
指摘対応 (`de50ffa`): 467c40 の translated call 2 箇所 (0x467cc9 / 0x467d5d) は `ICALL_AT` で元 call-site VA を渡す (#494 telemetry の site 計上; 数値は不変)。`SysReAllocStringLen` は NULL src 時に旧 prefix を min(旧長, 新長) 文字保持する (shimx `ole.c` と同じ; この経路の到達は本 e2e で未計測)。`SysFreeString` コメントの未記録の測定値は削除。

judge: stage 6 は Halt0/longjmp 無し・全 942 unit 実行・skip 0・DllMain rc=1 の時のみ。`--require-stage N` で未達を exit 1 (既定は報告のみ exit 0)。N は 1〜6 の整数のみ受け付け、0・7・x・欠落は usage (exit 2)。ネガコン実測 (`de50ffa`): `--require-stage 6` → `reached 4/6`, exit 1 / `--require-stage 4` → exit 0 / 不正値 4 種 → exit 2。合成入力 (`M11_JUDGE_WORK`) 942 完走 → 6/6 exit 0 / Halt0 経由で 942/942 → 5/6 exit 1 (`6654322` で実測)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 57 (0x16fde0) の 0xf960 (GetMem+40fb40) ↔ 0x79b10 反復後の Halt0 (未読) | 53/942 (完了 56) で停止, stage 5/6 未達 | 起票依頼 (PM 判断: 子 issue 新設 or #134 コメント)。#490 は本 PR が範囲 (unit 23 の間接 call 復元・boot5・BSTR) を取り込み済みのため積み増し先として不適 |
| unit 30/39/40 の Init 値 0xfa9390 (.text の関数途中・closure 外・skip 3)。skip は ret 0 のため当該 3 unit の init は未実行 | stage 6 の `skip 0` 未達。出所未確認 | 上と同じ (起票依頼 PM 判断) |
| D4 同型 (`mov r64,[reg]` の 1 段 deref 脱落) の他サイトの全数 | 他 unit の silent 誤動作の恐れ | DEFECTS.md 行案 (PM 判断) |

## 18. #134 [M11-N5]: main `93307cc6a` の停止点 (unit 101 = VA 0x5de960 の 535c11 OOB) と e2e 期待値の更新 (部分達成)

測定 commit: `93307cc6a` (origin/main、コードは変更していない)。`git diff 93307cc6a HEAD -- tools/m11/*.sh tools/m11/*.c tools/m11/*.py tools/m11/*.mjs` = 0 行。変更は `e2e_expect.env` (期待値 2 行) と本節のみ。
素材: `fl-win64` (`extracted/block00031_PE.bin` のみ・sha256 `b2c64da4…`)、`work-m11` (→ `tools/m11/work/`)、toolchain は `/opt` の既存。`work/lift_pe.sha256` を手で書き `m11_gen_ir2.sh` で IR のみ再生成 (`ir_sha256` `36079b29…822a6a`。`--full` は未実施)。

### 実測 (`bash tools/m11/m11_e2e.sh`, 4 vCPU, n=2 (期待値変更前後の run で同一値), 所要 71.2 s / 開始時 load 0.89)
| 項目 | 値 |
|---|---|
| 通常起動 | units_run 98 / skipped 3 (完了 101) / total 942。icall ok 391 miss 3。Halt0 0 |
| 通常起動の停止 | trap "memory access out of bounds" @ `function_535c11` ← `4fad10` ← `4fb910` ← `5de960` (unit index 101, VA 0x5de960) |
| stage | 4/6 (5・6 未達) |
| survey | ok 873 / noproc 1 / miss 46 / trap 22 (oom 0) / clobber 0 |
| 寛容起動 | attempted 942 / ok 875 / skipped 66 (miss 46, halt0 7, oob 13) |

前回 (`750340fc`、#134 コメント): 停止は unit 56 (`function_8c5eb0` unreachable)、survey 871/24。停止が unit 56 → 101 に進んだ原因 (main 側の複数の変更の合成) は未特定。

### 期待値の更新 (`e2e_expect.env`・ファイル内の m3 手順)
| 変数 | 変更前 | 変更後 | 根拠 |
|---|---|---|---|
| `M11_EXPECT_STRICT_DONE` | 56 | 101 | 通常起動の完了数 = units_run + skipped = 98 + 3 |
| `M11_EXPECT_SURVEY_OK_EXACT` | 872 | 873 | survey ok 実測 873 |

上限は変えていない: `M11_EXPECT_PTR_NEW_MAX` 69359 に対し実測 69668 (全件 run) で ptrcheck ゲートが不合格 (e2e は rc=1)。増分 +309 の内訳 (完了 unit 増に伴う正当な書込みか、未 remap の VA 語か) は未分析のため、上限は据え置いた。

### 停止点の切り分け
- `535c11` の `self` は 4fad10 が `535240(%42)` で得た R (`535b30` が `[R+8] = %42` を格納)。`535c11` は `[[R+8]+8]` を読むため、`%42` (4fad10 の table 項目 `[item+8]`) が線形メモリ外の値。
- `535240` の `ptrtoint 1003752` は `[rip+disp]` の値 (PE 上で `0x4f50e8`、linear `0xf50e8`) と一致し、誤りではない。
- `M11_FIX_535BF2=1` (#714 の `535c11`/`535bf2` 転記) でも停止は同じ unit・同じ trap。`535c11` の lift 形ではなく入力 `%42` が原因。
- 125.3 MB (131399680 B = 0x7d50000) の VirtualAlloc は unit 95 (0x5d2680) と unit 101 (0x5de960) の init 経路で発生 (`M11_VA_BIGTRACE=1`、呼出元 `4fb1f0`→`500570`→`534b40`→`410320` 周辺)。寛容起動では unit 101 は ok で、同じ要求を含む。要求元のサイズ算出の正否は未確認。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 101 (`5de960`) の `4fad10` が読む table 項目 `[item+8]` (`%42`) の出所 (上流 unit の書込み) | stage 5/6 未達 (101/942) | #134 (継続。PM 判断で子 issue 化) |
| 125 MB VirtualAlloc の要求元 (unit 95・101) のサイズ算出が誤 lift か | 上記 §1 の「巨大要求は誤 lift の疑い」と同じ | 同上 |
| `M11_EXPECT_PTR_NEW_MAX` 69359 と実測 69668 の差の分析 | e2e rc=1 (ptrcheck) | PM 判断 |
| FL_* 初期化 API 呼出し・skip 3 (0xfa9390) | stage 6 の前提 | #134 (継続) |

KPI (m11 = RetDec 路線の boot 部分起動): 通過 unit 101 (strict)・stage 4/6。FLEngine の最初のウィンドウ: 動かしていない (GUI なし、MessageBox 0 件)。
