#!/usr/bin/env python3
"""SR-3 step 4: signature DB + boundary cut table.
Seeds per library = (a) functions that reference an OSS anchor (string / constant table, sr3_anchors.py) and
(b) methods of RTTI vtables whose class name belongs to the library.  The library window is the function-index interval
that contains all seeds and minimises (entry functions from outside + address-taken entries); ties -> smaller byte span
(over-exclusion would drop DSP from the lift, under-exclusion only lifts extra code).
Each function gets a tag: anchor | vtable | window (window = inferred, 推定).
usage: sr3_cut.py <pe> <index.npz> <anchors.json> <out_dir>"""
import sys, re, json, struct, bisect, collections
import numpy as np
import pefile

PATH, IDX, ANCH, OUT = sys.argv[1:5]
IMG = 0x180000000
pe = pefile.PE(PATH, fast_load=True)
img = pe.get_memory_mapped_image()
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
RVA, RB = S['.rdata'].VirtualAddress, S['.rdata'].get_data()
z = np.load(IDX); funcs = z['funcs']; refs = z['refs']
fs = funcs[:, 0].tolist(); NF = len(fs)


def fi(rva):
    i = bisect.bisect_right(fs, rva) - 1
    return i if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else -1


# ---- RTTI vtables (same decode as dsp_closure.py)
classes = {}
for m in re.finditer(rb'\.\?A[UV][A-Za-z0-9_@$?]{2,400}@@\x00', img):
    td = m.start() - 16
    if td > 0:
        classes[td] = m.group(0)[:-1].decode()
cols = {}
for off in range(RVA, RVA + len(RB) - 24, 4):
    sig, o, cd, td, chd, selfr = struct.unpack_from('<IIIIII', img, off)
    if sig == 1 and selfr == off and td in classes and o < 0x1000:
        cols.setdefault(td, []).append((off, o))
col_by_va = {IMG + off: (td, o) for td, l in cols.items() for off, o in l}


def demangle(n):
    return '::'.join(reversed([p for p in n[4:-2].split('@') if p]))


vt = []  # (class, vtable_rva, [method idx])
for off in range(RVA, RVA + len(RB) - 8, 8):
    v = struct.unpack_from('<Q', img, off)[0]
    if v in col_by_va:
        td, o = col_by_va[v]
        ms = []; p = off + 8
        while True:
            r = struct.unpack_from('<Q', img, p)[0] - IMG
            k = fi(r)
            if k >= 0 and funcs[k][0] == r: ms.append(k); p += 8
            else: break
        vt.append((demangle(classes[td]), off + 8, ms))

# library -> RTTI class-name regexes (full demangled name)
RTTI = {
    'muparser': r'^(mu::|mu$)',
    'libsfz': r'^libsfz::',
    'pffft': r'^PFFFT',
    'zl_convolver': r'^ZL',
    'nlohmann_json': r'json_abi_v3_12_0|nlohmann',
}
# ---- anchor seeds
A = json.load(open(ANCH))
# anchors that are specific enough to be a seed (generic 2-4 byte tokens such as "sin"/"RF64" are evidence only)
SEED_OK = {
    ('sqlite', 'fileheader'), ('sqlite', 'sqlite_master'), ('sqlite', 'keywords'), ('sqlite', 'compile_opt'),
    ('nlohmann_json', 'parse_error'), ('nlohmann_json', 'type_error'), ('nlohmann_json', 'invalid_iter'),
    ('muparser', 'msg_unexp'),
    ('libsfz', 'generated'), ('libsfz', 'lokey'), ('libsfz', 'pitch_keycenter'),
    ('libsndfile', 'invalid_fmt'), ('libsndfile', 'nist'), ('flac', 'hdr_fail'),
    ('zstd', 'LL_bits'), ('zstd', 'ML_bits'),
}
seeds = collections.defaultdict(dict)  # lib -> idx -> tag
for e in A:
    if (e['lib'], e['name']) not in SEED_OK: continue
    for h in e['hits']:
        for f in h['ref_funcs']:
            k = fi(int(f, 16) - IMG)
            if k >= 0: seeds[e['lib']].setdefault(k, 'anchor')
# zlib / zstd tables referenced through function constants (hex anchors verified in step 2/3, see REPORT §10)
CONST_TABLES = {  # lib -> [(name, va, span)]
    'zlib': [('inflate_dbase', 0x180a97170, 128), ('inflate_lbase_clen', 0x180a97070, 0x700)],
    'sha512': [('sha512_K', 0x180a711d0, 640)],
}
rip = refs[refs[:, 2] == 0]
for lib, tabs in CONST_TABLES.items():
    for name, va, span in tabs:
        r = va - IMG
        m = (rip[:, 1] >= r) & (rip[:, 1] < r + span)
        for s in rip[m, 0]:
            k = fi(int(s))
            if k >= 0: seeds[lib].setdefault(k, 'anchor')
# zlib entry known from the inflate caller (REPORT §4.1: 0x18087da10 calls 3 functions)
for lib, rx in RTTI.items():
    for cn, vtr, ms in vt:
        if re.search(rx, cn):
            for k in ms: seeds[lib].setdefault(k, 'vtable')

# ---- edge graph
ed = refs[(refs[:, 2] == 1) | (refs[:, 2] == 2)]
src = np.array([fi(int(s)) for s in ed[:, 0]]); dst = np.array([fi(int(t)) for t in ed[:, 1]])
m = (src >= 0) & (dst >= 0) & (src != dst); src, dst = src[m], dst[m]
ls = np.array([fi(int(s)) for s in rip[:, 0]]); ld = np.array([fi(int(t)) for t in rip[:, 1]])
m = (ld >= 0) & (ls >= 0) & (ls != ld); ls, ld = ls[m], ld[m]


