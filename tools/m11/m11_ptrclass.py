#!/usr/bin/env python3
# [M11-N168] #3113: 実行後の新規 word を分類する定数集合を IR・PE・image から作る (m11_ptrcheck.mjs が読む)。
# 入力: 基準 IR (既定 tools/m11/work/boot_final.ll = m11_build.sh が wasm にする IR)、PE (FL_WIN64_DIR/extracted/block00031_PE.bin)、
#       image (既定 tools/m11/work/m11_image.bin = m11_image_gen.py が作る、実行時に載る PE 像)。
# 出力: tools/m11/work/ptrclass/classes.json (work/ は gitignore)。
#   code: IR の関数先頭 VA (`define @function_<VA>`)。m11_icall の target は VA (icall キー) で、
#         guest メモリに VA のまま入るのは設計どおり。→ 分類 A (未 remap に数えない)。
#   data: IR が `inttoptr (i64|i32 N to ptr)` のポインタとして使う定数 N のうち、
#         [0x400000, 0x400000+0x1ac0000) に入り、関数先頭ではなく、PE の非実行セクションを指すもの。
#         guest データのポインタは LVA で持つ規則 (VA→LVA: REPORT_N1318) なので、新規 word に VA のまま
#         現れれば未 remap の疑い。→ 分類 B (残件として数える)。ただし下の data_image_lva は除く。
#   data_image_lva: data のうち、image の .reloc DIR64 地点に実行時の値として入っているもの。
#         LB=0 では LVA = RVA で、VA 定数と数値が重なる (LVA のポインタ表の値)。新規 word がこれを持つのは
#         イメージ由来の LVA のコピーと見なす。→ 分類 D (未 remap に数えない)。
#   それ以外の新規 word は分類 C (整数・計算結果。値だけでは判定しない)。
# 使い方: FL_WIN64_DIR=... python3 m11_ptrclass.py [IR] [--pe PE] [--image IMG] [--lb LB] [--out OUT]
#         FL_WIN64_DIR=... python3 m11_ptrclass.py --hits <M11_PTRCHECK_DUMP の出力>   (分類 B・D の内訳と IR の使用関数を表示)
import re, json, hashlib, argparse, os
import pefile

IMG_LO = 0x400000
IMG_SIZE = 0x1ac0000
DEF = re.compile(r'^define [^\n]*@function_([0-9a-fA-F]+)\(', re.M)
PTR = re.compile(r'inttoptr \((?:i64|i32) (\d+) to ptr\)|inttoptr (?:i64|i32) (\d+) to ptr')

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('ir', nargs='?', default=os.path.join(HERE, 'work', 'boot_final.ll'))
ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
ap.add_argument('--image', default=os.path.join(HERE, 'work', 'm11_image.bin'))
ap.add_argument('--lb', type=lambda s: int(s, 0), default=int(os.environ.get('M11_LB_BASE', '0'), 0))
ap.add_argument('--out', default=os.path.join(HERE, 'work', 'ptrclass', 'classes.json'))
ap.add_argument('--hits', metavar='DUMP', help='M11_PTRCHECK_DUMP の出力 (新規 word の "offset value") を分類 B・D について集計し、IR の使用関数を出す (classes.json は作らない)')
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
if base != IMG_LO:
    raise SystemExit('ImageBase が 0x%x (想定 0x%x)' % (base, IMG_LO))
secs = [(s.Name.rstrip(b'\0').decode(errors='replace'),
         base + s.VirtualAddress,
         base + s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData),
         bool(s.Characteristics & 0x20000000))  # IMAGE_SCN_MEM_EXECUTE
        for s in pe.sections]

def section_of(v):
    for s in secs:
        if s[1] <= v < s[2]:
            return s
    return None

with open(a.ir, 'rb') as f:
    raw = f.read()
ir = raw.decode('utf-8', errors='replace')
code = set(int(m, 16) for m in DEF.findall(ir))
ptr_consts = set()
for m in PTR.finditer(ir):
    v = int(m.group(1) or m.group(2))
    if IMG_LO <= v < IMG_LO + IMG_SIZE:
        ptr_consts.add(v)
data = set()
for v in ptr_consts:
    if v in code:
        continue
    s = section_of(v)
    if s is not None and not s[3]:
        data.add(v)

# image の .reloc DIR64 地点に実行時に入る値 (m11_image_gen.py が補正済み)。.text/.data/.rdata/.didata 内の地点だけ (image_gen と同じ範囲)。
with open(a.image, 'rb') as f:
    img = f.read()
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_BASERELOC']])
top = max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)
          for s in pe.sections if s.Name.rstrip(b'\0').decode(errors='replace') in ('.text', '.data', '.rdata', '.didata'))
image_ptr = set()
for blk in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
    for e in blk.entries:
        if e.struct.Data >> 12 != 10:
            continue
        r = blk.struct.VirtualAddress + (e.struct.Data & 0xfff)
        if r + 8 <= top:
            image_ptr.add(int.from_bytes(img[a.lb + r:a.lb + r + 8], 'little'))
data_image_lva = sorted(data & image_ptr)

if a.hits:
    rows = [l.split() for l in open(a.hits) if l.strip()]
    words = [(int(o), int(v)) for o, v in rows]
    hit_b = [(o, v) for o, v in words if v in data and v not in set(data_image_lva)]
    hit_d = [(o, v) for o, v in words if v in set(data_image_lva)]
    print('new words %d / A %d / B %d / D %d / C %d' % (len(words), sum(1 for _, v in words if v in code), len(hit_b), len(hit_d),
          sum(1 for _, v in words if v not in code and v not in data)))
    byv = {}
    for o, v in hit_b + hit_d:
        byv.setdefault(v, []).append(o)
    lines = ir.split('\n')
    use_fn = {}
    cur = None
    for l in lines:
        if l.startswith('define '):
            m = re.search(r'@function_([0-9a-fA-F]+)\(', l)
            cur = m.group(1) if m else None
        for m in PTR.finditer(l):
            v = int(m.group(1) or m.group(2))
            if v in byv and v not in use_fn:
                use_fn[v] = cur
    dset = set(data_image_lva)
    print('distinct B+D values %d' % len(byv))
    for v in sorted(byv, key=lambda x: -len(byv[x])):
        s = section_of(v)
        print('0x%x class=%s words=%d section=%s ir_use_fn=%s heap_offsets=%s' % (v, 'D' if v in dset else 'B', len(byv[v]),
              s[0] if s else '-', use_fn.get(v), ','.join('0x%x' % o for o in byv[v][:2])))
    raise SystemExit(0)

out = {
    'schema': 2,
    'ir': os.path.relpath(a.ir, HERE),
    'ir_sha256': hashlib.sha256(raw).hexdigest(),
    'pe_sha256': hashlib.sha256(open(a.pe, 'rb').read()).hexdigest(),
    'image_sha256': hashlib.sha256(img).hexdigest(),
    'lb': a.lb,
    'image_base': base,
    'range': [IMG_LO, IMG_LO + IMG_SIZE],
    'sections': [[n, lo, hi, ex] for (n, lo, hi, ex) in secs],
    'counts': {'code': len(code), 'ir_ptr_consts_in_range': len(ptr_consts), 'data': len(data), 'data_image_lva': len(data_image_lva)},
    'code': sorted(code),
    'data': sorted(data),
    'data_image_lva': data_image_lva,
}
os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, 'w') as f:
    json.dump(out, f)
print('[ptrclass] code(A)=%d ir_ptr_consts_in_range=%d data=%d data_image_lva(D)=%d -> %s' % (len(code), len(ptr_consts), len(data), len(data_image_lva), a.out))
