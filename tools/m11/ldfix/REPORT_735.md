# #735 (LD-13): 41a670 / 666a60 のループ内 store の wrong-value reuse の切り分け

既知類型との関係: 該当なし (DEFECTS.md の D4・D17 と近縁だが症状が違う。理由は §1.1)。

**判定: 部分達成 (受入条件 1 の一部のみ)**。根本原因の段階 (RetDec lift 段階か、ldfix 段階か) を確定した。根本原因の機構 (RetDec のどの値番号付けか) と、検出信号・修復・DEFECTS 追記は未達。

検証起点: `origin/main` = `1f83c5ee`。機械語は `fl-win64` の `block00031_PE.bin`、IR は `work-m11` を使う (いずれも本 run で `$ARTIFACTS_DIR` から展開し、§1.1 の値を再検証した)。

## 1. 切り分け結果 (受入条件 1)

### 1.1 41a670 (41a6a3)

機械語 (PE から逆アセンブル。再現: `pip install capstone pefile` の後 `python3 tools/m11/ldfix/disasm_735.py <block00031_PE.bin>`。本 run の実測 (capstone 5.0.7 / pefile 2024.8.26) で下記と一致):

```
41a69c mov rax, qword ptr [rbp + 0x50]   ; rax = arg1
41a6a0 mov rax, qword ptr [rax]          ; rax = *arg1 (disp=0)
41a6a3 mov qword ptr [rip + 0xf8a9d6], rax ; head = *arg1
```

関数 `0x41a670` は `.pdata` 上 size `0x84`。

IR 表 (`tools/m11/work/` = `work-m11` の既存ファイル。本 run で検証済み。関数範囲は `function_41a670` の `define` から `}` まで):

| 段階 | ファイル | 41a6a3 相当の store (関数内 L15) |
|---|---|---|
| RetDec lift (ldfix 前) | `boot0.lift.ll` L25691 | `store i64 %2, ptr @global_var_13a5080, align 8` |
| RetDec DRC 後 | `boot0.drc.ll` L27823 (`!insn.addr !6974`) | `store i64 %2, i64* @global_var_13a5080, align 8` |
| norm0 | `boot0.norm0.ll` L27823 | `store i64 %2, ptr @global_var_13a5080, align 8` |
| 修復前 IR (prealloca) | `boot_final.prealloca.ll` | `store i64 %2, ptr inttoptr (i64 16404608 to ptr), align 8` |
| ldfix 適用後の出力 (値は未修復) | `boot_final.ll` / `boot_final2.ll` / `boot_final3.ll` | `store i64 %2, ptr inttoptr (i64 16404608 to ptr), align 8` |

- `16404608` = 0xFA5080 (`@global_var_13a5080` と同じアドレス。boot_final 系では名前でなく絶対アドレスで書かれる)。
- 取得コマンド (関数単位。IR 表の各行で同じ式):
  `cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot_final.ll | grep -n 'store i64 %2'`
  関数に絞らない `grep -n 'store i64 %2' boot_final.ll` は 3287 件ヒットするので使わない。
- `work-m11` の生成元と版: #516 qstore 以前の旧版 snapshot (`docs/WORKFLOW.md` §11、#680)。現 main の生成手順とは一致しない。`ir_conditions.json` は `work-m11` に含まれないため、`ir_sha256` の照合は未実施 (照合不能と明記)。

`%2 = load i64, ptr (%arg1 + 8)` であり、機械語の `[arg1+0]` (disp=0) と offset が違う。**値の取り違えは RetDec lift の段階で既に入っており、ldfix の修復前後で変わっていない** (lift の L25691 で確認。同関数内の `%2 = load` も本 run で確認)。`boot0.drc.config.json` の関数情報 (`function_41a670`) にはこの取り違えを示す情報は無い。

既知類型との照合 (DEFECTS.md 読了の上での判定):
- D4 (deref 脱落, 既知 F7): 症状は「`mov r64,[reg]` の load が消え `rD := reg` になる」。本件は load が残り、offset が +8 にずれる。D4 とは別型。
- D17 (幅縮小): 症状は 8B store が 4B に縮む。本件は幅ではなく offset の取り違え。別型。
- 該当なし。ただし機構が未特定なので、新類型として追加するかは子 issue で判断する。

