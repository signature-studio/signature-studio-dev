# #911 (LD-19): 41a670 の lift 段階 wrong-value reuse の機構 (部分達成)

親: #735 (LD-13)。前段の切り分けは `REPORT_735.md` §1 (PR #913, merged)。

**判定: 部分達成 (受入条件 1 の機構の手がかり、2 の突合まで)**。検出信号・修復・wasm 実測・DEFECTS 追記は未達。残りは子 issue `[LD-33]` (#1091) に起票済み (§5)。

検証起点: PR の base (baseRefOid) = `6ae75e48`。HEAD は main `5182c3c2` を merge 済み (`f04e0f05` は HEAD の祖先だが PR の base ではない)。
素材: `fl-win64` の `block00031_PE.bin` (機械語)。`tar --zstd -xf` で展開し (§6)、本 run で機械語を再確認した。IR (`work-m11` の `boot0.lift.ll` / `boot_final.ll`) は本 run の `$ARTIFACTS_DIR` に無く、IR 側の行番号は前 run の記録 (再確認なし)。

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
- lift IR (`boot0.lift.ll` L25677〜25691、前 run の記録。本 run では未再確認) では関数先頭の `%2 = load i64, ptr (%arg1+8)` (L25683) が 1 本だけで、41a6a3 相当の store (L25691 `store i64 %2, ptr @global_var_13a5080`) はこの `%2` を再利用している。`[arg1+0]` の load は IR に現れない。
- guard も IR にある: L25685〜25688 の `load @global_var_13a5080` → `icmp eq %4, %arg1` → `br` が、機械語の `41a693`〜`41a69a` の `cmp`/`jne` に対応する。store (L25691) は分岐先 `dec_label_pc_41a69c` (L25690 のラベル) の中にあり、guard 成立時のみ実行される。

仮説 (未検証): RetDec の lift で、同一ベースレジスタ (`arg1`) からの load を値番号付けする際に **displacement を鍵から落としている** (base だけで同一視)。REPORT_735 §1.1 の「offset が +8 にずれる」はこの見え方である。RetDec ソースでの該当箇所 (load forwarding / 値番号付け) は未調査。

既知類型との関係: D20 (既登録・機構未確定) と同型。D4 (deref 脱落) とは別 (load は残り offset が違う)。D17 (幅縮小) とも別。DEFECTS.md 側の追記は #1091 (受入 5) に残す。

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

IR (`boot_final.ll` L225098〜225175、前 run の記録。本 run では未再確認):

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

素材 (本 run で全件展開。最大 RSS 7.3MB (`/usr/bin/time` 実測)。展開時間は実行環境に依存するため記載しない。`block00031_PE.bin` sha256 `b2c64da4…9496d`):

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
- IR の確認 (§1・§2 の行番号) は `work-m11.tar.zst` を `tar --zstd -xf` で展開し、`tools/m11/work/` の `grep -n` と `sed -n` で行う想定。ただし本 run では `work-m11` が `$ARTIFACTS_DIR` に無く未実施。再現には `oc_artifacts: fl-win64 work-m11` で起動し直す必要がある。

## 6b. 検出信号の試行 (#735 run 3・不採用。コード変更は無し)

目的: 受入 3 (検出信号) として「機械語の zero-disp load 値の store に対し、IR の store 値が `load (argN + c)` (c≠0) か」を `audit_lsf.py` に追加する。

機械語の実測 (fl-win64 `block00031_PE.bin`、本 run で再確認): `41a670`〜`41a6d9` と `666aeb`〜`666b1f` は §1・§2 の記述と一致 (`ldmach.Machine.disasm_fn`)。

IR 側の検出試行 (参考値・再現手段なし): 前 run の試作では `41a670` を含む同形の store が検出されたが、誤検出も多く採用しなかった。本 run では `work-m11` が無く再実行していない。件数・関数名は再現できないため記載しない。
- 原因の推定: `transfer` は機械語側で disp=0 の load 値 (`('ld', n, w)`) しか追跡せず、IR 側の `c` と機械語の disp を照合できない。`(n, w)` だけで突き合わせると無関係な store を拾う。
- 結論: 検出信号は機械語側の値に disp を持たせる (`('ld', n, w, disp)`) 改修が前提。`transfer` の状態表現を変えるため、全関数の既存判定 (`SUSPECT_VAS` / `SUSPECT_USE_VAS`) への影響を再測定する必要があり、1 run の範囲を超える。
- 試作コードは取り消し済み (`audit_lsf.py` は未変更)。次 run は disp 追跡版を別 PR で作る (再現スクリプトは同 PR で `tools/m11/ldfix/` に置く)。

## 6c. #1091 (LD-33): RetDec のどの段で値が化けるか (段の特定まで。規則は未確認)

既知類型との関係 (DEFECTS.md): D20 (既登録・機構未確定) の 41a670 / 666a60 の同型。新規類型として報告する場合の候補は本節。

素材 (本 run で展開。`tar --zstd -xf`): `toolchain-retdec` の `rd/retdec/bin/retdec-decompiler`、`fl-win64` の `fl/extracted/block00031_PE.bin`。`work-m11` は本 run では展開していない (IR 行番号は §1・§2 の前 run の記録のまま)。RetDec の**ソースは素材に無い**。

**結論**: 41a670 の `41a6a0` (`mov rax,[rax]` = `[arg1+0]`) は、RetDec の LLVM パス **`Constants optimization` (段 16)** で `load @rcx` (= `[arg1+8]` の値) に置き換わる。
後段 (段 18 `LLVM instruction optimization using RDA`) で `41a6a3` の store 値もこの値に固定される。`boot0.drc.ll` (RetDec 直後) で既に誤りで、`norm0` / `ir5_patch` は値を変えない (型表記の置換のみ、diff で確認。前 run の記録)。
段 16 で deref を外す変換は、41a670 関数内で `41a6a0` と `41a6d3` の少なくとも 2 命令に起きる (下の負の対照)。

実測 (本 run、`retdec_stage_1091.py`。`--print-after-all` の段ダンプ):

| 機械語命令 | 段 | 段名 | IR の変化 |
|---|---|---|---|
| 41a6a0 `mov rax,[rax]` | 1 (= 段 2〜15) → 16 | Constants optimization | `load @rax` → `inttoptr`+`load` → **`load @rcx`** (誤) |
| 41a6a3 `mov [rip+..],rax` | 16 → 18 | RDA | 16 で `%rax` 由来 → 18 で `@rcx` 由来を保持 |
| 41a6d3 `mov rcx,[rcx]` | 1 → 16 | Constants optimization | `load *rcx` (`inttoptr`+`load`) → **`load @rcx`** (deref 脱落。41a6a0 と同型) |
| 666b10 `mov r8,[r8]` (666a60) | 16 → 17 | Constants optimization | `inttoptr(r8)` の load → **`load @rcx`** (誤。`rcx` = slot 先頭) |

41a6a0 の段 1 と段 16 の IR (本 run の出力。段 2〜15 は段 1 と同一。変化時のみ出力される):

```
段 1 (= 段 2〜15):                    段 16 Constants optimization:
  %66 = load i64, i64* @rax             %49 = load i64, i64* @rcx
  %67 = inttoptr i64 %66 to i64*        store i64 %49, i64* @rax
  %68 = load i64, i64* %67
  store i64 %68, i64* @rax
```

41a6d3 の段 1 と段 16 の IR (本 run):

```
段 1:                                  段 16:
  %133 = load i64, i64* @rcx             %93 = load i64, i64* @rcx
  %134 = inttoptr i64 %133 to i64*       store i64 %93, i64* @rcx
  %135 = load i64, i64* %134
  store i64 %135, i64* @rcx
```

負の対照 (本 run、`retdec_negctl_1091.py`): 41a670〜41a6f4 の 39 命令を段対ごとに比較した。

| 段対 | 変化件数 | 変化した命令 |
|---|---|---|
| 14→15 | 19 | 41a670 41a671 41a675 41a678 41a67c 41a681 41a68f 41a69c 41a6b3 41a6b7 41a6be 41a6c5 41a6cb 41a6cf 41a6db 41a6e2 41a6e6 41a6ee 41a6f2 (41a6a0 は含まない) |
| 15→16 | 5 | 41a693 **41a6a0** 41a6a3 41a6ac **41a6d3** |
| 16→17 | 2 | 41a689 41a6f3 |
| 17→18 | 30 | (RDA 段で広範に変化) |
| 18→19 | 0 | — |

結論: 段 16 は 41a6a0 固有ではない。段 15→16 では 41a6a0 と 41a6d3 の 2 命令が deref 脱落の型で変わる。規則が何かは未特定。

666a60 (本 run、範囲 666a60〜666b20、57 命令): 

| 段対 | 変化件数 | 備考 |
|---|---|---|
| 14→15 | 0 | — |
| 15→16 | 18 | 666b10 は含まない |
| 16→17 | 4 | **666b10** (`inttoptr` → `load @rcx`) を含む |
| 17→18 | 3 | 666b17 ほか |

666b10 の変化は段 16→17 (前 run の記録「15→17」の 17 段目と一致)。段番号の差は同じ pass (`Constants optimization`) の添字の差で、`Module Verifier` の出力回数の違いによる (付録 §6h)。
666a60 の行 (666b10 を含む 16→17 の結果) は本 run で範囲 666a60〜666b20 を再ダンプして得た値。

**未確定 (受入 1 の後半・受入 2 の確定)**:
- 段 16 の「どの変換規則が `load @rax` を `load @rcx` に畳んだか」は、RetDec のソースが無いため未特定 (素材に無い)。`Constants optimization` の名前からの推定に留まる。
- 666a60 の 666b10 も段 17 (Constants optimization) で同型に変わる。ただし段 16 と 17 の段番号が 41a670 と異なるため、**同一機構かの確定は、規則を特定してから**。

**残り (#1091 に残す)**: 検出信号 (受入 3)・修復 (受入 4)・wasm 直接呼び実測 (head=0x2222)・DEFECTS.md 行 (受入 5)。いずれも RetDec 再 lift と wasm 再ビルドを伴う。

再現コマンドと実測 (本 run。`RETDEC` / `PE` は上記の展開先):

```
python3 tools/m11/ldfix/retdec_stage_1091.py 41a670 41a670 41a6f4 41a6a0 --out <DIR>
python3 tools/m11/ldfix/retdec_negctl_1091.py <DIR>/dump.err 41a670 41a670 41a6f4 --pairs 15:16,16:17
```

- 所要 (秒、`retdec_stage_1091.py 41a670 41a670 41a6f4 41a6a0`、n=3・逐次): 8.43 / 8.47 / 8.45 (min 8.43 – max 8.47)
- load average (`uptime`): 実行前 1.14 / 実行後 1.09 (レビュー側の実測とは別の run)

### 6d. #1091 (LD-33): 段 16 の変換規則の特定 (RetDec ソース照合)

RetDec のソースは公開リポジトリ (avast/retdec) から取得して照合した。素材の toolchain-retdec の実バイナリは **v5.0** (`retdec-decompiler --version`: commit `53e55b4b`、build 2022-12-08)。`2019-03-08` は `share/retdec/support/version.txt` の日付であり版ではない。

- 段 16 の `Constants optimization` は `src/bin2llvmir/optimizations/constants/constants.cpp` の `ConstantsAnalysis` (登録名 `retdec-constants`、L37〜42 (v5.0 でも同じ行に登録))。
- 規則の該当箇所: `checkForGlobalInInstruction` の末尾。行番号は版で異なる: v5.0 (`53e55b4b`) は L165〜170、2019-03-09 時点 (`6edcaaea`) は L163〜168。`isa<LoadInst>(inst) && gv && root.ops.size() <= 1` のとき、load の pointer operand を `gv` (裸の GlobalVariable) に置き換える。`root` は `SymbolicTree::PrecomputedRda` で作った pointer operand の記号木 (`simplifyNode` 済み)。
- 版の確認: 同じ条件式 `isa<LoadInst>(inst) && gv && root.ops.size() <= 1` は 2019-03-09 時点の版 (`6edcaaea`) と v5.0 (`53e55b4b`、測定に使った実バイナリの版) の両方にある。最後の変更 `24b50de5` (2019-05-27) は別の条件 (`getActiveBits() <= 64`) の追加のみで、この分岐は触っていない。
- 版差: v5.0 では分岐内に `_toRemove.insert(val);` が追加されている (2019 版には無い)。この差が 41a6a0 / 666b10 の結果に効くかは**未確認**。
- 観測との対応: `41a6a0` の `load *rax` が `load @rcx` になるのは、記号木が `inttoptr(load @rax)` の pointer を gv `@rcx` まで簡約し、この分岐で deref の 1 段を落として gv を直接 load する形と整合する (§6c の段 1→16 の IR と一致)。

**未確認 (ここで止める)**: 分岐が実際に 41a6a0 で発火することの実行による確認 (RetDec をビルドしてログを出す作業は本 run に収まらない)。上記は「ソース上の唯一の該当分岐」であり、発火の証明ではない。

判定: 受入 1 後半 (変換規則の特定) は **ソース上の該当分岐までで達成**。発火の実行確認は子 issue に残す。

## 6e. #1432 (LD-49): 受入 2 — 666b10 の段 17 判定 (ビルド不要)

測定 commit: `209d5df9` (`tools/m11` のコード変更は `00083cdb` 以降なし)。素材: `toolchain-retdec` の実バイナリ **v5.0** (commit `53e55b4b`、build 2022-12-08) と `fl-win64` の `block00031_PE.bin`。

```
RETDEC=<retdec-decompiler> PE=<block00031_PE.bin> python3 tools/m11/ldfix/retdec_stage_1091.py 666a60 666a60 666b20 666b10 --out <DIR>
```

- 所要 9.458 秒 (real、n=1)。load average 実行前 1.10 / 実行後 1.16 (`00083cdb` 上の測定)。
- 再測定 (v5.0、本 run、`209d5df9`、n=1): real 6.347 秒、load average (1 分値) 実行前 0.69 / 実行後 0.74。出力は上表と一致 (段 1 `load @r8`→`inttoptr`→`load`、段 17 `load @rcx`→`store @r8`、段 19 は 17 と同じ)。
- 出力 (`666b10` の `mov r8,[r8]`):

| 段 | 段名 | IR |
|---|---|---|
| 1 | Input binary to LLVM IR decoding | `load @r8` → `inttoptr` → `load` → `store @r8` |
| 17 | Constants optimization | `load @rcx` → `store @r8` (誤。`rcx` = slot 先頭) |
| 19 | LLVM instruction optimization using RDA | 17 と同じ |

判定: 666b10 の変化は **段 17 の Constants optimization** で起き、41a6a0 (段 16) と同じ「ポインタ経由の load が gv の直接 load に畳まれる」形である。段 1 は RetDec の decoder 段で、ldfix 段ではない。**同一機構とまでは未確定**。分岐 (v5.0 L165〜170) への到達は発火確認 (子 #1967) に依存する。

## 6f. #1967 (LD-71): 分岐の実行確認 (結論のみ)

既存 v5.0 バイナリへの uprobe で、関数内の 3 呼び出し点 (siteA/B/C) の発火を測定。41a6a0・41a6d3・666b10 で siteA が各 1 回発火。siteA が L163〜166 (`gv` 分岐) に当たるかは DWARF 無しのため未確定。詳細・表は `tools/m11/ldfix/REPORT_911_APPENDIX_1967.md`。

## 6g. #2038 (LD-75): 発火行の確定 (ソースビルド)

v5.0 (`53e55b4b`) のソースビルドで発火行を確定。詳細・表・注は付録 `REPORT_911_APPENDIX_1967.md` §6g。
要点: **41a6a0・41a6d3・666b10 の発火は単独範囲の測定で、すべて L167 (gv 分岐)**。41a693-41a69a は L150。これにより §6f の siteA の所在は L167 と対応すると確定した。全体範囲 (41a670-41a6f4) の件数の内訳未確認の 2 回は付録 §6g に記す (L167 の結論は単独範囲に依存)。
判定 (受入 4): 同一分岐 (L167) での発火を実測で確認し、**同一機構と判定** (2315 / 付録 §6h)。段番号差は同じ pass の添字の差で解消。機構の所在は lift 段 (`retdec-constants`、RetDec 本体)。2019-03 版との差は #2314 に移した。

## 7. 検証 (`docs/WORKFLOW.md` §6)

- 検証 HEAD: PR head の hash は PR 本文と `gh pr view` が正本 (REPORT 内には書かない。自己参照になるため)。
- 変更は `tools/m11/ldfix/REPORT_911.md` と新規の `tools/m11/ldfix/retdec_negctl_1091.py` (負の対照の集計)。`audit_lsf.py` 等は未変更。
- 20MiB 超の blob は含まない。素材は `$RUNNER_TEMP` 配下で repo 外。
- 実測 (本 run、fl-win64): `41a69c`〜`41a6a3` は REPORT_735 §1.1 と一致 (`disasm_735.py`)。`41a670`〜`41a6aa` の全体、`666a60` の `666aeb`〜`666b1f` は上記 §6 のコマンドで取得。
- IR (`work-m11`): 本 run では未展開のため再確認していない。`boot0.lift.ll` L25677〜25691・`boot_final.ll` L225098〜225175 は前 run の記録 (§1・§2)。`boot_final3.ll` の sha256 は本 run では取得できない。
- 未実測: 修復後の IR・wasm (§4)。
