# #718: strict 候補 (ループ先頭ガード型) の真偽検証と、dropped_target_not_label の内訳

判定: 受入 3 (dropped_target_not_label の内訳) を達成。受入 2 (strict 候補の真偽) は**部分達成** (走査器の欠陥を発見し、規則を直した版で件数を再測定。件ごとの真偽は未判定)。受入 1 (RetDec の機構切り分け) と受入 4 (DEFECTS 行案) は未達で、子 issue に分割した (§6)。
検証 HEAD: `a7033aaf` (main) の worktree。素材は `work-m11` (`boot_final.ll`) と `fl-win64` (`block00031_PE.bin`)。

## 1. 走査器の再現 (#699 の数値)

`python3 tools/m11/guard699/scan_guard.py work/boot_final.ll --pe block00031_PE.bin` (4.6 秒, rc 0):

```
{"dropped": 1423, "dropped_target_not_label": 7058, "fn": 6969, "jcc": 25618, "jcc_noblock": 6, "strict": 406}
```

#699 の REPORT (§3-2) と一致した。

## 2. dropped_target_not_label 7058 の内訳 (受入 3)

`work/v718/breakdown.py` (5.1 秒、非コミット)。jcc の絶対 target T が IR に dec_label_pc_<T> として無いもの:

| 分類 | 件数 | 定義 |
|---|---|---|
| `in_fn_gap` | 6993 | T が自関数の VA 範囲内 (次の関数 entry 未満) |
| うち T が機械語の命令境界 | 6993 | (`in_fn_gap` の全件) |
| `outside` | 49 | 自関数範囲外・他関数 entry でもない |
| `tail_fn` | 16 | T が別 IR 関数の entry (tail jump) |

- 7058 のうち 6993 件は同一関数内の命令境界への jcc で、関数外 tail jump は 65 件 (49 + 16) のみ。
- ただし「ラベルが無い」は「IR で分岐が落ちている」と同義ではない。§3 の走査器欠陥がこの集計にも入る。

## 3. 走査器の欠陥: 接尾辞付きブロックの取り違え

`scan_guard.py` の `BLK_RE` は `^dec_label_pc_([0-9a-f]+):` だけを拾う。IR には接尾辞付きブロック (`dec_label_pc_1003756.preheader:` 等) が 1565 件ある。これを無視すると、直前の接尾辞無しブロックの末尾 `term` に別ブロックの終端が混ざる。

接尾辞を独立ブロックとして扱う版 (`work/v718/scan_suffix.py`、元の走査器は変更していない) の結果:

| 版 | dropped | dropped_target_not_label | strict |
|---|---|---|---|
| 元の scan_guard (接尾辞を無視) | 1423 | 7058 | 406 |
| 接尾辞対応 (`scan_suffix.py`) | 1096 | 6868 | 289 |

- 2 版の strict 集合の差: 元にのみ 120 件、接尾辞版にのみ 3 件 (集合の包含は成立しない)。
- 接尾辞版で strict から外れた 120 件の真偽は**未確認**。「偽陽性」と断定できる根拠は、現時点では 1 件の目視のみ (下記)。
- 接尾辞版でも `8c5eb0` の `8c5f18 jg → 8c6066` は strict に残る (#699 の真陽性)。

## 4. strict 候補の真偽 (受入 2) — 部分達成

- 検出規則は heuristic。件ごとの真偽判定は本 run では未完。
- **目視で確認した 1 件 (偽陽性を確認)**: `function_1003730` の `10039be: jg 0x1003bbe`。IR では `dec_label_pc_100399e` の後続に jcc が無いが、同関数の別ブロックに `br i1 %251, label %dec_label_pc_10039cb, label %dec_label_pc_1003bbe` が残っていた。接尾辞版でも strict に残る。**規則の誤判定 (偽陽性) と確認**。走査器は jcc の帰属ブロックを VA で決めるため、帰属が別ブロックに移った場合に誤る。
- **既知の真陽性**: `function_8c5eb0` の `8c5f18 jg → 8c6066` (#699 で修復済み)。
- 接尾辞版の strict 289 件について「成立先 T が同関数の IR の `br` 枝先に存在する」は全件成立 (`work/v718/classify.py`)。ただし上記の 10039be がこの条件を満たしたまま偽陽性なので、**この条件は偽陽性の除外には使えない** (必要条件にもならない)。
- **偽陽性率は未測定**。289 件の判定 (機械語の条件式と IR の条件式の突合) は本 run では完了しなかった。

## 5. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin"   # strict 406
python3 work/v718/scan_suffix.py work/boot_final.ll "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin" work/v718/strict_suffix.json  # strict 289
python3 work/v718/breakdown.py work/boot_final.ll "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin"  # in_fn_gap 6993 ...
python3 work/v718/show.py work/boot_final.ll "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin" 1003730 10039be  # §4 の目視
```

`work/v718/` は gitignore 対象で、コミットしない。

## 6. 未解決 (子 issue に分割)

- **(a) strict 候補の件ごとの真偽と偽陽性率** → #1187 (`[M11-N72]`): 接尾辞版 289 件と、元版にのみある 120 件を、機械語の条件式と IR の条件式で突合する。
- **(b) RetDec の脱落機構の切り分け** (受入 1) → #1188 (`[M11-N73]`): 生 lift 段の CFG 復元と命令翻訳のどちらで落ちるか。`8c5eb0` と同型の最小再現が要る。
- **(c) DEFECTS.md 行案の確定** (受入 4): (a)・(b) の結果に依存する。PM 判断。(a)・(b) の完了後に #718 の子として扱う。
- **(d) `scan_guard.py` の接尾辞対応** → #1190 (`[M11-N74]`): `BLK_RE` を接尾辞付きブロックに対応させ、帰属規則を直す。#699 の positive control (`8c5f18`) を崩さないことを確かめてから行う。

## 7. 範囲

- 本 REPORT のみ追加。`tools/m11/guard699/` は変更しない。
- 範囲外: `m11_ov.c`・`docs/DEFECTS.md` (PM 判断)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。
