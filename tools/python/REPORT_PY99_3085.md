# PY-99 付録 (#3085): SLOT? 49 件の先行辺ごとの store 集合・検算 (`REPORT_PY41_APPENDIX.md` の 250 行上限のため分割移動)

## PY-99 (#3085・親 #2874): SLOT? 49 件の先行辺ごとの store 集合 (実測)

親: #2874 (PY-99)。前段: `REPORT_PY41_APPENDIX.md` の PY-88 (#2788) 節。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
前提: 同名 path `analysis/py99_slot_paths.py` は #2874 の script (PR #3092・main 取り込み済み) が使う。本節の script は同名を避けて `analysis/py99_merge_sets.py` に改名した (main 取り込み時の add/add 競合の解消。両方の内容を残す)。2 本の統合は未決 (未解決表)。
測定 commit: `cbe89029` (negctl の S_p 表示と `--md` を入れたコード commit)。main 取り込み後の `3d25011b` で再測定し、stdout と表が一致した。`git diff cbe89029 3d25011b -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 9 ファイル (+344/−3)。py99 の入力 `py88_writes.py`・`py53_dispatch.py` は 0 行。

### 結論 (受入 2 達成・受入 1 の閉包は子 #3104 に移管・`Closes #3085` (範囲縮小))

- 受入 1 (SLOT? 49 件の書込みについて、合流の先行経路ごとの式を VA つきで記録): **S_p (先行辺ごとの store の VA 集合) と式の記録まで実施**。式の閉包は未達 (子 #3104)。閉じた書込みは **0/49**。読み 77 件 (異なり) の全件 (合流 65・先行辺 136) を `analysis/py99_merge_sets.md` に書き出した。
- 受入 2 (閉じた式の検算 mismatch 0・ネガティブコントロールを数値で): 算法 A (前向き固定点) と算法 B (後ろ向き BFS) の 77 件で mismatch **0**。辺 1 本を外すと mismatch **15**・exit **1**。

### 測定条件

- 素材: `fl-win64` の `block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'`・2.8 秒)。`analysis/py53_dispatch.py` → fn=4664 命令 → `work/py53/fn.txt`。
- 対象: py88 の既定 65 件のうち直接式で SLOT? のもの 49 件。読み = py88 の式の `SLOT[rbp+X]?@j` 葉 (読む命令 r と X の組) の異なり 77 件。
- 算法 B (後ろ向き): r から CFG の逆辺を BFS で遡り、`[rbp+X]` への dword/qword store で止める。線形に遡って最初の合流 J と、J の先行辺 p ごとの S_p を出す。CFG は fall-through・jmp・jcc から作る (間接分岐 0 件)。
- 算法 A (前向き): 同じ X の reaching-definitions 固定点 (gen・kill = 同 X の store)。読み r の IN(r) と B を 1 件ずつ比べる。
- store の式: py88 の `Slicer.def_value` (線形)。式に `⚠合流`・`SLOT[` 等が残るものは未閉。

### 件数 (実測・`python3 analysis/py99_merge_sets.py work/py53/fn.txt` の出力)

| 項目 | 件数 |
|---|---|
| 対象の書込み (直接式で SLOT?) | 49 |
| 異なる SLOT? の読み (書込み単位の和も 77) | 77 |
| うち合流 J を持つ読み / 合流なし | 65 / 12 |
| 先行辺の和 (合流 J の先行辺 p の総数) | 136 |
| 入口 (IN) に届く読み | 0 |
| 閉じた (読み,store) 対 / 未閉 | 17 / 77 |
| 閉じた書込み | 0 / 49 |

- 先行辺 p ごとの S_p: |S_p|=1 の辺 閉 16・未閉 119 / |S_p|=2 の辺 閉 0・未閉 1。
- 書込みごとの読み数 (`# 0x...` 行): 読みが 1 件の書込みが 27 件・読みが 2 件の書込みが 16 件・読みが 3 件の書込みが 6 件 (計 49)。

### S_p の全件表 (`analysis/py99_merge_sets.md`・自動生成)

