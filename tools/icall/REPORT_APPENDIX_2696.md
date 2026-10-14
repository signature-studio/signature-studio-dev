# 付録: icall #2696 (ICALL-82) — dsm の data 区分に実コードを含む closure 関数の実測

> 親: #2674 (ICALL-79)。受入 1 (`0x180da4030` の修復) と受入 3 (修復前後の sweep 比較) は本 PR では未達で、子 **#2708 (ICALL-83)** に移した。本 PR は受入 2 (実測と定義) だけを完了単位とする。
> 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。関数終端の fall-through 先の実コードが RetDec で data 区分になり IR から脱落する形は、D3 (store 消失)・D1b (jcc 先の dead code 削除) とは別。新規候補の類型は §5。

## 1. 結論

- closure 131 関数 (`work/rt_freshair-core/map.json` の `func_map`) のうち、dsm の data 区分に実コードを含む関数は、定義 A で **8 件**、定義 B で **63 件** (上限見積り。A は B に含まれる)。
- **定義 A (fall-through 系・確定候補) の 8 件**は全て、関数の dsm 区間の直後に実コードがあり、その先頭命令が `mov qword ptr [rsp+d], r64` (フレーム退避 store) である。route の IR (`after.0.restored.ll`) の `!insn.addr` には、8 件とも先頭アドレスが 0 件 (別経路の検算)。
- `0x180da4030` の fa_cmp は 8 入力で match 0 / mismatch 8 (native `0`、wasm 入力) で、#2674 の記述どおり再現。
- 修復は未着手。修復前の fa_sweep (base) は **54 / 66 / 9 / 2** (bit 一致 / native crash・timeout / wasm のみ err / 値の不一致)。

## 2. 定義と測定条件

| 項目 | 内容 |
|---|---|
| 入力 | `work/rt_freshair-core/before.0.drc.dsm` (RetDec 逆アセンブル) と `map.json` の `func_map` (131 キー)。IR 検算は `after.0.restored.ll` の `!insn.addr` |
| 関数区間 | dsm の `; function: NAME at S -- E` 行の `[S, E)`。closure 131 のうち dsm に関数行が無いのは 1 件 (`0x18100beb0`・5 B の断片)。この関数は数えず、対象は **130** |
| 定義 A | 区間 `[S, E)` の直後 (`A == E`) に data 区分 `[E, B)` がある。E 直前の最後の命令が `ret` / `jmp` / `ud2` / `hlt` / `int3` なら対象外 (脱落ではない)。data 区分の先頭から capstone で線形 decode し、**8 命令以上が連続して正常 decode**、先頭 16 B に `00 00` と `cc` が無いもの |
| 定義 B | 区間の先頭 S から次の関数行の開始 N までの data 区分 `[A, B)` のうち、capstone の線形 decode で **8 命令以上の連続 decode で、ret / call / j* を 1 つ以上含む run** があるもの。境界の条件は A より緩い (上限側) |
| 検算 | A の 8 件について、route IR に `!insn.addr` が A の先頭アドレスで付いた命令があるか (`ir_has_start`) |
| スクリプト | `tools/icall/diff/data_code_count.py` (本 PR で追加)。出力 `work/icall_data_code/data_code_count.json` |

## 3. 実測

### 3.1 件数

| 定義 | 件数 (130 対象) | 備考 |
|---|--:|---|
| A (fall-through 系) | **8** | 下表 |
| B (区間系・上限) | 63 | A ⊂ B。B のみ 55 件は個別に未確認 (§6) |
| A ∪ B | 63 | |
| A の先頭アドレスが route IR に無い | **8 / 8** | 検算 (`ir_has_start`) |

### 3.2 定義 A の 8 件

