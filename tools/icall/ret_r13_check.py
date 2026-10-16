#!/usr/bin/env python3
# #5843 (ICALL-119): cb_vtable_superset.py の slot 関数のうち r13 を書く関数について、
# 全 ret 経路の保存状態を分岐を辿る経路解析で分類する。rsp の再配置は扱わない。
# 分類 (排他・上から順に判定):
#   unbalanced         : 釣り合わない経路がある (push r13 の個数と pop r13 の個数が ret で合わない)
#   unresolved_indirect: 間接 jmp を含み、全 ret 経路が閉じない (未確認)
#   write_without_save : push r13 が関数本体に無いのに r13 を書く (保存の欠落)
#   write_before_save  : 保存あり・釣り合うが、r13 を書いてから push する経路がある
#   saved_balanced     : 保存あり・全 ret で釣り合い・全経路で保存が最初の書込みより前
# 使い方: python3 tools/icall/ret_r13_check.py <SlateCore.core_64> <core64.dsm>
#         python3 tools/icall/ret_r13_check.py --selftest
import re
import struct
import sys
from collections import Counter, deque

R13W = re.compile(r'^(?!cmp|test|push|call|jmp|pop|j[a-z]+\b)[a-z0-9]+\s+r13[bwd]?\b')
R13XCHG = re.compile(r'^xchg\s+.*\br13[bwd]?\b')
SAVE = re.compile(r'^push\s+r13$')
RESTORE_POP = re.compile(r'^pop\s+r13$')
SPILL = re.compile(r'^mov\s+QWORD PTR \[[^\]]*\],r13$')
JCC = re.compile(r'^j[a-z]+\s+0x([0-9a-f]+)')
JMP = re.compile(r'^jmp\s+0x([0-9a-f]+)')
MAXD = 8


def writes_r13(t):
    return bool(R13W.match(t) or R13XCHG.match(t))


def classify(body):
    idx = {a: i for i, (a, _) in enumerate(body)}
    has_save = any(SAVE.match(t) for _, t in body)
    has_spill = any(SPILL.match(t) for _, t in body)
    seen = set()
    q = deque([(0, 0, False)])
    rets = 0
    bad = []
    unresolved = False
    early_write = False
    while q:
        i, d, sv = q.popleft()
        if i >= len(body) or (i, d, sv) in seen:
            continue
        seen.add((i, d, sv))
        a, t = body[i]
        if writes_r13(t) and not sv:
            early_write = True
        if SAVE.match(t):
            d = min(d + 1, MAXD)
            sv = True
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
                q.append((idx[tgt], d, sv))
            elif d != 0:
                bad.append(('tail_jmp_unbalanced', a))
            continue
        if re.search(r'\bjmp\s+(?!0x)', t):
            unresolved = True
            continue
        m = JCC.match(t)
        if m:
            tgt = int(m.group(1), 16)
            if tgt in idx:
                q.append((idx[tgt], d, sv))
        q.append((i + 1, d, sv))
    if bad:
        cat = 'unbalanced'
    elif unresolved:
        cat = 'unresolved_indirect'
    elif not has_save:
        cat = 'write_without_save'
    elif early_write:
        cat = 'write_before_save'
    else:
        cat = 'saved_balanced'
    return {'cat': cat, 'rets': rets, 'bad': bad, 'spill': has_spill and not has_save}


def selftest():
    cases = [
        ([(0, 'mov    r13,rax'), (1, 'ret')], 'write_without_save'),
        ([(0, 'push   r13'), (1, 'mov    r13,rax'), (2, 'pop    r13'), (3, 'ret')], 'saved_balanced'),
        ([(0, 'mov    r13,rax'), (1, 'push   r13'), (2, 'pop    r13'), (3, 'ret')], 'write_before_save'),
        ([(0, 'push   r13'), (1, 'mov    r13,rax'), (2, 'ret')], 'unbalanced'),
        ([(0, 'push   r13'), (1, 'mov    r13,rax'), (2, 'jmp    rax')], 'unresolved_indirect'),
    ]
    ok = True
    for lines, want in cases:
        body = [(a, t) for a, t in lines]
        got = classify(body)['cat']
        print('selftest: %-22s (期待 %s)' % (got, want))
        ok = ok and got == want
    sys.exit(0 if ok else 1)


def load(pe_path, dsm_path):
    b = open(pe_path, 'rb').read()
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
    with open(dsm_path) as f:
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
    return slots, body_of


def main():
    slots, body_of = load(sys.argv[1], sys.argv[2])
    writers = sorted(s for s in slots if any(writes_r13(t) for _, t in body_of[s]))
    cnt = Counter()
    total_rets = 0
    bad_funcs = []
    spill_only = 0
    for s in writers:
        r = classify(body_of[s])
        cnt[r['cat']] += 1
        total_rets += r['rets']
        if r['spill'] and r['cat'] == 'write_without_save':
            spill_only += 1
        if r['cat'] == 'unbalanced':
            bad_funcs.append((s, r['bad']))
    print('slot_functions', len(slots))
    print('r13_writing_slot_functions', len(writers))
    print('ret_paths_checked', total_rets)
    for c in ['saved_balanced', 'write_before_save', 'write_without_save', 'unresolved_indirect', 'unbalanced']:
        print('class_' + c, cnt[c])
    print('write_without_save_with_mov_spill', spill_only)
    for s, bad in bad_funcs[:40]:
        print('  %x %s' % (s, bad[:3]))


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--selftest':
        selftest()
    if len(sys.argv) != 3:
        sys.exit('usage: ret_r13_check.py <SlateCore.core_64> <core64.dsm> | --selftest')
    main()
