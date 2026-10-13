#!/usr/bin/env python3
"""M11-N20 (#565): PE に静的実体として置かれた WNDCLASS{W,A,EXW,EXA} を走査し、lpfnWndProc の集合を列挙して
lift closure (IR の `define @function_<VA>`) の内外を判定する。closure 外の WNDPROC (+ その call/jmp 閉包) を seed として出力する。

  python3 m11_wndclass_scan.py --pe <PE> [--ir work/boot_final.ll] [--json-out results/wndclass_scan.json]
                               [--ranges-out work/boot_ranges_wnd.txt]   # 新規 closure 関数の RetDec --select-ranges (boot6 の lift 入力)
                               [--check]   # 判定: 最終 IR に定義の無い fn WNDPROC があれば exit 1 (検出件数が --min-instances 未満でも exit 1)

検出規則 (x64 WNDCLASS。EX 形は +0=cbSize(80)・style が +4、非 EX は +0=style・+4=0 の 8 バイト整列相当):
  +8 lpfnWndProc  : .reloc DIR64 の指す VA で .text 内かつ `.pdata` 関数先頭または import thunk (`ff 25`)
  +16/+20         : cbClsExtra / cbWndExtra = 0..0x1000
  +24..+56        : hInstance/hIcon/hCursor/hbrBackground/lpszMenuName = 小整数 (0 / COLOR_xxx+1) か reloc 済みポインタ
  +64 lpszClassName: reloc 済み VA で、指す先が識別子風の UTF-16 / ASCII 文字列 (2 文字以上)
全条件 AND。値は PE から直読みでヒューリスティックな外部入力は使わない (Ghidra 表も不要: 関数境界は `.pdata` のみ)。
"""
import argparse, json, os, re, struct, sys
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'm6'))

ap = argparse.ArgumentParser()
ap.add_argument('--pe', required=True)
ap.add_argument('--ir', default=os.path.join(HERE, 'work', 'boot_final.ll'), help='最終 IR (boot6 取込後の closure 判定 = --check 用)')
ap.add_argument('--base-lift', nargs='*', default=[os.path.join(HERE, 'work', 'boot%d.lift.ll' % i) for i in range(5)],
                help='WNDCLASS seed 導入前の lift (boot0..4)。ranges / seed の算出は常にこれを基準にする (boot6 取込後に再実行しても冪等)')
ap.add_argument('--json-out')
ap.add_argument('--ranges-out')
ap.add_argument('--check', action='store_true')
ap.add_argument('--min-instances', type=int, default=0, help='--check: 検出 WNDCLASS 件数の floor (走査が 0 件で空振り PASS するのを防ぐ)')
ap.add_argument('-q', action='store_true')
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=False)
IB = pe.OPTIONAL_HEADER.ImageBase
secs = [(s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.get_data()) for s in pe.sections]


def sec_of(rva):
    for n, lo, d in secs:
        if lo <= rva < lo + len(d):
            return n, lo, d
    return None


def u(fmt, rva):
    s = sec_of(rva)
    if not s:
        return None
    n, lo, d = s
    sz = struct.calcsize(fmt)
    if rva - lo + sz > len(d):
        return None
    return struct.unpack_from(fmt, d, rva - lo)[0]


relocs = set()
for ent in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
    for e in ent.entries:
        if e.type == 10:   # IMAGE_REL_BASED_DIR64
            relocs.add(e.rva)

TEXT_LO, TEXT_D = [(lo, d) for n, lo, d in secs if n == '.text'][0]
fn_size = {}   # RVA -> size (.pdata)
for n, lo, d in secs:
    if n == '.pdata':
        for i in range(len(d) // 12):
            b, e, _ = struct.unpack_from('<III', d, i * 12)
            if b and e > b:
                fn_size[b] = e - b

iat = {}
for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
    for imp in ent.imports:
        if imp.address:
            iat[imp.address - IB] = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
for ent in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):   # 遅延 import (.didata) の IAT スロットも thunk の飛び先になる
    for imp in ent.imports:
        if imp.address:
            iat.setdefault(imp.address - IB, 'delay:' + (imp.name.decode() if imp.name else 'ord%d' % imp.ordinal))