### 1.2 666a60 のループ内 store

`function_666a60` は `boot_final.ll` (L225098 の define) にのみ存在し、`boot0.lift.ll` には無い (lift 段階の比較は不可)。`boot_final.ll` のループ内の `store i64 %29, ptr %36, align 8` (L225157) は、`%29 = add i64 %26, %28` (L225147) の値を `%36 = inttoptr i64 %35` (L225156) へ書く。本 run ではこの store の存在のみ確認し、REPORT_509 §1 の「スロットを書く」という解釈は再検証していない。機械語 666b0c〜666b13 (`mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10], r8`) との突合は未実施。

## 2. 未達 (起票先)

| 未達 | 理由 | 起票先 |
|---|---|---|
| 根本原因 (RetDec のどの値番号付けか) の特定 | lift 段階で入ることは確定したが、RetDec 内部の機構は未調査 | 子 issue #911 |
| 検出信号の audit 追加 | 機構が確定してから定義するのが妥当 | 子 issue #911 |
| 修復 + wasm 直接呼び実測 (head=0x2222) | 上記 2 件の後 | 子 issue #911 |
| DEFECTS.md 追記 | 上記の後 | 子 issue #911 |
| 666a60 のループ内 store の機械語突合・REPORT_509 解釈の再検証 | 本 run では store の存在のみ確認 | 子 issue #911 |
| `ir_sha256` の照合 (`ir_conditions.json` の生成) | `work-m11` に `ir_conditions.json` が無い。`tools/m11/m11_gen_ir2.sh` での生成は本 run の範囲外 | 子 issue #911 |

## 2b. 検出信号の試作 (run 4・`audit_lsf_disp.py`、既存判定は無変更)

機械語 load に変位 (disp) を持たせ、IR の `store` 値の `load (argN + c)` の c と照合する。`audit_lsf.py` は変更していない (既存の SUSPECT_VAS / SUSPECT_USE_VAS は不変)。

**本 fix run で再測定済み。下記の数値 (135 関数・SUSPECT 4 件・個別の判定) は本 run の実測と一致した。**

