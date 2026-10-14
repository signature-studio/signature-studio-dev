# REPORT #2837 — spill 宛 未判定 関数 10c7cd0 (12 site) の消費者分類 (LD-134)

親: #2245 (LD-93)。兄弟: #2838 (LD-135・CLOSED)・#2921 (LD-138・CLOSED。ddf630 の 4 site は main 側で TRUE_DROP 確定)。残りの未判定・判定不能 site は開いた issue に移管 (§6)。本 issue の受入条件 1・2 (12 site 全件の分類・根拠の配置) は達成。受入条件 3 (`audit_lsf_ssa_e2e.sh` 7/7) は測定 commit `9b7ddcc7` で実測済み (rc=0・7/7・cmp 一致。§1)。

## 1. 測定

- 測定 commit: `9b7ddcc75c8e7dea72650757f9708293d9e279ee` (完全 SHA・e2e を実行した HEAD。main (`798bbb67`) の取り込み merge)。その後の commit は docs (REPORT・DOC_MAP) と main の取り込み merge (`e87eb52a` まで・測定対象のパスは main 側でも変更なし) のみ。`git diff 9b7ddcc7 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` の出力は 0 行 (`docs/WORKFLOW.md` §6)
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で `tools/m11/work/`・`tools/liftdiff/work/` (gitignore) に展開。PR 本文の `oc_artifacts: fl-win64 work-m11 work-liftdiff` で取得
- 実行: `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground・`timeout 900`)
- **測定 commit `9b7ddcc7` の結果**: rc=0・real 1m27.5s・load average (1 分値) 0.13 → 0.87。1〜7/7 完走 (`[audit_lsf_ssa_e2e] n/7` の 7 段すべて出力)。`drops_510.tsv` は results/ と cmp 一致、`spill178_1161.tsv` は results/ と cmp 一致
- step 7 の集計 (9b7ddcc7): 確定 136 (NO_CONSUMER 19・OK_LOAD 61・TRUE_DROP 56) / 判定不能 30 / 未判定 12 (10 関数)。脱落関数の和集合 76 (§5)
- 前測定 commit `412cd2ec` (main 取り込み前の HEAD): rc=0・real 1m34.2s・load average 1.12 → 1.08・1〜7/7 完走・cmp 一致。step 7: 確定 132 / 判定不能 30 / 未判定 16 / 和集合 75。`412cd2ec` → `9b7ddcc7` で main の #2921 (3ec6620c・ddf630 の 4 site が 未判定 → TRUE_DROP) が入り、未判定 16 → 12・確定 132 → 136。
- 先行測定 commit `a31084db` (分類 `results/candidate_verdicts_2837.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `results/spill178_1161.tsv` を入れた最後の commit。基点は `origin/main` の `b2b052ce`。作業 worktree `ws-2837` (branch `2837-spill-10c7cd0-consumer`)):
  - 結果: rc=0・real 2m36.5s・load average 0.68 → 0.99・1〜7/7 完走。7/7 で `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致 (cmp OK)
  - 変更前 (`b2b052ce`) の同スクリプト: rc=0・real 2m35.3s。確定 117 / 判定不能 30 / 未判定 31
  - 変更後 (`a31084db`・main 取り込み前): 確定 129 (+12) / 判定不能 30 / 未判定 19 (−12)
- `412cd2ec` → `9b7ddcc7` は main の取り込み (merge)。競合は `spill_classify_1161.py` の 1 箇所 (§8)。TSV の差分は main 側 #2921 の 4 行 (ddf630)。

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

- 測定 commit `9b7ddcc7` の e2e step 5・6 の出力 (`spill_classify_1161.py` の [5]・[6]):
  - [5] `drops_510.tsv`: store 宛 51 関数・frame 宛 22 関数・和集合 69
  - [6] spill 宛の確定 TRUE_DROP 関数 25 のうち drops_510 に無いもの 7 = 4120c0・41a5d0・466af0・6bb3f0・6c3700・ddf630・10c7cd0
- 和集合 = 69 + 7 = **76**。内訳の増分は 10c7cd0 (本 PR)・466af0 (#2838)・ddf630 (#2921)。main 側 (#2921 取り込み後) の和集合は 75。
- 参考: `412cd2ec` (#2921 取り込み前) は 75 (= 69 + 6)。`a31084db` 時点は 74 (= 69 + 5)。
- 残りの未判定 12 site・判定不能 30 site の決着で変わりうる → §6

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未判定 12 site (10 関数) | 脱落関数の和集合 76 が未確定 | 開いた issue: #2922 (12cb680 の 2 site)・#2923 (1046a30 の 1 site)・#2583 (LD-118・照合待ち 9 site: 1043e2d・12f9752・6c3c78・6c44bd・6c6125・77545c・77593b・815220・f3e0c2) |
| 判定不能 30 site | 同上 | 開いた issue: #2688 (LD-123・9 site)・#2253 (LD-95・7 site)・#2705 (LD-125・128f9e0 の 12 site)・#2922 (12cb8e1)・#2923 (1047556。再判定は子 #2958) |
| `cell_check` が K-8 の読みを見ない (8 site のオラクルが CELL_DEEP と出る) | オラクル列の表示が不正確。判定は IR 構造で行ったので結論には影響しない | PM agent の判断待ち: cell_check が K-8 の読みを数えない点を改修するか・既定案: 改修せず注記のまま (判定と数値に影響なし) |

## 7. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

## 8. main 取り込み (merge `9b7ddcc7`・競合解消)

- main (`798bbb67`) の #2921 (`3ec6620c`) は `spill_classify_1161.py` の docstring と読込行を書き換え、本 PR の `candidate_verdicts_2837.jsonl` の読込行を消していた (main 側に 2837 の参照は 0 件)。消したまま解消すると 10c7cd0 の 12 site が未判定に戻るため、2837 を残した。
- 解消後の読込は 1161・2245・2837・2838・2921 の 5 本。docstring の入力列挙も同じ 5 本。TSV は自動 merge (main 側 #2921 の ddf630 の 4 行と衝突しない)。
- 解消後の TSV は `audit_lsf_ssa_e2e.sh` の step 7 が `results/spill178_1161.tsv` と cmp 一致 (§1 の 9b7ddcc7 測定)。
- 解消後の件数: 確定 136 / 判定不能 30 / 未判定 12。和集合 76。§1・§5・§6 は 9b7ddcc7 の値。
- 92702b10 の時点では e2e を再実行できなかった (素材なし) が、412cd2ec で素材を取得して 7/7 を実測。以降は 9b7ddcc7 で実測。
