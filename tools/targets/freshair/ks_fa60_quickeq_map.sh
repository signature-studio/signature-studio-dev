#!/usr/bin/env bash
# QuickEq (KH 0x18035fb10 / SC 0x180ac5550) の param 写像を逆アセンブルで検査する (#4976 / FA-60)。判定はしない。
#   usage: bash tools/targets/freshair/ks_fa60_quickeq_map.sh   (素材: work-liftlib-targets を展開済み)
# 検査: 5 組それぞれについて「P の load → 同じ引数 slot (rsp+0x20/0x28/0x30) か xmm2/xmm3 への渡し → 同じ call」を、
#   途中で base (rax) と渡す register が書き換えられていないことまで含めて順に確認する。
# 確認しないこと: 意味ラベル (周波数・Q・フラグ)、呼出先 (0x180362700 / 0x180ad5ce0) の同一性。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
KH="$HERE/../kilohearts/work/winpkg/HeartCore.core_64"
SC="$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$KH" ] && [ -f "$SC" ] || { echo "missing core (work-liftlib-targets を展開する)" >&2; exit 2; }
kh=$(python3 "$HERE/disasm.py" "$KH" 0x18035fb10 1754)
sc=$(python3 "$HERE/disasm.py" "$SC" 0x180ac5550 2090)
python3 - "$kh" "$sc" <<'PY'
import re, sys

def parse(text):
    ins = []
    for ln in text.splitlines():
        m = re.match(r'^([0-9a-f]+): (\S+)\s*(.*)$', ln.strip())
        if m:
            ops = [o.strip() for o in m.group(3).split(',', 1)] if m.group(3) else []
            ins.append((m.group(1), m.group(2), ops))
    return ins

def norm(s):
    return re.sub(r'(dword|qword|xmmword) ptr |\s', '', s)

def writes(ins, reg, lo, hi):
    return any(ins[k][2][:1] == [reg] for k in range(lo + 1, hi))

def check(ins, name, base, mem, reg, slot, target):
    for i, (ia, mn, ops) in enumerate(ins):
        if mn not in ('movss', 'movd') or len(ops) != 2 or ops[0] != reg or norm(ops[1]) != mem:
            continue
        rax_w = [k for k in range(i) if ins[k][2][:1] == ['rax']]
        if not rax_w or ins[rax_w[-1]][1] != 'mov' or norm(ins[rax_w[-1]][2][1]) != base:
            continue
        end = i
        if slot:
            st = [k for k in range(i + 1, len(ins))
                  if ins[k][1] in ('movss', 'movd') and len(ins[k][2]) == 2
                  and norm(ins[k][2][0]) == slot and ins[k][2][1] == reg]
            if not st or writes(ins, reg, i, st[0]):
                continue
            end = st[0]
        calls = [k for k in range(end + 1, len(ins)) if ins[k][1] == 'call']
        if not calls or ins[calls[0]][2][:1] != [target]:
            continue
        if slot:
            if any(norm(ins[k][2][0]) == slot for k in range(end + 1, calls[0]) if len(ins[k][2]) == 2 and ins[k][1] in ('movss', 'movd')):
                continue
        elif writes(ins, reg, i, calls[0]):
            continue
        print(f"OK {name}: load {ia} ({reg}) -> {slot or reg} @{ins[end][0]} -> call {target} @{ins[calls[0]][0]}")
        return
    sys.exit(f"FAIL {name}: load -> slot -> call の連鎖が見つからない")

kh, sc = parse(sys.argv[1]), parse(sys.argv[2])
T_KH, T_SC = '0x180362700', '0x180ad5ce0'
B_KH, B_SC = '[rdx+0x3188]', '[rcx+0x90]'
for name, mem, reg, slot in [
    ('KH P+0', '[rax]', 'xmm4', '[rsp+0x20]'),
    ('KH P+4', '[rax+4]', 'xmm5', '[rsp+0x28]'),
    ('KH P+8', '[rax+8]', 'xmm1', '[rsp+0x30]'),
    ('KH P+0xc', '[rax+0xc]', 'xmm2', None),
    ('KH P+0x10', '[rax+0x10]', 'xmm3', None),
]:
    check(kh, name, B_KH, mem, reg, slot, T_KH)
for name, mem, reg, slot in [
    ('SC 0x9dc4', '[rax+0x9dc4]', 'xmm1', '[rsp+0x20]'),
    ('SC 0x9e0c', '[rax+0x9e0c]', 'xmm0', '[rsp+0x28]'),
    ('SC 0x9e54', '[rax+0x9e54]', 'xmm1', '[rsp+0x30]'),
    ('SC 0x9e9c', '[rax+0x9e9c]', 'xmm2', None),
    ('SC 0x9ee4', '[rax+0x9ee4]', 'xmm3', None),
]:
    check(sc, name, B_SC, mem, reg, slot, T_SC)
print("OK: QuickEq 写像 5 組の機械語の連鎖を確認 (意味ラベル・呼出先の同一性は未確認)")
PY
