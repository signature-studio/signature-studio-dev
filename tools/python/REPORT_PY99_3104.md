# PY-99 付録 (#3104): SLOT? 49 件の store 値を CFG 到達 store で閉じる

親: #2874 (PY-99)。前段: #3085 (`REPORT_PY99_3085.md`・先行辺 S_p と A/B 検算)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
測定 commit: `c814475ef` (`analysis/py99_closure.py` と `analysis/py99_closure.md` を追加した最後のコード commit)。
`git diff c814475ef HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行 (本節の commit は REPORT と DOC_MAP のみ)。

### 結論 (受入 1・2 達成。入口のレジスタ葉 3 種を残す)

- 受入 1 (閉じた式): SLOT? 葉 104 種・ACC?⚠合流 葉 22 種 (読み単位) を CFG 到達 store で再帰に閉じた。49 件の書込みすべてで、残る葉は関数入口のレジスタ値 `c_in`・`d_in`・`r8_in` だけ (**閉じた書込み 49/49**)。入口のレジスタ葉も未閉に数えると **0/49**。経路別の式 (VA つき) は `analysis/py99_closure.md` (49 行)。
- 受入 2 (検算): 閉包を算法 A (前向き固定点) と算法 B (後ろ向き BFS) で作って書込みごとに比べると、**mismatch 0 (49 件)**。ネガティブコントロール (辺 `0x104754a → 0x104755d` を B で外す) は **mismatch 17・exit 1**。
- コメント (2026-10-14T22:21) の 2 項目: (1) 線形で IN とした読み **0 件** (取りこぼしは 0)。全 frame 葉を CFG 到達で閉じるため、線形の取りこぼしは閉包の段階で入らない。(2) CFG 構築は、テキストから再構成した辺 5125 と **差 0**・入口から届かない命令 **0**・間接 jmp **0**。ただし同じ規則の再実装であり、独立な逆アセンブラとの照合ではない (限界)。

### 測定条件

- 素材: fl-win64 の `block00031_PE.bin` (`tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin'`・2.8 秒)。`analysis/py53_dispatch.py` → 関数 0x1046a30〜0x104ccca の 4664 命令 → `work/py53/fn.txt`。
- 実行 (`c814475ef`・コミット済み HEAD から再実行): `analysis/py99_closure.py` 既定 0.65 秒 (exit 0)・`--negctl drop-pred` 0.86 秒 (exit 1)。load average (1 分) 0.1。

### 閉包の定義

- 式は `py88_writes.Slicer.def_value` の線形式。ただしフレームの読みは、線形の store 解決 (`SLOT?` / `ACC?⚠合流` / `IN[rbp+X]` / `ACC`) を使わず、読み位置 r を残した葉 `FR[X/幅]@r` にする。
- 葉 (r, X) は、CFG 上で r に届く store 集合 R(r, X) で置き換える。R の各 store s は、その値の式を同じ規則で閉じたもの。|R| ≥ 2 のとき `{s1: E1 | s2: E2}` (経路別の場合分け)。
- 幅: store の幅が読みより大きいときは `and(E, mask)` で下位ビットを取る。store の幅が読みより小さい・byte/word の store が X に混ざるときは `⟪幅⟫` (未閉)。
- 循環は `⟪循環⟫`、長さ 8000 字超は `⟪長さ超過⟫` (いずれも未閉)。入口の値は `⟪IN⟫` (未閉)。

### 件数 (実測・`analysis/py99_closure.py work/py53/fn.txt` の出力)