IAT_RANGES = [(lo, lo + len(d)) for n, lo, d in secs if n in ('.idata', '.didata')]
thunks = {}   # import thunk RVA -> API 名 (名前表に無い .idata/.didata スロットは 'slot:<rva>')
for m in re.finditer(rb'\xff\x25(....)', TEXT_D, re.S):
    rva = TEXT_LO + m.start()
    tgt = rva + 6 + struct.unpack('<i', m.group(1))[0]
    if tgt in iat:
        thunks[rva] = iat[tgt]
    elif any(lo <= tgt < hi for lo, hi in IAT_RANGES):
        thunks[rva] = 'slot:%#x' % tgt


def ptr_rva(rva):
    if rva not in relocs:
        return None
    v = u('<Q', rva)
    if v is None or not (IB <= v < IB + 0x2000000):
        return None
    return v - IB


def name_at(rva):
    s = sec_of(rva)
    if not s:
        return None
    n, lo, d = s
    o = rva - lo
    w = ''
    for j in range(100):
        if o + 2 * j + 2 > len(d):
            break
        c = struct.unpack_from('<H', d, o + 2 * j)[0]
        if c == 0:
            break
        if not (0x20 <= c < 0x7f):
            w = None
            break
        w += chr(c)
    ok = r'[A-Za-z_][\w.:\- ]*'
    if w and len(w) >= 2 and re.fullmatch(ok, w):
        return w
    c8 = ''
    for j in range(100):
        if o + j >= len(d):
            break
        c = d[o + j]
        if c == 0:
            break
        if not (0x20 <= c < 0x7f):
            c8 = None
            break
        c8 += chr(c)
    return c8 if c8 and len(c8) >= 2 and re.fullmatch(ok, c8) else None


def small_or_ptr(rva):
    v = u('<Q', rva)
    return v is not None and (v < 0x10000 or ptr_rva(rva) is not None)


rows = []
rej = {'proc_not_fn': 0, 'fields': 0, 'name': 0}
for p in sorted(relocs):
    base = p - 8
    pr = ptr_rva(p)
    if pr is None or not (TEXT_LO <= pr < TEXT_LO + len(TEXT_D)):
        continue
    if not (pr in fn_size or pr in thunks):
        rej['proc_not_fn'] += 1
        continue
    w0, w4 = u('<I', base), u('<I', base + 4)
    ex = (w0 == 80)
    if not (ex or (w0 is not None and w0 < 0x10000 and w4 == 0)):
        rej['fields'] += 1
        continue
    cx, wx = u('<i', base + 16), u('<i', base + 20)
    if cx is None or wx is None or not (0 <= cx <= 0x1000 and 0 <= wx <= 0x1000) or not all(small_or_ptr(base + o) for o in (24, 32, 40, 48, 56)):
        rej['fields'] += 1
        continue
    cp = ptr_rva(base + 64)
    nm = name_at(cp) if cp is not None else None
    if nm is None:
        rej['name'] += 1
        continue
    rows.append({'wndclass_va': IB + base, 'section': sec_of(base)[0], 'wndproc_va': IB + pr, 'class_name': nm,
                 'wndproc': ('import_thunk:' + thunks[pr]) if pr in thunks else 'fn'})

# --- closure 内外 (lift 済みの定義 = IR の define @function_<VA>。RetDec の内部入口別関数化を含む) ---
DEF = re.compile(r'^define [^@]*@function_([0-9a-f]+)\(', re.M)
def defs(paths):
    out = set()
    for pth in paths:
        if os.path.exists(pth):
            out |= set(int(x, 16) for x in DEF.findall(open(pth).read()))
    return out
defined = defs(a.base_lift)       # seed 導入前の closure (boot0..4)
final_defined = defs([a.ir])      # 最終 IR (boot6 取込後)
if not defined:
    sys.exit('base lift (boot0..4) の define が 0 件: %s' % a.base_lift)
for r in rows:
    r['in_closure'] = (r['wndproc_va'] in defined) if r['wndproc'] == 'fn' else None
    r['in_final_ir'] = (r['wndproc_va'] in final_defined) if r['wndproc'] == 'fn' else None
