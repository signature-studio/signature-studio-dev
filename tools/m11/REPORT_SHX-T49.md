# SHX-T49: function_40b620 → function_40b290 の call 欠落 3 site の原因

親: #5576 / 本 issue: #5586 / 子 (修復): #5591 `[SHX-T52]`

## 1. 結論

- 3 site (0x40b8eb・0x40b938・0x40b963) は機械語では `function_40b620` 内の有効な call (`mov rcx, rbp` → `call 0x40b290`) である。
- IR に欠落するのは、lift 段 (RetDec の IR 化) が `function_40b620` を 0x40b666 付近の `ucomisd` 直後で `ret i64 0` により閉じるため。0x40b67a 以降 (3 site を含む約 170 命令) が丸ごと出ない。
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

機械語 (`Machine` で `function_40b620`、208 命令、0x40b620〜0x40b9c6):

| 位置 | 命令 | 意味 |
|---|---|---|
| 0x40b675 | `ucomisd xmm0, [rbp+0x28]` | flags を設定 |
| 0x40b67a | `jae 0x40b9ba` | 条件分岐 (後続の大半の命令への入口) |
| 0x40b8eb / 0x40b938 / 0x40b963 | `call 0x40b290` | 3 site (`mov rcx, rbp` 直後) |

IR (`work/boot0.lift.ll`、`boot_final3.ll` の元):

- `function_40b620` の本体は 24 行。`ucomisd` の後に `ret i64 0` (`!insn.addr` = 0x40b666 相当) で閉じる。
- 単体再現: `retdec-decompiler <block00031_PE.bin> --select-ranges 0x40b620-0x40b9c7 --select-decode-only` で同じ打ち切りを再現 (`.drc.ll` 65 行)。`dsm` は 406 行で `jae`/`jb` を含む。
- 1918 関数中、`ucomisd` 直後に `ret` で閉じる短い関数は `function_40b620` の 1 件だけ。
- 同じ `ucomisd` を含む他の 25 関数のうち 19 関数は `ucomisd` 後にも `br` を持つ。全体では `ucomisd` 直後の分岐が lift される例が多く、この関数だけ特異。

判定: 原因は RetDec の IR 化の段で、この関数の `ucomisd` 後の分岐 (0x40b67a) を落とす点。`m2/ir_normalize.py`・`m5/ir5_patch.py` の段は未確認 (raw の `.drc.ll` の時点で既に `ret` で閉じているため、後段ではない可能性が高い)。切り分けは #5591 で行う。

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
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の IR 化で `ucomisd` 後の分岐を落とす原因の特定と修復 | `function_40b620` の 3 site (と後続約 170 命令) が IR に出ない | #5591 `[SHX-T52]` |
| 同型の打ち切りが他の関数にも出ているか (今回は単発と判定) | 他の欠落の有無 | #5591 |
