# REPORT #2837 — spill 宛 未判定 関数 10c7cd0 (12 site) の消費者分類 (LD-134)

親: #2245 (LD-93)。兄弟: #2838 (LD-135・CLOSED。残りの未判定・判定不能 site は開いた issue に移管・§6)。本 issue の受入条件 1・2 (12 site 全件の分類・根拠の配置) は達成。受入条件 3 (`audit_lsf_ssa_e2e.sh` 7/7) は a31084db で実測済み。現 head の再測定は素材待ち (§1)。

## 1. 測定

- 測定 commit: `a31084db` (コードを変えた最後の commit。分類 `results/candidate_verdicts_2837.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `results/spill178_1161.tsv`)。基点は `origin/main` の `b2b052ce`。作業 worktree `ws-2837` (branch `2837-spill-10c7cd0-consumer`)
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で `tools/m11/work/`・`tools/liftdiff/work/` (gitignore) に展開
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)
- 測定 commit `a31084db` での結果: rc=0・real 2m36.5s・load average 0.68 → 0.99。1〜7/7 完走。7/7 で `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致 (cmp OK)
- 変更前 (`b2b052ce`) の同スクリプト: rc=0・real 2m35.3s。確定 117 / 判定不能 30 / 未判定 31
- 変更後 (`a31084db`): 確定 129 (+12) / 判定不能 30 / 未判定 19 (−12)
- 測定後の差分 (`git diff a31084db 92702b10 -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results`): 5 ファイル・168 挿入・11 削除。内容は main 取り込み (`b20470b0`) 由来と、競合解消の 1 行:
  - `ldfix.py`: #2745 の F3d pass (型タグ読みの load 復元)。既定は無効で `--passes f3d` のときだけ働く。既定の出力は変わらない
  - `f3d_negctl_2745.sh`: 新規 (F3d のネガティブコントロール・#2745)
  - `results/candidate_verdicts_2838.jsonl`: 新規 3 行 (466af0 の 3 site = TRUE_DROP・#2838)
  - `results/spill178_1161.tsv`: 466af0 の 3 site が 未判定 → TRUE_DROP 確定
  - `spill_classify_1161.py`: `candidate_verdicts_2838.jsonl` を読む 1 行を追加 (競合は両方残して解消)
- 現 head (`92702b10`) の TSV (178 行) の再集計: 確定 132 (NO_CONSUMER 19・OK_LOAD 61・TRUE_DROP 52) / 判定不能 30 / 未判定 16 (11 関数)。a31084db 時点からの増分は #2838 の 3 site (466af0)。本 commit は docs のみで、上の差分の対象パスは変えない
- **現 head の e2e は未実施**: 本 run では `work-m11`・`work-liftdiff` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、`tools/m11/work`・`tools/liftdiff/work` の検証スナップショットも無い。`audit_lsf_ssa_e2e.sh` は step 2 の入力 `boot_final3.ll` が無く走らない。よって現 head の rc・7/7・`cmp` は未測定。PR 本文に `oc_artifacts: fl-win64 work-m11 work-liftdiff` を書いたので、素材が揃う run で再測定し、その測定 commit と結果をここに書く。§8 の step 7 代替確認は e2e の代わりではない

## 2. 判定結果 (10c7cd0 の 12 site)

| site | 格納先 (rbp+) | 判定 | 根拠 (要点) |
|---|---|---|---|
| 10ca5ca・10cb9db・10cba2c・10cba77・10cbb80・10ccf91・10ccfe2・10cd02d (8 site) | 0x688・0x5e8・0x5e0・0x5d8・0x5b8・0x518・0x510・0x508 | TRUE_DROP | cell K=0x15e0ab0 から `mov rax,[rip+X]`→`mov rax,[rax]` の 2 段で W=[V] を格納し、`cmp`→`mov rax,[rax-8]` で count を読む。IR は K を 1 段 (V) だけ load し、V を null 判定と配列基底にのみ使う。count は `mem[K-8]` を読み、W と [W-8] は IR に無い (104cb44 と同型) |
| 10ca5a9 | 0x6a4 | OK_LOAD | lea 先の 1 段 load → IR 34470 `%605 = load i32` → 34471 `xor 0x425cd542` → 34515 `zext` が call 43a7e0 の引数 |
| 10cbb5f | 0x5d4 | OK_LOAD | lea 先の 1 段 load → IR 35441 `%1023 = load i32` → 35442 `xor` → 35484 `zext` が call 43a7e0 の引数 |
| 10cbb43・10cd0f8 | 0x48d8 | OK_LOAD | lea 先の 1 段 load → IR 35413 `%1021` (分岐 dec_label_pc_10cbb3a) / 36380 `%1432` → stack_var_-1072 → 36373 `%1430` (cmp) と 36433 `%1450` (zext → call 43a7e0) |

## 3. 対応の取り方

- 8 site の機械語形は全て同じ (K 読み出し → `[rax]` → 格納 → `cmp [slot],0` → `[rax-8]` → 格納 → 読み出し)。ssa.json の cell 欄も 8 site とも 0x15e0ab0 を指す。
- 機械語の site 順と IR の K 読み出し群 (34472・35307・35314・35325・35426・36276・36283・36294 の 8 群) は順序が一致する。site と群の対応は順序で付けた。
- jsonl の evidence にある「IR boot_final3.ll NNNNN」は、この 8 群のうち当該 site に対応づけた群の先頭行を指す群単位の参照。個々の行への対応ではない。8 群は同形のため、結論は site と群の対応の取り方に依存しない。
- IR の V (`%607` 等) は load・store・getelementptr の基底にならない (grep で確認)。機械語のループ基底 (10ca60d→10ca614 の K 2 段 = W) も、IR では V (`%612`) を基底にしている。同じ 1 段脱落が配列基底にも現れる。

## 4. オラクル (`cell_check`) の見落とし

- 8 site のオラクルは CELL_DEEP。`cell_check` は K 自身 (0x11e0ab0) の読みしか数えず、K-8 (0x11e0aa8) の読みを数えない。count が K-8 から来ることを検出できないため、IR に 2 段の連鎖があると判定している。
- 判定 (TRUE_DROP) はオラクルに依らず、機械語と IR の dataflow の比較で行った。
- 静的 image では V=0x12b81b0・mem[V]=0 (W=0)。実行時の値は静的に確定しないため、値ではなく構造 (IR に W の計算経路が無いこと) で判定した。

## 5. 脱落関数の集合

- 現 head (`92702b10`) の `spill_classify_1161.py` の [5]・[6] を、TSV と `drops_510.tsv` から同じ式で再計算した値 (ssa.json を使わない再計算):
  - [5] `drops_510.tsv`: store 宛 51 関数・frame 宛 22 関数・和集合 69 (a31084db から不変)
  - [6] spill 宛の確定 TRUE_DROP 関数 24 のうち drops_510 に無いもの 6 = 4120c0・41a5d0・466af0・6bb3f0・6c3700・10c7cd0
- 和集合 = 69 + 6 = **75** (main 74 + 10c7cd0)。増分は 10c7cd0 のみ。466af0 (#2838) は main 側で入った。
- a31084db 時点の値は 74 (= 69 + 5。466af0 が無く 10c7cd0 が入った形)。
- 残りの未判定 16 site・判定不能 30 site の決着で変わりうる → §6

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未判定 16 site (11 関数) | 脱落関数の和集合 75 が未確定 | 開いた issue: #2921 (ddf630 の 4 site)・#2922 (12cb680 の 2 site)・#2923 (1046a30 の 1 site)・#2583 (LD-118・照合待ち 9 site: 6c3700・6c3d20・6c5930・775340・815050・1042d20・f3e050・12f9730) |
| 判定不能 30 site | 同上 | 開いた issue: #2688 (LD-123・9 site)・#2253 (LD-95・7 site)・#2705 (LD-125・128f9e0 の 12 site)・#2922 (12cb8e1)・#2923 (1047556。再判定は子 #2958) |
| 現 head (`92702b10`) の e2e 再測定 (rc・7/7・cmp) | 測定値は a31084db のみ。現 head の step 7 は TSV からの代替確認 (§8) だけ | 本 PR (#2935) の次の run。`oc_artifacts:` 行で `work-m11`・`work-liftdiff` を取得した run で測定し、本節と §1 を更新 |
| `cell_check` が K-8 の読みを見ない (8 site のオラクルが CELL_DEEP と出る) | オラクル列の表示が不正確。判定は IR 構造で行ったので結論には影響しない | PM agent の判断待ち: cell_check が K-8 の読みを数えない点を改修するか・既定案: 改修せず注記のまま (判定と数値に影響なし) |

## 7. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

## 8. main 取り込み後 (競合解消 merge `b20470b0`)

- 競合は `spill_classify_1161.py` の読込行だけ。main 側 (#2838) は `candidate_verdicts_2838.jsonl` の `cand.update` を、本 PR は `candidate_verdicts_2837.jsonl` の `cand.update` を追加していた。両方を残し、docstring の入力列挙も両方書いた。`spill178_1161.tsv` は自動 merge で衝突せず、判定 JSONL との照合で全行一致 (手動 510・候補 2837・2838 の全 key が TSV の判定と一致)。
- e2e (`audit_lsf_ssa_e2e.sh`) は再実行していない。本 run の素材は `fl-win64` のみで、`work-m11`・`work-liftdiff` が無い (IR の入力が無いため step 2 以降は走らない)。
- 代替として step 7 だけを実行: ssa.json は IR から作れないため、TSV の行 (site・オラクル・text) から ssa.json を組んで `spill_classify_1161.py` を実行した。rc 0。出力 TSV は merge 後の `results/spill178_1161.tsv` と `cmp` 一致。これは読込と集計の検査であり、ssa.json 由来の分類そのものは検査していない。
- 解消後の件数 (step 7 の [2]・[5]・[6]): 確定 132 / 判定不能 30 / 未判定 16。脱落関数の和集合 = 69 + 6 = **75** (main 74 + 10c7cd0)。未判定 16 site は 11 関数 (和集合外 10)。
- §1 の「変更後 129 / 19 / 74」は a31084db 時点の値として読む。§5・§6 は現 head の値に書き直した。
