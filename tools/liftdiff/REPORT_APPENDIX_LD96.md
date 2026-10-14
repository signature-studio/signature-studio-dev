# liftdiff REPORT 付録: LD-96 (#2258) heap 持ち越しによる sample:800 (shard 1) の件数揺れの切り分け

親 issue #1637 (LD-58)。前提は `REPORT_APPENDIX_LD58.md` §3・§7。

## 結論

- 受入 (a) 仮説検証: **部分達成**。shard 1 の全体 run で 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` の `s1` 列 mismatch) が揺れることを再現した。単独 run (同 19 関数のみ) では 19/19 `match`。
- 揺れは 19 関数を末尾に足す run の組み合わせに依存する (表 §2)。ただし `cmd_batch` の 400 件 chunk 境界と runner の作り直しが各 run で変わるため、**二分の結果は chunk 境界と交絡しており、原因範囲は特定できなかった**。
- 受入 (b) 原因の分類 (heap の残りか、別の状態か): **未達**。heap 全域比較の計測は未実施 (本 run の時間内に入らなかった)。
- 受入 (c): 測定 commit と差分は §4。

## 1. 測定条件

- 測定 commit: `a1d55799` (origin/main)。本 PR は `tools/liftdiff/REPORT_APPENDIX_LD96.md` と `results/ld96_heap_carryover_s1.tsv` のみ変更 (コード変更なし)。
- 測定 runner: 4 vCPU。`uptime` の load は全体 run 前後で 0.9 程度 (11:03 時点 0.94)。
- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`・`FL_WIN64_DIR`)。`work/` 側は `tools/liftdiff/work/m11`・`tools/m11/work` の既展開物を使用。
- 生データ: `tools/liftdiff/work/ld58/` (gitignore)。

## 2. 測定 (全て `--shards 1 --nobuild --state auto`)

shard 1 は 1 つの runner で順に流れる (`ldlib/session.py` `run_functions`)。`cmd_batch` は 400 件 chunk ごとに `run_functions` を呼ぶため、chunk 内だけで持ち越しが起きる。

| run | 流した関数 | 19 関数の mismatch | match |
|---|---|---|---|
| A | sample:800 全体 (shard 1, 2 chunk) | **19** | 0 |
| B | 19 関数のみ (`file:`) | 0 | 19 |
| C | 先頭 100 件 + 19 関数 | 0 | 19 |
| D | 先頭 200 件 + 19 関数 | 0 | 19 |
| E | 全体 run の順で 781 件 + 19 関数 | **19** | 0 |
| F | 先頭 390 件 + 19 関数 | 0 | 19 |
| G | 後半 391 件 + 19 関数 | **9** | 10 |
| H | G の前半 195 件 + 19 関数 | **1** | 18 |

- run A の件数: 342 / 248 / 210 (REPORT_APPENDIX_LD58 §7 の shard 1 と一致)。
- `wall` (実測): A 6m38.6s (`time` 出力)。B 25s (`done 25s`)。**C・D・E・F・G・H の wall は未記録** (`[batch] done` の値を本節に転記していない)。load は A 開始時点 (11:03) の `uptime` 0.94 のみ記録。
- ログの所在: 生ログ `work/ld58/*.log` は gitignore 対象 (`**/work/`) のためローカル保存のみ。repo 外で再現不可。
- 注: run E は 781 件 (run A から 19 関数を除いた順) の後ろに 19 関数を足したもの。run A と完全に同じ並びではない (19 関数が run A では途中に挟まる)。

## 3. 読み取り

- 19 関数だけ (B) や先頭 200 件までを前置した run (C・D) では揺れない。一方、781 件を前置した run (E) と、同じ 800 件の全体 run (A) では 19 件すべて揺れる。
- 後半 391 件 (G) では 9 件、その前半 195 件 (H) では 1 件だけ揺れる。揺れは段階的に変わるが、chunk 境界の影響を分離していないため、「どの関数の状態が効いたか」は言えない。
- 結論: 揺れは「どの関数が先に走ったか」に依存する。ただし heap 全域比較を入れていないため、heap の残りが原因かは未確定。
- 次の一手 (未実施): chunk 境界を固定する (`--chunk` 相当の引数追加、または `run_functions` を直接呼ぶ小さな driver) うえで、case 後に heap 全域を pristine と比較する計測を入れる。

## 4. 測定 commit と差分

- 測定 commit: `a1d55799`。
- `git diff a1d55799 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py` は本 PR の時点で空 (コード変更なし)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| heap 残り (`ld_model_reset` の hw 範囲外) が原因かの確定 (case 後に heap 全域を pristine と比較する計測) | 件数 360/361 の揺れの説明 | #2258 (残作業) |
| chunk 境界を固定した二分 (run H の 1 件の特定) | 揺れの個別特定 | #2258 (残作業) |
| 受入 (b) の原因分類 | LD-96 の完了条件 | #2258 を `Refs` のまま残す |
