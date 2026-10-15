#!/usr/bin/env python3
"""WaveformColouring_CreateInstance の差分テスト (T-SH-52 / #3216)。 usage: wc_diff_test.py <workdir>
  参照 (native): wc_native_ref.c が元の機械語を VA 0x30000000 に敷設し ms_abi で直接実行した結果 (res_native.bin)
  被験 (wasm)  : lift 済み wc.wasm を wc_run_wasm.mjs で実行した結果 (res_wasm.bin)
  case ごとに 戻り値 RAX・import 呼出回数・heap (arena)・.data の全バイトを比較する。native が落ちた case は比較対象外として件数を出す。
  判定: 全 case で一致 かつ 比較対象が 1 件以上 なら exit 0。それ以外は exit 1。"""
import sys, json, struct

W = sys.argv[1]
L = json.load(open(f"{W}/layout.json"))
ARENA_SZ, DATA_SZ = L["arena_sz"], L["data_sz"]
REC = 16 + ARENA_SZ + DATA_SZ
CRASH = 0xC2A5C2A5C2A5C2A5
nat = open(f"{W}/res_native.bin", "rb").read()
wsm = open(f"{W}/res_wasm.bin", "rb").read()
n = len(nat) // REC
assert len(nat) == len(wsm) == n * REC, f"size mismatch native={len(nat)} wasm={len(wsm)} rec={REC}"
ok = bad = excl = 0
first = []
for c in range(n):
    a = nat[c * REC:(c + 1) * REC]
    b = wsm[c * REC:(c + 1) * REC]
    if struct.unpack_from("<Q", a, 8)[0] == CRASH:
        excl += 1
        continue
    if a == b:
        ok += 1
        continue
    bad += 1
    fields = []
    if a[:8] != b[:8]: fields.append("rax")
    if a[8:16] != b[8:16]: fields.append("hits")
    ar = a[16:16 + ARENA_SZ]; br = b[16:16 + ARENA_SZ]
    if ar != br:
        off = next(i for i in range(ARENA_SZ) if ar[i] != br[i]); fields.append(f"arena@+0x{off:x}")
    dr = a[16 + ARENA_SZ:]; er = b[16 + ARENA_SZ:]
    if dr != er:
        off = next(i for i in range(DATA_SZ) if dr[i] != er[i]); fields.append(f".data@+0x{off:x}")
    first.append(f"case {c}: " + ", ".join(fields))
print(f"[wc diff] cases={n} PASS={ok} FAIL={bad} excluded(native crash)={excl}")
for line in first[:10]:
    print("  " + line)
sys.exit(0 if bad == 0 and ok >= 1 else 1)