- 生成: `cd tools/python && python3 analysis/py99_merge_sets.py work/py53/fn.txt --md analysis/py99_merge_sets.md` (先頭行に同じコマンドを書く。DOC_MAP §2)。
- 内容: 合流を持つ 65 件の先行辺 136 行 (読み・X・書込み・J・p・S_p・閉否)、合流なし 12 件の到達 store、store の式 32 件 (閉 3)。閉の S_p 行は 16 件 (|S_p|=1 の閉辺と一致)。

### 検算と negative control (実測)

| 実行 | 対象 | mismatch | 終了コード |
|---|---|---|---|
| `analysis/py99_merge_sets.py work/py53/fn.txt` (A と B) | 77 件 | 0 | 0 |
| 同 `--negctl drop-pred` | 77 件 | 15 | 1 |

- negctl の辺: `0x104754a → 0x104755d` (合流 J = 0x104755d)。読み `0x1047b93 [rbp+0x520]` の S_p = {0x1047543} は、この辺以外に寄与しない store (`mov qword ptr [rbp+0x520], rax`) を選んだ。B の結果は {0x1047556} のみになり、A の {0x1047543, 0x1047556} と 15 件 (すべて X = 0x520) で食い違う。
- `--negctl` の出力は、外した辺の S_p を cut 後の値で出し、その行に「B の到達集合からは除外」と付ける。
- 選び方: 読みを VA 順に見て、S_p が他の先行辺の S_q に無い store を含む最初の p。

### 限界

- 閉じた式は、store の式に `⚠合流`・`SLOT[`・`ACC`・`IN[`・`_in`・`clob@`・`VCALL`・`CALL[`・`<`・`…`・`⚠addr-taken` のいずれも含まないもの。式の同値性は見ていない (文字列の規則)。
- 算法 A と B は同じ CFG を使う。検算が見るのは到達計算だけで、CFG 構築の誤りは両方に効く。
- py88 が線形で IN とした読み (線形に先行 store が無い読み) は CFG 上の到達を見ていない (ループの戻り辺で届く store を取りこぼし得る)。
- 解析した X は 21 種。`lea` で取られたもの 0・X と重なる別オフセットの frame store 0 件・frame の非定数オフセット store 0 件 (実測)。ポインタ経由の書込み (callee 内) は見ていない。
- 算法 B の S_p の式は py88 の線形の式なので、store の値に含まれる他の SLOT? 葉は、その葉の読みの経路を別途解いていない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉じた書込み 0/49: 未閉の (読み,store) 77 対。store 値に残る SLOT? 葉 (入れ子の読み) と ⚠合流 の閉包 | 元の受入 1 (閉じた式) | #3104 (PY-162) |
| ACC?⚠合流 (`[rbp+0x5b8]` の合流読み・30 件) を同じ算法で解く | 元の受入 1 の一部 (ACC 側) | #3104 (PY-162) |
| py88 が線形で IN とした読みの CFG 到達 (ループの戻り辺) | 取りこぼしの有無 | #3104 (PY-162・2 項目をコメントで追記) |
| CFG 構築 (A・B 共通) の検証。mismatch 0 は到達計算の一致のみ | 検算の範囲 | #3104 (PY-162・同上) |
| 2 本の PY-99 script (`analysis/py99_slot_paths.py` = #2874 の経路列挙・`analysis/py99_merge_sets.py` = 本節の先行辺 S_p と A/B 検算) の統合 | 同じ PY-99 を別算法で扱う重複。統合するまで両方の出力を正として扱う | PM agent の判断待ち: 統合するか。本 PR は同名を避けて改名し、両方残した (既定の「後の PR が統合」は未実施) |

### 再現コマンド

    cd tools/python
    python3 analysis/py99_merge_sets.py work/py53/fn.txt                      # 終了コード 0 (mismatch 0)
    python3 analysis/py99_merge_sets.py work/py53/fn.txt --negctl drop-pred   # 終了コード 1 (mismatch 15)
    python3 analysis/py99_merge_sets.py work/py53/fn.txt --md analysis/py99_merge_sets.md  # 表の再生成

`work/` は作業用ディレクトリ (`py53/fn.txt` を置く場所。PY-88 と同じ入力)。