fn_rows = [r for r in rows if r['wndproc'] == 'fn']
procs = sorted(set(r['wndproc_va'] for r in fn_rows))
outside = [p for p in procs if p not in defined]

# --- 閉包: closure 外 WNDPROC から call/jmp 即値を辿り、lift 済み (defined) に当たったら止める。境界は `.pdata` のみ ---
from ottlib import Bin, Dis   # capstone 必須
bin_ = Bin(a.pe)
dis = Dis(bin_)


def fsize(va):
    # `.pdata` 関数 + import thunk (`jmp [IAT]`, 6B, unwind 無し。m11 の boot_fns も 6B 関数として lift している)
    return fn_size.get(va - IB) or (6 if (va - IB) in thunks else 0)


def edges(va):
    sz = fsize(va)
    code = bin_.read_at(va - IB, sz) if sz else None
    out = []
    if code is None:
        return out
    for ins in dis.cs.disasm(code, va):
        if ins.mnemonic in ('jmp', 'call') and ins.operands and ins.operands[0].type == 2:
            t = ins.operands[0].imm
            if not (va <= t < va + sz) and fsize(t):
                out.append(t)
    return out


new_fns, q = {}, list(outside)
while q:
    f = q.pop()
    if f in new_fns or f in defined:
        continue
    new_fns[f] = fsize(f)
    q.extend(edges(f))
import_thunk_targets = sorted(set(r['wndproc'] for r in rows if r['wndproc'] != 'fn'))
summary = {
    'wndclass_instances': len(rows),
    'by_section': {s: sum(1 for r in rows if r['section'] == s) for s in sorted(set(r['section'] for r in rows))},
    'wndproc_fn_instances': len(fn_rows),
    'wndproc_import_thunk_instances': len(rows) - len(fn_rows),
    'import_thunk_targets': import_thunk_targets,
    'distinct_fn_wndprocs': len(procs),
    'wndproc_in_closure': len(procs) - len(outside),
    'wndproc_outside_closure': len(outside),
    'closure_new_functions': len(new_fns),
    'closure_new_bytes': sum(new_fns.values()),
    'base_lift_defined_functions': len(defined),
    'final_ir_defined_functions': len(final_defined),
    'wndproc_outside_final_ir': len([p for p in procs if p not in final_defined]),
    'rejected_candidates': rej,
}
if not a.q:
    print(json.dumps(summary, indent=1))
    for r in rows:
        print('  %#x %-6s proc=%#x %-28s %-28s in_closure=%s' % (r['wndclass_va'], r['section'], r['wndproc_va'], r['class_name'], r['wndproc'], r['in_closure']))
    if new_fns:
        print('closure 外 WNDPROC から閉包した新規 lift 対象: %d 関数 / %d B' % (len(new_fns), sum(new_fns.values())))
if a.json_out:
    os.makedirs(os.path.dirname(os.path.abspath(a.json_out)), exist_ok=True)
    json.dump({'summary': summary, 'wndclasses': rows, 'seeds_outside_closure': ['0x%x' % p for p in outside],
               'closure_new_functions': {'0x%x' % k: v for k, v in sorted(new_fns.items())}}, open(a.json_out, 'w'), indent=1)
if a.ranges_out:
    open(a.ranges_out, 'w').write(','.join('0x%x-0x%x' % (k, k + v) for k, v in sorted(new_fns.items())))
if a.check:
    bad = []
    if len(rows) < a.min_instances:
        bad.append('WNDCLASS 検出 %d < floor %d (走査の空振り)' % (len(rows), a.min_instances))
    miss = [p for p in procs if p not in final_defined]
    if miss:
        bad.append('最終 IR (%s) に定義の無い WNDPROC %d 件: %s' % (os.path.basename(a.ir), len(miss), ' '.join('%#x' % p for p in miss)))
    print('WNDCLASS-CHECK %s' % ('FAIL: ' + '; '.join(bad) if bad else 'PASS (instances=%d, fn wndproc=%d, 最終 IR で未定義=0)' % (len(rows), len(procs))))
    sys.exit(1 if bad else 0)