| 項目 | 件数 |
|---|---|
| 対象の書込み (直接式で SLOT?・#3085 と同じ 49 件) | 49 |
| 閉包が処理した frame 葉 (読み単位・異なり) | SLOT? 104・ACC?⚠合流 22 |
| 閉包が読んだ frame の X | 24 種 |
| 多経路の読み (\|R\| ≥ 2) | 19 |
| 幅が合わない frame 読み (`⟪幅⟫`) | 0 |
| 残る葉が入口のレジスタ値 (`c_in`/`d_in`/`r8_in`) だけの書込み | **49/49** |
| 閉じた書込み (入口のレジスタ葉を未閉に数えた厳格判定) | 0/49 |
| 線形で IN とした読み / そのうち CFG 上で store に届く | 0 / 0 |
| 入口のレジスタ値の読み (線形で定義なし) / CFG 上で同レジスタの定義が届く | 3 / 0 |
| 未確定の葉 (`⚠合流`・`SLOT[`・`ACC`・`CALL[`・`VCALL`・`clob@`・`⟪`) | 0 |

- 入口のレジスタ値 3 件の読みは、式中に `⚠合流` が付かない (= 読みの前に分岐先が無い) ため、線形の遡りが唯一の経路と一致する。CFG 上の検査 (定義・clob の到達) も 0 件。
- `rint(...)` (call 0x40c660 = cvtsd2si) は既存の式の表記どおり閉じた式として数えた (p99 の閉の規則と同じ)。

### 検算 (算法 A・B と negative control)

| 実行 | 対象 | mismatch (閉包の文字列 A と B) | exit |
|---|---|---|---|
| 既定 | 書込み 49 件 | 0 | 0 |
| `--negctl drop-pred` | 書込み 49 件 | 17 | 1 |

- negctl の辺: `0x104754a → 0x104755d` (合流 J = 0x104755d・読み `0x1047b93 [rbp+0x520]`)。外し方は `analysis/py99_merge_sets.py` と同じ (寄与する先行辺を選ぶ)。
- 同じ CFG・同じ読み集合での S_p 検算 (`analysis/py99_merge_sets.py`) は既定 mismatch 0 (exit 0)・negctl mismatch 15 (exit 1) で、#3085 の値と一致する (再現した)。

### CFG 構築の検査

- 辺 5125 を、`Cfg` クラスとは別のテキスト直読み (jcc/jmp/ret/順次の規則) で作り直して比べた。差 0。
- 入口から到達しない命令 0・間接 jmp 0。
- 限界: 同じ規則の再実装であり、独立な逆アセンブラや実行トレースとは照合していない。`call` の後は順次に続くと仮定 (noreturn の呼出しを見ていない)。

### 限界

- 閉じた式の同値性は見ていない (文字列の一致で A と B を比べた)。
- 入口のレジスタ葉 `c_in`・`d_in`・`r8_in` は関数の入力 (関数 0x1046a30 の ecx 分岐の入力と同じ。呼出し側の値は見ていない)。
- レジスタの 32bit 切り詰めは式に出さない (レジスタ族の値として扱う。py88 と同じ規則)。
- ポインタ経由の書込み (callee 内) は見ていない。解析した X 24 種への `lea [rbp+X]` は 0 件。`rbp` を値として渡す命令は 0 件 (`push rbp`・`mov rbp, rsp`・`pop rbp` のみ)。
- byte/word の frame store 29 件は、閉包が読んだ X と重ならない (幅 8 の保守的判定で 0 件)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 入口のレジスタ葉 `c_in`・`d_in`・`r8_in` (3 種) が式に残る | 49 件の式は関数の入力 (ecx・edx・r8d) の式になる。値の確定は呼出し側の解析が要る | #2874 (PY-99 の残り・呼出し側) |
| CFG の順次仮定 (noreturn の呼出しを見ていない)・独立な逆アセンブラとの照合 | 到達集合が過大になる方向の誤りの有無は未確認 | #2874 (PY-99) |
| 2 本の PY-99 script の統合 (`py99_slot_paths.py` と `py99_merge_sets.py`) | #3085 節の未解決 (判断待ち) | `REPORT_PY99_3085.md` の未解決表 (本節では扱わない) |

前段 `REPORT_PY99_3085.md` の未解決表の 4 行 (閉じた書込み・ACC?⚠合流・CFG 到達・CFG 構築) は、本節で解決した。数値は本節だけに書く。

### 再現

    cd tools/python
    python3 analysis/py99_closure.py work/py53/fn.txt                      # 終了コード 0 (mismatch 0)
    python3 analysis/py99_closure.py work/py53/fn.txt --negctl drop-pred   # 終了コード 1 (mismatch 17)
    python3 analysis/py99_closure.py work/py53/fn.txt --md analysis/py99_closure.md  # 表の再生成

`work/` は作業用ディレクトリ (`py53/fn.txt` を置く場所。PY-88 と #3085 と同じ入力)。
