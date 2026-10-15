# #3121 REPORT — 修正前 IR の `"$"` 番地の fold 123 行を BLK 由来で分類し、section 伸びを icall の版ごとに切り分ける [PLG-P0b-30]

- 担当 issue: #3121 `[PLG-P0b-30]` (親 #2566)。前提 PR #3123 (REPORT_2566) は 2026-10-14 22:34Z に merge 済み。子 #3120 (smoke PASS) は OPEN のため、受入 2・3 (init_reach・n≥3) は未着手 (§6)。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。REPORT_2510 §6 の D24 候補 (BLK slot の constant 化) の続き。

## 0. 結論 (1 行)

修正前 IR の 123 行のうち 104 行は、値の流れを遡ると BLK slot の読みに届く (上限寄りの判定。一般命令では 25%)。修正後の IR では `function_40ea20` の入口分岐が定数式でなくなる。section の +285,040 B (0x45970) のうち #2584 の寄与は +752 B で、残りは icall 側の 5 つの merge (+284,288 B・主因は #617 の +255,616 B)。受入 2・3 (smoke PASS 待ち) と受入 4 (RetDec の機構) は未達。

## 1. 検証起点と測定 commit

- 起点: `origin/main` `624fca112`。worktree `../ws-3121`・branch `3121-plg-p0b-30-blk-classify`。
- 測定 commit: **`ab210bc8b`** (分類スクリプト `fw_blk_fold_map.py` の追加 commit)。同 commit で分類を再実行し、§3 の表と一致することを確認した。
- 素材: `work-fw-stage1` (修正前 IR・10/10 生成) と `work-liftlib` を展開。修正前 IR は展開直後の `fw6.restored.ll` を退避して使う (`fw_lift.sh` が上書きするため)。`fl-win64` は member 2 本のみ展開。`[RETDEC]` は runner 既存 (`docs/REFERENCES.md` §1)。
- 補助物: `fw_hash_counts.json` は `{}` で代用 (REPORT_2566 §1 と同じ。framework 統計のみに影響)。
- 実行環境: nproc 4・RAM 15 GiB。

## 2. 実測 (n=1・基点 `624fca112`)

| 手順 | 結果 | 所要 (real) | load average (終了時 1/5/15 分) |
|---|---|---|---|
| `fw_prep.py` | F.ranges 11,736 件 | 36.6 s | — |
| `icall_rewrite.py` (blk `8a1000`) | rewrote 11,736 funcs / 6,159 sites・`errors {}`・section +5,924,861 B | 23.4 s | — |
| `fw_lift.sh` (RetDec 8 chunk・restore・merge) | rc 0・`fw_all.restored.ll` 11,939 defines | 10 分 16 秒 | 1.08 2.06 1.72 |

- `fw_lift.sh` の所要は REPORT_2566 (5 分 42 秒)・REPORT_3120 (5 分 50 秒) より長い。原因は未切り分け (load 計測は終了時の値のみ)。

## 3. 受入 1 の前半: 修正前 IR の 123 行の分類

分類は `tools/plugins/framework/fw_blk_fold_map.py`。修正前の `fw6.restored.ll` の各行を `(関数名, !insn.addr)` で修正後 IR (`fw0`〜`fw7.restored.ll`・chunk ごとに metadata を読む) の同じ命令に対応づけ、その命令の入力を SSA の def-use で遡る。遡った先が BLK 領域 `[0x8A1000, 0x8A1280)` の読み (`load ... inttoptr (i64 9048xxx)`) に届けば BLK。スタック変数 (`reg2mem`) は同一基本ブロック内で、読みより前の直近の store だけを見る。

| 分類 | 件数 | 意味 |
|---|---|---|
| BLK | 104 | 値の流れを遡ると BLK 読みに届く |
| UNK | 11 | 呼出し結果・判定不能 (うち `uselistorder` 行 6 件・NOADDR 継承 10 件) |
| MISS | 8 | 修正後 IR に同じ (関数, insn.addr) の命令が無い |
| 計 | 123 | `!insn.addr` の無い 16 行は直前の insn.addr を引き継ぎ (分類の `*`) |

- 52 関数に散在 (上位 `function_63fde0`・`function_463820`・`function_550000`・`function_5928f0`)。
- 同一命令だけを見る版 (遡り無し) では BLK は 30 件 (下限)。
- **精度の対照**: BLK 読みを含まない一般命令 (`icmp`・`store`・`sub`・`trunc`・無作為 300 件・seed 3121) に同じ判定を掛けると、BLK 76 件 (25%)・NOBLK 32・UNK 192。遡りは一般に過大評価になりうる。fold 側の BLK 比率 (104/123 = 85%) は一般命令 (25%) より高いと言えるが、「全 123 行が BLK 由来」とは言えない。件数は上限寄りの値として扱う。

## 4. 受入 1 の後半: 修正後 IR で入口分岐が定数式でない

| | 修正前 IR (`fw6.restored.ll` 5141 行) | 修正後 IR (`fw6.restored.ll` 5545〜5547 行) |
|---|---|---|
| 入口分岐 | `br i1 or (icmp eq (and (p,p),0), icmp slt (and (p,p),0))` (`p` = `ptrtoint @1`・定数式) | `%14 = trunc i64 %2`・`%2 = load i64 inttoptr (9048088)` (BLK+0x18 の実読み)・`%15 = icmp slt i32 %14, 1`・`br i1 %15` |
| 意味 | `x==0 ∨ x<0` (`x` = `p`) ⇔ `x<1` | 同じ `x<1`。ただし `x` は BLK の実読み |

