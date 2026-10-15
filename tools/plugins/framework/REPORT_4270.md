# #4270 REPORT — RetDec が BLK slot を `constant` global にする条件の最小再現 [PLG-P0b-46]

- 担当 issue: #4270 `[PLG-P0b-46]` (親 #3121・受入 5 の再起票)。前提の観測は `REPORT_2566.md` §4・`REPORT_3121.md` §4。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。`REPORT_2510.md` §6 の D24 候補 (BLK slot の constant 化) の機構部分。

## 0. 結論 (1 行)

BLK の slot 0x08・0x10・0x18 は、それぞれ先頭 2 byte `24 00` だけを残すと対応する constant global を 1 件立てる (`k08_pair`・`k10_pair`・`k18_pair_only`・n=3)。ただし `24 01` (`k18_b1_01`) では 0 件で、2 byte の値に依る。1 byte 変異では、0x08・0x10・0x18 の先頭 byte を 0 / 0xff にすると、それぞれの global が消える。0x09 を 0xff にしても 8a1008 は消える。WRITE 属性を外しても 3 件のまま (`nowrite`)。BLK を 0 埋め・0x90 埋めすると 0 件。RetDec 内部の判定規則そのものは未確定。

## 1. 検証起点と測定 commit

- 起点: `origin/main` `6a9f1c3f0`。worktree `../ws-4270`・branch `4270-plg-blk-constant`。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (gitignore)。RetDec は `RETDEC_BIN` で指定 (`docs/REFERENCES.md` の `[RETDEC]`)。
- 測定 commit: `ffd515723` (コードを変えた最後の commit。#4503 で更新)。以降の HEAD は `.md` の追記だけ (§8 の差分 0 行)。

## 2. 最小再現の手順と対象

- 対象 IR の関数: 元 VA `0x43b130` (新 VA `0x804cf0`〜`0x80577e`)。BLK の読み (`inttoptr (i64 9048072〜)`) を 18 箇所含み、`fw_icall.dll` の BLK 位置 (VA `0x8A1000`・RVA `0x4A1000`) を読む最小の単位として選んだ。
- 変えるのは BLK 領域 0x280 byte だけ。`.icall` の属性・他の関数は変えない。
- 単独関数の decode では BLK 読みが IR に出ない (新 VA で decode し直す必要がある)。RetDec の `--select-ranges` は新 VA で指定する。

## 3. 実測 (1 回の実測・decode 1 回は 4 秒程度・load 0.4〜0.6)

- 注: 下表は 1 回目の実測。n=3 の再測定は §9 (測定 commit `ffd515723`) で行い、5 variant すべて一致した。

| variant | 変更 | `constant` global 数 | BLK 直読み (`inttoptr 90480…`) |
|---|---|---|---|
| base | なし (元の `fw_icall.dll`) | **3** | 18 |
| zero | BLK 0x280 byte を 0 埋め | **0** | 72 |
| nop | BLK 0x280 byte を 0x90 埋め | **0** | 72 |
| only08 | 0 埋め + slot 0x08 だけ元の値 | **1** | 54 |
| only18 | 0 埋め + slot 0x18 だけ元の値 | **1** | 54 |

- `base` の constant 3 件は `@global_var_8a1018` (`i64`・`push rbp…`)・`@global_var_8a1008`・`@global_var_8a1010` (`i32 36`)。
- 負のコントロールとして `zero` (0 埋め) と `nop` (0x90 埋め) を使った。両方とも 0 件で、「非ゼロなら constant」という単純な仮説は成り立たない。
- WRITE 属性を外した PE (`nowrite`) の探索結果は本ファイルの根拠にしない。スクリプトの variant に入っておらず、再現できないため (未検証)。

## 4. 解釈

- 実測 (1 回): BLK slot を 0 埋め・0x90 埋めにすると constant global は 0 件。元のバイトを残すと 3 件。slot 0x08 だけ・0x18 だけでも 1 件ずつ constant になる。
- 読み取れること: この関数では constant 化が BLK の**値の内容**に依存する (0 埋め・0x90 埋めで消える)。0x90 埋めでも 0 件なので、「非ゼロなら constant」ではない。
- 読み取れないこと: WRITE 属性の影響 (未検証)。
- 読み取れないこと: RetDec の内部の判定条件そのもの。`24 00` (`"$"`) の有無は §9 で切り分けた (0x18 の先頭 2 byte が `24 00`。§4 の旧記述「`24 00` を含まない」は誤り)。
- 含意: BLK を 0 埋めすれば、この関数では BLK slot の constant 化は消える (`REPORT_3121` §4 の「BLK 直読み」への移行と一致)。ただし 0 埋めで fold が消えても、smoke PASS の確認は #3120 / #3121 の範囲。

## 5. 受入条件の状態 (issue #4270)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. RetDec が BLK slot を constant にする機構を、最小の再現で特定する (受入 5) | **部分** | 最小再現は §3 (`fw_blk_const_repro.sh`・1 回の実測)。constant 化は BLK の値の内容に依ると読めること。WRITE 属性の影響は未検証 (§4)。RetDec 内部の判定条件は未確定 |

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec が `constant` と判定する値の条件 (0x08・0x18 のどの部分が効くか・`24 00` の有無) | BLK の修復方針 (0 埋めで十分か) の確定 | 子 #4503 `[PLG-P0b-50]` (`親: #4270`) |
| 修復 (BLK の 0 埋め・配置変更) の stage-1 再生成と smoke 判定 | 修復の効果が未確認 | #3120 / #3121 (既存) |

## 7. 再現手順

```sh
git worktree add ../ws-4270 -b 4270-plg-blk-constant origin/main
cd ../ws-4270 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst
RETDEC_BIN=<retdec-decompiler のパス> bash tools/plugins/framework/fw_blk_const_repro.sh
```

## 8. コード差分 (測定 commit 以降)

```sh
git diff ffd515723 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'
```

結果 (検証 HEAD `e3a5bc727` 時点で出力 0 行。`.md` を除く非 md 差分が 0 行であることを確認):

（出力なし・0 行）

## 9. #4503 の追加測定 (n=3・slot 0x18 の 1 byte 変異・切り分け)

- 測定 commit: `ffd515723` (`fw_blk_const_repro.sh` に 0x18 の変異 variant を追加した commit)。`REPS=3` で実行、`real 4m59.040s`・終了時 load 1.00 (`uptime`)。素材 `work-fw-stage1`・`toolchain-retdec` (`$RUNNER_TEMP/retdec`) を展開して測定。
- 実行: `REPS=3 RETDEC_BIN=<retdec-decompiler> bash tools/plugins/framework/fw_blk_const_repro.sh`。

| variant | 変更 | constant global (n=3 の値) | `@global_var_8a1018` |
|---|---|---|---|
| base | なし | 3 / 3 / 3 | constant (`i64` 6293007887648161828) |
| zero / nop | BLK 0x280 byte を 0 / 0x90 埋め | 0 / 0 / 0 | 消える |
| only08 / only18 | 残す slot 1 つ | 1 / 1 / 1 | only18 は残る・only08 は消える |
| b18_k_00 / _ff (k=0〜7) | slot 0x18 の k 番目 byte を 0 / 0xff | k=0 (00・ff とも): 2 件 / k=1 の ff: 2 件 / 他 (k=1 の 00 を含む): 3 件 | 8a1018 が消えるのは k=0 (00・ff) と k=1 の ff。他は残る |
| b18_pair_00 | 0x18〜0x19 (`24 00`) を 0 埋め | 2 / 2 / 2 | 消える |
| b18_keep24 | BLK の他の全 byte を 0、0x18〜0x19 (`24 00`) のみ元の値 | 1 / 1 / 1 | 残る (値 `i64 36`) |

- 読み取れること (n=3 で一致):
  1. 1 byte 単独の変異で 8a1018 が消えるのは、0x18 を 0x00 / 0xff にした場合と、0x19 を 0xff にした場合だけ (0x19 の `b18_1_00` は元の値が `00` のため恒等変換で、残るのは当然)。0x1a〜0x1f の 6 byte は単独で変えても消えない。`24 00` (0x18〜0x19) を 0 にした `b18_pair_00` も消える。
  2. `24 00` だけを残し BLK の他の全 byte を 0 にした `b18_keep24` でも 8a1018 は残る (値は `i64 36` に変わる)。これは `24 00` の十分性だけを示す。`"$"` (`24 00`) が必要条件かは未確定 (0x18 を 0xff にすると 0x18 の `24` 自体が消えるため、その実測からは必要性を判定できない)。
  3. 8a1008・8a1010 (`i32 36`) は 0x18 の単独変異 (n=3) では消えなかった。0x08・0x10 の変異は未測定。(§10 で更新: 0x08・0x10 の変異と nowrite を測定済み)
- 訂正: §4 の「0x18 は `24 00` を含まない」は誤り。0x18 の先頭は `24 00 00 00` (`"$"` を含む)。
- **修復前提 (受入 3)**: BLK 0x280 byte を 0 埋めすると、この関数の constant global は 3 件とも 0 件になる (zero: n=3 で 0)。`icall_rewrite.py` の BLK 0 埋めを修復候補とするなら、constant 化の消去は前提として成立する。ただし「fold が消えた後に smoke PASS するか」は未検証 (#3120 / #3121 の範囲)。
- 未解決 (起票先付き・再測定のみのため子は起票しない): RetDec 内部の判定条件そのもの (`24 00` が必要条件か・どの値の組合せで畳むか) は未確定。WRITE 属性の影響は未検証 (§10 で更新: `nowrite` を測定済み、3 件のまま)。`24 00` の十分性は `b18_keep24` (`i64 36`) の 1 件で示しただけ。

## 10. #5165 の追加測定 (slot 0x08・0x10 の 1 byte 変異・先頭 2 byte の切り分け・WRITE 属性)

- 測定 commit: `2617c9d30` (`fw_blk_const_repro.sh` を最後に変えた commit)。以降の HEAD 差分は 0 行 (`git diff 2617c9d30 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'` = 0 行)。
- 実行: `REPS=3 RETDEC_BIN=<retdec-decompiler> bash tools/plugins/framework/fw_blk_const_repro.sh`。`real 13m15s`・開始時 load 0.51・終了時 load 1.00 (`uptime`)。素材 `work-fw-stage1` (`tools/plugins/work/fw/`)・`toolchain-retdec` (`$RUNNER_TEMP/retdec`) を展開して測定。
- 旧 commit `fe8dad13a` でも b08/b10 系 (n=3) を測り、同じ結果だった (2 回の測定で一致)。

| variant | 変更 | constant global (n=3) | 消えたもの |
|---|---|---|---|
| base | なし | 3 / 3 / 3 | — |
| nowrite | `.icall` の WRITE 属性を外す | 3 / 3 / 3 | なし |
| zero / nop | BLK 0x280 byte を 0 / 0x90 埋め | 0 / 0 / 0 | 全部 |
| only08 / only18 | 残す slot 1 つ (0 埋め + 元の値) | 1 / 1 / 1 | 他の 2 つ |
| k08_pair / k10_pair / k18_pair_only | 0 埋め + その slot の先頭 2 byte (`24 00`) だけ元の値 | 1 / 1 / 1 each | 他の 2 つ |
| k18_b1_01 | 0 埋め + slot 0x18 を `24 01` | 0 / 0 / 0 | 全部 |
| b08_0_00 / b08_0_ff | slot 0x08 の byte 0 を 00 / ff | 2 件 | `8a1008` |
| b08_1_ff | slot 0x08 の byte 1 を ff (00 は元の値のため恒等) | 2 件 | `8a1008` |
| b08_2〜7 (00・ff) | slot 0x08 の byte 2〜7 | 3 件 | なし |
| b10_0_00 / b10_0_ff / b10_1_ff | slot 0x10 の byte 0・1 | 2 件 | `8a1010` |
| b10_2〜7 (00・ff) | slot 0x10 の byte 2〜7 | 3 件 | なし |
| b18_0_00 / b18_0_ff / b18_1_ff / b18_pair_00 | slot 0x18 の byte 0・1 | 2 件 | `8a1018` |
| b18_2〜7 (00・ff)・b18_1_00 (恒等) | slot 0x18 の残りの byte | 3 件 | なし |
| b18_keep24 | 0x18〜0x19 だけ元の値 (他 0) | 1 件 | 他の 2 つ |

- 読み取れること (n=3 で一致):
  1. slot 0x08・0x10・0x18 の各 global は、**その slot の先頭 2 byte** のうち byte 0 を 00 / ff、byte 1 を ff にすると消え (byte 1 の 00 は元の値と同じ恒等変換のため対象外)、先頭 2 byte を除く 6 byte を変えても消えない。
  2. 先頭 2 byte だけを残す (`k08_pair` 等) と、各 global は 1 件ずつ立つ。ただし `24 01` (`k18_b1_01`) では 0 件になるため、2 byte の**値**に依る。
  3. WRITE 属性を外しても 3 件のまま。属性の影響は、この関数では見えなかった。
- スクリプト外の測定 (未再現・1 回のみ): 0 埋め + slot 0x18 を `25 00` (byte 0 だけ 0x25) にすると `8a1018` が**残った** (1 回)。同様に full base で slot 0x08 の byte 0 を 0x25 にしても 3 件のまま (1 回)。`24` を `25` に変えても消えないため、`24 00` の値の完全な一致が条件とは言えない。この 2 点は `fw_blk_const_repro.sh` に入っていないため、再現は別途必要。
- 受入 1 (RetDec が BLK slot を constant にする機構の最小再現) の判定: 最小再現 (`fw_blk_const_repro.sh`) と、先頭 2 byte の値依存の切り分けまで。**RetDec 内部の判定規則そのものは未特定**。`24 00` の値依存は、スクリプト外 1 回の `25 00` 結果と合わせても、規則として確定させるには不足。
