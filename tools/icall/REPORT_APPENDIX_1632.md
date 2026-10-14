# 付録: icall #1632 (ICALL-36) — 値不一致 9 関数の切り分け

> 親: #1451 (ICALL-28)。付録元: `tools/icall/REPORT_APPENDIX_1451.md` §3・§4。
> 子: lift 欠落の修復 ICALL-41 (起票先は §4)。

## 1. 結論

- 値不一致 9 関数は、native と wasm の両方が正常終了して xmm0 の bit が違う。
- 疑われていた未実装 SIMD stub 5 種 (`__asm_int` `__asm_int3` `__asm_movntps` `__asm_vucomisd` `__asm_vucomiss`) は **9 関数のどれにも到達しない**。直接の本体にも、推移的な callee にも現れない (§3.2)。stub 仮説は否定した。
- 8 関数は wasm 側が一律 `0` を返す。native で存在する分岐・call が lift 済み IR から落ちているのが症状として見える (§3.3)。`1803de190` は native に `je` 5 本・call 2 本があるのに、IR は 1 ブロック・0 call で、戻り値は未初期化の alloca (`%1`) になる。
- 残り 1 関数 `18105d9fc` も IR 1 ブロック・0 分岐。native は 4 命令のみで call を持たず、戻り値の出どころは同じく未初期化 alloca (`ret i64 %1`)。
- 原因の正式な特定 (どの lift 段で CFG・命令が落ちるか) は未了。DEFECTS.md の D1b・D15・D19 と同型の疑いが強い。修復は子 ICALL-41。

## 2. 測定

測定 commit: `ff78a960` (main `000c6143` を取り込んだ `1632-icall-xmm0-mismatch` の HEAD。コード変更なし)。

| 項目 | 値 |
|---|---|
| 素材 | `fl-win64`・`plugins-freshair`・`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` を `$HOME/artifacts` から展開 (実在確認済み) |
| plugins-freshair | `fetch.sh` rc 0 (win 17 files / factory .epf 8)。mac は pkg・xar 無しで skip |
| `fa_route_build.sh` | OK、7.4 s (real)、開始 load 1.18 |
| `fa_sweep.sh 8 60` | 131 関数、71 s (07:02:31 → 07:03:42)、開始 load 1.15・終了 1.04 (4 vCPU) |
| 内訳 | **bit 一致 41 / native crash・timeout 66 / wasm のみ err 15 / 値の不一致 9** (§3 と一致) |

前回 (測定 commit `2626e445`) も同値 (41 / 66 / 15 / 9)。9 件の集合は `0x1803de190` `0x180829c20` `0x180c98240` `0x180c99430` `0x180da4030` `0x181055400` `0x181056a4c` `0x181056aa0` `0x18105d9fc` で、1451 の §3 と一致する。main の `REPORT_APPENDIX_1606.md` は 40 / 66 / 15 / 10 (1 関数差) と記録しているが、本 run の HEAD では再現しなかった。差の 1 関数は未特定で、#1606 側の記録に残る。

コード差分: `git diff 2626e445 ff78a960 -- tools/icall` は `REPORT_APPENDIX_1606.md` の追加のみ (+92 行、コード無し)。本 PR で変えたのは付録だけなので、測定 commit からのコード差分は 0。

## 3. 切り分け

### 3.1 9 関数の戻り値と入力

| 関数 | native xmm0 (入力 1 件目) | wasm | 区分 |
|---|---|---|---|
| `1803de190` | `c000c5300342457c` | `0` | 8 関数 同型 |
| `180829c20` | 同上 | `0` | 同型 |
| `180c98240` | 同上 | `0` | 同型 |
| `180c99430` | 同上 | `0` | 同型 |
| `180da4030` | 0 (wasm 側に値) | `c000c5300342457c` | 同型 (native と wasm が逆) |
| `181055400` | 同上 | `0` | 同型 |
| `181056a4c` | 同上 | `0` | 同型 |
| `181056aa0` | 同上 | `0` | 同型 |
| `18105d9fc` | `0000000050400010` | `00000000104af398` | 別値 (整数ポインタ相当) |

`180da4030` は native と wasm の向きが逆。wasm が値を返し native が 0 を返すので、どちらが正かは未確定。

### 3.2 SIMD stub の到達性 (仮説の否定)

`work/rt_freshair-core/after.0.restored.ll` (131 関数) で、各関数から直接・推移的に到達できる関数を辿った。辿るのは名前付きの直接 call (`@function_...`) のみで、間接 call (`call i64 %x`) 先は含まない (その分は未確認)。

| 関数 | 到達 関数数 | 未実装 stub |
|---|---|---|
| 9 関数すべて | 1〜3 | なし |

`fa_route` の `oi.simd.c` では stub 5 種は `m11_simd_unimpl_once` を出す実装 (silent 0 返却) だが、9 関数のどれからも呼ばれない。値不一致の原因ではない。

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
| 元の受入条件「原因を切り分ける」は本付録で部分達成 (SIMD stub 仮説は否定、lift 欠落が主因の疑い) | 原因の正式確定 | ICALL-41 (#1838) |
| CRT 初期化の native 再現 | 66 関数が判定不能 | #1606 (既存) |
| closure 外 callee の wasm err 15 関数 | 15 関数 | #1633 (既存) |

## 5. 再現

```
bash tools/icall/fa_route_build.sh
bash tools/ott/native/build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 1803de190 --n 8
```
