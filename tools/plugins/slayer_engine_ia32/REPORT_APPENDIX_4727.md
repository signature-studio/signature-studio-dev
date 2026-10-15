# REPORT_APPENDIX_4727 — 判定保留 `0x10010bbf` の全数確認と (b) 区間の根拠 (PLG-G2-56 #4727)

- 親: `REPORT_APPENDIX_3546.md` §2 (判定保留)・`REPORT.md`。 本付録が測定値の正本。
- 前提: #3546 (PR #4740・merge 済み 2026-10-15)。 素材: `fl-win64` (block22434_PE.bin・SHA-256 `84b64c43…724a9` と一致)、`toolchain-emsdk` (emcc 24.19.0)。
- 測定 commit: 本 PR の HEAD (下の §5 に書く)。 `lift_text.py` は `HOLD_B` の**コメント**だけを変えた (動作は #4740 と同一)。

## 1. 結論

- **判定保留 `0x10010bbf` は保留のまま** (`HOLD_B = {0x10010BC0}` を変えない)。 全数確認の結果、関数先頭 `0x10010bc0` の lift は未完で、case 先の 3 命令先が lift されていない (§3)。 保留を外すと silent miscompile になり得る。
- (b) 区間 `0x1000ea92` の確定 (#3546) は reloc 5 本の位置で裏付けた (§2)。
- gate C1〜C4・jt 23/23・iat 80/80・`emcc -c` (pass 1・pass 2) は全て PASS (§4)。

## 2. `0x1000ea92` (b) の reloc 5 本

`reloc_lifted_4727.py` (lift 出力と照合):

| reloc 位置 | 値 | 判定 |
|---|---|---|
| `0x1000eaa0` | `0x1000eaac` | lift 済み命令の途中 (`push imm32`) |
| `0x1000eae1` | `0x1000eab4` | lift 済み命令の途中 (`push imm32`) |
| `0x1000eb4a` | `0x1000eab4` | **未 lift** (`cmp [ecx+4], imm32` の位置を含む命令が lift 外) |
| `0x1000eb64` | `0x100270b0` | **未 lift** (`mov ebx, imm32`) |
| `0x1000eb6d` | `0x100270b0` | lift 済み命令の途中 (`mov ebx, imm32`) |

- reloc は全て命令の途中 (線形掃引でも 5 本とも途中) で、データ表の参照ではない。 値 `0x1000eaac`・`0x1000eab4` は push 即値として既に roots に入る。
- `0x1000eb4a`・`0x1000eb64` の 2 本は、(b) 関数 `0x1000ea94` の本体 (`0x1000eb8c` 系) の内側。 lift の範囲外の位置だが、reloc の値 (`0x1000eab4`・`0x100270b0`) は (b) 判定の根拠を崩さない (imm32 の参照のみ)。 本付録ではこの 2 本の lift 外を未解決として残す (§5)。

## 3. `0x10010bbf` 822 B の reloc 46 本 (全数)

`reloc_lifted_4727.py` を HEAD で実行 (区間は #3546 の判定どおり)。 **保留を外した実験** (`HOLD_B = set()`・`lift_text.py` を一時変更・測定後に戻した) の lift 出力に当てた結果:

| 分類 | 本数 | 内容 |
|---|---:|---|
| jt-table | 17 | `lift_meta` の jt_ranges (`0x10010d08`・`0x10010d18`・`0x10010ea0` 等の case 表) の中の値 |
| lifted-insn-inside | 10 | `jmp [reg*4+base]` の disp32 (base = 表の先頭) |
| NOT-LIFTED | 19 | 位置が lift されていない (`0x10010c24`〜`0x10010c2c`・`0x10010dac`〜`0x10010e4c` の表) |
| **計** | **46** | 全数 |

- 保留を外した実験の結果: coverage 86.70% (63,290 / 73,002 B)、jt 30/30、iat 80/80、`emcc -c` rc 0。 gate は全て通った。
- ただし NOT-LIFTED 19 本のうち、**値 (case 先)** が lift されていないものがある:
  - `0x10010c0d`: `jmp dword ptr [eax*4 + 0x10010c20]` の表 `0x10010c20`。 case 先 `0x10010c30`・`0x10010c5c`・`0x10010c80` は未 lift (`0x10010c24`・`0x10010c28`・`0x10010c2c` の値)。 `lift_meta.jt_ranges` はこの表を 4 B (`0x10010c20` の 1 entry) しか持たず、残り 2 entry の 8 B は gate の対象外。
  - 同じ表の case 先は `0x10010bc0` の misaligned copy 経路 (`test edi,3`・`0x10010be6`) から到達する。 lift しないと、この経路で `ott_dispatch` が未知の target を受ける。
- よって `0x10010bbf` 区間を関数として保留から外す根拠は、現時点で**足りない**。 関数先頭 `0x10010bc0` の prologue (`55 8b ec`) は関数であることを示すが、その区間の全 case 先の lift は未完。

## 3b. (b) 区間の先頭と prologue (受入条件 2)

区間先頭の生バイト (PE 生データ・`gap_classify.py` の (b) 判定の先頭):

| 先頭 | 先頭バイト | prologue (`55 8b ec`) | 判定 |
|---|---|---|---|
| `0x1000c516` (571 B 区間の先頭) | `83 ec 2c db 3c 24` | 無し (`sub esp,0x2c` で始まる) | (b) のまま。 prologue が無いため関数か断片かは未確定 |
| `0x1000c529` (後半・552 B) | `83 ec 2c db 7c 24 0c` | 無し | 同上。 roots 未登録 (#4815) |
| `0x10012a10` (475 B 区間の先頭) | `55 8b ec 57 56 53 8b 75` | 有り | (b) 関数。 roots に入る (pass 2) |
| `0x10012ae0` (後半・257 B) | `55 8b ec 57 56 53 8b 4d` | 有り | (b) 関数の後半。 roots 未登録 (#4815) |
| `0x1000ea94` (#3546 の (b) 確定) | `55 8b ec 53 56 57 55 6a` | 有り | (b) 関数。 roots に入る |
| `0x10010bc0` (保留・本付録 §3) | `55 8b ec 57 56 8b 75 0c` | 有り | 関数だが case 先が未 lift (§3) |

- 「prologue 無し」の `0x1000c516` は、(b) の分類 (区間の先頭が関数と読める) と矛盾する。 本付録では判定を変えず、未確定として残す (#4815 の範囲)。
- 区間後半の `0x10012ae0`・`0x1000c529` は、前半 (`0x10012a10`・`0x1000c516`) から roots が届かない区間 (lift_text.py は roots を 1 回だけ作るため) で、#4815 で扱う。

## 4. gate (HEAD・`HOLD_B = {0x10010BC0}`)

測定 commit での値 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`PATH` に emcc):

| gate | 結果 |
|---|---|
| `lift_text.py` pass 1 | 被覆 84.46% (61,654 / 73,002 B)・`emcc -c` rc 0・object 1,404,905 B |
| `lift_text.py` pass 2 | 被覆 86.18% (62,911 / 73,002 B)・`emcc -c` rc 0・object 1,502,017 B・selftest PASS |
| `jt_check.py` | 23 本・case 値 合計 245・生データ一致 23・不一致 0 |
| `iat_check.py` | import slot 55・lift の IAT 参照 80 / 80・名前不一致 0 |
| `measure.py` (C1〜C4) | C1 machine 0x14c PASS・C2 VirtualSize 73,002 PASS・C3 undecoded 4 B (0.0055%) PASS・C4 priv 15 ≤ 15 PASS |
| `measure.py` 所要 | elapsed 0.37 s・load avg 1 分 0.27 → 0.27・parallelism 1 |
| `lift_text.py` 所要 | real 約 13 s (`time` 計測) |

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x10010bbf` 区間の case 先 (`0x10010c30`・`0x10010c5c`・`0x10010c80`) の未 lift。 jt_ranges の 4 B 制限 (表 `0x10010c20` の残り 8 B)。 保留の解除 | 被覆 822 B の不足。 保留は継続 | #4727 (本 issue・残作業は親 #3546 の本文にも記載) |
| `0x1000ea92` (b) の reloc `0x1000eb4a`・`0x1000eb64` が lift 外 (`0x1000eb47`・`0x1000eb63` の命令を含む範囲) | (b) 関数 `0x1000ea94` の本体の一部が未 lift | #4727 |
| (c) 中身あり 36 区間の間接 call 検査と最終判定 | 関数か data か未確定 | #4729 ([PLG-G2-57]) |
| pass 2 の (b) 2 区間 `0x1000c529`・`0x10012ae0` の先頭が roots 未登録 | 被覆の不足 (809 B) | #4815 ([PLG-G2-62]) |
