# 付録: icall #1632 (ICALL-36) — 値不一致 9 関数の切り分け

> 親: #1451 (ICALL-28)。付録元: `tools/icall/REPORT_APPENDIX_1451.md` §3・§4。
> 子: lift 欠落の修復 ICALL-41 (起票先は §4)。

## 1. 結論

- 値不一致 9 関数は、native と wasm の両方が正常終了して xmm0 の bit が違う。
- 疑われていた未実装 SIMD stub 5 種 (`__asm_int` `__asm_int3` `__asm_movntps` `__asm_vucomisd` `__asm_vucomiss`) は、**直接 call の到達範囲では 9 関数のどれにも現れない** (§3.2)。間接 call 先は未確認のため、SIMD stub 仮説は直接経路では否定、間接経路は未確認。
- 7 関数 (`1803de190` `180829c20` `180c98240` `180c99430` `181055400` `181056a4c` `181056aa0`) は wasm 側が一律 `0` を返す。`180da4030` は逆向きで、wasm が値を返し native が 0 を返す。`18105d9fc` は整数ポインタ相当の別値 (§3.1)。native で存在する分岐・call が lift 済み IR から落ちているのが症状として見える (§3.3)。`1803de190` は native に `je` 5 本・call 2 本があるのに、IR は 1 ブロック・0 call で、戻り値は未初期化の alloca (`%1`) になる。
- `18105d9fc` は IR 1 ブロック・0 分岐。native は 4 命令のみで call を持たず、戻り値の出どころは同じく未初期化 alloca (`ret i64 %1`)。
- 原因の正式な特定 (どの lift 段で CFG・命令が落ちるか) は未了。DEFECTS.md の D1b・D15・D19 と同型の疑いが強い。修復は子 ICALL-41。

## 2. 測定

測定 commit: `1c3dca8f` (sweep を実行した commit。以後 HEAD までのコード差分は 0。詳細は下の「コード差分」)。

| 項目 | 値 |
|---|---|
| 素材 | `fl-win64`・`plugins-freshair`・`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` を `$HOME/artifacts` から展開 (実在確認済み) |
| plugins-freshair | `fetch.sh` rc 0 (win 17 files / factory .epf 8)。mac は pkg・xar 無しで skip |
| native | `tools/ott/native/build.sh` OK。出力は `tools/ott/work/libottnative.so` (build.sh の `../work` 解決) |
| `fa_route_build.sh` | OK、5.5 s (real)、開始 load 2.05 |
| `fa_sweep.sh 8 60` | 131 関数、69.2 s (`real 1m9.194s`)、開始 load 1.81・終了 1.28 (4 vCPU)。HEAD `1c3dca8f` での再実行: 68.7 s (`real 1m8.738s`)、終了 load 0.85 |
| 内訳 | **bit 一致 41 / native crash・timeout 66 / wasm のみ err 15 / 値の不一致 9** (REPORT_APPENDIX_1451 §3 と一致) |
| 注記 | main の `REPORT_APPENDIX_1606.md` §2.2 は同じ sweep を 40 / 66 / 15 / 10 と記録。本 run の実測は 41 / 9 で、1606 の記録とは 1 関数ずれる。差の 1 関数は未特定 (1606 は関数別の出力を残していない) |

前回 (測定 commit `2626e445`) も同値 (41 / 66 / 15 / 9)。9 件の集合は `0x1803de190` `0x180829c20` `0x180c98240` `0x180c99430` `0x180da4030` `0x181055400` `0x181056a4c` `0x181056aa0` `0x18105d9fc` で、1451 の §3 と一致する。main の `REPORT_APPENDIX_1606.md` は 40 / 66 / 15 / 10 (1 関数差) と記録しているが、本 run の HEAD では再現しなかった。差の 1 関数は未特定で、#1606 側の記録に残る。

コード差分: 測定 commit `1c3dca8f` から HEAD までの `git diff 1c3dca8f HEAD -- tools/icall tools/ott tools/liftlib tools/m11 tools/targets/freshair` は本付録の文言修正のみ (実行コードの差分 0)。`1c3dca8f` は main の merge を含み、その中には `tools/m11/m11_build.sh`・`trap_triage/probe_entry.sh`・`trap_triage/scan_1588_slot.py` の実コード変更がある。sweep はその merge の後に実行したので、測定値はこれらを含む状態のもの。本 PR で変えたのは付録だけ。

## 3. 切り分け

### 3.1 9 関数の戻り値と入力

| 関数 | native xmm0 (入力 1 件目) | wasm | 区分 |
|---|---|---|---|
| `1803de190` | `c000c5300342457c` | `0` | 同型 |
| `180829c20` | `c000c5300342457c` | `0` | 同型 |
| `180c98240` | `c000c5300342457c` | `0` | 同型 |
| `180c99430` | `c000c5300342457c` | `0` | 同型 |
| `180da4030` | `0` | `c000c5300342457c` | 逆向き (native と wasm が逆) |
| `181055400` | `c000c5300342457c` | `0` | 同型 |
| `181056a4c` | `c000c5300342457c` | `0` | 同型 |
| `181056aa0` | `c000c5300342457c` | `0` | 同型 |
| `18105d9fc` | `0000000050400010` | `00000000104af398` | 別値 (整数ポインタ相当) |

