#!/usr/bin/env python3
# #5843 (ICALL-119): cb_vtable_superset.py の slot 関数のうち r13 を書く関数について、
# 全 ret 経路で push r13 (または mov [rsp±X],r13 の退避) が pop r13 (または mov r13,[rsp±X]) で戻るかを
# 分岐を辿る経路解析で数える。rsp の再配置は扱わず、保存の個数の釣り合いだけを見る。
# 使い方: python3 tools/icall/ret_r13_check.py <SlateCore.core_64> <core64.dsm>
import re
import struct
import sys
from collections import deque

if len(sys.argv) != 3:
    sys.exit('usage: ret_r13_check.py <SlateCore.core_64> <core64.dsm>')
PE, DSM = sys.argv[1], sys.argv[2]
b = open(PE, 'rb').read()
pe = struct.unpack_from('<I', b, 0x3c)[0]
nsec = struct.unpack_from('<H', b, pe + 6)[0]
optsz = struct.unpack_from('<H', b, pe + 20)[0]
opt = pe + 24
imagebase = struct.unpack_from('<Q', b, opt + 24)[0]
secs = []
off = opt + optsz
for _ in range(nsec):
    vsize, va, rawsz, rawptr = struct.unpack_from('<IIII', b, off + 8)
    secs.append((va, vsize, rawptr, rawsz))
    off += 40


def read_qword_va(v):
    for va, vsize, rawptr, rawsz in secs:
        lo = imagebase + va
        if lo <= v < lo + max(vsize, rawsz):
            return struct.unpack_from('<Q', b, rawptr + (v - lo))[0]
    return None


LINE = re.compile(r'^\s*([0-9a-f]+):\t(?:[0-9a-f]{2} ?)+\s+(.*)$')
funcs = []
cur = None
after_ret = False
in_pad = False
with open(DSM) as f:
    for raw in f:
        m = LINE.match(raw.rstrip('\n'))
        if not m:
            continue
        addr, text = int(m.group(1), 16), m.group(2).strip()
        is_pad = text.startswith('int3')
        if is_pad and after_ret:
            in_pad = True
            continue
        if cur is None or (in_pad and not is_pad):
            cur = (addr, [])
            funcs.append(cur)
            in_pad = False
        cur[1].append((addr, text))
        after_ret = text.startswith('ret')
starts = {s for s, _ in funcs}
body_of = {s: body for s, body in funcs}

LEA_ANY = re.compile(r'^lea\s+r[a-z0-9]+,\[rip\+0x[0-9a-f]+\]\s+# 0x([0-9a-f]+)')
cands = set()
for _, body in funcs:
    for _, text in body:
        m = LEA_ANY.match(text)
        if m:
            cands.add(int(m.group(1), 16))
slots = set()
for vt in cands:
    s1 = read_qword_va(vt + 8)
    s2 = read_qword_va(vt + 16)
    if s1 in starts and s2 in starts:
        slots.add(s1)
        slots.add(s2)

R13W = re.compile(r'^(?!cmp|test|push|call|jmp|pop|j[a-z]+\b)[a-z0-9]+\s+r13[bwd]?\b')
R13XCHG = re.compile(r'^xchg\s+.*\br13[bwd]?\b')
SAVE = re.compile(r'^push\s+r13$')
RESTORE_POP = re.compile(r'^pop\s+r13$')
RESTORE_MOV = re.compile(r'(?!)')
JCC = re.compile(r'^j[a-z]+\s+0x([0-9a-f]+)')
JMP = re.compile(r'^jmp\s+0x([0-9a-f]+)')
MAXD = 8
unresolved = set()


def check(s):
    body = body_of[s]
    idx = {a: i for i, (a, _) in enumerate(body)}
    seen = set()
    q = deque([(0, 0)])
    rets = 0
    bad = []
    while q:
        i, d = q.popleft()
        if i >= len(body) or (i, d) in seen:
            continue
        seen.add((i, d))
        a, t = body[i]
        m = SAVE.match(t)
        if m:
            d = min(d + 1, MAXD)
        elif RESTORE_POP.match(t):
            d -= 1
            if d < 0:
                bad.append(('restore_without_save', a))
                d = 0
        if t.startswith('ud2') or t.startswith('int3'):
            continue
        if t.startswith('ret'):
            rets += 1
            if d != 0:
                bad.append(('ret_unbalanced', a))
            continue
        m = JMP.match(t)
        if m:
            tgt = int(m.group(1), 16)
            if tgt in idx:
                q.append((idx[tgt], d))
            elif d != 0:
                bad.append(('tail_jmp_unbalanced', a))
            continue
        if re.search(r'\bjmp\s+(?!0x)', t):
            unresolved.add(s)
            continue
        m = JCC.match(t)
        if m:
            tgt = int(m.group(1), 16)
            if tgt in idx:
                q.append((idx[tgt], d))
        q.append((i + 1, d))
    return rets, bad


writers = sorted(s for s in slots
                 if any((R13W.match(t) or R13XCHG.match(t)) and not RESTORE_MOV.match(t)
                        for _, t in body_of[s]))
total_rets = 0
bad_funcs = []
for s in writers:
    rets, bad = check(s)
    total_rets += rets
    if bad:
        bad_funcs.append((s, bad))
print('slot_functions', len(slots))
print('r13_writing_slot_functions', len(writers))
print('ret_paths_checked', total_rets)
print('functions_with_unbalanced_path', len(bad_funcs))
for s, bad in bad_funcs[:40]:
    print('  %x %s' % (s, bad[:3]))
print('functions_with_indirect_jmp_unresolved', len([s for s in writers if s in unresolved]))
print('functions_balanced_without_indirect_jmp', len([s for s in writers if s not in unresolved and not any(s == b for b, _ in bad_funcs)]))
