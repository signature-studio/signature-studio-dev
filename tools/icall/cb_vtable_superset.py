#!/usr/bin/env python3
# #5843 (ICALL-119): control block の vtable の上界。vtable_r13.py は「lea の直後に mov [reg],reg で格納する」形だけを数える。
# ここでは、コード中の任意の `lea reg,[rip+X]` の参照先 X を候補とし、slot1 (_Destroy)・slot2 (_Delete_this) が
# どちらも関数開始のときだけ vtable とみなす。格納の形を問わないので vtable_r13.py の集合の上位集合になる。
# 使い方: python3 tools/icall/cb_vtable_superset.py <SlateCore.core_64> <core64.dsm>
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
R13W = re.compile(r'^(?!cmp|test|push|call|jmp|j[a-z]+\b)[a-z0-9]+\s+r13[bwd]?\b')
R13PUSH = re.compile(r'^push\s+r13\b')
R13POP = re.compile(r'^pop\s+r13\b')
R13XCHG = re.compile(r'^xchg\s+.*\br13[bwd]?\b')
R13SPILL = re.compile(r'^mov\s+QWORD PTR \[rsp[+-]0x[0-9a-f]+\],r13$')

cands = set()
for _, body in funcs:
    for _, text in body:
        m = LEA_ANY.match(text)
        if m:
            cands.add(int(m.group(1), 16))

pairs = {}
for vt in cands:
    s1 = read_qword_va(vt + 8)
    s2 = read_qword_va(vt + 16)
    if s1 in starts and s2 in starts:
        pairs[vt] = (s1, s2)

slots = set()
for s1, s2 in pairs.values():
    slots.add(s1)
    slots.add(s2)


def unsaved(s):
    body = body_of[s]
    if any(R13PUSH.match(t) for _, t in body) or any(R13SPILL.match(t) for _, t in body):
        return 0
    n = 0
    for _, t in body:
        if R13POP.match(t):
            continue
        if R13W.match(t) or R13XCHG.match(t):
            n += 1
    return n


bad = sorted(s for s in slots if unsaved(s))
print('lea_targets', len(cands))
print('vtable_like_both_slots_code', len(pairs))
print('distinct_slot_functions', len(slots))
print('slot_functions_writing_r13_unsaved', len(bad))
for s in bad[:40]:
    print('  %x writes=%d' % (s, unsaved(s)))

writes_any = [s for s in slots if any(R13W.match(t) or R13XCHG.match(t) for _, t in body_of[s] if not R13POP.match(t))]
push_saved = [s for s in writes_any if any(R13PUSH.match(t) for _, t in body_of[s])]
spill_saved = [s for s in writes_any if s not in push_saved and any(R13SPILL.match(t) for _, t in body_of[s])]
print('slot_functions_writing_r13_any', len(writes_any))
print('  with_push_r13', len(push_saved))
print('  with_spill_only', len(spill_saved))
