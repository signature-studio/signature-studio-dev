# #735 (LD-13): 41a670 / 666a60 のループ内 store の wrong-value reuse の切り分け

**判定: 部分達成 (受入条件 1 の一部のみ)**。根本原因の段階 (RetDec lift 段階か、ldfix 段階か) を確定した。根本原因の機構 (RetDec のどの値番号付けか) と、検出信号・修復・DEFECTS 追記は未達。

検証起点: `origin/main` = `1f83c5ee`。素材: `work-m11` (`tools/m11/work/` に展開、gitignore 対象)。`fl-win64` は取得していない (PE 無し)。

## 1. 切り分け結果 (受入条件 1)

### 1.1 41a670 (41a6a3)

機械語 (逆アセンブル、capstone。`ldmach_img.py` の `ImageMachine` 経由):

```
41a69c mov rax, [rbp+0x50]      ; rax = arg1
41a6a0 mov rax, [rax]           ; rax = *arg1 (disp=0)
41a6a3 mov [rip+0xf8a9d6], rax  ; head = *arg1
```

段階別の IR (`tools/m11/work/` の既存ファイル。ldfix 適用前から確認):

| 段階 | ファイル | 41a6a3 相当の store の値 |
|---|---|---|
| RetDec lift (ldfix 前) | `boot0.lift.ll` L25690 付近 | `store i64 %2, ptr @global_var_13a5080` |
| RetDec DRC 後 | `boot0.drc.ll` (insn.addr !6974) | `store i64 %2, i64* @global_var_13a5080` |
| norm0 | `boot0.norm0.ll` | `store i64 %2, ptr @global_var_13a5080` |
| 修復前 IR (prealloca) | `boot_final.prealloca.ll` | `store i64 %2, ...` |
| 現行 (修復後) | `boot_final.ll` / `boot_final2.ll` / `boot_final3.ll` | `store i64 %2, ...` (未修復) |

`%2 = load i64, ptr (%arg1 + 8)` であり、機械語の `[arg1+0]` (disp=0) と offset が違う。**値の取り違えは RetDec lift の段階で既に入っており、ldfix の修復前後で変わっていない。** `boot0.drc.config.json` の関数情報 (`function_41a670`) にはこの取り違えを示す情報は無い。

### 1.2 666a60 のループ内 store

`boot0.lift.ll` と `boot_final.ll` で 666a60 を比べると、ループ内の `store i64 %29, ptr %36` (boot_final.ll L225157) が、REPORT_509 §1 の記述どおり `%29` (スロット) を書いている。機械語 666b0c〜666b13 (`mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10], r8`) との突合は、この run では逆アセンブルを取っていない (未実施)。

## 2. 未達 (起票先)

| 未達 | 理由 | 起票先 |
|---|---|---|
| 根本原因 (RetDec のどの値番号付けか) の特定 | lift 段階で入ることは確定したが、RetDec 内部の機構は未調査 | 子 issue (下記) |
| 検出信号の audit 追加 | 機構が確定してから定義するのが妥当 | 子 issue |
| 修復 + wasm 直接呼び実測 (head=0x2222) | 上記 2 件の後 | 子 issue |
| DEFECTS.md 追記 | 上記の後 | 子 issue |
| 666a60 のループ内 store の機械語突合 | 本 run では未実施 | 子 issue |

## 3. 再現

```
cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot0.lift.ll
```