| 関数 | data 区分 | 先頭命令 (data の先頭) | route IR に先頭が無い |
|---|---|---|:-:|
| `0x1803b5500` | `0x1803b550f–0x1803b5b60` | `mov qword ptr [rsp+0x30], rdi` | ✓ |
| `0x1803de190` | `0x1803de1b7–0x1803de310` | `mov qword ptr [rsp+0x40], rsi` | ✓ |
| `0x18040c950` | `0x18040c9c7–0x18043bef0` | `mov qword ptr [rsp+0x38], rsi` | ✓ |
| `0x180829930` | `0x18082993a–0x180829c20` | `mov qword ptr [rsp+0x30], rbx` | ✓ |
| `0x180829c20` | `0x180829c37–0x180848140` | `mov qword ptr [rsp+0x40], rbx` | ✓ |
| `0x180c97f20` | `0x180c97f3c–0x180c98240` | `mov qword ptr [rsp+0x50], rbx` | ✓ |
| `0x180c98240` | `0x180c98256–0x180c99430` | `mov qword ptr [rsp+0x40], rdi` | ✓ |
| `0x180da4030` | `0x180da4081–0x180da41a0` | `mov qword ptr [rsp+0x20], rbp` | ✓ |

- 8 件の先頭命令は全て同じ形 (フレーム退避 store)。`frame_slot_restore.py` (ICALL-77) が扱う store と同じ形だが、本付録では restore の効果は測っていない (§6)。
- `0x180da4030` の data 区分は `0x180da4081` 以降に `movups`・`lock cmpxchg` のループを含む。IR (`after.0.restored.ll` の `function_180da4030`) では `xor eax,eax` (0x180da407f) のブロックが直接 `ret i64 %24` で終わり、0x180da4081 以降が無い。

### 3.3 ネガティブコントロール

| 操作 | A の件数 | B の件数 | 判定 |
|---|--:|--:|---|
| 通常 (`MIN_RUN=8`) | 8 | 63 | — |
| `MIN_RUN=1000` (decode 条件を外せない長さに) | 0 | 0 | 条件が効いている (FAIL させる入力で 0 になる) |

## 4. fa_cmp と fa_sweep (base = `FA_FRAME_SLOT` 未設定)

| コマンド | 結果 | 所要 | load (開始→終了) |
|---|---|--:|---|
| `python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8` | match 0 / mismatch 8 (native `0000000000000000`、wasm `c000c5300342457c` ほか) | 未計時 | 0.44 (17:09:13 の uptime) |
| `bash tools/icall/diff/fa_sweep.sh 8 60` (base) | **bit 一致 54 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 2** (計 131) | 70.1 s (d32e3a32) / 69.5 s (HEAD) | 0.44 → 0.83 (d32e3a32) |

