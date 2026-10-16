# SHX-T49: function_40b620 → function_40b290 の call 欠落 3 site の原因

親: #5576 / 本 issue: #5586 / 子 (修復): #5591 `[SHX-T52]`

## 0. 測定条件と再確認の範囲

- 作者の測定 (§2・§3 の生 grep・IR 行数・`dsm` 行数) の測定 commit は記録されていなかった。`work/boot_final3.ll`・`work/boot0.lift.ll` は本 worktree に無く、再実行できない。
- 修正 run (検証 HEAD: 本 commit の直前 `f95fe8ce4`) で再確認したのは機械語のみ。`block00031_PE.bin` (fl-win64 展開物) を PE の .text 区間から capstone で逆アセンブルした (`0x40b620` のファイル位置 `0xaa20`、208 命令、0x40b620〜0x40b9c6)。
- よって §2・§3 の IR 側の数値 (行番号・65 行・406 行・sha256) は**作者の記録のまま、本 run では未再現**。機械語側 (§3 の表) は本 run で再確認済み。
- この PR の範囲 (`git diff 27efdde43 HEAD -- tools/m11 tools/m2 tools/m5 tools/m0` の差分は本 REPORT 以外に 0 行) は lift 段のコードを変えていない。

## 1. 結論

- 3 site (0x40b8eb・0x40b938・0x40b963) は機械語では `function_40b620` 内の有効な call (`mov rcx, rbp` → `call 0x40b290`) である (本 run で再確認)。
- IR に欠落するのは、作者の記録では lift 段 (RetDec の IR 化) が `function_40b620` を `ucomisd` 直後の `ret i64 0` で閉じるため。0x40b67a 以降 (3 site を含む約 170 命令) が丸ごと出ない。閉じる命令の番地は §3 の注を参照 (未確定)。
- decoder (逆アセンブル) の欠陥ではない。`dsm` は全命令を読めている。欠落は RetDec の IR 化の段。
- 修復は lift パイプラインの変更になるため、この PR では行わない。子 #5591 に切り出した。

## 2. 受入 1: 生 grep による `no_ir_call` の確定

素材 `work/boot_final3.ll` (sha256 先頭 16 桁 `010451add5147d37`) に対する生 grep:

```
$ grep -n '@function_40b290(' work/boot_final3.ll
112286:define weak i64 @function_40b290(ptr %arg1, i64 %arg2) local_unnamed_addr {
501907:  %r = call i64 @function_40b290(ptr %c0, i64 %a1)
```

- 501907 行の call は `@m11_tr_function_40b290` (wrapper) の中にあり、`function_40b620` の本体 (112514〜112537 行) には `function_40b290` を含む行が 0 件。
- よって 3 site はすべて `no_ir_call` で確定。

## 3. 受入 2: 原因箇所の特定

機械語 (本 run で再確認。capstone・PE .text のファイル位置 0xaa20・208 命令、0x40b620〜0x40b9c6):

| 位置 | 命令 | 意味 |
|---|---|---|
| 0x40b660 | `pand xmm0, [rip+0x398]` (8 バイト) | 0x40b668 まで続く |
| 0x40b668 | `movsd [rbp+0x28], xmm0` | |
| 0x40b675 | `ucomisd xmm0, [rbp+0x28]` | flags を設定 |
| 0x40b67a | `jae 0x40b9ba` | 条件分岐 (後続の大半の命令への入口) |
| 0x40b688 | `ucomisd xmm0, [rbp+0x28]` | 2 つ目の比較 |
| 0x40b68d | `jb 0x40b746` | 条件分岐 |
| 0x40b8eb / 0x40b938 / 0x40b963 | `call 0x40b290` | 3 site (`mov rcx, rbp` 直後) |

IR 側 (作者の記録。本 run では未再現):

- 記録では `function_40b620` の本体は 24 行で、`ucomisd` の後に `ret i64 0` で閉じる。`ret` の `!insn.addr` は記録上 0x40b666 とあるが、**0x40b666 は命令境界ではなく (`pand` の途中)、`ucomisd` (0x40b675) より前のため「直後」とは両立しない**。閉じる命令の番地は未確定。確定は #5591 で行う。
- 単体再現の手順は §5。`.drc.ll` 65 行・`dsm` 406 行は作者の記録で、本 run では再実行していない。
- 「1918 関数中の 1 件」「他 25 関数中 19 件」は再現手順が無かったため、本 run では検証できていない (§5 に集計手順を追記)。

判定: 原因は RetDec の IR 化の段と推定する (作者の記録では raw の `.drc.ll` の時点で既に閉じている)。`m2/ir_normalize.py`・`m5/ir5_patch.py` の段は未確認。切り分けは #5591 で行う。

## 4. 修復の状況

- 未修復。修復は lift パイプライン (RetDec の IR 化) の変更になり、本 issue の範囲 (調査と原因特定) を超える。
- 受入 2 の「修復するか、修復不能なら理由を記録」のうち、今回は原因特定まで。修復は #5591。

## 5. 再現手順

```
export PATH="$RETDEC_ROOT/bin:$PATH"   # toolchain-retdec を展開したもの
retdec-decompiler "$FL_WIN64_DIR/extracted/block00031_PE.bin" -o work/f40b620.drc.c \
  --select-ranges 0x40b620-0x40b9c7 --select-decode-only --timeout 100
grep -c 'dec_label_pc_40b' work/f40b620.drc.ll    # 1 (分岐先ラベルが無い)
grep -n 'ret i64 0' work/f40b620.drc.ll           # ucomisd 直後
# 集計 (「1918 関数中 1 件」等): work/boot0.lift.ll の define 単位で、本体に ucomisd を含み、かつ本体末尾が ret のみで閉じる関数を数える
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の IR 化で `ucomisd` 後の分岐を落とす原因の特定と修復 | `function_40b620` の 3 site (と後続約 170 命令) が IR に出ない | #5591 `[SHX-T52]` |
| 同型の打ち切りが他の関数にも出ているか (今回は単発と判定) | 他の欠落の有無 | #5591 |
