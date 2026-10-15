# #3121 REPORT — 修正前 IR の `"$"` 番地の fold 123 行を BLK 由来で分類し、section 伸びを icall の版ごとに切り分ける [PLG-P0b-30]

- 担当 issue: #3121 `[PLG-P0b-30]` (親 #2566)。前提 PR #3123 (REPORT_2566) は 2026-10-14 22:34Z に merge 済み。子 #3120 (smoke PASS) は OPEN のため、受入 2・3 (init_reach・n≥3) は未着手 (§6)。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。REPORT_2510 §6 の D24 候補 (BLK slot の constant 化) の続き。

## 0. 結論 (1 行)

分類器の BLK 判定を修正した (`c7ef3b716`・合成入力 13 件で修正版は全件一致、旧版は 8 件誤判定)。旧版の判定値 (BLK 104 / UNK 11 / MISS 8) は無効で、修正版での実 IR の再分類は素材 (`work-fw-stage1`・`toolchain-retdec`) が本 run に無く未実施 (§7)。section の +285,040 B (0x45970) のうち #2584 は +752 B、icall 側は単一 merge の #617 (+255,616 B) が最大で、残りは個別未測定の区間 (§5)。受入 1〜4 は未達。

## 1. 検証起点と測定 commit

- 起点: `origin/main` `624fca112` (実 IR の基点)。worktree `../ws-3121`・branch `3121-plg-p0b-30-blk-classify`。
- 分類器の測定 commit: 旧版 `ab210bc8b`、修正版 **`c7ef3b716`** (BLK 判定の修正)。修正版の `--selftest` は `c7ef3b716` で実行した (§3.1)。
- 実 IR の素材 (旧版の実測時): `work-fw-stage1` (修正前 IR・10/10 生成) と `work-liftlib` を展開。修正前 IR は展開直後の `fw6.restored.ll` を退避して使う (`fw_lift.sh` が上書きするため)。`fl-win64` は member 2 本のみ展開。`[RETDEC]` は runner 既存 (`docs/REFERENCES.md` §1)。
- 補助物: `fw_hash_counts.json` は `{}` で代用 (REPORT_2566 §1 と同じ。framework 統計のみに影響)。
- 実行環境 (旧版の実測時): nproc 4・RAM 15 GiB。
- 本 run (修正 run) の素材: `$ARTIFACTS_DIR` には `fl-win64` のみ。`toolchain-retdec`・`work-fw-stage1`・`work-liftlib` は無く、`fw_lift.sh` は RetDec 未配置のため実行不能。

## 2. 実測 (n=1・基点 `624fca112`・旧版の実測時)

| 手順 | 結果 | 所要 (real) | load average (終了時 1/5/15 分) |
|---|---|---|---|
| `fw_prep.py` | F.ranges 11,736 件 | 36.6 s | — |
| `icall_rewrite.py` (blk `8a1000`) | rewrote 11,736 funcs / 6,159 sites・`errors {}`・section +5,924,861 B | 23.4 s | — |
| `fw_lift.sh` (RetDec 8 chunk・restore・merge) | rc 0・`fw_all.restored.ll` 11,939 defines | 10 分 16 秒 | 1.08 2.06 1.72 |

- `fw_lift.sh` の所要は REPORT_2566 (5 分 42 秒)・REPORT_3120 (5 分 50 秒) より長い。原因は未切り分け (load 計測は終了時の値のみ)。

## 3. 受入 1 の前半: 修正前 IR の 123 行の分類

分類器は `tools/plugins/framework/fw_blk_fold_map.py`。修正前の `fw6.restored.ll` の各行を `(関数名, !insn.addr)` で修正後 IR (`fw0`〜`fw7.restored.ll`・chunk ごとに metadata を読む) の同じ命令に対応づけ、その命令を SSA の def-use で遡る。

