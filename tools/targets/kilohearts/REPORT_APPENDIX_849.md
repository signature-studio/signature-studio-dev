# KH-19c (#849) 付録: rip_data 参照先の CFG/XFG dispatch 同定と、呼び先 rax の出所の分類

- 測定 commit (修正前・測定済み): `aa5897d56`。コードを変えた最後の commit は修正 `bea32d40f` (rip 相対 load の分類と暗黙の rax 書き込み)。
- **修正後の 8 条件は未再測定**。素材 `plugins-kilohearts` が本 run に無い (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ)。§2・§3 の値は修正前のもので、§0 の結論は保留。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。作業は repo 外 (`$RUNNER_TEMP` 配下)。4 vCPU。
- 再現 (`tools/targets/kilohearts` で実行): `python3 scripts/rtti_walk.py <core> <work>/rtti_vtables.json` → `callgraph.py <core> <work>/rtti_vtables.json <work>/callgraph.pkl 14` → `vtable_closure.py <core> <work>/callgraph.pkl <work>/rtti_vtables.json <ns> <all|nogui> <out.json>` (8 条件)。出力 JSON の `cfg_dispatch_slots`・`cfg_call_resolution`・`after_cfg_*` が本付録の値。
- 単体テスト: `cd scripts && python3 test_rax_source.py` (capstone の機械語で `rax_source` の分類を固定)。

## 0. 結論

- rip_data の参照先 2 slot (`0x1813a1d38` / `0x1813a1d40`) は、load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` と**一致**した。`call [slot]` は CFG/XFG の dispatch で、呼び先は**直前に rax に入った値**で決まる (参照先の thunk は `jmp rax`)。
- **修正前の結論は保留**。修正前の `rax_source` は `mov rax, qword ptr [rip+X]` (rip 相対 load) も vtable 形 (`vtable_cfg`) に分類していた (単体で `('vtable_cfg', 64)` を再現)。対照 Gain (all) の rip_data 呼び出し 54 件のうち 40 件を「vtable 規則で候補確定」とした §3 の判定は、この分類を含む。修正 `bea32d40f` で rip 相対 load は `rip_load` に分けた。40 件のうち rip 相対 load の件数は、修正後の再測定まで分からない。
- 残りの未確定件数 (対照 Gain・all) も修正前の値。呼び出し戻り値などの追跡は子 issue **#3363 (KH-55)**。
- 確定した slot 側の候補は 0 件 (変わらず)。before / after / after_rip は修正前の全 8 条件で `REPORT_KH19.md` の値と一致した。`rax_source` は `after_cfg` の計算だけに使うため、`after` / `after_rip` は修正の影響を受けない。

## 1. 規則 (`scripts/vtable_closure.py`・#849 の追加分)

1. `cfg_dispatch_slots`: load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` の VA を集める (pefile)。
2. `is_cfg_call`: `call [rip+X]` で X が `cfg_dispatch_slots` に入る site を CFG 経由とする。
3. `rax_source`: 同一関数内で CFG call の直前から逆向きに、rax (eax/ax/al/ah を含む) を書く最後の命令を探す。
   - 暗黙に rax を書く命令 (`cdqe`・`cwde`・`cmpxchg`・`lods*`・`cpuid`・`rdtsc` 等、1 オペランドの `mul`・`imul`・`div`・`idiv`、rax を相手に取る `xchg`・`xadd`) → `other_write:<mn>`。
   - `mov rax, qword ptr [R+d]` (R は rip 以外) → `vtable_cfg` (arg = d)。呼び先は `[R+d]` で、`call [R+d]` と同じ。
   - `mov rax, qword ptr [rip+X]` (rip 相対 load) → `rip_load` (arg = X の参照先 VA)。
   - `lea rax, [rip+F]` で F が関数先頭 → `lea_fn`、それ以外 → `lea_nonfn`。
   - それ以外は `reg_copy` / `other_write:<mn>` (`ror`・`mov` (indexed) 等)。
   - 間に `call` があれば `call_ret` (戻り値。未追跡)。分岐先 (label) を跨げば `label_barrier` (経路が一意でない)。
4. `after_cfg` = 不動点。`vtable_cfg` は vtable 規則 (同 ns の slot `d/8`)、`lea_fn` は F を加える。`after` / `after_rip` の計算は変えていない。

