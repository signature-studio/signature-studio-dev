# PY-317 (#4332) 付録: rint 6 件の negative control (--negctl drop-part)

親: #3913 (PY-271)。本体は `REPORT_PY99_3104.md` の「未解決」表の行 (解決 #4332)。本節は REPORT_PY99_3104 の 250 行上限のため分割移動した (内容は削除していない)。


測定 commit: `150ba28e6` (usage 文言の修正のみ。最後のコード commit)。`--negctl drop-part` の追加は `e4c4099df`。実測は `150ba28e6` で行った (`e4c4099df` からの差は usage 文言 2 行のみ)。`git diff 150ba28e6 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は本節の commit で 0 行。
素材: `fl-win64` の `extracted/block00031_PE.bin` (`tar --zstd -xf fl-win64.tar.zst extracted/block00031_PE.bin`)。`analysis/py53_dispatch.py` → `fn=4664 dispatch=13 r8d_tests=174`。

### 既存の `--negctl drop-pred` が 6 件で使えない理由

6 件の書込みの直接の読み (`r0.reads`) は 3 件 (0x1048ea8・0x1049059・0x10491d1)。閉包が辿る読みは 8 件 (`reach_before` で store を再帰に辿った先を含む)。どの合流でも、先行辺ごとの到達 store 集合 S_p が**同一**で、辺 1 本を外しても到達集合が変わらない (`contributing=[]`)。そのため `drop-pred` は「寄与を持つ先行辺が無い」で終了する。

### 追加した辺の選び方 (`--negctl drop-part`)

読みの後ろ向きに辿れる辺のうち、外したときに到達集合が**一部だけ減る** (空にならない) 辺を、VA 順に最初の 1 本選ぶ。合流の先行辺ではなく、経路の途中の辺を対象にする (合流の寄与は重なるため)。`drop-pred` と既定の挙動は変えていない。

### 結果 (commit `e4c4099df`)

| 実行 | 結果 | exit |
|---|---|---|
| `analysis/py99_closure.py work/py53/fn.txt` (既定 49 件) | mismatch 0 件 | 0 |
| `analysis/py99_closure.py work/py53/fn.txt --negctl drop-pred` (49 件) | 辺 `0x104754a -> 0x104755d` を外す・mismatch 17 件 | 1 |
| `analysis/py99_closure.py work/py53/fn.txt --negctl drop-part` (49 件) | 辺 `0x1047543 -> 0x104754a` を外す・mismatch 17 件 | 1 |
| `analysis/py99_closure.py work/py53/fn.txt --rint` (6 件) | mismatch 0 件・閉包の A と B が一致 | 0 |
| `analysis/py99_closure.py work/py53/fn.txt --rint --negctl drop-pred` (6 件) | 「寄与を持つ先行辺が無い」で終了 (mismatch は出ない) | 1 |
| `analysis/py99_closure.py work/py53/fn.txt --rint --negctl drop-part` (6 件) | 辺 `0x1047543 -> 0x104754a` を外す・**mismatch 1 件** (書込み `0x1048ed3`・読み `0x1048ea8`・X=0x520 の到達集合が `{0x1047543, 0x1047556}` → `{0x1047556}`) | 1 |

- 6 件の閉包を壊す辺は 1 本 (`0x1047543 → 0x104754a`) で、mismatch = 1・exit 1 を数値で確認した。
- 他の 5 件 (0x10483d3・0x104906e・0x10491ed・0x104a876・0x104a999) は、この辺を外しても変わらない。
- 0x1048ed3 の閉包は、この辺を外すと読み 0x1048ea8 の R が 1 件 (`0x1047556`) だけになる。A (前向き) は 2 件のままなので mismatch が出る。
- 所要: `--rint --negctl drop-part` 実測 3 回とも real 0.38 秒 (rc 1)・load (1 分) 0.04 (測定開始時 `0.04 0.12 0.13`)。

### 再現

    cd tools/python
    python3 analysis/py99_closure.py work/py53/fn.txt --rint --negctl drop-part   # 終了コード 1 (mismatch 1)
