# #911 (LD-19): 41a670 の lift 段階 wrong-value reuse の機構 (部分達成)

親: #735 (LD-13)。前段の切り分けは `REPORT_735.md` §1 (PR #913, merged)。

**判定: 部分達成 (受入条件 1 の機構の手がかり、2 の突合まで)**。検出信号・修復・wasm 実測・DEFECTS 追記は未達。残りは子 issue `[LD-33]` (#1091) に起票済み (§5)。

検証起点: PR の base = merge-base `f04e0f05` (PR 作成時の main)。run 時点の `origin/main` は `5182c3c2`。
素材: `fl-win64` の `block00031_PE.bin` と `work-m11` (`tools/m11/work/` の `boot0.lift.ll` / `boot_final.ll`)。いずれも `tar --zstd -xf` で展開し (§6)、本 run で機械語と IR の両方を確認した。

## 1. 受入条件 1: 41a670 の機構 (手がかり。RetDec 側は未確定)

機械語 (fl-win64 `block00031_PE.bin`。出典は §6):

```
41a67c  mov [rbp+0x50], rcx        ; arg1 を保存
41a681  mov rax, [rbp+0x50]        ; rax = arg1
41a685  mov rcx, [rax+8]           ; 呼び出し引数 = [arg1+8]
41a689  call 0x41a5d0
41a68f  mov rax, [rbp+0x50]        ; rax = arg1
41a693  cmp rax, [rip+0xf8a9e6]    ; [0x13a5080] と比較 (@global_var_13a5080)
41a69a  jne 0x41a6ac               ; 不一致なら 41a6ac 以降 (連結リスト走査)
41a69c  mov rax, [rbp+0x50]        ; rax = arg1 (再ロード)
41a6a0  mov rax, [rax]             ; rax = [arg1+0]  (disp=0)
41a6a3  mov [rip+0xf8a9d6], rax    ; [0x13a5080] = [arg1+0]  (head)
41a6aa  jmp 0x41a6ee
```

- **store は条件付き**: `41a6a3` の store は `41a693`〜`41a69a` の `cmp`/`jne` で guard されており、`arg1 == [0x13a5080]` のときだけ実行される。不一致時は `41a6ac` 以降の連結リスト走査に入る。以下の議論はこの前提に立つ。「無条件の store」として扱わない。
- 機械語には `[arg1+8]` と `[arg1+0]` の **2 本の load** がある。
- lift IR (`boot0.lift.ll` L25677〜25691、本 run で確認済み) では関数先頭の `%2 = load i64, ptr (%arg1+8)` (L25683) が 1 本だけで、41a6a3 相当の store (L25691 `store i64 %2, ptr @global_var_13a5080`) はこの `%2` を再利用している。`[arg1+0]` の load は IR に現れない。
- guard も IR にある: L25685〜25688 の `load @global_var_13a5080` → `icmp eq %4, %arg1` → `br` が、機械語の `41a693`〜`41a69a` の `cmp`/`jne` に対応する。store (L25691) は分岐先 `dec_label_pc_41a69c` (L25690 のラベル) の中にあり、guard 成立時のみ実行される。

仮説 (未検証): RetDec の lift で、同一ベースレジスタ (`arg1`) からの load を値番号付けする際に **displacement を鍵から落としている** (base だけで同一視)。REPORT_735 §1.1 の「offset が +8 にずれる」はこの見え方である。RetDec ソースでの該当箇所 (load forwarding / 値番号付け) は未調査。

既知類型との関係: D4 (deref 脱落) とは別 (load は残り offset が違う)。D17 (幅縮小) とも別。新類型候補だが、機構確定まで DEFECTS.md には入れない。

## 2. 受入条件 2: 666a60 のループ内 store の機械語突合

機械語 (`666a60` 全体のうち該当部分。`ldmach.Machine(pe).disasm_fn(0x666a60)` の出力から抜粋):

```
666a6f  mov [rbp+0x28], rcx          ; 元の rcx (= IR の %arg1) を保存
666a92  call 0x409470
666a97  mov rax, [rbp+0x28]
666a9b  mov r14, [rax]               ; r14 = *(arg1)  ← 1 段の deref
666a9e  mov dword [r14], ebx         ; *(r14) へ書く
666ab9  call 0x666960                ; r14 は保持したまま
666ad6  call qword [rax]             ; 間接 call
666aeb  movsxd rcx, eax              ; ループ本体 (eax = i)
666aee  shl rcx, 2
666af2  lea rcx, [r14 + rcx*8 + 0x40] ; rcx = r14 + 0x40 + 0x20*i (slot 先頭)
666af7  mov qword [rcx], 0
666afe  movsxd r8, r13d
666b01  movsxd r9, eax
666b04  lea r8, [r8 + r9]
666b08  mov [rcx+8], r8
666b0c  mov r8, [rbp+0x28]
666b10  mov r8, [r8]                 ; r8 = *(arg1) を再ロード
666b13  mov [rcx+0x10], r8           ; slot+0x10 へ書く
666b17  mov qword [rcx+0x18], 0
666b1f  add eax, 1
```

- **`rcx` の同一性 (指摘 4)**: `666aeb`〜`666af2` で各反復ごとに `rcx` を再計算してから使う。`666af7`〜`666b10` の間に `rcx` への書き込みは無く、`666afe`〜`666b10` が書くのは `r8`・`r9` のみ (`666b0c`〜`666b10` は `[rbp+0x28]` から読むだけ)。よって `666b13` の `rcx` は当該反復の slot 先頭 `r14 + 0x40 + 0x20*i`。`666a92` の call (0x409470) はループ前で、`rcx` は `666aeb` で再定義されるため影響しない。slot の大きさは 32 byte (`eax*4*8`)。
- **`r8` の値 (前回の記述の訂正)**: `666b13` が書くのは `r14` ではなく、`666b0c`〜`666b10` で再ロードした `*(arg1)`。これが `r14` (= `666a9b` で取った `*(arg1)`) と一致するのは、その間に `*(arg1)` が変わらない場合に限る。`666ab9` (call 0x666960) と `666ad6` (間接 call) がその間にあるため、「`r14` を書く」とは断定しない。`r14` は Win64 ABI で非揮発のため call を跨いでも保持されるが、`*(arg1)` の値そのものが call で変わりうる点は残る。

IR (`boot_final.ll` L225098〜225175、本 run で確認済み):

- 先頭の `%15 = inttoptr %arg1` / `store i32 %10, ptr %15` は、機械語の `mov dword [r14], ebx` (r14 = `*(arg1)`) と対応させると **`*(arg1)` の 1 段の deref が IR に無い** (IR は `%arg1` を直接の書き込み先にしている)。
- ループ内の `store i64 %29, ptr %36` (L225157) は、機械語では「`*(arg1)` を再ロードした値を slot+0x10 へ書く」だが、IR は `%29` (スロットアドレス側の計算値) を書く。値が一致しない。

判定: **同一機構 (deref 脱落 / 間接 load の取り違え) の疑い。確定ではない**。`function_666a60` は `boot_final.ll` にのみ存在し (lift 段階の `boot0.lift.ll` には無い)、どの段で落ちたかは未確定。REPORT_509 §1 の「スロットを書く」解釈は、この突合で再検証が必要と判明したため保留する。

## 3. 受入条件 3 (検出信号): 未定義

機構が確定してから定義する。候補は「機械語の `ld(n,w)` の store 値が、IR の store 値として argN からの load と一致しない」(issue 本文の案)。ただし §2 の結果から、`*(arg1)` の deref 脱落を別に拾う信号が要る可能性がある。`audit_lsf.py` は未変更。

## 4. 受入条件 4・5 (修復・wasm 実測・DEFECTS): 未着手

修復前後の wasm 直接呼び (`dyn_509.mjs`) は、機構確定後に行う。wasm 再ビルドは 942 unit 規模の作業が前提 (REPORT_509 §4.2) で、本 run では実施していない。DEFECTS.md 行案も未作成。

## 5. 未解決と起票先

| 未解決 | 起票先 |
|---|---|
| RetDec の値番号付けで displacement が落ちる機構の特定 (受入 1) | #1091 ([LD-33]) に起票済み (OPEN) |
| 666a60 の `*(arg1)` deref 脱落の確定と、検出信号の定義 (受入 2・3) | #1091 ([LD-33]) |
| 修復 + wasm 直接呼び実測 (head=0x2222) (受入 4) | #1091 ([LD-33]) |
| DEFECTS.md 追記 (受入 5) | #1091 ([LD-33]) |

## 6. 再現

素材 (本 run で展開。所要 8.5 秒、実測):

```
mkdir -p "$RUNNER_TEMP/ld19/extracted"
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/ld19/extracted"
# 展開後の PE: $RUNNER_TEMP/ld19/extracted/extracted/block00031_PE.bin
pip install --user capstone pefile
python3 tools/m11/ldfix/disasm_735.py "$RUNNER_TEMP/ld19/extracted/extracted/block00031_PE.bin"
# 41a670〜41a6aa 全体 (41a681〜41a689, 41a68f〜41a69a を含む):
python3 -c "import sys; sys.path.insert(0,'tools/m11/ldfix'); from ldmach import Machine; m=Machine('<PE>'); [print('%x %s %s'%(i.address,i.mnemonic,i.op_str)) for i in m.disasm_fn(0x41a670) if i.address>=0x41a670]"
```

- `disasm_735.py` の出力は `41a69c`〜`41a6a3` の 3 命令 (`mov rax,[rbp+0x50]` / `mov rax,[rax]` / `mov [rip+..],rax`) のみ。41a681〜41a689 と 41a68f〜41a69a は上記の全体出力から取った。
- IR の確認 (§1・§2 の行番号) は `work-m11.tar.zst` を `tar --zstd -xf` で展開し、`tools/m11/work/` の `grep -n` と `sed -n` で行った (展開は約 2.5 秒、実測)。PR 本文の `oc_artifacts: fl-win64 work-m11` で取得する。

## 7. 検証 (`docs/WORKFLOW.md` §6)

- 検証 HEAD: PR head の hash は PR 本文と `gh pr view` が正本 (REPORT 内には書かない。自己参照になるため)。
- 変更は `tools/m11/ldfix/REPORT_911.md` のみ。コード変更なし (`audit_lsf.py` 等は未変更)。
- 20MiB 超の blob は含まない。素材は `$RUNNER_TEMP` 配下で repo 外。
- 実測 (本 run、fl-win64): `41a69c`〜`41a6a3` は REPORT_735 §1.1 と一致 (`disasm_735.py`)。`41a670`〜`41a6aa` の全体、`666a60` の `666aeb`〜`666b1f` は上記 §6 のコマンドで取得。
- 実測 (本 run、work-m11): `boot0.lift.ll` L25677〜25691 (guard L25685〜25688 を含む)、`boot_final.ll` L225098〜225175 (store L225157) を確認し、REPORT の記述と一致。
- 未実測: 修復後の IR・wasm (§4)。
