# REPORT_APPENDIX_4729 — Slayer_Engine.dll (block22434) の未被覆 (c) 中身あり区間の間接参照の検査 (#4729 / 親 #3546 / 祖先 #2814)

- 測定 commit: `961f4a1a2` (コードを変えた最後の commit。 `gap_indirect.py` を追加)。 `git diff 961f4a1a2 HEAD -- tools/ott tools/plugins/slayer_engine_ia32` の出力は (本 PR 作成時点で) 空。
- 入力: `block22434_PE.bin` (179,512 B・sha256 `84b64c43…de724a9`。 素材 `fl-win64` の `extracted/` だけ展開)。 `lift_text.py` は素材 `toolchain-emsdk` の emcc 6.0.12 で pass 2 まで再現 (被覆 62,320 / 73,002 B = 85.37%・functions 472・未被覆 237 区間 10,682 B。 `REPORT_APPENDIX_3128.md` の値と一致)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 lift 出力 (`tools/ott`・`lift_text.py`) は変えていない。

## 1. 結論

1. 対象は issue の「37 区間」ではなく **34 区間**。 pass 2 の未被覆 237 区間のうち分類 (c) で padding でないもの (34 区間・計 6,083 B)。 内訳: `GAP_CLASSES_2814.md` の 33 区間 (pass 1 の区間) と、pass 2 で新たに現れた `0x1000ef59` (1,164 B)。 pass 1 と pass 2 で区間がずれるため、同じ数にならない (`REPORT_APPENDIX_3128.md` 冒頭の注記と同じ)。
2. 34 区間の全てに、間接参照 (表引き `call`/`jmp`・即値・disp の指す先) も、reloc 値の指す先も **0 件**。 よって「間接 call の先」の証拠は得られなかった。 関数の根拠 (prologue・直接 call の先・間接参照) も、data の根拠 (表・ポインタ) も無い。 **判定は (c) のまま据え置く** (関数とも data とも断定しない)。 区間ごとの根拠 (VA・B・先頭 8 B・線形 decode 命令数・ret 数・間接参照の件数) は [GAP_INDIRECT_4729.md](GAP_INDIRECT_4729.md) の表 (自動生成) に全 34 行を置く。
3. 表の反映方式: `GAP_CLASSES_2814.md` は自動生成のため人手編集しない。 検査結果は別表 `GAP_INDIRECT_4729.md` (自動生成) に置き、区間の VA で `GAP_CLASSES_2814.md` と突き合わせる。 再生成手順は §4。
4. 未解決: 下記 §5 の 2 点 (判定保留の 2 区間 `0x10010bbf`・`0x1000ea92` は親 #3546 の受入 2 で未着手・検出の限界)。

## 2. 検査の内容 (`gap_indirect.py`)

| 記号 | 検査 | 結果 (34 区間) |
|---|---|---|
| T | 間接 `jmp`/`call` (`ff /4`・`ff /2`) の memory 先頭の表 (イメージ内・最大 32 要素) の要素が区間を指す | 0 件 |
| I | 全命令の即値・memory disp のうち、区間内を指すもの (直接 jmp/call/jcc は除く) | 0 件 |
| R | 全 section の reloc (type 3) の値が区間を指す (vtable・関数ポインタ表を含む) | 0 件 |

- 検査の確認 (検出器が機能すること): 入力の reloc は 2,488 件 (type 3 が 2,477)、そのうち値が `.text` を指すものは 794 件。 表引き間接 jmp/call は 22 表を解析。 33 区間の `GAP_CLASSES_2814.md` の表も読めている。 0 件は検出器が壊れたことを示さない。
- 参照の有無が 0 なので、区間の線形 decode (命令数・ret 数) は補助情報として残すのみ (`GAP_INDIRECT_4729.md`)。

## 3. 限界 (0 件を「参照なし」と断定できない理由)

- 表引きは、表の先頭が**イメージ内の絶対 disp** の場合だけ読む。 レジスタの計算で作る表・ベースを別に持つ `call [reg+disp]` (disp が小さい) は見ていない。
- 実行時に作る vtable・関数ポインタ (`.data` に起動時に代入) は reloc に現れない。 PE の reloc は静的に書かれた絶対アドレスだけを持つため、ここは検出できない。 ただし `.data` に静的に入る vtable は reloc で見える (R が 0 件)。
- 即値・disp の検査は `.text` 全体の線形掃引に依存する。 掃引が命令境界を取り違えた箇所の即値は落ちうる (上限ではなく下限)。
- よって「間接 call の先ではない」とは言えない。 言えるのは「静的な絶対参照・reloc の経路では、34 区間のどれにも到達しない」まで。

## 4. 再生成手順

```
export PATH=<emsdk>/upstream/emscripten:$PATH FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
python3 tools/plugins/slayer_engine_ia32/lift_text.py                 # pass 2 の区間 (work/lift_text)
python3 tools/plugins/slayer_engine_ia32/gap_classify.py $FL_WIN64_DIR/extracted/block22434_PE.bin work/lift_text --md > work/final_classes.md
python3 tools/plugins/slayer_engine_ia32/gap_indirect.py $FL_WIN64_DIR/extracted/block22434_PE.bin work/final_classes.md --md > GAP_INDIRECT_4729.md
```

- 依存: capstone==5.0.7・pefile (`uv venv` + `uv pip install`)。 `gap_indirect.py` の 2 番目の引数が分類表 (`GAP_CLASSES_2814.md` 形式・pass 1)、または `gap_classify.py --md` の出力 (pass 2)。 いずれも `| n | 0xVA | B | c | ... |` の行を読む。
- 所要: `gap_indirect.py` 単体で wall 0.21 s・maxrss 59.6 MB (load 0.30 → 0.40・cpu 4)。 `lift_text.py` は wall 16.95 s。

## 6. 関数/data の判定 (受入 1)

- 測定 commit: `94c02ca97` (`gap_func_4729.py` と `GAP_FUNC_4729.md` を追加した commit)。 入力は §4 と同じ block22434_PE.bin (sha256 `84b64c43…`)、区間は GAP_INDIRECT_4729.md の 34 行。 `94c02ca97` で再生成した表が commit 済みの `GAP_FUNC_4729.md` と一致した。
- 判定の根拠 (区間ごと): 表 [GAP_FUNC_4729.md](GAP_FUNC_4729.md) (自動生成)。 P = 先頭の prologue、C = 直接 call/jmp rel32 の先頭 (0 件)、X = 線形 decode の境界一致、E = 末尾が ret/jmp/ud2、Z = 0x00 の割合、N = 不正バイト数。
- 結果: **func 6 / data 0 / hold 28** (計 34)。
  - func 6: 0x1000a690・0x1000ba48・0x1000d70c・0x1000e987・0x1000ef59・0x10012415。 prologue あり・decode 境界一致・末尾が ret。 ただし呼び元 (C) は 0 件なので、**関数の確定ではない**。 prologue の 1〜2 バイトは data にも現れるため、根拠は弱い。
  - data 0: 0x1000b883 は 0x00 が 60% だが、中身が `call rel32` (直接の参照) なので data としない。 Z (0x00 の割合) だけでは data と判定しない。
  - hold 28: prologue も直接 call の先も無い。 末尾が `int3`・`fstp` など関数の末尾として閉じないものや、`cc` (int3 padding) だけの区間を含む。 判定を据え置く。
- 限界 (§3 と同じ): 呼び元が静的な直接 call・間接表・reloc に無いため、func 6 の関数性と hold 28 の data 性は、どちらも確定できない。 この表の出力は「判定の根拠の並べ替え」であり、`GAP_CLASSES` の (c) を書き換える根拠にはしない。
- 反映方式 (受入 2 の続き): `GAP_CLASSES_2814.md` は自動生成のため手で変えない。 判定は GAP_FUNC_4729.md を VA で突き合わせて読む。 再生成は `python3 gap_func_4729.py block22434_PE.bin work/gap34.md --md > GAP_FUNC_4729.md` (`work/gap34.md` は GAP_INDIRECT_4729.md の VA 列から作る。 §4 の手順で `work/final_classes.md` を作ってから `gap_func_4729.py` に渡してもよい)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 判定保留 2 区間 `0x10010bbf` (822 B・reloc 46 本)・`0x1000ea92` (466 B・reloc 8 本) の命令境界の確定 | 親 #3546 の受入 2。 本 issue の範囲外 | #3546 (PLG-G2-28) |
| 間接参照の検出が (レジスタ計算・実行時の表) に届かない限界 | (c) 34 区間の関数性を確定できない。 0 件は下限の証拠 | 本付録 §3 の限界として残す (追加の検出法は子 issue にせず、必要になったら起票) |
| issue の「37 区間」と本付録の 34 区間の差 | 親 #3546 の本文の数 (33 + 判定保留 2 = 35 区間) と一致しない | 本 PR の issue 更新で数字を直す (issue #4729 を縮める) |
