> **正本**: `tools/ott/REPORT.md` §15 (結論 1 行)。本付録は #1200 の詳細と実測 (旧 REPORT §15 を分割移動。内容は削除していない)。

# #1200 — 画像 base の相対化 (OTT_RELOC=1, 親 #989 / 子 #1201)

## 結論

- **既定 base (0x30000000) での同一性のみ確認**。相対化の実証 (別 base・複数インスタンス N=16) は未実施 → #1200 に残す。
- 測定 commit: **`b5d7663c`** (コードを変えた最後の commit。main `63ed695b` を取り込んだ merge)。以下の実測値はすべてこの commit で取った。
- 現 HEAD までのコード差分 (`tools/ott` の REPORT 系を除く) は空 (下記 §実測 の確認)。

## 実装

- `lift/x64c.py` の `OTT_RELOC=1` で画像 VA 定数を `(ott_gbase + RVA)` で出力。`OTT_RELOC=1` と `OTT_VEXCOV=1` は fail-fast (VEXCOV の shifted VA 定数は相対化未対応)。
  `rt/ott_glue.c` に `ott_gbase` (既定 0x30000000) と `ott_set_gbase`。`crtinit/ott_crt.c` は cookie・api-set 表・encoded slot・`__FlsIndex`・trampoline 番地を RVA + `ott_gbase` で持つ。
- 既定 lift (`OTT_RELOC` 未設定): 生成 `ott_lifted.c` / `ott_data.c` が main `490f4313` の lift 出力と byte 一致 (`cmp`)。

## 実測 (測定 commit `b5d7663c`)

素材: `analysis-ott-binaries` / `toolchain-emsdk` (`$HOME/analysis` / `/opt/emsdk` に展開済み、[EMSDK] 参照)。直列実行。load average は `uptime` の 1 分値 (開始 → 終了)。

| 実行 | 結果 | real | 内容 |
|---|---|---|---|
| `bash tools/ott/ott_e2e.sh` (既定) | PASS | 25.32 s | scenario 89 / cells 50236 / bit-equal 50236 / max_ulp 0 / state_diff_qwords 0。load 0.79 → 0.98 |
| `OTT_RELOC=1 bash tools/ott/ott_e2e.sh` (相対化) | PASS | 235.30 s (3 m 55 s) | scenario 89 / cells 50236 / bit-equal 50236 / max_ulp 0 / state_diff_qwords 0。load 0.90 → 1.90 |
| lift 既定 (`lift/lift_build.sh`) | OK | 6.07 s | `functions 75, insns 5790, unsup {}`。SIG_ONLY `sig=6b1696f0` (nonzeroOut 256) |
| lift 相対化 (`OTT_RELOC=1`) | OK | — | `functions 75, insns 5790, unsup {}`。`ott_lifted.c` の `ott_gbase` 出現 807 箇所 (776 行)。SIG_ONLY `sig=6b1696f0` (nonzeroOut 256) |
| 既定 lift vs main `490f4313` の lift | 一致 | — | `ott_lifted.c` / `ott_data.c` とも `cmp` 一致 |

SIG_ONLY は `node tools/perf/harness/ott_x64c_bench.mjs <ottl.cjs>` (`SIG_ONLY=1`)、N=1、gbase 既定値。

### コード差分 (測定 commit から)

前版 (`110d65e7`) から測定 commit `b5d7663c` までの `tools/ott` のコード差分 (`git diff 110d65e7 b5d7663c -- tools/ott ":!tools/ott/REPORT.md"` の出力。REPORT.md は除く):