## 2. 実測 (修正前・測定 commit `aa5897d56`・4 vCPU・各 1 回)

| ns | モード | CFG 経由 call | before 関数 / B | after 関数 / B | after_rip 関数 | after_cfg 関数 / B | vtable_cfg | call_ret | reg_copy | other_write:ror | other_write:mov | label | lea_fn |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Snap Heap (micropass) | nogui | 20 | 311 / 97,327 | 1,531 / 722,713 | 1,531 | 1,531 / 722,713 | 8 | 7 | 1 | 2 | 1 | 1 | 0 |
| Snap Heap (micropass) | all | 54 | 311 / 97,327 | 3,094 / 1,388,293 | 3,094 | 3,094 / 1,388,293 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |
| Multipass (multipass) | nogui | 20 | 321 / 113,050 | 1,802 / 817,610 | 1,802 | 1,802 / 817,610 | 8 | 7 | 1 | 2 | 1 | 1 | 0 |
| Multipass (multipass) | all | 54 | 321 / 113,050 | 3,328 / 1,476,922 | 3,328 | 3,328 / 1,476,922 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |
| Phase Plant (phaseplant) | nogui | 56 | 504 / 228,241 | 3,767 / 1,791,711 | 3,767 | 3,767 / 1,791,711 | 41 | 9 | 2 | 2 | 1 | 1 | 0 |
| Phase Plant (phaseplant) | all | 56 | 504 / 228,241 | 5,582 / 2,768,378 | 5,582 | 5,582 / 2,768,378 | 41 | 9 | 2 | 2 | 1 | 1 | 0 |
| 対照 Gain (gain) | nogui | 8 | 160 / 39,357 | 555 / 178,451 | 555 | 555 / 178,451 | 3 | 2 | 0 | 2 | 0 | 1 | 0 |
| 対照 Gain (gain) | all | 54 | 160 / 39,357 | 1,995 / 731,396 | 1,995 | 1,995 / 731,396 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |

- 各行: CFG 経由 call = vtable_cfg + call_ret + reg_copy + other_write:ror + other_write:mov + label + lea_fn (行和で一致)。`CFG 経由 call` 列は `REPORT_KH19.md` §2・§4 の `rip_data` 列と同じ数。
- 修正前の分類には `rip_load` の列が無い。rip 相対 load は `vtable_cfg` 列に含まれていた (修正後は別列)。
- before / after / after_rip は `REPORT_KH19.md` §2・§4 の値と全 8 条件で一致 (修正前)。
- 所要: `vtable_closure.py` 1 回 7.3〜8.8 s (`date` の差)。load average は開始時 0.23、終了時 1.18。

## 3. 判定 (#849 の受入・修正前の値に基づく。再測定まで保留)

- 受入 (rip_data の候補): 修正前は、CFG 経由 call のうち `vtable_cfg` 形を vtable 規則で候補確定とし、閉包に加えた結果 `after_cfg` = `after` (差 0)。全モードで新規の関数は 0 件。
  修正後は rip 相対 load が `vtable_cfg` から `rip_load` へ移るため、この判定は再測定で確定し直す。
- 未確定件数の種別別 (修正前): 対照 Gain・all は 14 件 (call_ret 8・reg_copy 2・other_write:ror 2・label 1・other_write:mov 1)。残りは子 #3363 (KH-55)。他の ns・モードは §2 の列の値から同様に読める。
- 閉包内の既存 vtable 呼び出しの slot 別件数に基づく説明は、再現可能な形でコミットしていない。本付録の判定の根拠には使わない。

## 4. 検証 (コード差分と単体テスト)

- 単体テスト (`scripts/test_rax_source.py`・修正 commit `bea32d40f`): `python3 test_rax_source.py` → 8 件 OK (capstone 5.0.7)。同じテストを修正前の `vtable_closure.py` (`aa5897d56`) に対して実行すると 4 件 FAIL (rip 相対 load・`cdqe`・`mul rcx`・`xchg rax, rcx` の各ケースが誤って `vtable_cfg` になる)。
- コード差分 (測定 commit から HEAD まで): `git diff aa5897d56 HEAD -- tools/targets/kilohearts/scripts` の出力。差分があるため、§2・§3 の値は HEAD の値ではない。

