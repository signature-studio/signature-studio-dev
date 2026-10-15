# REPORT_APPENDIX_3546 — 未被覆 .text の区間判定と判定保留 2 区間の扱い (PLG-G2-28 #3546)

- 親: `tools/plugins/slayer_engine_ia32/REPORT.md`。 本付録が測定値の正本。
- 前提: #2814 (PR #3547・merge 済み)。 その区間表 `GAP_CLASSES_2814.md` は pass 1 の区間 (239 区間)。
- 素材: `fl-win64` (block22434_PE.bin・SHA-256 `84b64c43…724a9`)・`toolchain-emsdk` (emcc 6.0.12)。

## 1. 区間表と被覆 (pass 1 → pass 2)

`lift_text.py` は pass 1 → 分類 → (b) の関数先頭 (`fva`) を roots に加えて pass 2。 #3547 の表は pass 1 の区間。

| 区間表 | (a) | (b) | (c) | うち padding | 被覆 |
|---|---|---|---|---|---|
| pass 1 (#3547 の表と一致) | 17 区間 2,677 B | 5 区間 2,388 B | 217 区間 6,283 B | 184 区間 | 84.46% (61,654 / 73,002 B) |
| pass 1 (本 PR の分類器) | 15 区間 1,389 B | 8 区間 4,151 B | 216 区間 5,808 B | 184 区間 | 84.46% |
| pass 2 (本 PR・roots 8 本) | 20 区間 2,246 B | 2 区間 809 B | 231 区間 7,008 B (中身あり 37) | 194 区間 | **86.22%** (62,939 / 73,002 B・未被覆 10,063 B・253 区間) |

- 分類器の変更 (本 PR) で pass 1 の (a)・(b) の内訳が #3547 の表と変わる。 これは (b) の判定を prologue 優先にした結果。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/slayer_engine_ia32/lift_text.py` (16.4 s・load 1 分 0.28)。
- pass 2 の被覆増分: 85.37% (#3547・pass 2) → 86.22% (本 PR)。 増分の内訳は roots の差 (`0x1000ea94`・`0x10010bc0`・`0x10012a10` の関数先頭) による。
- gate (本 PR の HEAD・pass 2 の出力): `emcc -c` rc 0 (object 1,501,220 B)・`jt_check.py` OK (生データ一致 30 本)・`iat_check.py` OK (80 件)・`measure.py` C1〜C4 PASS (4/4)。 ネガコン: `jt_check.py neg` FAIL (期待どおり)・`iat_check.py neg` FAIL (期待どおり)。

## 2. 判定保留 2 区間 (受入条件 2)

| 区間 | B | 先頭 | 判定 | 根拠 |
|---|---:|---|---|---|
| `0x1000ea92` | 466 | `cc cc 55 8b ec 53 56 57` | **(b) 関数** (先頭 `0x1000ea94`) | 先頭 2 B は int3。 `0x1000ea94` から `push ebp; mov ebp,esp; push ebx/esi/edi` の関数。 `fs:[0]` を 4 箇所 (`0x1000eae5` push・`0x1000eaec` mov・`0x1000eb30` pop・`0x1000eb40` mov ecx) で使う SEH 型。 区間内を指す reloc のうち 5 本 (`0x1000eaa0`・`0x1000eae1`・`0x1000eb4a`・`0x1000eb64`・`0x1000eb6d`) は、逆アセンブルで命令の即値 (`push 0x1000eaac`・`push 0x1000eab4`・`cmp` の即値・`mov ebx, 0x100270b0`) に当たることを確認した。 残りの reloc は全数未確認。 ポインタ表ではない |
| `0x10010bbf` | 822 | `cc 55 8b ec 57 56 8b 75` | **(b) 関数** (先頭 `0x10010bc0`) | 先頭 1 B は int3。 `0x10010bc0` から `push ebp; mov ebp,esp; push edi/esi` の関数 (逆アセンブルで確認)。 reloc 46 本の命令への対応は全数未確認 (線形掃引が区間内で途中停止し、機械的に取れなかった)。 判定は prologue と逆アセンブルの連続性で支える |

- 判定の根拠は、区間内の reloc 位置を線形掃引の命令に当てた結果 (`work/reloc_insn_3546.py`)。
- 分類器の変更: prologue 判定を reloc 判定 (a) より前に置き、先頭 pad を飛ばした位置 `fva` で判定する (`gap_classify.py`)。 `lift_text.py` の roots は `fva` を使う。 `--json` の経路は `fva` を持たないため、従来どおり `va` で動く。
- 2 区間とも pass 2 で被覆に入った (roots `0x1000ea94`・`0x10010bc0`)。 全数の reloc 対応は子 #4727 で確かめる。

### 残る誤判定 (未修正)

- `0x1000eab4` (432 B・`mov ecx,[esp+4]` で始まる関数・`ret` で終わる) が (a) (reloc 7 本) のまま。 prologue が無いため順序変更では直らない。 子 #4726。

## 3. (c) 中身あり区間の参照検査 (受入条件 1)

検査: 全セクション (`.text` `.rdata` `.data` `.rsrc` `.reloc`) の 4 バイト値・reloc 値・`.text` 内の全命令の即値と絶対変位を照合 (`work/gap_refs_3546.py`・出力 `work/gap_refs_final.out`)。 対象は pass 2 の (c) 中身あり 37 区間。

| 結果 | 件数 | 区間 |
|---|---:|---|
| 参照なし (raw dword・reloc・即値のいずれも無し) | 36 | 下記 |
| 区間内の分岐のみ | 1 | `0x10009f72` (38 B・先頭への参照なし・`jmp` の即値が区間内) |

参照なし: `0x10007ce2` `0x10009cd9` `0x10009edd` `0x10009fa2` `0x1000a12d` `0x1000a16e` `0x1000a179` `0x1000a2b5` `0x1000a690` `0x1000b57c` `0x1000b5d6` `0x1000b689` `0x1000b6bf` `0x1000b721` `0x1000b883` `0x1000b88d` `0x1000b89b` `0x1000b9ec` `0x1000ba48` `0x1000ba6b` `0x1000ca1e` `0x1000d69a` `0x1000d70c` `0x1000d7f8` `0x1000e987` `0x1000ec7f` `0x1000ecbd` `0x1000ef59` `0x1000fca7` `0x100107e2` `0x10010d3d` `0x10010d7e` `0x10010d89` `0x10010ec5` `0x10012415` `0x10012cec`。

- 判定の限界: 「参照なし」は直接の call/jmp・絶対即値・reloc・生 dword が無いことだけを示す。 `call [reg+disp]` のような間接 call で表を引く先は検出できない。 この判定は子 #4729。
- 関数の prologue を持たない区間 (`0x1000a690` `0x1000ba48` `0x1000d7f8` など) は、関数か断片かが未確定。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1000eab4` 432 B の誤判定 (prologue が無い関数が (a) のまま) | 被覆の不足 432 B (未実測) | #4726 ([PLG-G2-55]) |
| 判定保留 2 区間の reloc の全数対応・pass 2 の (b) 区間の根拠 | 判定の根拠が一部のみ | #4727 ([PLG-G2-56]) |
| (c) 中身あり 37 区間の間接 call 検査と最終判定 | 関数か data かが未確定 | #4729 ([PLG-G2-57]) |

注: 子 issue の題名の番号 `[PLG-G2-55]`〜`[PLG-G2-57]` は本 PR の時点の連番。 GitHub の issue 番号は #4726・#4727・#4729。
