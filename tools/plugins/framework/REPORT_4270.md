# #4270 REPORT — RetDec が BLK slot を `constant` global にする条件の最小再現 [PLG-P0b-46]

- 担当 issue: #4270 `[PLG-P0b-46]` (親 #3121・受入 5 の再起票)。前提の観測は `REPORT_2566.md` §4・`REPORT_3121.md` §4。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。`REPORT_2510.md` §6 の D24 候補 (BLK slot の constant 化) の機構部分。

## 0. 結論 (1 行)

RetDec が BLK slot を `constant` にするかは、**セクション属性 (WRITE) ではなく、BLK の各 slot のバイト内容**で決まる。0x18 の slot (`push rbp…`) を含む元の BLK は 3 件 constant、BLK を 0 埋め・0x90 埋めすると 0 件になる (再現: `fw_blk_const_repro.sh`)。「どの値で constant と判定されるか」の厳密な条件は未確定。

## 1. 検証起点と測定 commit

- 起点: `origin/main` `6a9f1c3f0`。worktree `../ws-4270`・branch `4270-plg-blk-constant`。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (gitignore)。RetDec は `RETDEC_BIN` で指定 (`docs/REFERENCES.md` の `[RETDEC]`)。
- 測定 commit: 本 PR の HEAD (§5 に記載)。

## 2. 最小再現の手順と対象

- 対象 IR の関数: 元 VA `0x43b130` (新 VA `0x804cf0`〜`0x80577e`)。BLK の読み (`inttoptr (i64 9048072〜)`) を 18 箇所含み、`fw_icall.dll` の BLK 位置 (VA `0x8A1000`・RVA `0x4A1000`) を読む最小の単位として選んだ。
- 変えるのは BLK 領域 0x280 byte だけ。`.icall` の属性・他の関数は変えない。
- 単独関数の decode では BLK 読みが IR に出ない (新 VA で decode し直す必要がある)。RetDec の `--select-ranges` は新 VA で指定する。

## 3. 実測 (n=3・1 回の decode は 4 秒程度・load 0.4〜0.6)

| variant | 変更 | `constant` global 数 | BLK 直読み (`inttoptr 90480…`) |
|---|---|---|---|
| base | なし (元の `fw_icall.dll`) | **3** | 18 |
| zero | BLK 0x280 byte を 0 埋め | **0** | 72 |
| nop | BLK 0x280 byte を 0x90 埋め | **0** | 72 |
| only08 | 0 埋め + slot 0x08 だけ元の値 | **1** | 54 |
| only18 | 0 埋め + slot 0x18 だけ元の値 | **1** | 54 |

- `base` の constant 3 件は `@global_var_8a1018` (`i64`・`push rbp…`)・`@global_var_8a1008`・`@global_var_8a1010` (`i32 36`)。
- 負のコントロールとして `zero` (0 埋め) と `nop` (0x90 埋め) を使った。両方とも 0 件で、「非ゼロなら constant」という単純な仮説は成り立たない。
- 探索時に WRITE 属性を外した PE (`nowrite`) も試し、`base` と同じ 3 件だった。ただし単独の探索結果で、スクリプトの variant には入れていない。

## 4. 解釈

- 実測 (n=3 で一致): BLK slot を 0 埋め・0x90 埋めにすると constant global は 0 件。元のバイトを残すと 3 件。slot 0x08 だけ・0x18 だけでも 1 件ずつ constant になる。
- 読み取れること: constant 化は BLK の**値の内容**に依存する。WRITE 属性は関係しない (`nowrite` 版は base と同じ、前回の探索で確認)。0x90 埋めでも 0 件なので、「非ゼロなら constant」ではない。
- 読み取れないこと: どの値の形で RetDec が畳むか (RetDec の内部の判定条件)。`24 00` (`"$"`) を含むかは未検証 (0x18 の slot は `24 00` を含まない)。
- 含意: BLK を 0 埋めすれば、この関数では BLK slot の constant 化は消える (`REPORT_3121` §4 の「BLK 直読み」への移行と一致)。ただし 0 埋めで fold が消えても、smoke PASS の確認は #3120 / #3121 の範囲。

## 5. 受入条件の状態 (issue #4270)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. RetDec が BLK slot を constant にする機構を、最小の再現で特定する (受入 5) | **部分** | 最小再現は §3 (`fw_blk_const_repro.sh`・n=3 で一致)。constant 化は BLK の値の内容に依存し、属性・セクションには依らないことまで。RetDec 内部の判定条件は未確定 |

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

測定 commit 以降の差分は本 PR の HEAD で確定させる (§5 と合わせて記載)。
