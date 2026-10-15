# REPORT_4204 — 5cb210 `5cb4aa` の call 戻り値の別名判定 (LD-204 / 親 #4166)

## 1. 結論

`5cb4aa` の判定は **UNDETERMINED (BARRIER(ALIAS_FRAME_PTR), 根: `5cb47d`)** のまま。DROP にも LIVE-IN にもしない。
受入 3 (示せない) に該当する。理由は 2 つ (§4):

1. `call 0x409410` の戻り値 `rax` は、間接 call 先 `407a50` の戻り値に依存する。`407a50` の戻り値が frame を指さないことを示すには、5 個の呼出し先まで解析が必要。
2. `5cb210` は frame アドレスの自己保存 (`5cb21e mov qword ptr [rbp+0x68], rbp`) を含み、関数全体が glk (漏出あり) になる。`5cb4aa` の読みは `5cb47d mov dword ptr [rax+8], ecx` の store で `ALIAS_FRAME_PTR` により打ち切られる (#3225 (LD-150) の範囲)。

判定器 `audit_frame_store_alias_2211.py` の規則は本 PR では変えていない。ただし、測定 commit `0607eacb1` の後に #4090 (`b1b8aee45`) で判定器が変わっており、現 HEAD の判定器で測定し直した (§2・§5)。

## 2. 測定条件

- 測定 commit: `12c1e804f` (判定器 `audit_frame_store_alias_2211.py` の blob `99ddc743ec00`・#4090 の `b1b8aee45` を含む)。作業ツリーは `12c1e804f` と同一 (`tools/m11/ldfix` に未コミット変更なし)。結果 JSON はこの判定器で生成した。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211・#4166 と同じ)。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 判定器: 対照 0.27 秒・`--negctl-glk` 0.26 秒・`--negctl-nosync` 0.27 秒 (いずれも rc 0)。load average 0.21 (4 vCPU)。
- 対照の出力は `results/frame_store_verdict_4090.json` と **byte 一致** (`cmp`) した。現 HEAD の判定器の出力と #4090 の結果は一致する。
- 旧測定 (`0607eacb1` の判定器) の値は §5 に併記しない (現 HEAD の判定器と比べられないため撤回)。

## 3. 機械語の追跡 (受入 1)

| 段 | 機械語 | 結果 |
|---|---|---|
| 0 | `5cb3d3 call 0x409410` → `5cb3d8 mov [rbp+0x148], rax` → `5cb43c mov rdi, [rbp+0x148]` → `5cb456 movsq [rdi], [rsi]` (LEAK_STORE 打ち切り) | `5cb4aa` の読みは `5cb456` で止まる。`rdi` が frame を指すかが問題 |
| 1 | `409410`: `test rcx,rcx; jg 40941e`。`40941a xor ebx,ebx` か `40941e call qword ptr [rip+0xf9c86c]`。`mov rbx,rax`・`test rbx,rbx`・`jne`・`mov rax,rbx`・`ret` | 戻り値 `rax` = `rbx`。`rbx` は 0 か、間接 call の戻り値。`40942c call 0x409730` (cl=1) は `rbx` = 0 の経路だけで、戻り値に影響しない |
| 2 | 間接 call の slot `RVA 0xfa5c90` (`.data`) | import directory に対応無し。静的初期値は `0x407a50`。全 57816 関数の rip 相対参照を走査し、書き込みは見つからなかった。参照は call 3 箇所のみ (`409410`・`409470`・`41c250`) |
| 3 | 直接 call 先 `407a50` (243 命令。`lock cmpxchg` を含むアロケータ形) | 戻り値 `rax` の生成は `mov rax,[rdx+0x18]`・`mov eax,0x100`・`lea rax,[rip+...]`・`call 0x4073e0/0x4074d0/0x407570/0x407680/0x407770`・`mov rax,rsi`・`xor rax,rax` など。`frame_derived` の F は rbp/rsp だけ |
| 4 | `407a50` の呼出し先 5 個 (`4073e0`・`4074d0`・`407570`・`407680`・`407770`) | この run では解析しなかった。戻り値の由来を閉じるには、これらの戻り値規則まで広げる必要がある (#4238) |

段 2 の走査は `ldmach.Machine` で `.pdata` の関数境界を使い、rip 相対の実効アドレスを比べた。

## 4. 判定の理由 (受入 2・3)

1. **戻り値の規則が閉じない**: 判定器の現行規則は「戻り値は rax のみ」「call は ENTRY_AFTER_CALL の印を付けるだけ」。`409410` の戻り値を frame 非派生と示すには `407a50` の戻り値を示し、その中の 5 個の呼出し先の戻り値まで辿る必要がある。
2. **漏出 store が残る**: `5cb210` は `frame_derived` の F への漏出を複数持つ。現判定器 (#4090 の `lea` 規則込み) の先頭 8 件 (`fn_info.5cb210.leaks`) は次のとおり。
   - `5cb21e mov [rbp+0x68], rbp` (frame アドレスの自己保存・STORE_PTR)
   - `5cb222`・`5cb229`・`5cb230`・`5cb237`・`5cb245` (引数・rax の rbp+0x180 以降への保存・STORE_PTR)
   - `5cb2bc call 0x5cab10`・`5cb2e8 call 0x424280` (引数レジスタが F・CALL_ARG)

   前回の記述「漏出は `5cb21e` の 1 箇所だけ」は現判定器では成り立たない (撤回)。ただし、どの漏出も `5cb210` を glk にする点は同じ。`5cb4aa` の読みを止めるのは `5cb47d` の store (§5 の `barrier_addrs`) で、理由は `ALIAS_FRAME_PTR`。

## 5. ネガティブコントロール (受入 4)

| 条件 | 関数 DROP / LIVE-IN / UNDETERMINED | site DROP / LIVE-IN / UNDETERMINED / PTR_READ | 結果 JSON |
|---|---|---|---|
| 対照 (規則変更なし) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | `results/frame_store_alias_4204.json` |
| `--negctl-glk` (全関数の漏出を True) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | `results/negctl_alias_4204_glk.json` |
| `--negctl-nosync` (区間 sync 無効) | 3 / 1 / 44 | 3 / 1 / 46 / 1 | `results/negctl_alias_4204_nosync.json` |

**ネガコンは対照と区別できない。** 3 条件は関数・site の判定が全件一致する (関数 verdict の差 0、site の差 0)。理由:

- 対照の時点で **45/48 関数が既に glk=True** (#4090 の `lea` 規則で F が広がったため)。`--negctl-glk` が変えるのは残り 3 関数だけ (`412160`・`6ca580`・`6ca6c0`)。
- その 3 関数の判定は glk に依存しない。`412160` は LIVE-IN (`NO_DEF_ON_ANY_PATH`)、`6ca580`・`6ca6c0` は `BARRIER(ALIAS_FRAME_PTR)` で、どちらも glk の値では変わらない。
- `--negctl-nosync` も判定を 1 件も変えない (rsp/rbp 同一視の区間が、対照の 48 関数の判定に効いていない)。

したがって、本 PR の測定では「漏出規則が効いていること」「sync 規則が効いていること」を示せていない。前回の「ネガコンは `negctl_alias_2211_glk.json` と一致し、漏出規則が効いていることを再確認した」は、現判定器では根拠にならない (撤回)。区別できるネガコン (対照で glk=True の関数を glk=False に落とす条件など) は、判定器の規則を広げる作業 (#4238) で設計する。

対照の `5cb210` は `5cb4aa` が `BARRIER:ALIAS_FRAME_PTR` (`5cb47d`) で、判定は UNDETERMINED。HEAD でも UNDETERMINED のままで、漏出の根 (`5cb21e`) は変わらない。

## 6. 差分 (WORKFLOW §6)

- 測定 commit: `12c1e804f`。
- 測定 commit から HEAD までの `tools/m11/ldfix` の差分 (`git diff 0607eacb1 12c1e804f -- tools/m11/ldfix --stat`):

```
 tools/m11/ldfix/REPORT_2211.md                     |   59 +
 tools/m11/ldfix/REPORT_3382.md                     |   79 +
 tools/m11/ldfix/REPORT_3418.md                     |   75 +
 tools/m11/ldfix/REPORT_4204.md                     |   57 +
 tools/m11/ldfix/audit_frame_store_alias_2211.py    |   24 +-
 tools/m11/ldfix/fix_site_3418.py                   |  117 ++
 tools/m11/ldfix/judge_copy_3382.py                 |  119 ++
 tools/m11/ldfix/ldfix_e2e.sh                       |    3 +
 .../ldfix/results/frame_store_verdict_4090.json    | 1857 ++++++++++++++++++++
 9 files changed, 2380 insertions(+), 10 deletions(-)
```

- 判定器の差分 (`git diff 0607eacb1 12c1e804f -- tools/m11/ldfix/audit_frame_store_alias_2211.py`)。この差分は測定結果に効く (`lea` 派生を F に入れ、`leak_site` を `leak_sites` に変えた):

```diff
diff --git a/tools/m11/ldfix/audit_frame_store_alias_2211.py b/tools/m11/ldfix/audit_frame_store_alias_2211.py
index af3b696de..99ddc743e 100644
--- a/tools/m11/ldfix/audit_frame_store_alias_2211.py
+++ b/tools/m11/ldfix/audit_frame_store_alias_2211.py
@@ -71,7 +71,9 @@ def frame_derived(cs, seq):
         changed = False
         for ins in seq:
             ops = ins.operands
-            if not ops or ops[0].type != capstone.CS_OP_REG or not writes_dst(ins.mnemonic):
+            if not ops or ops[0].type != capstone.CS_OP_REG:
+                continue
+            if not (writes_dst(ins.mnemonic) or ins.mnemonic.startswith('lea')):
                 continue
             dst = rname(cs, ops[0].reg)
             if dst is None or dst in F:
@@ -89,24 +91,25 @@ def frame_derived(cs, seq):
     return F
 
 
-def leak_site(cs, seq, F):
-    """漏出の最初の命令 (addr, 理由) を返す。無ければ None。"""
+def leak_sites(cs, seq, F):
+    """漏出の命令 (addr, 理由) を全て返す (順序は命令順)。無ければ空リスト。"""
+    out = []
     for ins in seq:
         ops = ins.operands
         m = ins.mnemonic
         a = '%x %s %s' % (ins.address, m, ins.op_str)
         if m.startswith('call'):
             if any(r in F for r in ARG_REGS):
-                return a, 'CALL_ARG'
+                out.append((a, 'CALL_ARG'))
             continue
         if m.startswith('ret'):
             if 'rax' in F:
-                return a, 'RET_PTR'
+                out.append((a, 'RET_PTR'))
             continue
         if ops and ops[0].type == capstone.CS_OP_MEM and writes_dst(m):
             if any(op.type == capstone.CS_OP_REG and rname(cs, op.reg) in F for op in ops[1:]):
-                return a, 'STORE_PTR'
-    return None
+                out.append((a, 'STORE_PTR'))
+    return out
 
 
 NO_SYNC = False
@@ -255,11 +258,12 @@ def main():
         esc = v1.frame_escaped(mach.cs, seq)
         preds, ijmp = v1.build_preds(mach.cs, seq, va, ent[1])
         F = frame_derived(mach.cs, seq)
-        leak = leak_site(mach.cs, seq, F)
-        glk = (leak is not None) or force_glk
+        leaks = leak_sites(mach.cs, seq, F)
+        glk = bool(leaks) or force_glk
         sync = sync_range(mach.cs, seq)
         fn_info[fn] = dict(escaped=esc, ijmp=ijmp, n_ins=len(seq), glk=glk,
-                           leak=None if leak is None else '%s [%s]' % leak,
+                           leak=None if not leaks else '%s [%s]' % leaks[0],
+                           leaks=['%s [%s]' % x for x in leaks[:8]],
                            derived=sorted(F - set(FRAME_REGS)),
                            sync=None if sync is None else '%x-%x' % sync)
         idx_of = {x.address: i for i, x in enumerate(seq)}
```

- `tools/m11/ldfix` の変更は本 REPORT だけではない (上の stat の 9 ファイル)。旧 REPORT の「本 REPORT のみ」は誤り (撤回)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出し先 `407a50` と 5 個 (`4073e0`・`4074d0`・`407570`・`407680`・`407770`) の戻り値規則 | `409410` の戻り値が frame 非派生と示せず、`5cb4aa` の判定が閉じない | #4238 [LD-205] |
| 漏出 store `5cb47d` (`ALIAS_FRAME_PTR`・frame 自己保存 `5cb21e` などが根) | 関数 5cb210 が glk のまま `5cb4aa` が UNDETERMINED | #3225 [LD-150] |
| 区別できるネガコンが無い (§5。対照と全件一致) | 漏出規則・sync 規則が効いていることを本 PR では示せない | #4238 の範囲で設計 (起票先未定) |