- 修正後 IR では `ptrtoint ([2 x i8]* @1 to i32)` が 0 行 (修正前 123 行)、`@global_var_8a10*` の constant global が 0 件 (修正前 4 件)。REPORT_2566 §4 の数値を再現した。

## 5. 受入 5: section 伸び `+0x45970` B の切り分け

`icall_rewrite.py` を版ごとに実行した (`git archive <commit> tools/icall` で版を取り出し、同じ `F.ranges` を使う・1 回 約 24 秒)。BLK は全版で `0x8A1000` (固定オフセット `sect_va + 0x100000`)。

| commit (main の first-parent で icall に触る merge) | 日時 (UTC) | section 増分 (B) | 差分 (B) |
|---|---|---|---|
| `809702b82` (旧 artifact と一致) | 10-10 08:32 | 5,639,821 (= 0x560e8d) | — |
| `49eb6e68e` (PR #404) | 10-12 21:47 | 5,639,821 | 0 |
| `3ce661c93` (PR #326 229-icall-liftlib-stack-blk) | 10-13 01:41 | 5,656,221 | +16,400 |
| `20778a74c` (PR #539 514-plg-f2-icall-restore) | 10-13 03:55 | 5,668,269 | +12,048 |
| `3dac0302c` (PR #641 600-liftlib-e2e-run) | 10-13 06:46 | 5,668,269 | 0 |
| `086590342` (PR #617 361-icall-crt-fma3) | 10-13 07:06 | 5,923,885 | **+255,616** |
| `fd3465111` (PR #1300 1067-icall-fresh-air-residual) | 10-13 20:51 | 5,923,981 | +96 |
| `bb7cb2677` (PR #1855 1633-icall-fa-missing-callee) | 10-14 07:01 | 5,924,109 | +128 |
| `5d33ba04a` (PR #2495 2310-icall-blk0-lift-class) | 10-14 15:34 | 5,924,109 | 0 |
| `ca4945baf` (PR #2584 2565-icall-blk-placement) | 10-14 15:56 | 5,924,861 | **+752** |
| HEAD `624fca112` | 10-15 | 5,924,861 | 0 |

- 旧 artifact の section (`0x560e8d` = 5,639,821) は `809702b82` の icall で再現した (基点の一致確認)。
- 総和 285,040 B = `0x45970`。内訳は #2584 が +752 B、icall 側の 5 merge が +284,288 B。
- `fd3465111` と `086590342` の間の 83〜85 番目の commit は未測定 (+96 の帰属は `fd3465111` の merge 単位)。`3dac0302c` と `20778a74c` の間の 93 番目は両端が同値のため net 0 と見る (未測定)。
- 結論: `+0x45970` B を「#2584 の `place()` だけによる」とは言えない。#2584 の寄与は 0.3% 未満で、大半は後続の icall 変更 (主因は #617) による。

## 6. 受入の状態 (issue #3121 の 5 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. 旧 IR 123 行の BLK / 他由来の分類と、修正後 IR の入口分岐 | 達成 (分類は上限寄り) | §3・§4 |
| 2. `init_reach` の直接呼出の計測 | 未達 (blocked) | #3120 が OPEN で smoke 未 PASS。PASS 後に測る |
| 3. n≥3 の実測 | 未達 (blocked) | 同上 |
| 4. RetDec が BLK slot を constant にする機構 | 未達 | 観測のみ (§4: 修正後 IR で BLK の constant global が 0 件)。最小再現は未着手 |
| 5. section 伸びの切り分け | 達成 | §5 |

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `init_reach` の直接呼出 (受入 2) と n≥3 (受入 3) | #3120 の smoke PASS が前提 | #3121 (継続。#3120 PASS 後に測る) |
| RetDec が BLK slot を constant にする機構 (受入 4) | BLK を外すだけで fold が消えるかが未確定 | #3121 (継続) |
| 分類の過大評価 (§3 の対照 25%)・分類外 UNK 11 と MISS 8 | BLK 由来の件数は上限寄り | #3121 (継続。遡りの改善) |
| section 増分の未測定 (§5 の 83〜85・93 番目) | +96 の帰属の細部 | 再測定のみのため子 issue は起票しない (本表で記録) |

## 8. 再現手順

```sh
git worktree add ../ws-3121 -b 3121-plg-p0b-30-blk-classify origin/main
cd ../ws-3121 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
cp tools/plugins/work/fw/fw6.restored.ll $RUNNER_TEMP/old_fw6.ll   # 修正前 IR (fw_lift.sh が上書きする)
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
cd tools/plugins/work/fw && python3 ../../../icall/icall_rewrite.py --pe $D/extracted/block18983_PE.bin --funcs F.ranges --out fw_icall.dll --map fw_map.json && cd ../../../..
FL_WIN64_DIR=$D bash tools/plugins/framework/fw_lift.sh                 # 10 分 16 秒
python3 tools/plugins/framework/fw_blk_fold_map.py $RUNNER_TEMP/old_fw6.ll tools/plugins/work/fw/fw[0-7].restored.ll --csv $RUNNER_TEMP/fold.csv
```

§5 は `git archive <commit> tools/icall | tar -x -C <dir>` で版を取り出し、`F.ranges` を複写して `icall_rewrite.py` を同じ引数で実行し、`section +N B` を読む。

## 9. コード差分 (測定 commit 以降)

測定 commit `ab210bc8b` 以降の実行コードの差分は無し (本 PR の追記は REPORT と DOC_MAP のみ)。

```sh
git diff ab210bc8b HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```