- 同じ base の sweep を、コミット済み HEAD の worktree (`6aa8a94d` + 本 PR の script) で再実行し、`cmp` で `sweep.jsonl` が完全一致 (SAME) することを確認した。
- ICALL-78 付録 (`REPORT_APPENDIX_2508.md` §3.4) の base 値 53 / 66 / 9 / 3 とは 1 件異なる (値の不一致 3 → 2)。差の 1 件は特定していない。ICALL-78 で報告した `0x1803dee20` の揺れ (#2302 で追跡) と同種の可能性がある (未確認)。
- 受入 3 (修復前後で他の判定が変わらない) は修復を入れていないため測れない。子 #2708 で行う。

## 5. 新規類型の候補 (DEFECTS.md 形式・PM 判断)

| 項目 | 内容 |
|---|---|
| 症状 | 関数の dsm 区間の直後 (fall-through 先) に実コードがあるのに RetDec が data 区分にし、IR に載らない。route の wasm 出力は native と異なる (`0x180da4030`: native xmm0 = 0、wasm = 入力) |
| 根本原因 | 未確定。RetDec が関数の終端を fall-through 先の前で切っている。`xor eax,eax` 直後の 0x180da407f で切れる例は確認したが、他 7 件の終端命令の形は未分類 |
| 観測 | 定義 A で 8 件 / 130 関数。先頭命令は全て `mov qword ptr [rsp+d], r64`。IR の `!insn.addr` に先頭が無い 8 / 8 |
| 検出信号 | dsm で関数行の `E` と data 行の `A == E` が一致し、data 先頭から 8 命令以上 decode でき、`00 00`・`cc` を含まない |
| 修復 | 未実装 (子 #2708 の候補 1〜3)。修復の是非は受入 1 と 3 で判定する |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1: `0x180da4030` の 0x180da4081–0x180da4176 を IR に載せる修復 | silent miscompile (fa_cmp 8/8 mismatch) | 子 #2708 (ICALL-83) |
| 受入 3: 修復前後の sweep 比較 (base 54/66/9/2 を基準) | 修復の影響範囲が未確定 | 子 #2708 (ICALL-83) |
| A 型 8 件のうち `0x180da4030` 以外 7 件の判定 (修復対象か対象外か) | 7 件の wasm 出力は未検証 (fa_cmp は未実施) | 子 #2708 (ICALL-83) |
| B 型のみ 55 件の個別確認 (実コードか jump table・定数か) | 定義 B は上限見積りで、件数の正確さは未確認 | 本 PR の未解決表 (PM 判断。個別の追跡は子を増やさない) |
| A 型の先頭 store と ICALL-77 の `frame_slot_restore.py` の関係 (8 件の先頭が同じ形) | restore pass が A 型に効くかは未測定 | 本 PR の未解決表 (事実の記録。子 #2708 の検証で扱う) |
| 既存 sweep の base 値の 1 件差 (53/66/9/3 → 54/66/9/2) | 比較の基準が揺れる | #2302 (既存の揺れ追跡。本 PR は 1 件差を記録のみ) |

## 7. 測定 commit と差分

- 測定 commit: `6aa8a94d` (origin/main)。route・fa_cmp・fa_sweep の初回測定は `d32e3a32` (main) で行い、`6aa8a94d` の worktree で route を再 build して sweep を再実行した (§4 の cmp が SAME)。
- `git diff d32e3a32 6aa8a94d -- tools/icall tools/ott tools/m2 tools/m5 tools/m11 tools/targets/freshair tools/liftlib --stat` の出力は 2 ファイル (`tools/icall/diff/fa_va_sha.py` 新規 40 行・`tools/icall/REPORT_APPENDIX_2675.md` 61 行)。`fa_va_sha.py` は route からも sweep からも参照されない (`grep -rn fa_va_sha tools --include=*.sh --include=*.py` が 0 件)。
- 本 PR のコード commit: `0ab44c27` (測定用 `tools/icall/diff/data_code_count.py` の追加のみ。route の入力ではない)。`git diff 6aa8a94d HEAD -- tools/icall/fa_route_build.sh tools/icall/ir_*.py tools/icall/frame_slot_restore.py tools/icall/vex_gen.py tools/icall/rt tools/icall/diff/fa_cmp.py tools/icall/diff/fa_sweep.sh tools/m2 tools/m5 tools/m11 tools/ott tools/targets/freshair tools/liftlib --stat` の出力は**空** (route・sweep の経路は差分 0)。
- 本 PR の追加: 測定用スクリプト、本付録、`tools/icall/REPORT.md` §15 の 1 行 (行数は 250 のまま)、`docs/DOC_MAP.md` の登録行。

## 8. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .          # tools/icall/work/ (展開 18 s)
bash tools/ott/native/build.sh                                    # fa_cmp に必要 (1.6 s)
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"   # plugins-freshair が無いときの代替 (REPORT_APPENDIX_2508 §5)
bash tools/icall/fa_route_build.sh                                # base route (5 s)
python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8               # 期待: match 0 / mismatch 8 (修復前)
bash tools/icall/diff/fa_sweep.sh 8 60                           # 期待 (base): 最終行の集計 54 / 66 / 9 / 2 (実測 70.1 s)
python3 tools/icall/diff/data_code_count.py                      # 期待: closure_funcs 131, A 8, B 63, A_start_absent 8
```
