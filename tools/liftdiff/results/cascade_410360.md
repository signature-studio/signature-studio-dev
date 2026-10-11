# 自動生成: `liftdiff` batch (CAB-238 採点・`cascade_410360` 出力)

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

wasm_trap case 個別化 (f_410360 カスケード) — batch_closure_hybrid.jsonl
trap case 計 941 / 関数 211

分類 (case):
  trap_upstream          528
  trap_direct            246
  trap_direct_other      167

innermost trap frame 上位 (wasm JS trap chain):
  f_410360                   573
  f_412770                   115
  f_415c30                   108
  f_407e20                    45
  f_511fe0                    26
  f_412020                    11
  f_412d60                     9
  f_535d10                     9
  ?                            5
  f_479b40                     5

乖離点の種類 (trap_upstream 内):
  call_arg                 265
  native_extra_call        181
  wasm_extra_call           55
  call_name                 23
  call_ret                   4

乖離内容 上位:
  ('FreeLibrary', ('0x50000000', '0x13a7cc4', '0x13a7bc8', '0x        55
  ('InitializeCriticalSection', ('0x1e3d7c8', '0x0', '0x0', '0        43
  ('InitializeCriticalSection', ('0x1e3d848', '0x0', '0x0', '0        41
  ('GetCurrentThreadId', ('0x1e52e10', '0xffffffff', '0x15e6a3        23
  ('InitializeCriticalSection', ('0x1e3d808', '0x0', '0x0', '0        21
  ('GetCurrentThreadId', ('0x1', '0x0', '0x9', '0x0'), ('0x1',        17
  ('GetModuleFileNameW', ('0x400000', '0x7fffffffd62e', '0x208        16
  ('CreateEventW', ('0x0', '0xffffffff', '0x0', '0x0'), '0x600        12
  ('EnterCriticalSection', 'FreeLibrary')                              9
  ('RegOpenKeyExW', ('0xffffffff80000002', '0x5d1c44', '0x0',          9

f_410360 経由の OOB 地点 (innermost < 呼び出し元) 上位:
  f_410360<481790                    111
  f_410360<40f9e0                    100
  f_410360<5af120                     35
  f_410360<448d40                     25
  f_410360<448ee0                     19
  f_410360<cf2020                     18
  f_410360<534cb0                     18
  f_410360<7978d0                     13

trap 多発 root 関数 上位 (dispatch された VA / case 数):
  0x136b2a0        9  {'trap_direct_other': 9}
  0x1310a30        9  {'trap_direct_other': 9}
  0x12ddf10        9  {'trap_direct_other': 9}
  0x12d83a0        9  {'trap_direct_other': 9}
  0x12c6950        9  {'trap_upstream': 9}
  0x12bf910        9  {'trap_upstream': 9}
  0x1264cb0        9  {'trap_direct': 9}
  0x113cfb0        9  {'trap_direct_other': 9}
  0x10c7850        9  {'trap_direct': 9}
  0x102af10        9  {'trap_upstream': 9}
  0xefba50         9  {'trap_direct_other': 9}
  0xe21de0         9  {'trap_upstream': 9}