- BLK 読み: load のアドレス、または getelementptr の基底が BLK 領域 `[0x8A1000, 0x8A1280)` の整数 (`load ... inttoptr (i64 9048xxx ...)`) か `@global_var_8a10xx`。
- store は値オペランドだけを遡る (書込み先は読みではない)。call は引数の SSA だけを遡る (引数の整数は読みではない)。`br` の `label %x` と phi のラベルは値として数えない。
- スタック変数 (`alloca`) の読みは同一基本ブロック内で、読みより前の直近の store の値だけを見る。直前の store が無ければ UNK。

### 3.1 分類器の検証 (合成入力 13 件・素材不要)

`python3 tools/plugins/framework/fw_blk_fold_map.py --selftest` で実行する (入力は `fw_blk_fold_map.py` の `SELFTEST_IR`)。旧版は同じ入力を `old.scan` / `old.classify` で読んだ。

| 関数 / insn.addr | 入力の型 | 期待 | 旧版 `ab210bc8b` | 修正版 `c7ef3b716` |
|---|---|---|---|---|
| a000 / 1001 | 非 BLK の値を BLK 番地へ store | NOBLK | BLK (誤: 書込み先を読みに数えた) | NOBLK |
| a001 / 1004 | BLK 読みの加算 | BLK | BLK | BLK |
| a001 / 1005 | BLK 由来の値を stack へ store | BLK | BLK | BLK |
| a001 / 1006 | stack の直前 store からの読み | BLK | NOBLK (誤: store の転送を見ない) | BLK |
| a002 / 1002 | `load @global_var_8a1018` | BLK | NOBLK (誤: グローバル名を取りこぼし) | BLK |
| a002 / 1007 | call の整数引数 (BLK 番地) | NOBLK | BLK (誤) | NOBLK |
| a002 / 1008 | call 結果の加算 | UNK | UNK | UNK |
| a002 / 1009 | BLK 基底の getelementptr | BLK | BLK | BLK |
| a002 / 1010 | BLK 基底の GEP からの load | BLK | BLK | BLK |
| a002 / 1011 | GEP の整数 index (基底は非 BLK) | NOBLK | BLK (誤) | NOBLK |
| a002 / 1012 | 直前 store の無いスタック読み | UNK | NOBLK (誤: 判定不能を NOBLK にした) | UNK |
| a002 / 1015 | 非 BLK の load の値を BLK 番地へ store | NOBLK | BLK (誤) | NOBLK |
| a003 / 1013 | br の label 参照 | NOBLK | UNK (誤: label を値に数えた) | NOBLK |

- 旧版は 13 件中 8 件が誤り (1001・1002・1006・1007・1011・1012・1013・1015)。修正版は 13/13 一致 (`selftest 13 cases, 0 fail`)。

### 3.2 旧版の分類結果 (無効・結論に使わない)

旧版 (`ab210bc8b`) で修正前 IR の 123 行を分類した結果。§3.1 の誤判定 (BLK 側の過大・取りこぼし) を含むため、件数は根拠にしない。修正版での再分類は §7 の素材待ち。

| 分類 (旧版) | 件数 | 意味 |
|---|---|---|
| BLK | 104 | (旧判定器) 値の流れを遡ると BLK 読みに届く |
| UNK | 11 | (旧判定器) 呼出し結果・判定不能 |
| MISS | 8 | 修正後 IR に同じ (関数, insn.addr) の命令が無い |
| 計 | 123 | `!insn.addr` の無い 16 行は直前の insn.addr を引き継ぎ (分類の `*`) |

- 52 関数に散在 (上位 `function_63fde0`・`function_463820`・`function_550000`・`function_5928f0`)。
- 旧版で数えた対照 (無作為 300 件の一般命令) と内訳 (遡り無しの件数・uselistorder・NOADDR の件数) は、committed script と §8 の手順からは再現できないため削除した (Git 履歴の `ab210bc8b` に残る)。

## 4. 受入 1 の後半: 修正後 IR で入口分岐が定数式でない