<details>
<summary>git diff aa5897d56 HEAD -- tools/targets/kilohearts/scripts (117 行)</summary>

```diff
diff --git a/tools/targets/kilohearts/scripts/test_rax_source.py b/tools/targets/kilohearts/scripts/test_rax_source.py
new file mode 100644
index 000000000..f87e81478
--- /dev/null
+++ b/tools/targets/kilohearts/scripts/test_rax_source.py
@@ -0,0 +1,63 @@
+#!/usr/bin/env python3
+"""rax_source (vtable_closure.py) の分類を capstone の機械語で固定する回帰テスト (#849)。
+実行: python3 test_rax_source.py (pefile / capstone が必要)。"""
+import unittest
+
+import capstone
+
+import vtable_closure as vc
+
+BASE = 0x140000000
+ADDR = 0x140001000
+MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
+
+
+def classify(code, res=None):
+    ins = list(MD.disasm(code, ADDR))
+    k = next(i for i, x in enumerate(ins) if x.mnemonic == 'call')
+    return vc.rax_source(ins, k, BASE, res or {})
+
+
+CALL_RIP = bytes.fromhex('ff1500000000')  # call [rip+0]
+
+
+class RaxSourceTest(unittest.TestCase):
+    def test_rip_qword_load_is_rip_load_not_vtable(self):
+        # mov rax, qword ptr [rip+0x40]; call [rip+0]
+        kind, arg = classify(bytes.fromhex('488b05' + '40000000') + CALL_RIP)
+        self.assertEqual(kind, 'rip_load')
+        self.assertEqual(arg, ADDR + 7 + 0x40)
+
+    def test_vtable_form_is_vtable_cfg(self):
+        # mov rax, qword ptr [rax+0x18]; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('488b4018') + CALL_RIP), ('vtable_cfg', 0x18))
+
+    def test_cdqe_overwrites_rax(self):
+        # mov rax, qword ptr [rax+0x18]; cdqe; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('488b4018' + '4898') + CALL_RIP), ('other_write:cdqe', None))
+
+    def test_one_operand_mul_overwrites_rax(self):
+        # mov rax, qword ptr [rax+0x18]; mul rcx; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('488b4018' + '48f7e1') + CALL_RIP), ('other_write:mul', None))
+
+    def test_xchg_with_rax_overwrites_rax(self):
+        # mov rax, qword ptr [rax+0x18]; xchg rax, rcx; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('488b4018' + '4891') + CALL_RIP), ('other_write:xchg', None))
+
+    def test_indexed_mov_is_other_write_mov(self):
+        # mov rax, qword ptr [rcx+rdx*8]; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('488b04d1') + CALL_RIP), ('other_write:mov', None))
+
+    def test_reg_copy(self):
+        # mov rax, rcx; call [rip+0]
+        self.assertEqual(classify(bytes.fromhex('4889c8') + CALL_RIP), ('reg_copy', None))
+
+    def test_lea_rip_to_function_head(self):
+        # lea rax, [rip+0x10]; call [rip+0]  (target = ADDR+7+0x10 が res の関数先頭)
+        res = {ADDR + 7 + 0x10 - BASE: {'size': 1, 'calls': [], 'jmps': []}}
+        self.assertEqual(classify(bytes.fromhex('488d05' + '10000000') + CALL_RIP, res),
+                         ('lea_fn', ADDR + 7 + 0x10))
+
+
+if __name__ == '__main__':
+    unittest.main()
diff --git a/tools/targets/kilohearts/scripts/vtable_closure.py b/tools/targets/kilohearts/scripts/vtable_closure.py
index c53a05806..0dd2165f0 100644
--- a/tools/targets/kilohearts/scripts/vtable_closure.py
+++ b/tools/targets/kilohearts/scripts/vtable_closure.py
@@ -146,12 +146,24 @@ def is_cfg_call(insn, cfg_slots):
 
 RAX_NAMES = {'rax', 'eax', 'ax', 'al', 'ah'}
 MEM_BASE_DISP = re.compile(r'qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]')
+IMPLICIT_RAX_WRITE = {'cdqe', 'cwde', 'cbw', 'lahf', 'xlat', 'cmpxchg', 'cmpxchg8b', 'cmpxchg16b',
+                      'lods', 'lodsb', 'lodsw', 'lodsd', 'lodsq', 'cpuid', 'rdtsc', 'rdtscp', 'xgetbv', 'syscall'}
+ONE_OP_RAX_WRITE = {'mul', 'imul', 'div', 'idiv'}
+
+
+def writes_rax_implicitly(w, ops):
+    """オペランドに rax 族を明示せずに rax を書く命令 (cdqe・1 オペランドの mul/div・xchg/xadd の rax 相手 等)。"""
+    if w.mnemonic in IMPLICIT_RAX_WRITE:
+        return True
+    if w.mnemonic in ONE_OP_RAX_WRITE and len(ops) == 1:
+        return True
+    return w.mnemonic in ('xchg', 'xadd') and any(o in RAX_NAMES for o in ops)
 
 
 def rax_source(ins, idx, base, res):
     """guard 経由の call (ins[idx]) の直前で rax に入った値の出所を、同一関数内を逆向きに追う (#849)。
-    戻り値 (kind, arg): vtable_cfg (arg=disp, `mov rax, [R+disp]`) / lea_fn (arg=VA, 関数先頭) / lea_nonfn /
-    rip_load / reg_copy / other_write:<mn> / call_ret / label_barrier / block_end / unresolved。
+    戻り値 (kind, arg): vtable_cfg (arg=disp, `mov rax, [R+disp]`、R は rip 以外) / lea_fn (arg=VA, 関数先頭) / lea_nonfn /
+    rip_load (arg=参照先 VA) / reg_copy / other_write:<mn> (暗黙の書き込みを含む) / call_ret / label_barrier / block_end / unresolved。
     分岐先 (label) を跨ぐ場合は、経路が一意でないため label_barrier とする。"""
     labels = {int(i.op_str, 16) for i in ins if i.mnemonic.startswith('j') and i.op_str.startswith('0x')}
     if ins[idx].address in labels:
@@ -165,11 +177,14 @@ def rax_source(ins, idx, base, res):
             return 'call_ret', None
         if w.mnemonic in ('ret', 'jmp'):
             return 'block_end', None
-        first = w.op_str.split(',')[0].strip()
+        ops = [o.strip() for o in w.op_str.split(',')] if w.op_str else []
+        if writes_rax_implicitly(w, ops):
+            return 'other_write:' + w.mnemonic, None
+        first = ops[0] if ops else ''
         if first in RAX_NAMES and w.mnemonic not in ('cmp', 'test'):
             src = w.op_str.split(',', 1)[1].strip() if ',' in w.op_str else ''
             m = MEM_BASE_DISP.fullmatch(src)
-            if w.mnemonic == 'mov' and m:
+            if w.mnemonic == 'mov' and m and m.group(1) != 'rip':
                 d = m.group(2)
                 return 'vtable_cfg', (0 if d is None else int(d, 16) if d.startswith('0x') else int(d))
             if w.mnemonic == 'lea' and 'rip' in src:
```

</details>

- 再測定 (修正後 8 条件): 未実施 (素材 `plugins-kilohearts` が無い)。PR 本文の `oc_artifacts: plugins-kilohearts` で取得した run で、`rtti_walk.py` → `callgraph.py` → `vtable_closure.py` (8 条件) を実行し、§0・§2・§3 と `REPORT_KH19.md` §4 を更新する。

## 5. 制限

- 閉包の over-approximation (slot 番号一致) は変えていない。`vtable_cfg` の候補も同じ規則なので、型による絞り込みは #848 の結論 (呼び出し鎖の伝播が要る) のまま。
- `rax_source` は同一関数内の直線区間のみ。分岐越えは打ち切る (`label_barrier`)。callee の戻り値 (`call_ret`) は追わない。
- `mov rax, [rsp+d]` / `[rbp+d]` の load も `vtable_cfg` 形として扱う (スタック上の関数ポインタかどうかを区別していない。未検証)。
- `lea_fn` (exact) は 0 件 (修正前)。XFG の hash (`movabs r10`) は呼び先の判定に使っていない。
- 素材は `plugins-kilohearts` のみ (fl-win64 は不要)。lift / build は行っていない (#850・#3063 の範囲)。
