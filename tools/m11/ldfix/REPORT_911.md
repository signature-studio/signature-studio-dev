# #911 (LD-19): 41a670 の lift 段階 wrong-value reuse の機構 (部分達成)

親: #735 (LD-13)。前段の切り分けは `REPORT_735.md` §1 (PR #913, merged)。

**判定: 部分達成 (受入条件 1 の機構の手がかり、2 の突合まで)**。検出信号・修復・wasm 実測・DEFECTS 追記は未達。残りは子 issue `[LD-33]` に起票 (§5)。

検証起点: `origin/main` = `f04e0f05`。素材は `fl-win64` の `block00031_PE.bin` (`$RUNNER_TEMP/ld19/extracted/`) と `work-m11` の `boot0.lift.ll` / `boot_final.ll` (`tools/m11/work/`)。`pip install capstone pefile` (capstone/pefile は `--user` で導入)。

## 1. 受入条件 1: 41a670 の機構 (手がかり。RetDec 側は未確定)

機械語 (`disasm_735.py` で再取得。REPORT_735 §1.1 と一致):

```
41a681  mov rax, [rbp+0x50]      ; rax = arg1
41a685  mov rcx, [rax+8]         ; 呼び出し引数 = [arg1+8]
41a689  call 0x41a5d0
41a69c  mov rax, [rbp+0x50]      ; rax = arg1 (再ロード)
41a6a0  mov rax, [rax]           ; rax = [arg1+0]  (disp=0)
41a6a3  mov [head], rax
```

機械語には `[arg1+8]` と `[arg1+0]` の **2 本の load** がある。lift IR (`boot0.lift.ll` L25677〜25691) では関数先頭の `%2 = load i64, ptr (%arg1+8)` が 1 本だけで、41a6a3 相当の store (L25691 `store i64 %2, ptr @global_var_13a5080`) はこの `%2` を再利用している。`[arg1+0]` の load は IR に現れない。

仮説 (未検証): RetDec の lift で、同一ベースレジスタ (`arg1`) からの load を値番号付けする際に **displacement を鍵から落としている** (base だけで同一視)。REPORT_735 §1.1 の「offset が +8 にずれる」はこの見え方である。RetDec ソースでの該当箇所 (load forwarding / 値番号付け) は未調査。

既知類型との関係: D4 (deref 脱落) とは別 (load は残り offset が違う)。D17 (幅縮小) とも別。新類型候補だが、機構確定まで DEFECTS.md には入れない。

## 2. 受入条件 2: 666a60 のループ内 store の機械語突合

機械語 (`666a60` の prologue と `666b0c`〜`666b13`):

```
666a6f  mov [rbp+0x28], rcx          ; 元の rcx (= IR の %arg1) を保存
666a97  mov rax, [rbp+0x28]
666a9b  mov r14, [rax]               ; r14 = *(arg1)  ← 1 段の deref
666a9e  mov dword [r14], ebx         ; *(r14) へ書く
666b0c  mov r8, [rbp+0x28]
666b10  mov r8, [r8]                 ; r8 = *(arg1) = r14
666b13  mov [rcx+0x10], r8           ; slot+0x10 へ r14 を書く
```

IR (`boot_final.ll` L225098〜225175):

- 先頭の `%15 = inttoptr %arg1` / `store i32 %10, ptr %15` は、機械語の `mov dword [r14], ebx` (r14 = `*(arg1)`) と対応させると **`*(arg1)` の 1 段の deref が IR に無い** (IR は `%arg1` を直接の書き込み先にしている)。
- ループ内の `store i64 %29, ptr %36` (L225157) は、機械語では「`*(arg1)` (= r14) を書く」だが、IR は `%29` (スロットアドレス側の計算値) を書く。値が一致しない。

判定: **同一機構 (deref 脱落 / 間接 load の取り違え) の疑い。確定ではない**。`function_666a60` は `boot_final.ll` にのみ存在し (lift 段階の `boot0.lift.ll` には無い)、どの段で落ちたかは未確定。REPORT_509 §1 の「スロットを書く」解釈は、この突合で再検証が必要と判明したため保留する。

## 3. 受入条件 3 (検出信号): 未定義

機構が確定してから定義する。候補は「機械語の `ld(n,w)` の store 値が、IR の store 値として argN からの load と一致しない」(issue 本文の案)。ただし §2 の結果から、`*(arg1)` の deref 脱落を別に拾う信号が要る可能性がある。`audit_lsf.py` は未変更。

## 4. 受入条件 4・5 (修復・wasm 実測・DEFECTS): 未着手

修復前後の wasm 直接呼び (`dyn_509.mjs`) は、機構確定後に行う。wasm 再ビルドは 942 unit 規模の作業が前提 (REPORT_509 §4.2) で、本 run では実施していない。DEFECTS.md 行案も未作成。

## 5. 未解決と起票先

| 未解決 | 起票先 |
|---|---|
| RetDec の値番号付けで displacement が落ちる機構の特定 (受入 1) | 子 issue `[LD-33]` (本 PR 作成後に起票。番号は PR 本文・issue コメントに記載) |
| 666a60 の `*(arg1)` deref 脱落の確定と、検出信号の定義 (受入 2・3) | 同上 |
| 修復 + wasm 直接呼び実測 (head=0x2222) (受入 4) | 同上 |
| DEFECTS.md 追記 (受入 5) | 同上 |

## 6. 再現

```
pip install --user capstone pefile
python3 tools/m11/ldfix/disasm_735.py "$RUNNER_TEMP/ld19/extracted/block00031_PE.bin"
cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot0.lift.ll | grep -n 'load i64\|store i64'
cd tools/m11/work && sed -n 225098,225175p boot_final.ll
```

素材: `oc_artifacts: fl-win64 work-m11` (本 run で `tar --zstd -xf` により展開。展開先は `$RUNNER_TEMP/ld19/`)。

## 7. 検証 (`docs/WORKFLOW.md` §6)

- 検証 HEAD: 本 PR の commit (hash は PR 本文に記載)。
- 変更は `tools/m11/ldfix/REPORT_911.md` の新規追加のみ。コード変更なし (`audit_lsf.py` 等は未変更)。
- 20MiB 超の blob は含まない。素材は `$RUNNER_TEMP` 配下で repo 外。
- 実測: `disasm_735.py` の出力は REPORT_735 §1.1 と一致 (3 命令、`41a69c`〜`41a6a3`)。