| | 修正前 IR (`fw6.restored.ll` 5141 行) | 修正後 IR (`fw6.restored.ll` 5545〜5547 行) |
|---|---|---|
| 入口分岐 | `br i1 or (icmp eq (and (p,p),0), icmp slt (and (p,p),0))` (`p` = `ptrtoint @1`・定数式) | `%14 = trunc i64 %2`・`%2 = load i64 inttoptr (9048088)` (BLK+0x18 の実読み)・`%15 = icmp slt i32 %14, 1`・`br i1 %15` |
| 意味 | `x==0 ∨ x<0` (`x` = `p`) ⇔ `x<1` | 同じ `x<1`。ただし `x` は BLK の実読み |

- 修正後 IR では `ptrtoint ([2 x i8]* @1 to i32)` が 0 行 (修正前 123 行)、`@global_var_8a10*` の constant global が 0 件 (修正前 4 件)。REPORT_2566 §4 の数値を再現した。
- この節は IR の目視と grep による観測で、分類器の判定を使っていない。

## 5. 受入 5: section 伸び `+0x45970` B の切り分け

`icall_rewrite.py` を測定点ごとに実行した (`git archive <commit> tools/icall` で版を取り出し、同じ `F.ranges` を使う・1 回 約 24 秒)。BLK は全点で `0x8A1000` (固定オフセット `sect_va + 0x100000`)。

表は測定点 11 行 (基点・HEAD を含む)。「区間の icall commit 数」は、直前の測定点 A と本点 B の間で `git rev-list --first-parent --count A..B -- tools/icall` が数えた commit 数 (A を含まず B を含む)。全区間の合計は 103 件。区間が 1 件のときだけ、その commit に Δ を帰属できる。

| 測定点 commit | PR | 日時 (UTC) | section 増分 (B) | Δ (B) | 区間の icall commit 数 | 帰属 |
|---|---|---|---|---|---|---|
| `809702b82` (基点・旧 artifact と一致) | — | 10-10 08:32 | 5,639,821 (= 0x560e8d) | — | — | — |
| `49eb6e68e` | #404 | 10-12 21:47 | 5,639,821 | 0 | 7 | 区間の合計 0 (個別未測定) |
| `3ce661c93` | #326 | 10-13 01:41 | 5,656,221 | +16,400 | 1 | #326 に帰属 |
| `20778a74c` | #539 | 10-13 03:55 | 5,668,269 | +12,048 | 1 | #539 に帰属 |
| `3dac0302c` | #641 | 10-13 06:46 | 5,668,269 | 0 | 2 | 区間の合計 0 (個別未測定) |
| `086590342` | #617 | 10-13 07:06 | 5,923,885 | +255,616 | 1 | #617 に帰属 |
| `fd3465111` | #1300 | 10-13 20:51 | 5,923,981 | +96 | 9 | 区間の合計 +96 (個別未測定) |
| `bb7cb2677` | #1855 | 10-14 07:01 | 5,924,109 | +128 | 20 | 区間の合計 +128 (個別未測定) |
| `5d33ba04a` | #2495 | 10-14 15:34 | 5,924,109 | 0 | 40 | 区間の合計 0 (個別未測定) |
| `ca4945baf` | #2584 | 10-14 15:56 | 5,924,861 | +752 | 1 | #2584 に帰属 |
| `624fca112` (HEAD) | — | 10-15 | 5,924,861 | 0 | 21 | 区間の合計 0 (個別未測定) |

- 旧 artifact の section (`0x560e8d` = 5,639,821) は `809702b82` の icall で再現した (基点の一致確認)。
- 総和 285,040 B = `0x45970`。内訳: #2584 が +752 B、それ以外の icall 側が +284,288 B。icall 側のうち単一 commit に帰属できるのは #617 (+255,616)・#539 (+12,048)・#326 (+16,400) の 3 件 (計 +284,064 B)。残り +224 B (+96 と +128) は区間の合計で、個別の commit は未測定。
- 結論: `+0x45970` B を「#2584 の `place()` だけによる」とは言えない。#2584 の寄与は +752 B (0.3% 未満)。大半は #617 の単一 commit による。

