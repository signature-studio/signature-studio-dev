# REPORT #2837 — spill 宛 未判定 関数 10c7cd0 (12 site) の消費者分類 (LD-134)

親: #2245 (LD-93)。兄弟: #2838 (LD-135・残り未判定 site と判定不能 site)。本 issue の受入条件 1〜3 は全て達成 (12 site 全件を分類)。

## 1. 測定

- 測定 commit: `a31084db` (コードを変えた最後の commit。分類 `results/candidate_verdicts_2837.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `results/spill178_1161.tsv`)。基点は `origin/main` の `b2b052ce`。作業 worktree `ws-2837` (branch `2837-spill-10c7cd0-consumer`)
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で `tools/m11/work/`・`tools/liftdiff/work/` (gitignore) に展開
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)
- 測定 commit `a31084db` での結果: rc=0・real 2m36.5s・load average 0.68 → 0.99。1〜7/7 完走。7/7 で `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致 (cmp OK)
- 変更前 (`b2b052ce`) の同スクリプト: rc=0・real 2m35.3s。確定 117 / 判定不能 30 / 未判定 31
- 変更後 (`a31084db`): 確定 129 (+12) / 判定不能 30 / 未判定 19 (−12)
- 測定後の差分 (`git diff a31084db HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results`): 出力なし (本 REPORT の追加のみ)

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
- IR の V (`%607` 等) は load・store・getelementptr の基底にならない (grep で確認)。機械語のループ基底 (10ca60d→10ca614 の K 2 段 = W) も、IR では V (`%612`) を基底にしている。同じ 1 段脱落が配列基底にも現れる。

## 4. オラクル (`cell_check`) の見落とし

- 8 site のオラクルは CELL_DEEP。`cell_check` は K 自身 (0x11e0ab0) の読みしか数えず、K-8 (0x11e0aa8) の読みを数えない。count が K-8 から来ることを検出できないため、IR に 2 段の連鎖があると判定している。
- 判定 (TRUE_DROP) はオラクルに依らず、機械語と IR の dataflow の比較で行った。
- 静的 image では V=0x12b81b0・mem[V]=0 (W=0)。実行時の値は静的に確定しないため、値ではなく構造 (IR に W の計算経路が無いこと) で判定した。

## 5. 脱落関数の集合

- `spill_classify_1161.py` の [6]: spill 宛の確定 TRUE_DROP 関数 23 (前 22)。drops_510 に無いもの: 4120c0・41a5d0・6bb3f0・6c3700・10c7cd0
- A ∪ B ∪ C = 69 + 5 = **74** (前 73)。増分は 10c7cd0 のみ。残りの未判定 19 site と判定不能 30 site の決着で変わりうる → #2838

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `cell_check` が K-8 の読みを見ない (8 site のオラクルが CELL_DEEP と出る) | オラクル列の表示が不正確。判定は IR 構造で行ったので結論には影響しない | PM (オラクル改修の要否) |
| 未判定 19 site (12 関数: ddf630 4・466af0 3 ほか) と判定不能 30 site | 脱落関数の和集合 74 が未確定 | #2838 (LD-135) |

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
- 解消後の件数 (step 7 の [2]・[5]・[6]): 確定 132 / 判定不能 30 / 未判定 16 (§1 の 129 / 19 は a31084db 時点。#2838 が 466af0 の 3 site を決着)。脱落関数の和集合 = 69 + 6 = **75** (main 74 + 10c7cd0)。未判定 16 site は 11 関数 (和集合外 10)。
- 以降の §5・§6 の「未判定 19」「和集合 74」は a31084db 時点の値として読む。