`180da4030` は native と wasm の向きが逆。wasm が値を返し native が 0 を返すので、どちらが正かは未確定。値は `work/fa_route/sweep.jsonl` の `first` (入力 0・1 の 2 件) で確認した。sweep は先頭 2 件の値しか残さないため、残り 6 入力の値は未確認。

### 3.2 SIMD stub の到達性 (直接経路での否定・間接経路は未確認)

`work/rt_freshair-core/after.0.restored.ll` (131 関数) で、各関数から直接・推移的に到達できる関数を辿った。辿るのは名前付きの直接 call (`@function_...`) のみで、間接 call (`call i64 %x`) 先は含まない。間接 call 先は未確認。

| 関数 | 到達 関数数 | 未実装 stub |
|---|---|---|
| 9 関数すべて | 1〜3 | 直接 call 範囲には なし |

`fa_route` の `oi.simd.c` では stub 5 種は `m11_simd_unimpl_once` を出す実装 (silent 0 返却) だが、直接 call の到達範囲の 9 関数からは呼ばれない。間接 call 経由で呼ばれる可能性は未確認のため、値不一致の原因を確定はしない。

また `__asm_movsd` は 9 関数の一部が使うが、`oi.simd.c` で実装済み (`set_u64_lo` / `u64` 返却)。

### 3.3 lift 段の分岐・call 欠落

native (`SlateCore.core_64`、`objdump -d`) と IR の構造比較。

| 関数 | native 命令数 | native call | native jcc | IR fn-call | IR br | IR 行数 |
|---|---|---|---|---|---|---|
| `1803de190` | 59 | 2 | 5 | **0** | **0** | 13 |
| `180829c20` | 48 | 2 | 2 | 1 | 2 | 24 |
| `180c98240` | 48 | 2 | 2 | 1 | 2 | 24 |
| `180c99430` | 110 | 4 | 16 | 1 | 7 | 78 |
| `180da4030` | 20 | 1 | 1 | 1 | 1 | 45 |
| `181055400` | 16 | 2 | 0 | 2 | 2 | 75 |
| `181056a4c` | 24 | 1 | 1 | 0 | 0 | 23 |
| `181056aa0` | 37 | 4 | 0 | 0 | 0 | 23 |
| `18105d9fc` | 4 | 0 | 0 | 0 | 0 | 23 |

- `1803de190`: native は `test rbx,rbx; je 0x1803de22d` で分岐し、`call 0x1803ddb30` を含むループを持つ。IR は `movsd` の定数読み 4 回のみで、ループ・分岐・call が無い。ret の値は未初期化の alloca。
- `181056aa0`・`181056a4c`: native に call 4 本・1 本があるのに IR は 0 call。
- `18105d9fc`: native 4 命令・call 0・分岐 0。IR 23 行。定数 `0x182329160` を読み、戻り値は未初期化 alloca。
- `lift` 時の警告 `[NonRecursiveCFGBuilder] there is no node for an edge ... skipping this edge` (`rt_freshair-core/after.0.log`) が多数出ており、CFG 復元で辺が捨てられている。

### 3.4 既知欠陥類型との対応 (`docs/DEFECTS.md`)

- D1b (jcc が IR から消え、戻り値が定数・未初期化で代役) と症状が同型。
- D15 (`call [mem]` が IR に現れない) は一部の call 欠落を説明しうる。
- D19 (件数 0 のループの本体が実行される) とは逆向き。
- 根本原因 (CFG 復元か命令翻訳か) は未特定。`after.0.log` の `skipping this edge` が手がかり。

## 4. 未解決 (子 issue)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8〜9 関数の lift 段の分岐・call 欠落 (CFG 復元で辺・call が捨てられる) の原因特定と修復 | 値不一致 9 関数。`fa_sweep` の 9 件 | ICALL-41 (#1838・子) |
| `180da4030` の native と wasm の向きが逆 (どちらが正か未確定) | 1 関数の判定 | ICALL-41 (#1838) の受入条件に含める |
| `18105d9fc` の wasm 値と native 値の不一致 (整数ポインタ相当) | 1 関数 | ICALL-41 (#1838) の受入条件に含める |
| 元の受入条件「原因を切り分ける」は本付録で部分達成 (直接経路では SIMD stub 仮説は否定、間接経路は未確認。lift 欠落が主因の疑い) | 原因の正式確定 | ICALL-41 (#1838) |
| CRT 初期化 (DllMain・グローバル初期化) の native 再現 | 66 関数が判定不能 | #1874 (ICALL-47・open。親 #1814 は CLOSED) |
| closure 外 callee の wasm err 15 関数 | 15 関数 | #1633 (ICALL-37) |
| 1606 (40/10) と本 run (41/9) の 1 関数差 | 集計の再現性 | 未特定 (本 PR 内で追跡せず、本文に記録のみ) |

## 5. 再現

```
bash tools/icall/fa_route_build.sh
bash tools/ott/native/build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 1803de190 --n 8
```