## 6. 受入の状態 (issue #3121 の 5 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. 旧 IR 123 行の BLK / 他由来の分類と、修正後 IR の入口分岐 | 未達 (分類器は修正済み・実 IR の再分類は素材待ち) | §3.1 (分類器の検証)・§4 (入口分岐)。§3.2 の旧値は無効 |
| 2. `init_reach` の直接呼出の計測 | 未達 (blocked) | #3120 が OPEN で smoke 未 PASS。PASS 後に測る |
| 3. n≥3 の実測 | 未達 (blocked) | 同上 |
| 4. RetDec が BLK slot を constant にする機構 | 未達 | 観測のみ (§4: 修正後 IR で BLK の constant global が 0 件)。最小再現は未着手 |
| 5. section 伸びの切り分け | 達成 (切り分けの形: #2584 = +752 B / #2584 より前の icall 変更 = +284,288 B) | §5 |

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正版の分類器で実 IR を再分類し、§3.2 を置き換える | 受入 1 の件数が未確定。素材 `work-fw-stage1`・`toolchain-retdec` が本 run に無い | #3121 (継続。PR 本文の `oc_artifacts:` 行で素材を指定して再実行) |
| `init_reach` の直接呼出 (受入 2) と n≥3 (受入 3) | #3120 の smoke PASS が前提 | #3121 (継続。#3120 PASS 後に測る) |
| RetDec が BLK slot を constant にする機構 (受入 4) | BLK を外すだけで fold が消えるかが未確定 | #3121 (継続) |
| §5 の個別未測定の区間 (`809702b82`→`49eb6e68e` 7 件、`3dac0302c` 2 件、`fd3465111` 9 件、`bb7cb2677` 20 件、`5d33ba04a` 40 件、HEAD 21 件) | +96・+128 B の帰属の細部 | 再測定のみのため子 issue は起票しない (本表で記録) |

## 8. 再現手順

```sh
python3 tools/plugins/framework/fw_blk_fold_map.py --selftest      # 合成入力 13 件・素材不要 (c7ef3b716 で 13/13)
git worktree add ../ws-3121 -b 3121-plg-p0b-30-blk-classify origin/main
cd ../ws-3121 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
cp tools/plugins/work/fw/fw6.restored.ll $RUNNER_TEMP/old_fw6.ll   # 修正前 IR (fw_lift.sh が上書きする)
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
cd tools/plugins/work/fw && python3 ../../../icall/icall_rewrite.py --pe $D/extracted/block18983_PE.bin --funcs F.ranges --out fw_icall.dll --map fw_map.json && cd ../../../..
FL_WIN64_DIR=$D bash tools/plugins/framework/fw_lift.sh                 # 10 分 16 秒 (旧測定)・RetDec は [RETDEC] 必要
python3 tools/plugins/framework/fw_blk_fold_map.py $RUNNER_TEMP/old_fw6.ll tools/plugins/work/fw/fw[0-7].restored.ll --csv $RUNNER_TEMP/fold.csv
```

- 素材 (PR 本文の `oc_artifacts:` 行): `fl-win64 toolchain-retdec toolchain-emsdk work-fw-stage1 work-liftlib`。`toolchain-retdec` は `[RETDEC]` に展開される (`docs/REFERENCES.md` §4)。
- §5 は `git archive <commit> tools/icall | tar -x -C <dir>` で版を取り出し、`F.ranges` を複写して `icall_rewrite.py` を同じ引数で実行し、`section +N B` を読む。区間の commit 数は `git rev-list --first-parent --count A..B -- tools/icall`。

## 9. コード差分 (測定 commit 以降)

分類器の測定 commit は `c7ef3b716`。以降の実行コードの差分は無し (本 PR の追記は REPORT と DOC_MAP のみ)。

```sh
git diff c7ef3b716 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```
