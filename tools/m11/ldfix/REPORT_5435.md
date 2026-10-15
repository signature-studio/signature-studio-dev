# REPORT #5435 — spill 宛 `128f9e0` 12 site の到達経路 (BFS) と frame F=2088 の照合 (LD-270)

親: #4959 (LD-246)。元: #2705 (LD-125, merged)。兄弟: #5434 (LD-269: 受入 1・2)。
入口: `ld125_lift_gap.py` と `results/ld125_lift_gap_128f9e0.tsv` (#2705)。
生成物: `ld270_bfs_frame.py` → `results/ld270_bfs_128f9e0.tsv`。

## 1. 測定

- 作業 worktree `ws-5435` (branch `5435-ld270-spill-128f9e0-bfs-frame`、起点 `origin/main`)。
- 素材: `work-m11` と `work-liftdiff` を repo ルートで `tar --zstd -xf` (アーカイブは `tools/m11/work/` の形で入る)。gitignore 対象で commit しない。
- 実行 (foreground): `python3 tools/m11/ldfix/ld270_bfs_frame.py` → rc=0・real 0.32s (実行後の uptime load 0.57)。
- 再実行: `python3 tools/m11/ldfix/ld125_lift_gap.py` → rc=0 (TSV は #2705 の結果と同一)。
- `ld120_frame_128f9e0.py` → rc=0 (F=2088・12 site の stack_var と config locals は ld120 の結果と同一)。

## 2. 受入 3: 入口から 12 site への到達経路 (BFS 親)

- 機械語 CFG (leader 423 件) を入口 `128f9e0` から BFS すると、leader は 423 件すべて到達する。IR CFG (lift 段の label 35 件) も 35 件すべて到達する。
- 12 site は全て機械語 BFS で到達する。経路は全 site で `128f9e0 → 1290081 → 12900bb → 129024a → … → 12905b1 → 1290645` を通り、`0x1290645` (欠落区間の始点) が必ず経路上に乗る。
- 欠落区間の始点 `0x12905da je 0x1290645`・`0x129060e jmp 0x1290645` は機械語に存在する (本 run で確認)。
- 経路上で IR label が無い機械 leader の数 (欠落の有無) は site ごとに 5〜22 件 (§2 の表)。全経路の詳細は `results/ld270_bfs_128f9e0.tsv` の `gap_on_path` 列と、`python3 ld270_bfs_frame.py` の `機械経路:` 行。

| site | 機械 BFS 経路の点数 | 経路上で欠落の leader | site を含む IR block | site 番地に IR label |
|---|---|---|---|---|
| 12906d1 | 18 | 5 | 1290610 (到達 yes) | no |
| 1291ac3 | 28 | 15 | 1290610 (到達 yes) | no |
| 1291b14 | 29 | 16 | 1290610 (到達 yes) | no |
| 1291b5f | 30 | 17 | 1290610 (到達 yes) | no |
| 1291c20 | 21 | 8 | 1290610 (到達 yes) | no |
| 1293012 | 31 | 18 | 1290610 (到達 yes) | no |
| 1293063 | 32 | 19 | 1290610 (到達 yes) | no |
| 12930ae | 33 | 20 | 1290610 (到達 yes) | no |
| 129312c | 23 | 10 | 1290610 (到達 yes) | no |
| 129450c | 33 | 20 | 1290610 (到達 yes) | no |
| 129455d | 34 | 21 | 1290610 (到達 yes) | no |
| 12945a8 | 35 | 22 | 1290610 (到達 yes) | no |

読み: 12 site は全て、IR で `0x1290610` の block が次の label まで飲み込む区間 (= 欠落区間) に入る。IR の到達は block 単位では成立するが、site 番地に IR label は無い。これは #2705 の結論 (欠落区間 `0x1290610`〜`0x129460b`) と一致する。

## 3. 受入 4: frame F=2088 の site ごとの照合

- F は prologue から独立に算出した: `push` 2 本 (16) + `sub rsp, 2072` = **2088** (0x828)。ld120 の `frame_size` と一致する。
- 各 site の `[rbp+disp]` から `stack_var_-(F-disp)` を出す (disp は命令の op_str から取る。番地 `d` の値とは別)。

| site | disp | stack_var | IR alloca | IR 本体の言及 | config locals |
|---|---|---|---|---|---|
| 12906d1 | 0x530 | stack_var_-760 | no | 0 | yes |
| 1291ac3 | 0x490 | stack_var_-920 | no | 0 | yes |
| 1291b14 | 0x488 | stack_var_-928 | no | 0 | yes |
| 1291b5f | 0x480 | stack_var_-936 | no | 0 | yes |
| 1291c20 | 0x468 | stack_var_-960 | no | 0 | yes |
| 1293012 | 0x3c8 | stack_var_-1120 | no | 0 | yes |
| 1293063 | 0x3c0 | stack_var_-1128 | no | 0 | yes |
| 12930ae | 0x3b8 | stack_var_-1136 | no | 0 | yes |
| 129312c | 0x3a0 | stack_var_-1160 | no | 0 | yes |
| 129450c | 0x300 | stack_var_-1320 | no | 0 | yes |
| 129455d | 0x2f8 | stack_var_-1328 | no | 0 | yes |
| 12945a8 | 0x2f0 | stack_var_-1336 | no | 0 | yes |

読み: F=2088 は全 site で一致する (名前は `stack_var_-(F-disp)` の式どおり)。slot 名は config の locals に宣言されているが、IR 本体 (`boot_final3.ll`) には alloca も言及も無い。ld120 の UNDETERMINED の根拠 (IR に store・load が無い) を、F 照合で裏付ける。

## 4. 判定への含意

- 受入 3・4 は測定で満たした。判定 (TRUE_DROP / OK_LOAD / NO_CONSUMER) は変えていない。`candidate_verdicts_1161.jsonl` は変更なし。
- 欠落区間 `0x1290645`〜`0x129460a` を IR に戻す修復と、12 site の判定は本 issue の範囲外 (親 #4959 の受入 5 と、#5434 の範囲)。
- 機構 (RetDec のどの段が `0x1290645`→`0x129460b` を付け替えたか) は未確定のまま (#5434 側)。

## 5. 再現

- `cd tools/m11/ldfix && python3 ld270_bfs_frame.py` (前提: `tools/m11/work` を展開済み)。
- 出力 `results/ld270_bfs_128f9e0.tsv` (13 行: ヘッダ 1 + site 12)。