測定条件:
- 測定 commit: `d684ed9f` (`audit_lsf_disp.py` 追加 commit)。以後 `tools/m11/ldfix/` の本体コードは変わっていない (`git diff d684ed9f HEAD -- tools/m11/ldfix/audit_lsf_disp.py tools/m11/ldfix/audit_lsf.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/ldmach_img.py` の出力は空)。
- 入力: `$ARTIFACTS_DIR/work-m11.tar.zst` を `tar --zstd -xf` で `tools/m11/work/` に展開 (gitignore 対象)。`work-m11` は `docs/WORKFLOW.md` §11 の R2 スナップショット (#516 qstore 以前の旧版・`ir_conditions.json` 無し)。`tools/m11/m11_gen_ir2.sh` からの生成物ではない。このため `ldfix=applied` と `ir_sha256` の照合はできない。

再測定 (本 fix run、HEAD のコードで実行):

1. 実行コマンド (作業ディレクトリは repo root):
   ```
   python3 tools/m11/ldfix/audit_lsf_disp.py tools/m11/work/boot_final.ll tools/m11/work/m11_image.bin 'tools/m11/work/boot*.drc.config.json' --json tools/m11/ldfix/work/audit_735_disp.json
   ```
   出力 (rc 0、10.5 s):
   ```
   {"functions": 7421, "mach_fns": 135, "suspect_fns": 4, "suspect_keys": 4}
   SUSPECT_DISP_VAS 41a670 6677a0 d237e0 de1da0
   ```
2. 入力の sha256 (`sha256sum` の実測):
   - `boot_final.ll` `69c774ded8aaf717c66d765925ff7435c65771ba63db952243daf5c5a7932a43`
   - `m11_image.bin` `2d10d6926f3fd2b57d0f6a140380bdb0764517f8c514fa0ca1320c4c7e10feeb`
   - `boot0.drc.config.json` `068bf845195daf5eafd0d65679b46e7fdb2e21fcc0ae2c8fa816e0db6d7ac50e`
   - `boot1.drc.config.json` `431601c6b15a9a7848a8f39d23d2b63205774dcd512881c014e927bc072f6b82`
   - `boot2.drc.config.json` `18a68547e3a19ee4eb8a5fbeb141b99aea13e735032ab0421c3ec7bb15ce1ac1`
   - `boot3.drc.config.json` `a68346e13e4249ceb3ee003e99054ee225c8017c3149ea25f8518cd91eea0452`
   - `boot4.drc.config.json` `afce98523c2d960e626181810a2a9e1e8ad8c1ac49794ea4ffc1c7964ba2254c`
3. JSON (`tools/m11/ldfix/work/audit_735_disp.json`、gitignore 対象・コミットしない) の miss 集合: `41a670` (arg1,64) disp {0} / IR {8} / miss {8}、`6677a0` (arg2,64) disp {72,80,88,96} / IR {36,72,80,88,96} / miss {36}、`d237e0` (arg2,64) disp {20,72,96} / IR {20,36,72,96} / miss {36}、`de1da0` (arg1,64) disp {172,192} / IR {172,192,244} / miss {244}。

実測 (全 7421 関数):

| 項目 | 値 |
|---|---|
| 機械語の LSF 列挙があった関数 | 135 |
| SUSPECT (SIGNAL 成立) 関数 | 4: `41a670` / `6677a0` / `d237e0` / `de1da0` |

- `41a670`: 機械語の (arg1, 64bit) disp = {0}、IR の c = {8}、miss = {8}。目的の型。
- `6677a0` (arg2, 64): 機械語 disp = {72,80,88,96}、IR c = {36,72,80,88,96}、miss = {36}。IR の `arg2+36` は `store i64` 3 本のうち 1 本。機械語側の列挙漏れの可能性が高いが、未突合。
- `d237e0` (arg2, 64): miss = {36}。IR の `arg2+36` は `%126 = add i64 %arg2, 36` → `load i64` (`%128`) → `store i64 %128` (`arg1+632` へ書く) で、load 値は捨てられていない。よって「ほぼ誤検出」とは断定せず、未突合として扱う。
- `de1da0` (arg1, 64): miss = {244}。未突合。

判定: **検出信号としては採用しない** (誤検出・列挙漏れ 3 件の突合が未了)。`41a670` は 1 件で拾える。
次に必要なのは、3 件の機械語 (disp 列挙の漏れ・store 先ごとの値) の逆アセンブル突合。これは #1091 (LD-33) の範囲に含める。

再現性:
- 上記 1〜3 は本 fix run で実行した。同じ入力・同じコードで再実行すれば同じ結果になることを確認した (元 run の記録とも一致)。
- `audit_lsf_disp.py` は `python3 -m py_compile` も通る。
- 入力 (`work-m11`) は R2 の旧スナップショットで、`ir_conditions.json` 無し。`ir_sha256` の照合はできない (上記)。

## 3. 再現

機械語 (本 run で実行済み。`fl-win64` の `block00031_PE.bin` が必要。依存は `pip install capstone pefile`):

```
python3 tools/m11/ldfix/disasm_735.py "$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin"
```

IR (`work-m11` が必要。取得は `oc_artifacts: fl-win64 work-m11`。本 run で実行済み):

```
cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot0.lift.ll | grep -n 'store i64 %2'
cd tools/m11/work && awk '/^define .*function_41a670\(/{p=1} p{print} p&&/^}/{exit}' boot_final.ll | grep -n 'store i64 %2'
```

## 4. 検証 (`docs/WORKFLOW.md` §6)

- 検証起点: `1f83c5ee` (`origin/main`)。検証 HEAD は本 fix commit (PR 本文に hash を記載)。
- 本 run の `git status --porcelain=v1 -- tools/m11/ldfix` (commit 直前): `M REPORT_735.md` の 1 件のみ (他担当 WIP 無し)。`disasm_735.py` は `d08d51be` で commit 済み。
- `git diff origin/735-ld13-wrong-value-reuse HEAD -- tools/m11/ldfix`: 変更は `REPORT_735.md` のみ (fix commit)。
- 20MiB 超の blob: `find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` の結果は空 (本 run で確認)。
- REPORT の行数: 82 行 (`wc -l`、250 行以内)。