def stats(lo, hi):
    ind = (dst >= lo) & (dst <= hi); ins = (src >= lo) & (src <= hi)
    ent = len(set(dst[ind & ~ins].tolist()))
    ext = len(set(dst[ins & ~ind].tolist()))
    lea = len(set(ld[(ld >= lo) & (ld <= hi) & ~((ls >= lo) & (ls <= hi))].tolist()))
    return ent, ext, lea


# Window growth = linkage-connected contiguous range.  Seeds are clustered (index gap > CLUSTER_GAP => separate cluster);
# each cluster grows outward one function at a time while the next function is linked (call/jmp/address-ref in either
# direction) to the current window; growth stops after GAP consecutive unlinked functions (those are trimmed back).
# This keeps the window to code that actually talks to the seeds, unlike an entry-minimising window which swallows neighbours.
CLUSTER_GAP = {'sqlite': 400}  # default 150
GAP = {'sqlite': 6, 'zstd': 6, 'zlib': 4, 'muparser': 4, 'libsndfile': 4, 'flac': 4, 'libsfz': 4, 'zl_convolver': 3, 'sha512': 0, 'pffft': 3}
adj = collections.defaultdict(set)
for a_, b_ in zip(src.tolist(), dst.tolist()): adj[a_].add(b_); adj[b_].add(a_)
for a_, b_ in zip(ls.tolist(), ld.tolist()): adj[a_].add(b_); adj[b_].add(a_)


def grow(lo, hi, gap):
    for direction in (-1, 1):
        miss = 0; cur = lo if direction < 0 else hi; edge = cur
        while 0 <= cur + direction < NF and miss <= gap:
            nxt = cur + direction
            win = range(lo, hi + 1) if direction > 0 else range(lo, hi + 1)
            if any(lo <= q <= hi for q in adj[nxt]):
                if direction < 0: lo = nxt
                else: hi = nxt
                edge = nxt; miss = 0
            else:
                miss += 1
            cur = nxt
            if direction < 0: lo = min(lo, edge)
            else: hi = max(hi, edge)
    return lo, hi


rows = []; db = {}
for lib in sorted(seeds):
    sd = sorted(seeds[lib])
    if lib == 'nlohmann_json':
        for k in sd: rows.append((lib, k, seeds[lib][k]))
        db[lib] = dict(seeds=len(sd), window=None, note='header-only templates, scattered; seeds only')
        continue
    clusters = [[sd[0]]]
    for k in sd[1:]:
        if k - clusters[-1][-1] > CLUSTER_GAP.get(lib, 150): clusters.append([k])
        else: clusters[-1].append(k)
    wins = []
    for c in clusters:
        lo, hi = grow(c[0], c[-1], GAP.get(lib, 4))
        wins.append((lo, hi, c))
    for lo, hi, c in wins:
        for k in range(lo, hi + 1): rows.append((lib, k, seeds[lib].get(k, 'window')))
    tb = sum(int(funcs[hi][1] - funcs[lo][0]) for lo, hi, c in wins)
    es = [stats(lo, hi) for lo, hi, c in wins]
    db[lib] = dict(seeds=len(sd), clusters=[dict(seed_funcs=len(c), window=[hex(IMG + fs[lo]), hex(IMG + int(funcs[hi][1]))],
                   window_funcs=hi - lo + 1, window_bytes=int(funcs[hi][1] - funcs[lo][0]), entry_funcs=e[0], exit_callees=e[1],
                   addr_taken_entries=e[2]) for (lo, hi, c), e in zip(wins, es)], window_funcs=sum(hi - lo + 1 for lo, hi, c in wins),
                   window_bytes=tb)

# a function claimed by several libraries: keep the library with the more specific tag (anchor > vtable > window), then smaller window
RANK = {'anchor': 0, 'vtable': 1, 'window': 2}
best = {}
wsize = {lib: d.get('window_funcs', 1) for lib, d in db.items()}
for lib, k, tag in rows:
    cur = best.get(k)
    c = (RANK[tag], wsize[lib], lib)
    if cur is None or c < cur[0]: best[k] = (c, lib, tag)
with open(f'{OUT}/sr3_cut_table.tsv', 'w') as f:
    f.write('func_va\tbytes\tlibrary\ttag\n')
    for k in sorted(best):
        _, lib, tag = best[k]
        f.write(f'{hex(IMG + fs[k])}\t{int(funcs[k][1] - funcs[k][0])}\t{lib}\t{tag}\n')
tot = collections.Counter(); byt = collections.Counter(); tagc = collections.Counter()
for k, (_, lib, tag) in best.items():
    tot[lib] += 1; byt[lib] += int(funcs[k][1] - funcs[k][0]); tagc[(lib, tag)] += 1
for lib in db:
    db[lib]['cut_funcs'] = tot[lib]; db[lib]['cut_bytes'] = byt[lib]
    db[lib]['by_tag'] = {t: tagc[(lib, t)] for t in RANK if tagc[(lib, t)]}
allb = sum(byt.values()); allf = sum(tot.values())
db['_total'] = dict(cut_funcs=allf, cut_bytes=allb, lift_funcs_before=NF, lift_funcs_after=NF - allf,
                    lift_bytes_before=int((funcs[:, 1] - funcs[:, 0]).sum()),
                    lift_bytes_after=int((funcs[:, 1] - funcs[:, 0]).sum()) - allb)
json.dump(db, open(f'{OUT}/sr3_signature_db.json', 'w'), indent=1, sort_keys=True)
for lib, d in sorted(db.items()): print(lib, json.dumps(d))
