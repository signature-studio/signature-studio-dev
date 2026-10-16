#!/usr/bin/env python3
# #5843 (ICALL-119): 実際にオブジェクトへ書き込まれる vtable (lea reg,[rip+X] の直後の mov [reg],reg) を集め、
# その slot1 (_Destroy)・slot2 (_Delete_this) の関数が r13 を push/pop 無しで書くかを数える。
import re
import struct
import sys

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
    name = b[off:off+8].rstrip(b'\0').decode(errors='replace')
    vsize, va, rawsz, rawptr = struct.unpack_from('<IIII', b, off + 8)
    secs.append((name, va, vsize, rawptr, rawsz))
    off += 40


def read_qword_va(v):
    for name, va, vsize, rawptr, rawsz in secs:
        lo = imagebase + va
        if lo <= v < lo + max(vsize, rawsz):
            o = rawptr + (v - lo)
            return struct.unpack_from('<Q', b, o)[0]
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

LEA = re.compile(r'^lea\s+(r[a-z0-9]+),\[rip\+0x[0-9a-f]+\]\s+# 0x([0-9a-f]+)')
STORE = re.compile(r'^mov\s+QWORD PTR \[(r[a-z0-9]+)\],(r[a-z0-9]+)$')
R13W = re.compile(r'^(?!cmp|test|push|call|jmp|j[a-z]+\b)[a-z0-9]+\s+r13[bwd]?\b')
R13PUSH = re.compile(r'^push\s+r13\b')
R13POP = re.compile(r'^pop\s+r13\b')
R13XCHG = re.compile(r'^xchg\s+.*\br13[bwd]?\b')


def r13_unsaved(s):
    # 本体に push r13 があれば保存済みとして 0 を返す (r13 への書込みが保存を要するのは push r13 が無い関数)
    body = body_of[s]
    if any(R13PUSH.match(t) for _, t in body):
        return 0
    n = 0
    for _, t in body:
        if R13POP.match(t):
            continue
        if R13W.match(t) or R13XCHG.match(t):
            n += 1
    return n


vt_sites = {}
for s, body in funcs:
    for i in range(len(body) - 1):
        m = LEA.match(body[i][1])
        if not m:
            continue
        reg, tgt = m.group(1), int(m.group(2), 16)
        m2 = STORE.match(body[i + 1][1])
        if m2 and m2.group(2) == reg:
            vt_sites.setdefault(tgt, []).append(body[i][0])

targets = {}
for vt, sites in vt_sites.items():
    s1 = read_qword_va(vt + 8)
    s2 = read_qword_va(vt + 16)
    if s1 in starts and s2 in starts:
        targets[vt] = (s1, s2)

slots = set()
for vt, (s1, s2) in targets.items():
    slots.add(s1)
    slots.add(s2)

bad = sorted(s for s in slots if r13_unsaved(s))
print('vtable_targets_stored', len(vt_sites))
print('vtables_with_slot1_slot2_code', len(targets))
print('distinct_slot_functions', len(slots))
print('slot_functions_writing_r13_unsaved', len(bad))
for s in bad[:40]:
    print('  %x writes=%d' % (s, r13_unsaved(s)))
