#!/usr/bin/env python3
"""SR-21b: RTTI (MSVC x64) vtable check for the non-.pdata code blocks (out/sr21_classify.tsv).
A vtable is a run of 8-byte pointers into .text (members) in .rdata/.data whose slot -1 points to an MSVC x64
Complete Object Locator (COL): signature == 1 and pSelf (COL+0x14, RVA) == the COL's own RVA.
The COL's pTypeDescriptor (COL+0x0C, RVA) gives the mangled class name (TypeDescriptor+0x10, ".?AV<cls>@<ns>@@").
A member is a function entry by definition, so a gap block whose start is a member is a strong entry (vt hit).
Controls: block starts shifted by +8 bytes must hit ~0 members.
Owner of a member = the first vtable in scan order (sections .rdata, .data, _RDATA; ascending RVA) that lists it
(member_owner.setdefault). A member shared by several vtables keeps that one owner; all owners are kept in `owners`.
usage: sr21_vtable.py <pe> <index.npz> <sr21_classify.tsv> <out_dir>"""
import sys, bisect, collections, re, struct
import numpy as np
import pefile

PE_PATH, IDX, CLS, OUT = sys.argv[1:5]
pe = pefile.PE(PE_PATH, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
TVA = t.VirtualAddress; TLEN = len(t.get_data())
DATA = [s for s in pe.sections if s.Name.rstrip(b'\0') in (b'.rdata', b'.data', b'_RDATA')]
DATA_SPANS = [(s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in DATA]
z = np.load(IDX)
funcs = z['funcs']
pstart = funcs[:, 0].tolist(); pend = funcs[:, 1].tolist(); pset = set(pstart)


def in_pdata(rva):
    i = bisect.bisect_right(pstart, rva) - 1
    return i >= 0 and rva < pend[i]


def q(rva):
    return struct.unpack_from('<Q', img, rva)[0]


def dw(rva):
    return struct.unpack_from('<I', img, rva)[0]


def is_text_va(v):
    return TVA <= v - IMG < TVA + TLEN


def in_data(rva):
    return any(a <= rva < b for a, b in DATA_SPANS)


def tdname(ptd):
    raw = bytes(img[ptd + 0x10: ptd + 0x10 + 512])
    name = raw.split(b'\0', 1)[0].decode('ascii', 'replace')
    if not name.startswith('.?A'):
        return name or '?'
    comps = []
    for p in name[4:].split('@'):
        if p == '':
            break
        comps.append(p)
    return '::'.join(reversed(comps)) if comps else name


def col_name(slot):
    """Return (col_rva, class name) if the 8 bytes before slot hold a verified COL pointer, else None."""
    col = q(slot - 8) - IMG
    if not (0 < col < len(img) - 0x18 and in_data(col)):
        return None, None, False
    if dw(col) != 1:
        return None, None, False
    ptd = dw(col + 0x0C)
    if dw(col + 0x14) != col or not (0 < ptd < len(img) - 0x10):
        return col, None, True
    return col, tdname(ptd), True


vtables = []
n_sig1 = 0
for a, b in DATA_SPANS:
    for r in range(a + 8, b - 7, 8):
        if r % 8:
            continue
        col, name, sig = col_name(r)
        if sig:
            n_sig1 += 1
        if name is None:
            continue
        mem = []
        k = 0
        while r + 8 * k + 8 <= b and k < 4096:
            v = q(r + 8 * k)
            if not is_text_va(v):
                break
            mem.append(v - IMG)
            k += 1
        vtables.append(dict(rva=r, col=col, cls=name, mem=mem))

member_owner = {}
owners = collections.defaultdict(set)
for vt in vtables:
    for m in vt['mem']:
        member_owner.setdefault(m, vt)
        owners[m].add(vt['cls'])

rows = [ln.rstrip('\n').split('\t') for ln in open(CLS)][1:]
blk = {}
for r in rows:
    blk[int(r[0], 16) - IMG] = r
bstarts = sorted(b for b in blk)
gap_n = sum(1 for r in blk.values() if r[2] != 'padding')
chance = gap_n * len(member_owner) / TLEN
ctrl_hits = sum(1 for va, r in blk.items() if r[2] != 'padding' and (va + 8) in member_owner)


def containing(m):
    i = bisect.bisect_right(bstarts, m) - 1
    if i < 0:
        return None
    b = bstarts[i]
    return blk[b] if m < b + int(blk[b][1]) else None


member_loc = {}
loc = collections.Counter()
for m, vt in member_owner.items():
    if m in pset:
        L, cr = 'pdata_start', None
    elif m in blk and blk[m][2] != 'padding':
        L, cr = 'gap_start', blk[m]
    elif containing(m) is not None:
        L, cr = 'gap_mid', containing(m)
    elif in_pdata(m):
        L, cr = 'pdata_inner', None
    else:
        L, cr = 'other', None
    member_loc[m] = L
    loc[L] += 1

with open(OUT + '/sr21_vtable.tsv', 'w') as f:
    f.write('vtable_va\tcol_va\trtti_class\tmembers\tmembers_pdata_start\tmembers_gap\n')
    for vt in vtables:
        ps = sum(1 for m in vt['mem'] if member_loc.get(m) == 'pdata_start')
        gs = sum(1 for m in vt['mem'] if member_loc.get(m, '').startswith('gap'))
        f.write(f"{hex(IMG + vt['rva'])}\t{hex(IMG + vt['col'])}\t{vt['cls']}\t{len(vt['mem'])}\t{ps}\t{gs}\n")

hits = []
for m, vt in sorted(member_owner.items()):
    L = member_loc[m]
    if not L.startswith('gap'):
        continue
    cr = blk[m] if L == 'gap_start' else containing(m)
    hits.append((hex(IMG + m), L, cr[0], cr[2], hex(IMG + vt['rva']), vt['cls'], cr[12]))
with open(OUT + '/sr21_vtable_hits.tsv', 'w') as f:
    f.write('member_va\tlocation\tblock_va\tclass\tvtable_va\trtti_class\tcut_library\n')
    for h in hits:
        f.write('\t'.join(h) + '\n')

cls_tot = collections.Counter(r[2] for r in blk.values() if r[2] != 'padding')
cls_hit = collections.Counter(h[3] for h in hits if h[1] == 'gap_start')
cls_hit_B = collections.Counter()
for h in hits:
    if h[1] == 'gap_start':
        cls_hit_B[h[3]] += int(blk[int(h[0], 16) - IMG][1])

oss = re.compile(r'^(mu::|ZL|nlohmann|libsfz|sqlite|zstd|FLAC|PFFFT|pffft|Vorbis|sndfile)')
oss_out = collections.Counter(h[5] for h in hits if h[6] == '-' and oss.match(h[5]))
names = collections.Counter(h[5] for h in hits)
cut_of = {int(h[0], 16) - IMG: h[6] for h in hits}
gap_m = sorted(cut_of)
multi_all = sum(1 for m in member_owner if len(owners[m]) >= 2)
multi_gs = sum(1 for m in member_owner if member_loc[m] == 'gap_start' and len(owners[m]) >= 2)
oss_first = [m for m in gap_m if cut_of[m] == '-' and oss.match(member_owner[m]['cls'])]
oss_any = [m for m in gap_m if cut_of[m] == '-' and any(oss.match(c) for c in owners[m])]
mid_bytes = [img[m - 1] for m in gap_m if member_loc[m] == 'gap_mid']
mid_hex = collections.Counter(f"0x{b:02X}" for b in mid_bytes)
mid_cat = collections.Counter('0xCC (int3)' if b == 0xCC else 'ret (0xC2/0xC3)' if b in (0xC2, 0xC3) else 'other' for b in mid_bytes)
NAME_CLS = [('VSTGUI', r'^VSTGUI::'), ('Steinberg', r'^Steinberg::'), ('std', r'^std::'), ('OSS', oss.pattern),
            ('Serum', r'^(Serum|Xfer|V[A-Z])|ProxyParameter|Controller|Editor|Lane|NoteGrid|PianoRoll'), ('other', '')]


def name_class(n):
    for k, p in NAME_CLS:
        if p == '' or re.search(p, n):
            return k


name_cnt = collections.Counter(name_class(member_owner[m]['cls']) for m in gap_m)

lines = []
lines.append(f"COL signature==1 candidates (slot-1 pointer into .rdata/.data): {n_sig1}")
lines.append(f"vtables (COL pSelf verified): {len(vtables)}")
lines.append(f"distinct members: {len(member_owner)}")
for k in ['pdata_start', 'gap_start', 'gap_mid', 'pdata_inner', 'other']:
    lines.append(f"member location {k}\t{loc[k]}")
lines.append('## gap_start members by block class: class / blocks / vt-member blocks / bytes')
for k in ['entry_call', 'entry_rip', 'branch_only', 'table_ptr', 'ptr_single', 'unref', 'data']:
    lines.append(f"{k}\t{cls_tot[k]}\t{cls_hit[k]}\t{cls_hit_B[k]}")
lines.append(f"control: non-padding block starts +8 that hit a member\t{ctrl_hits}\texpected by chance\t{chance:.2f}")
lines.append(f"owner sharing: members with >=2 distinct owner class names\t{multi_all} of {len(member_owner)}\tgap_start {multi_gs} of {loc['gap_start']}")
lines.append('## gap members by name class of first owner (regex; first match wins)')
for k, p in NAME_CLS:
    lines.append(f"{k}\t{name_cnt[k]}\t{p or '(rest)'}")
lines.append('## gap_mid members: byte before the member (hex count, then category)')
for k, c in sorted(mid_hex.items(), key=lambda kv: (-kv[1], kv[0])):
    lines.append(f"{k}\t{c}")
for k in ['0xCC (int3)', 'ret (0xC2/0xC3)', 'other']:
    lines.append(f"{k}\t{mid_cat[k]}")
lines.append('## OSS-namespace members outside the cut windows (cut_library -): first owner / any owner')
lines.append(f"OSS outside cut windows\t{len(oss_first)}\t{len(oss_any)}")
for n, c in oss_out.most_common():
    lines.append(f"{c}\t{n}")
lines.append('## OSS members counted only through a non-first owner (outside cut windows): va / first owner / OSS owners')
for m in oss_any:
    if m not in oss_first:
        lines.append(f"{hex(IMG + m)}\t{member_owner[m]['cls']}\t{' | '.join(sorted(c for c in owners[m] if oss.match(c)))}")
lines.append('## rtti class of gap members (top 25)')
for n, c in names.most_common(25):
    lines.append(f"{c}\t{n}")
with open(OUT + '/sr21_vtable_summary.txt', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