```diff
diff --git a/tools/ott/lift/verify_ia32_jt.py b/tools/ott/lift/verify_ia32_jt.py
new file mode 100644
index 00000000..ce2a6543
--- /dev/null
+++ b/tools/ott/lift/verify_ia32_jt.py
@@ -0,0 +1,30 @@
+# verify_ia32_jt.py: ia32 jump table (Slayer_Engine.dll 0x10001310) の lift 出力 case 集合を PE の表データと突き合わせる (#1117)。
+# 使い方: FL_PE=<block22434_PE.bin> python3 verify_ia32_jt.py <ott_lifted.c> [neg]
+import pefile, re, sys, struct
+import os
+P=os.environ['FL_PE']
+C=sys.argv[1]; NEG=len(sys.argv)>2
+pe=pefile.PE(P); IMG=pe.OPTIONAL_HEADER.ImageBase
+def rva_bytes(va,n):
+    rva=va-IMG
+    for s in pe.sections:
+        if s.VirtualAddress<=rva<s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData):
+            off=s.PointerToRawData+(rva-s.VirtualAddress)
+            return pe.__data__[off:off+n]
+    raise SystemExit('no section')
+TBL=0x100014a4; N=25  # cmp eax,0x18 (ja 0x1000149c) → 有効 index 0..24
+raw=[struct.unpack('<I',rva_bytes(TBL+4*k,4))[0] for k in range(N)]
+if NEG: raw[7]^=0x10   # ネガコン: 表の 1 エントリを故意に壊す
+src=open(C).read()
+m=re.search(r'switch \(LD32\(\(R\[0\]\*4 \+ 0x100014a4ULL\)\)\) \{ (.*?) default', src, re.S)
+if m is None: raise SystemExit('[jt] FAIL: switch not found')
+cases=re.findall(r'case (0x[0-9a-f]+)ULL: goto (L_[0-9a-f]+);', m.group(1))
+case_vals={int(c,16):l for c,l in cases}
+# 各 case の遷移先ラベルが実在し、そのラベルの VA が case 値と一致する
+label_ok=all(re.search(r'\n%s:;' % l, src) and int(l[2:],16)==v for v,l in case_vals.items())
+tbl_set=set(raw)
+print('[jt] switch cases %d, PE table entries %d (idx 0..%d @ 0x%x)' % (len(case_vals), N, N-1, TBL))
+if not label_ok or set(case_vals)!=tbl_set:
+    print('[jt] FAIL: only-in-C %s, only-in-PE %s' % (sorted(hex(x) for x in set(case_vals)-tbl_set), sorted(hex(x) for x in tbl_set-set(case_vals))))
+    sys.exit(1)
+print('[jt] OK: case 値集合 == PE jump table 実データ (%d B)' % (4*N))
diff --git a/tools/ott/lift/x64c.py b/tools/ott/lift/x64c.py
index 9e1b32f6..7693c4c0 100644
--- a/tools/ott/lift/x64c.py
+++ b/tools/ott/lift/x64c.py
@@ -178,7 +178,7 @@ class FnLift:
                                 self.tail.add(va)       # 他関数への tail call
                             else:
                                 self.targets.add(t); work.append(t)
-                        elif op.type == X86_OP_REG:
+                        elif op.type == X86_OP_REG or (IA32 and op.type == X86_OP_MEM and op.mem.index != 0):
                             tg = self.jump_table(va, ins)
                             if tg:
                                 self.jtabs[va] = tg
@@ -201,6 +201,10 @@ class FnLift:
         """MSVC 形式 jump table: ... mov eY,[rX+rIdx*4+tbl]; add rY,rX; jmp rY (tbl = image RVA)"""
         cand = sorted([x for x in self.insns if x < va], reverse=True)[:24]
         tbl = None; n = None
+        if ins.operands[0].type == X86_OP_MEM:   # ia32: jmp dword ptr [idx*4+tbl] (tbl は絶対 VA)
+            m = ins.operands[0].mem
+            if m.scale == 4 and m.index != 0 and m.base == 0 and m.disp:
+                tbl = m.disp & 0xffffffff
         for x in cand:
             i = self.insns[x]
             if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM:
```

現 HEAD までの差分: `git diff b5d7663c HEAD -- tools/ott ':!tools/ott/REPORT.md' ':!tools/ott/REPORT_APPENDIX_1200.md'` は空。

## 受入条件の状態

