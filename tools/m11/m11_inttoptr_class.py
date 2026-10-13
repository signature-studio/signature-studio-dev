#!/usr/bin/env python3
# [M11-N82] 10 進 inttoptr 命令 (`%x = inttoptr i64 N to ptr`) の VA→LVA 仕分け (#1318).
# 入力: 基準 IR (既定 work/boot_allfx.ll = M11_M2P=1 が remap する直前の IR) と PE (FL_WIN64_DIR/extracted/block00031_PE.bin)。
# 対象: 10 進の命令形 `%x = inttoptr i64 N to ptr` 全件 (M2p と同じ正規表現)。
# 分類は全使用箇所で判定する (1 箇所でも非アドレス用途があれば「要確認」):
#   - 範囲外 (N が [0x400000, 0x1abf400) に無い): VA のまま (整数定数・ビット列・小さな数値。remap 対象外)
#   - 範囲内で全使用が load/store/gep のアドレス: VA→LVA にすべき (メモリ像の参照)
#   - 範囲内で整数として使われる (ptrtoint 等): 要確認 (VA ではなく数値の可能性)
#   - 範囲内で call 引数・store 値・その他: 要確認
# 使い方: FL_WIN64_DIR=... python3 m11_inttoptr_class.py [IR] [--pe PE] [--list-other]
import re, argparse, collections, os
import pefile

IMG_LO = 0x400000
IMG_HI = 0x1abf400
DEF = re.compile(r'^\s*(%[\w.$-]+)\s*=\s*inttoptr i64 (\d+) to ptr')
TOK = re.compile(r'%[\w.$-]+')

ap = argparse.ArgumentParser()
ap.add_argument('ir', nargs='?', default='work/boot_allfx.ll')
ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
ap.add_argument('--list-other', action='store_true', help='範囲内で「要確認」の全件を行付きで出す')
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
secs = [(s.Name.rstrip(b'\0').decode(errors='replace'),
         base + s.VirtualAddress, base + s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData),
         bool(s.Characteristics & 0x20000000))  # IMAGE_SCN_MEM_EXECUTE
        for s in pe.sections]

def sec_of(va):
    for n, lo, hi, ex in secs:
        if lo <= va < hi:
            return n + ('(x)' if ex else '')
    return '(none)'

lines = open(a.ir, encoding='utf-8', errors='replace').read().split('\n')
defs = []
uses = collections.defaultdict(list)
for i, l in enumerate(lines):
    m = DEF.match(l)
    if m:
        defs.append((i, m.group(1), int(m.group(2))))
    for t in set(TOK.findall(l)):
        uses[t].append(i)

ADDR, OTHER = 'addr', 'other'

# 手動判定 (根拠は REPORT_N1318.md §3)。キーは IR の行番号 (1-based)。
# 行 185227: QueryPerformanceFrequency の結果 (10000000 = 10 MHz)。ptr 型 global に入るが整数データで、
# 読み側は ptrtoint → cvtsi2sd。VA ではないので remap すると周波数が壊れる → VA のまま。
MANUAL_INT = {185227: 'QPF 周波数 10000000 (整数データ・ptrtoint→cvtsi2sd)'}

def use_kinds(name, di):
    kinds = set()
    for j in uses.get(name, []):
        if j == di:
            continue
        u = lines[j]
        if re.search(r'\bptrtoint\s+ptr\s+' + re.escape(name) + r'\b', u):
            kinds.add('ptrtoint')
        elif re.search(r'\bstore\s+ptr\s+' + re.escape(name) + r'\s*,', u):
            kinds.add('store-value')
        elif re.search(r'=\s*load\b', u) and re.search(r'\bptr ' + re.escape(name) + r'\b', u):
            kinds.add(ADDR)
        elif re.search(r'\bstore\b', u) and re.search(r',\s*ptr ' + re.escape(name) + r'\b', u):
            kinds.add(ADDR)
        elif re.search(r'\bgetelementptr\b', u) or re.search(r'=\s*select\b', u):
            kinds.add(ADDR)
        elif re.search(r'\bcall\b', u):
            kinds.add('call-arg')
        elif re.search(r'\bstore\b', u):
            kinds.add('store-value')
        else:
            kinds.add(OTHER)
    return kinds

cls = collections.Counter()
by_sec = collections.Counter()
ex = collections.defaultdict(list)
other_rows = []
for di, name, v in defs:
    if not (IMG_LO <= v < IMG_HI):
        cls['VA のまま (範囲外・整数定数)'] += 1
        continue
    ks = use_kinds(name, di)
    sec = sec_of(v)
    by_sec[sec] += 1
    if di + 1 in MANUAL_INT:
        c = 'VA のまま (手動: 整数データ)'
        cls[c] += 1
        if len(ex[c]) < 3:
            ex[c].append((di + 1, name, hex(v), sec))
        continue
    if not ks:
        c = 'VA のまま候補 (使用なし)'
    elif ks == {ADDR}:
        c = 'VA→LVA にすべき (全使用がメモリ参照)'
    else:
        c = '要確認 (非アドレス用途あり: %s)' % ','.join(sorted(ks))
        other_rows.append((di + 1, name, v, sec, ','.join(sorted(ks))))
    cls[c] += 1
    if len(ex[c]) < 3:
        ex[c].append((di + 1, name, hex(v), sec))

print('decimal instr inttoptr 全件 =', len(defs))
print('VA 範囲内 [0x400000,0x1abf400) =', sum(by_sec.values()))
print('-- 分類 (全件) --')
for k, n in cls.most_common():
    print('%6d  %s' % (n, k))
print('-- 範囲内の PE section --')
for k, n in by_sec.most_common():
    print('%6d  %s' % (n, k))
print('-- 代表例 --')
for k in ex:
    for e in ex[k]:
        print('  [%s] line %d %s value=%s sec=%s' % (k, e[0], e[1], e[2], e[3]))
if a.list_other:
    print('-- 要確認 (全件) --')
    for r in other_rows:
        print('  line %d %s value=%s sec=%s uses=%s' % (r[0], r[1], hex(r[2]), r[3], r[4]))
