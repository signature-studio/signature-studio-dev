# #735 (LD-13): 41a670 / 666a60 のループ内 store の wrong-value reuse の切り分け

既知類型との関係: 該当なし (DEFECTS.md の D4・D17 と近縁だが症状が違う。理由は §1.1)。

**判定: 部分達成 (受入条件 1 の一部のみ)**。根本原因の段階 (RetDec lift 段階か、ldfix 段階か) を確定した。根本原因の機構 (RetDec のどの値番号付けか) と、検出信号・修復・DEFECTS 追記は未達。

検証起点: `origin/main` = `1f83c5ee`。機械語は `fl-win64` の `block00031_PE.bin` を使う (本 run で展開・再現済み)。IR の素材 `work-m11` は本 run に無く、§1.1 の IR 表は **本 run では再検証していない** (前 run の記述を転記)。

## 1. 切り分け結果 (受入条件 1)

### 1.1 41a670 (41a6a3)

機械語 (PE から逆アセンブル。再現: `python3 tools/m11/ldfix/disasm_735.py <block00031_PE.bin>`、本 run の実測):

```
41a69c mov rax, qword ptr [rbp + 0x50]   ; rax = arg1
41a6a0 mov rax, qword ptr [rax]          ; rax = *arg1 (disp=0)
41a6a3 mov qword ptr [rip + 0xf8a9d6], rax ; head = *arg1
```

関数 `0x41a670` は `.pdata` 上 size `0x84`。

IR 表 (`tools/m11/work/` = `work-m11` の既存ファイル。**本 run では無く未検証**):

| 段階 | ファイル | 41a6a3 相当の store の値 |
|---|---|---|
| RetDec lift (ldfix 前) | `boot0.lift.ll` L25690 付近 | `store i64 %2, ptr @global_var_13a5080` |
| RetDec DRC 後 | `boot0.drc.ll` (insn.addr !6974) | `store i64 %2, i64* @global_var_13a5080` |
| norm0 | `boot0.norm0.ll` | `store i64 %2, ptr @global_var_13a5080` |
| 修復前 IR (prealloca) | `boot_final.prealloca.ll` | `store i64 %2, ...` |
| ldfix 適用後の出力 (値は未修復) | `boot_final.ll` / `boot_final2.ll` / `boot_final3.ll` | `store i64 %2, ...` |

- 取得コマンド (IR 表の各行): `cd tools/m11/work && grep -n 'store i64 %2, ptr @global_var_13a5080' boot0.lift.ll`。`boot0.drc.ll` / `boot0.norm0.ll` も同じ式で取る。`boot_final*.ll` も同じ式で取るが、ldfix 適用後の値は `grep -n 'store i64 %2' boot_final.ll`。
- `work-m11` の生成元と版: #516 qstore 以前の旧版 snapshot (`docs/WORKFLOW.md` §11、#680)。現 main の生成手順とは一致しない。`ir_conditions.json` が無いため、`boot_final*.ll` の `ir_sha256` は照合できない (照合不能と明記)。

`%2 = load i64, ptr (%arg1 + 8)` であり、機械語の `[arg1+0]` (disp=0) と offset が違う。**値の取り違えは RetDec lift の段階で既に入っており、ldfix の修復前後で変わっていない** (前 run の IR 表による。本 run で未検証)。`boot0.drc.config.json` の関数情報 (`function_41a670`) にはこの取り違えを示す情報は無い。

既知類型との照合 (DEFECTS.md 読了の上での判定):
- D4 (deref 脱落, 既知 F7): 症状は「`mov r64,[reg]` の load が消え `rD := reg` になる」。本件は load が残り、offset が +8 にずれる。D4 とは別型。
- D17 (幅縮小): 症状は 8B store が 4B に縮む。本件は幅ではなく offset の取り違え。別型。
- 該当なし。ただし機構が未特定なので、新類型として追加するかは子 issue で判断する。

### 1.2 666a60 のループ内 store

`boot0.lift.ll` と `boot_final.ll` で 666a60 を比べると、ループ内の `store i64 %29, ptr %36` (boot_final.ll L225157) が、REPORT_509 §1 の記述どおり `%29` (スロット) を書いている (前 run の記述。本 run で未検証)。機械語 666b0c〜666b13 (`mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10], r8`) との突合は未実施。

## 2. 未達 (起票先)

| 未達 | 理由 | 起票先 |
|---|---|---|
| 根本原因 (RetDec のどの値番号付けか) の特定 | lift 段階で入ることは確定したが、RetDec 内部の機構は未調査 | 子 issue #911 |
| 検出信号の audit 追加 | 機構が確定してから定義するのが妥当 | 子 issue #911 |
| 修復 + wasm 直接呼び実測 (head=0x2222) | 上記 2 件の後 | 子 issue #911 |
| DEFECTS.md 追記 | 上記の後 | 子 issue #911 |
| 666a60 のループ内 store の機械語突合 | 本 run では未実施 | 子 issue #911 |
| IR 表 (§1.1・§1.2) の再検証 | 本 run に `work-m11` が無い。PR 本文に `oc_artifacts: fl-win64 work-m11` を足して次の run で行う | PR #913 の次回 run |

## 3. 再現

機械語 (本 run で実行済み。`fl-win64` の `block00031_PE.bin` が必要):

```
python3 tools/m11/ldfix/disasm_735.py "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin"
```

IR (`work-m11` が必要。取得は `oc_artifacts: fl-win64 work-m11`):

```
cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot0.lift.ll
```

## 4. 検証 (`docs/WORKFLOW.md` §6)

- 検証起点: `1f83c5ee` (`origin/main`)。
- `git status --porcelain=v1 -- tools/m11/ldfix` (commit 直前, 本 run): `M REPORT_735.md` / `?? disasm_735.py` の 2 件のみ (他担当 WIP 無し)。
- `git diff 1f83c5ee HEAD -- tools/m11/ldfix` (commit 後): 変更は `REPORT_735.md` と `disasm_735.py` のみ。
- 20MiB 超の blob: `find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` の結果は空 (本 run で確認)。