| 条件 | 状態 | 根拠 |
|---|---|---|
| 既定モードの生成 C・wasm の署名が変わらない | 達成 (b5d7663c で確認) | 既定 lift の `ott_lifted.c` / `ott_data.c` が main `490f4313` と `cmp` で byte 一致。署名 `6b1696f0`。e2e PASS |
| 相対化モードの lift で署名 `6b1696f0` (N=1, gbase 既定値 0x30000000) | 既定 base での同一性確認 (b5d7663c) | `OTT_RELOC=1` lift → SIG_ONLY `sig=6b1696f0`。**gbase を変えていないため、相対化そのものは実証していない** |
| 相対化モードで N=16 (複数インスタンス・別 base) も `6b1696f0` | **未達 (#1200 に残す)** | 未実施。別 base の敷設・`ott_set_gbase` 経路は本 PR で一度も検証していない |

## 未実施・未解決 (起票先)

- N=16 の複数インスタンス署名確認 (別 base 敷設・`ott_set_gbase` 経路の実証) → #1200 に残す (本 PR は `Refs`)。
- crtinit の chain (cookie・trampoline) を通す e2e → 未実施 (#1200 に残す)。lift・署名の範囲のみ。
- 相対化の CPU コスト・SIDE_MODULE PIC 税 → #1201 (起票済み・既存)。

## 前版 (参考。現行の値ではない)

- 測定 commit `110d65e7` (main 取り込み前。`x64c.py` の ia32 jump table 変更を含まない): 既定 lift real 6.3 s、相対化 lift real 3 m 36 s、load 1.08、`ott_gbase` 807 箇所、署名 `6b1696f0`。
- 測定 commit `80cd4a2a`: 既定 lift real 6.8 s、相対化の `ott_gbase` 参照 776 箇所、署名 `6b1696f0`。
- 110d65e7 の指摘対応 (VEXCOV+RELOC の fail-fast、`ott_crt.c` の絶対番地の gbase 相対化、`ott_cpu.c` の unlifted 診断) は、上記 b5d7663c の測定に含まれる。

## 付録 A: 旧 REPORT §15 全文 (測定 commit 110d65e7 時点・内容は削除せず移動)

### A. #1200 — 画像 base の相対化 (OTT_RELOC=1, 親 #989 / 子 #1201)

- 結論: **既定 base (0x30000000) での同一性のみ確認**。相対化の実証 (別 base・複数インスタンス N=16) は未実施 → #1200 に残す。
- 実装: `lift/x64c.py` の `OTT_RELOC=1` で画像 VA 定数を `(ott_gbase + RVA)` で出力。`OTT_RELOC=1` と `OTT_VEXCOV=1` は fail-fast (VEXCOV の shifted VA 定数は相対化未対応)。
  `rt/ott_glue.c` に `ott_gbase` (既定 0x30000000) と `ott_set_gbase`。`crtinit/ott_crt.c` は cookie・api-set 表・encoded slot・`__FlsIndex`・trampoline 番地を RVA + `ott_gbase` で持つ。
- 既定 lift (`OTT_RELOC` 未設定): 生成 `ott_lifted.c` / `ott_data.c` が main 版 (558b47b0) と byte 一致 (`cmp`)。
- 測定 commit: **110d65e7** (素材 `analysis-ott-binaries` + `toolchain-emsdk` 展開、node 22.23.3 / emsdk node 24.19.0 は SIG_ONLY の実行)。
  - 既定 lift: real 6.3 s、`functions 75, insns 5790, unsup {}`。
  - 相対化 lift (`OTT_RELOC=1`): real 3 m 36 s、`functions 75, insns 5790, unsup {}`、`ott_lifted.c` の `ott_gbase` 参照 807 箇所。
  - main 558b47b0 の既定 lift: real 6.1 s、`ott_lifted.c` / `ott_data.c` とも既定 lift と `cmp` 一致。
  - 署名 (SIG_ONLY, N=1, gbase 既定値): 既定 `6b1696f0` / 相対化 `6b1696f0` / main `6b1696f0`。nonzeroOut 256。
  - 負荷: load average 1.08 (1 分値)、直列実行。
- 前版 (80cd4a2a): 既定 6.8 s、相対化の `ott_gbase` 参照 776 箇所、署名は同じ `6b1696f0`。110d65e7 で `x64c.py` / `ott_crt.c` / `ott_cpu.c` が変わったため、以後はこちらを正とする。
- 110d65e7 の指摘対応 (VEXCOV+RELOC の fail-fast、`ott_crt.c` の絶対番地の gbase 相対化、`ott_cpu.c` の unlifted 診断) は上記測定に含まれる。
  ただし crtinit の chain (cookie・trampoline) の e2e 実行は未実施 (lift・署名の範囲のみ)。
- 未達: N=16 / 別 base での `ott_set_gbase` 経路 → #1200 に残す。相対化の CPU コスト・SIDE_MODULE PIC 税 → #1201。
