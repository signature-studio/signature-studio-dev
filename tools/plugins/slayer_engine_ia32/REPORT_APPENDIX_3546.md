# REPORT_APPENDIX_3546 — 未被覆 .text の区間判定と判定保留 1 区間の扱い (PLG-G2-28 #3546)

- 親: `tools/plugins/slayer_engine_ia32/REPORT.md`。 本付録が測定値の正本。
- 前提: #2814 (PR #3547・merge 済み)。 その区間表 `GAP_CLASSES_2814.md` は pass 1 の区間 (239 区間)。
- 素材: `fl-win64` (block22434_PE.bin・SHA-256 `84b64c43…724a9` と一致)。 emcc は本 run の runner に無く、`emcc -c` は未実行 (§4)。
- 測定 commit: `04cf39eb6` (main 取り込み merge・コードを変えた最後の commit)。 以下の数値は全てこの commit で測定した。

## 1. 区間表と被覆 (pass 1 → pass 2)

`lift_text.py` は pass 1 → 分類 → (b) の関数先頭 (`fva` と push 即値の関数先頭) のうち判定保留を除いたものを roots に加えて pass 2 を行う。

| 区間表 | (a) | (b) | (c) | うち padding | 被覆 |
|---|---|---|---|---|---|
| pass 1 (#3547 の表) | 17 区間 2,677 B | 5 区間 2,388 B | 217 区間 6,283 B | 184 区間 | 84.46% (61,654 / 73,002 B) |
| pass 1 (本 PR の分類器) | 15 区間 1,389 B | 8 区間 4,151 B | 216 区間 5,808 B | 184 区間 | 84.46% |
| pass 2 (本 PR・roots +10 本) | 15 区間 1,389 B | 3 区間 1,631 B | 223 区間 7,071 B | 187 区間 | **86.18%** (62,911 / 73,002 B・未被覆 10,091 B・241 区間) |

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/slayer_engine_ia32/lift_text.py --no-emcc` (実測 4.4 s・rc 0・selftest PASS)。 `--no-emcc` は被覆の測定だけに使い、gate は走らない。
- pass 2 の分類表: `cd tools/plugins/slayer_engine_ia32 && python3 gap_classify.py <PE> work/lift_text --md` (`work/` は gitignore)。 `work/lift_text/gap_classes.json` は pass 1 の結果 (239 区間) なので pass 2 の表には使わない。
- 被覆増分: 84.46% (pass 1) → 86.18% (pass 2)。 増分は roots の差 (`0x1000bd6b` `0x1000beeb` `0x1000c077` `0x1000c516` `0x1000ea94` `0x1000eaac` `0x1000eab4` `0x1000eb8c` `0x1000ed9d` `0x10012a10`)。
- pass 2 の表 (分類器を pass 2 の出力に当てた結果) で (b) は 3 区間: `0x1000c529` (552 B)・`0x10012ae0` (257 B)・`0x10010bbf` (822 B・判定保留 §2)。 この 2 区間は pass 1 の (b) 区間 `0x1000c516`〜`0x1000c751` (571 B) と `0x10012a06`〜`0x10012be1` (475 B) の内側にある。 pass 1 で (b) の先頭 `0x1000c516`・`0x10012a10` を roots に入れた後も、その区間の後半 (`0x1000c529`・`0x10012ae0` 以降) が未被覆のまま残る。 `lift_text.py` は roots を pass 1 の分類から 1 回だけ作り、pass 2 の後に再分類しないため、この 2 区間の先頭は roots に入らない (§5)。 残る原因 (lift の関数範囲が区間の後半に届かない理由) は未確認。

## 2. 判定保留 1 区間と (b) 確定 1 区間 (受入条件 2)

reloc 位置の命令境界は `reloc_boundary_3546.py` で確かめる: `python3 tools/plugins/slayer_engine_ia32/reloc_boundary_3546.py <PE> <区間先頭> <区間終端>`。

| 区間 | B | 先頭 | 判定 | 根拠 |
|---|---:|---|---|---|
| `0x1000ea92` | 466 | `cc cc 55 8b ec 53 56 57` | **(b) 関数** (先頭 `0x1000ea94`)。 roots に入れる (pass 2 で被覆) | 区間 `0x1000ea92`〜`0x1000ec64` 内の reloc は HIGHLOW 5 本 (`0x1000eaa0`・`0x1000eae1`・`0x1000eb4a`・`0x1000eb64`・`0x1000eb6d`)。 全て命令の途中 (push・cmp・mov の imm32 フィールド)。 命令境界の外に当たる reloc は無い。 `0x1000ea94` から `push ebp; mov ebp,esp; push ebx/esi/edi` の関数 |
| `0x10010bbf` | 822 | `cc 55 8b ec 57 56 8b 75` | **判定保留** (roots に入れない・`HOLD_B`) | 先頭 `0x10010bc0` は prologue を持つ。 しかし区間 `0x10010bbf`〜`0x10010ef5` 内の reloc 46 本のうち 29 本が命令の途中に当たる。 残りは jump table (`jmp dword ptr [reg*4+base]` の base 例 `0x10010da8`・`0x10010ea0`) の参照。 区間全体を関数とする根拠が足りない (全数未確認) |

- `0x10010bbf` は pass 2 で roots に入れない (`lift_text.py` の `HOLD_B`)。 被覆はこの区間の分だけ低く出る (86.18%)。 jump table を関数として lift すると silent miscompile になり得るため、保留は安全側。
- 保留を外す判断 (reloc 全数の確認・区間内の関数先頭 `0x10010bc0` の確認) は子 #4727 で行う。
- `0x1000eab4` は #4726 の push 即値規則で (b) と分類され、pass 2 の roots に入る (#4726 側の扱い。 本 PR では変えない)。

## 3. (c) 中身あり区間の参照検査 (受入条件 1)

検査: `cd tools/plugins/slayer_engine_ia32 && python3 gap_refs_3546.py <PE> work/lift_text`。 生の 4 バイト値 (全ファイル位置)・`.reloc` の HIGHLOW 値・`.text` 内の命令の即値と絶対変位を、(c) の区間 (padding 除く) と照合する。 対象は pass 2 の (c) 中身あり 36 区間。 結果:

| 結果 | 件数 | 区間 |
|---|---:|---|
| 参照なし (生の値・reloc・即値のいずれも無し) | 35 | 下記 |
| 区間内の分岐のみ | 1 | `0x10009f72` (38 B・先頭への参照なし・分岐の先 `0x10009f8f` `0x10009f96` は区間内) |

参照なし: `0x10007ce2` `0x10009cd9` `0x10009edd` `0x10009fa2` `0x1000a12d` `0x1000a16e` `0x1000a179` `0x1000a2b5` `0x1000a690` `0x1000b57c` `0x1000b5d6` `0x1000b689` `0x1000b6bf` `0x1000b721` `0x1000b883` `0x1000b88d` `0x1000b89b` `0x1000b9ec` `0x1000ba48` `0x1000ba6b` `0x1000ca1e` `0x1000d69a` `0x1000d70c` `0x1000d7f8` `0x1000e987` `0x1000eb3e` `0x1000eb82` `0x1000ec49` `0x1000ec7f` `0x1000ecbd` `0x1000ef59` `0x1000fca7` `0x100107e2` `0x10012415` `0x10012cec`。

- 判定の限界: 「参照なし」は直接の call/jmp・絶対即値・reloc・生 dword が無いことだけを示す。 `call [reg+disp]` のような間接 call で表を引く先は、この検査では検出できない。 この判定は子 #4729。
- 関数の prologue を持たない区間は、関数か断片かが未確定。

## 4. gate (未実施)

- `emcc -c`・`jt_check.py`・`iat_check.py`・`measure.py` C1〜C4 は、本 run の runner に emcc が無く実行していない。 旧版の付録に書いた PASS の値は、この測定 commit では再現していないため採らない。 再実行は子 #4727 で行う。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x10010bbf` 822 B の判定保留 (reloc 46 本中 29 本が命令の途中・jump table の全数確認・区間内の関数先頭 `0x10010bc0` の確認)。 gate の再実行 | 被覆 822 B 分の不足。 gate 未実行 | #4727 ([PLG-G2-56]) |
| pass 2 の (b) 2 区間 `0x1000c529` (552 B・区間 571 B の後半)・`0x10012ae0` (257 B・区間 475 B の後半) の先頭が roots に未登録 (roots は pass 1 の分類から 1 回だけ作るため)。 残る未被覆の内訳は未測定 | 被覆の不足 (未測定 B。 上の 2 区間の合計は 809 B) | #4815 ([PLG-G2-62]) |
| (c) 中身あり 36 区間の間接 call 検査と最終判定 | 関数か data かが未確定 | #4729 ([PLG-G2-57]) |

注: 子 issue の題名の番号 `[PLG-G2-56]`・`[PLG-G2-57]`・`[PLG-G2-62]` は連番。 GitHub の issue 番号は #4727・#4729・#4815。
