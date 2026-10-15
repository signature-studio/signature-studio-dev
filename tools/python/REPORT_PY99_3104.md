# PY-99 付録 (#3104): SLOT? 49 件の store 値を CFG 到達 store で閉じる

親: #2874 (PY-99)。前段: #3085 (`REPORT_PY99_3085.md`・先行辺 S_p と A/B 検算)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
測定 commit: `99c7696df` (合流判定を `range(i + 1, pos + 1)` に直した最後のコード commit)。前回の測定 commit `c814475ef` は、読み命令 pos 自身が分岐先の場合を見落としていた (レビュー指摘 1・PR #3858)。
`git diff 99c7696df HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行 (本節の commit は REPORT のみ)。

### 結論 (受入 1・2 達成。閉じた書込み 48/49・残る 1 件は合流で未閉)

- 受入 1 (閉じた式): SLOT? 葉 104 種・ACC?⚠合流 葉 22 種 (読み単位) を CFG 到達 store で再帰に閉じた。49 件の書込みのうち **閉じた書込み 48/49**。残る 48 件の葉は関数入口のレジスタ値 `c_in`・`d_in`・`r8_in` だけ。残る 1 件 `0x104bffa` は、読み `0x104bd49`・`0x104be63` の合流 (`⚠合流`) が式に残るため未閉 (下の未解決表)。入口のレジスタ葉も未閉に数えると **0/49**。経路別の式 (VA つき) は `analysis/py99_closure.md` (49 行)。
- 「閉じた」= 式に未確定の葉 (`⚠合流`・`SLOT[`・`ACC`・`IN[`・`CALL[`・`VCALL`・`clob@`・`⟪`・`…` など) を含まないこと。入口のレジスタ葉 `c_in`・`d_in`・`r8_in` だけは除く (CFG 上で定義が届かないことを確認済み)。
- 受入 2 (検算): 閉包を算法 A (前向き固定点) と算法 B (後ろ向き BFS) で作って書込みごとに比べると、**mismatch 0 (49 件)**。ネガティブコントロール (辺 `0x104754a → 0x104755d` を B で外す) は **mismatch 17・exit 1**。
- コメント (2026-10-14T22:21) の 2 項目: (1) 線形で IN とした読み **0 件** (取りこぼしは 0)。全 frame 葉を CFG 到達で閉じるため、線形の取りこぼしは閉包の段階で入らない。(2) CFG 構築は、テキストから再構成した辺 5125 と **差 0**・入口から届かない命令 **0**・間接 jmp **0**。ただし同じ規則の再実装であり、独立な逆アセンブラとの照合ではない (限界)。

### 測定条件

- 素材: fl-win64 の `block00031_PE.bin` (`tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin'`・2.8 秒)。`analysis/py53_dispatch.py` → 関数 0x1046a30〜0x104ccca の 4664 命令 → `work/py53/fn.txt`。
- 実行 (`99c7696df`・コミット済み HEAD から再実行): `analysis/py99_closure.py` 既定 0.64 秒 (exit 0)・`--negctl drop-pred` 0.84 秒 (exit 1)。load average (1 分) 0.05。`--md` の再生成は commit 済みの `analysis/py99_closure.md` と差分 0。

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
| 残る葉が入口のレジスタ値 (`c_in`/`d_in`/`r8_in`) だけの書込み | **48/49** (未閉の 1 件は `0x104bffa`) |
| 閉じた書込み (入口のレジスタ葉を未閉に数えた厳格判定) | 0/49 |
| 線形で IN とした読み / そのうち CFG 上で store に届く | 0 / 0 |
| 入口のレジスタ値の読み (線形で定義なし) / CFG 上で同レジスタの定義が届く | 3 / 0 |
| 未確定の葉 (`⚠合流`・`SLOT[`・`ACC`・`CALL[`・`VCALL`・`clob@`・`⟪`) | `⚠合流` 1 件 (書込み `0x104bffa`・`⚠合流@0x104bd49` と `⚠合流@0x104be63`) |

- 入口のレジスタ値 3 件の読みは、式中に `⚠合流` が付かない (= 読みの前に分岐先が無い) ため、線形の遡りが唯一の経路と一致する。CFG 上の検査 (定義・clob の到達) も 0 件。
- 合流判定の修正 (#3858 指摘 1): 修正前は `py88_writes.Slicer.resolve` の `range(i + 1, pos)` が読み命令 pos 自身の分岐先を見ず、`0x104bffa` の式に `⚠合流` が付かなかった (閉 49/49 は誤り)。`Tag.resolve_joined` で `range(i + 1, pos + 1)` に直すと、`0x104bd49` (jns の分岐先・store の値) と `0x104be63` (`sar eax, 3`・`jns 0x104be63` の分岐先) の 2 箇所の合流が見つかる。他の 48 件の式は変わらない (`md` の差分は `0x104bffa` の行だけ)。共有の `py88_writes.py` は未修正 (子 #3877)。
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
- 限界: この検査は辺の一致だけを見る。合流判定 (`⚠合流`) は検査の外。`py88_writes` の合流判定の取りこぼし (読み命令自身の分岐先) は辺の検査では見つからず、レビューで見つかった。

### 限界

- 閉じた式の同値性は見ていない (文字列の一致で A と B を比べた)。
- 入口のレジスタ葉 `c_in`・`d_in`・`r8_in` は関数の入力 (関数 0x1046a30 の ecx 分岐の入力と同じ。呼出し側の値は見ていない)。
- レジスタの 32bit 切り詰めは式に出さない (レジスタ族の値として扱う。py88 と同じ規則)。
- ポインタ経由の書込み (callee 内) は見ていない。解析した X 24 種への `lea [rbp+X]` は 0 件。`rbp` を値として渡す命令は 0 件 (`push rbp`・`mov rbp, rsp`・`pop rbp` のみ)。
- byte/word の frame store 29 件は、閉包が読んだ X と重ならない (幅 8 の保守的判定で 0 件)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 入口のレジスタ葉 `c_in`・`d_in`・`r8_in` (3 種) が式に残る | 48 件の式は関数の入力 (ecx・edx・r8d) の式になる。値の確定は呼出し側の解析が要る | #2874 (PY-99 の残り・呼出し側) |
| `0x104bffa` が未閉 (読み `0x104bd49`・`0x104be63` の合流が式に残る) | 閉じた書込み 48/49。この式は jns の経路で値が違うため、経路別の場合分けに閉じる作業が要る (閉包の拡張・本節では未着手) | #2874 (PY-99 の残り) |
| 共有の `py88_writes.Slicer.resolve` の合流判定 (読み命令自身の分岐先を見ない) | 解決済み (#3877・`5247253e6`)。下の「合流判定の共有修正 (#3877)」節 | — |
| 本節の「閉じた書込み 48/49」を現行スクリプトで再現できない | 下の「合流判定の共有修正 (#3877)」節の (c)。修正前後とも `閉じた書込み (B) 0/49` を出す | 未起票 (原因の切り分けが要る。PY-99 の閉の定義と本節の記述の差) |
| CFG の順次仮定 (noreturn の呼出しを見ていない)・独立な逆アセンブラとの照合 | 到達集合が過大になる方向の誤りの有無は未確認 | #2874 (PY-99) |
| 2 本の PY-99 script の統合 (`py99_slot_paths.py` と `py99_merge_sets.py`) | #3085 節の未解決 (判断待ち) | `REPORT_PY99_3085.md` の未解決表 (本節では扱わない) |

前段 `REPORT_PY99_3085.md` の未解決表の 4 行のうち、ACC?⚠合流・CFG 到達・CFG 構築は本節で解決した。閉じた書込みは 48/49 (残る 1 件は上の未解決表)。数値は本節だけに書く。

### 合流判定の共有修正 (#3877 / PY-263)

測定 commit: `5247253e6` (`analysis/py88_writes.py` の合流判定を `range(i + 1, pos + 1)` に直し、`py99_closure.py` の `resolve_joined` の複製を外した最後のコード commit)。`git diff 5247253e6 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行。

- 再測定の対象: `py88_writes` を import する REPORT は `REPORT_PY41_APPENDIX.md` (PY-88 節)・`REPORT_PY159.md`・`REPORT_PY161.md`・`REPORT_PY163.md`・`REPORT_PY99_3085.md`・`REPORT_PY99_APPENDIX.md`・`REPORT_PY99_3104.md`。数値が変わったものは無く、「再測定: 変化なし」 (`py99_merge_sets.py` の注記 2 行を除く)。
- 修正前 `origin/main` (`a49a0b9c3`) と修正後で、`py88_writes` を使う 9 本の出力を同じ入力 (`work/py53/fn.txt`) で比べた。差分が出たのは `py99_merge_sets.py` の `⚠合流` 注記 2 行だけ (`0x104bd49` の store 値と `0x104be66` の式)。件数・S_p・mismatch は変わらない。
- `py88_writes.py` の 65 件の式表 (PY-88・PY-159・PY-161・PY-163 の表の元) は、修正前後で出力差分 0 行。既存の `⚠合流` 30 件は、読み命令より前の位置で検出済みだったため変わらない。
- `py99_merge_sets.md` は再生成し、注記 2 行 (`⚠合流@0x104bd49`・`⚠合流@0x104be63`) が入った。`py99_closure.md` は差分 0。
- (c) 本節 (上の結論) の「閉じた書込み 48/49」は、修正前の `origin/main` でも現行の `py99_closure.py` は `閉じた書込み (B) 0/49・(A) 0/49` を出した。`0x104bffa` の式に `⚠合流` が付く点は両方で同じ。48/49 の数え方は、この節の記述の時点のスクリプトと一致しない。原因の切り分けは未了。

| 実測 (commit `5247253e6`・`work` 入力 `fn.txt` 4664 命令) | 結果 | 所要 | load (1 分) |
|---|---|---|---|
| `analysis/py99_closure.py work/py53/fn.txt` | mismatch 0 (49 件)・exit 0 | 0.43 秒 | 0.00 |
| `analysis/py99_closure.py work/py53/fn.txt --negctl drop-pred` | mismatch 17・exit 1 | 0.54 秒 | 0.00 |
| `analysis/py99_merge_sets.py work/py53/fn.txt` | mismatch 0 (対象 77 件)・exit 0 | 0.35 秒 | 0.00 |
| `py99_closure.py --md` / `py99_merge_sets.py --md` の再生成 | 差分 0 (パス行を除く) | — | — |

素材: `fl-win64` の `block00031_PE.bin` (`tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin'`・1.7 秒)。`analysis/py53_dispatch.py` の出力 `fn=4664 dispatch=13 r8d_tests=174`。

### 再現

    cd tools/python
    python3 analysis/py99_closure.py work/py53/fn.txt                      # 終了コード 0 (mismatch 0)
    python3 analysis/py99_closure.py work/py53/fn.txt --negctl drop-pred   # 終了コード 1 (mismatch 17)
    python3 analysis/py99_closure.py work/py53/fn.txt --md analysis/py99_closure.md  # 表の再生成

`work/` は作業用ディレクトリ (`py53/fn.txt` を置く場所。PY-88 と #3085 と同じ入力)。
