#!/usr/bin/env python3
"""Reverse-BFS callers (direct calls + vtable instantiation edges) + annotated listing.
usage:
  zone.py <graph.pkl> <seedVA hex> [depth=4]   reverse reachability
  zone.py <graph.pkl> --list <VA> [VA ...]     one-line summaries (+vtable slots)
  zone.py <graph.pkl> --who <VA> [VA ...]      referrers of an address (data ref / vtable use / direct call)
"""
import sys, pickle, bisect, collections

PE_PATH = sys.argv[1].replace('graph.pkl', '') + '../../work/Serum2_win64.vst3'

g = pickle.load(open(sys.argv[1], 'rb'))
funcs, adj, drefs, daddrs, vt_of, vt_starts, IMG = (
    g['funcs'], g['adj'], g['drefs'], g['daddrs'], g['vt_of'], g['vt_starts'], g['IMG'])
n = len(funcs); starts = [b for b, e in funcs]
def fidx(va):
    r = va - IMG
    i = bisect.bisect_right(starts, r) - 1
    return i if i >= 0 else -1

# ---- RTTI-validated vtables (COL sig=1 self-back-pointer) ----
import re as _re, struct as _struct, pefile as _pefile
_pe = _pefile.PE(PE_PATH, fast_load=True)
IMG2 = _pe.OPTIONAL_HEADER.ImageBase
_secs = {s.Name.rstrip(b'\0').decode(): s for s in _pe.sections}
dm = _pe.get_memory_mapped_image()
RD = _secs['.rdata']; RB = RD.get_data(); RVA0 = RD.VirtualAddress
TVA = _secs['.text'].VirtualAddress; TLN = len(_secs['.text'].get_data())
classes = {}
for m in _re.finditer(rb'\.\?A[UV][A-Za-z0-9_@$?]{2,400}@@\x00', dm):
    td = m.start() - 16
    if td > 0:
        classes[td] = m.group(0)[:-1].decode()
def demangle(nm):
    return '::'.join(reversed([p for p in nm[4:-2].split('@') if p]))
col_at = {}   # col rva -> (td_rva)
for off in range(RVA0, RVA0 + len(RB) - 24, 4):
    sig, o, cd, td, chd, selfr = _struct.unpack_from('<IIIIII', dm, off)
    if sig == 1 and selfr == off and td in classes:
        col_at[off] = td
col_va = {IMG + off: td for off, td in col_at.items()}
rtti_vt = {}   # vt_start_rva -> (class_name, [fn rvas...])
for off in range(RVA0, RVA0 + len(RB) - 8, 8):
    v = _struct.unpack_from('<Q', dm, off)[0]
    if v in col_va:
        ms = []
        p = off + 8
        while True:
            q = _struct.unpack_from('<Q', dm, p)[0]
            r = q - IMG
            if TVA <= r < TVA + TLN and fidx(r) >= 0 and funcs[fidx(r)][0] == r:
                ms.append(r); p += 8
            else:
                break
        if len(ms) >= 2:
            rtti_vt[off + 8] = (demangle(classes[col_va[v]]), ms)
rtti_vt_start = set(rtti_vt)
radj = [[] for _ in range(n)]
for i in range(n):
    for j in adj[i]:
        radj[j].append(i)

# vtable start (run begin) -> list of (func_idx, slot)
slots_by_start = collections.defaultdict(list)
for st, (cname, ms) in rtti_vt.items():
    for k, r in enumerate(ms):
        j = fidx(r)
        if j >= 0:
            slots_by_start[st].append((j, k))
# func idx -> [(vt_start, slot)]  (RTTI only)
vt_of2 = collections.defaultdict(list)
for st, lst in slots_by_start.items():
    for j, k in lst:
        vt_of2[j].append((st, k))
vt_of = dict(vt_of2)

# referrer index over daddrs (address -> func idxs)
addr_refs = collections.defaultdict(set)
for fi in range(n):
    for t in (daddrs[fi] or ()):
        addr_refs[t].add(fi)

def vtable_users(fi):
    """functions that reference a vtable containing func fi (constructors etc.)"""
    out = set()
    for st, k in vt_of.get(fi, []):
        for kk in range(len(slots_by_start[st])):
            for u in addr_refs.get(st + 8 * kk, ()):
                if u != fi:
                    out.add(u)
    return out

def ann(fi, maxi=6):
    ds = list((drefs[fi] or {}).items())
    vt = vt_of.get(fi)
    s = ' '.join(v for _, v in ds[:maxi])
    if vt:
        names = []
        for st, k in vt[:3]:
            cn = rtti_vt.get(st, ('?',))[0]
            names.append(f"{cn.split('::')[-1]}#{k}")
        s += f" VT[{','.join(names)}]"
    return s

def expand_callers(fi):
    cs = set(radj[fi]) | vtable_users(fi)
    cs.discard(fi)
    return sorted(cs)

if sys.argv[2] == '--list':
    for va in sys.argv[3:]:
        fi = fidx(int(va, 16))
        if fi < 0:
            print(f"{va} NOT-PDATA"); continue
        b, e = funcs[fi]
        print(f"{hex(IMG + b)} sz={e-b:6d} in={len(radj[fi]):3d} vtuse={len(vtable_users(fi)):3d} out={len(adj[fi]):3d} | {ann(fi)}")
    sys.exit(0)

if sys.argv[2] == '--who':
    for va in sys.argv[3:]:
        a = int(va, 16)
        refs = sorted(addr_refs.get(a - IMG, ()))
        st = a - IMG
        cname = rtti_vt.get(st, ('?',))[0] if st in rtti_vt else None
        print(f"{va}: class={cname or '-'} "
              f"data_refs={[hex(IMG + funcs[r][0]) for r in refs[:16]]}")
    sys.exit(0)

t = fidx(int(sys.argv[2], 16)); depth = int(sys.argv[3]) if len(sys.argv) > 3 else 4
seen = {t}
front = [t]
for d in range(depth):
    nxt = []
    for x in front:
        cs = [c for c in expand_callers(x) if c not in seen]
        if cs:
            print('  ' * d + f"{hex(IMG + funcs[x][0])} [{ann(x, 3)}] <- {[hex(IMG + funcs[c][0]) for c in cs[:8]]}{' ...' if len(cs) > 8 else ''}")
        for c in cs:
            seen.add(c); nxt.append(c)
    front = nxt[:300]
print(f"total={len(seen)}")
