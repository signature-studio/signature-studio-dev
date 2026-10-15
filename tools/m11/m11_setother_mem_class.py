#!/usr/bin/env python3
"""set_other 非 imm 台帳のうち、メモリ読込・lea の 256 件 (#3142 / M11-N174) の接続方式による 3 値分類.

入力は m11_setother_nonimm_class.py が出す nonimm_class_rows.json のうち、理由が load_* / lea_* / chain>load_* の行.
IR は変更しない (分類と値の算出のみ). 区分:
  実値化   : rip 相対の読込 (load_global) で、読込先が読み取り専用セクション (IMAGE_SCN_MEM_WRITE なし) かつ
             Base Relocation の fixup に掛からない範囲。値は PE ファイル内のバイト (幅と符号拡張は命令どおり)。
  復元不能 : 読込先が書込可能なのに保証が無い等の理由で、呼出し後の値が確定しない (本測定では 0 件を想定)。
  未決     : 上記以外。接続方式 (conn) ごとに「IR のどの対象へ結ぶか」を書く:
             global_store : 書込可能グローバル (.data/.bss)。対象は呼出し元 CFG 上の最後のグローバル格納 (store)。
             reloc_global : 読み取り専用だが fixup に掛かる範囲。値はロード時に変わり得る。
             stack_slot   : [rbp/rsp + d] の読込。対象は同じ slot への最後の格納 (store) (CFG 到達定義).
             ptr_mem      : [reg + d] のポインタ経由読込。対象はポインタ先のメモリ SSA (別名解析が要る).
             alloca       : lea [rbp/rsp + d]。対象はフレーム slot に対応する alloca.
             gep          : lea [reg + d] (ポインタ演算)。対象は基底 reg の SSA 値に対する GEP.
  chain>X  : 終端が X (接続方式は X と同じ) であることを示す。

使い方: python3 m11_setother_mem_class.py nonimm_class_rows.json --pe PE
出力: 区分別件数 (stdout)、行ごとの結果を mem_class_rows.json (入力と同じ dir) に書く。
"""
import argparse, bisect, collections, json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
sys.path.insert(0, HERE)
import capstone
import pefile
import ldmach

ap = argparse.ArgumentParser()
ap.add_argument('rows'); ap.add_argument('--pe', required=True)
a = ap.parse_args()
dirn = os.path.dirname(os.path.abspath(a.rows))
rows = json.load(open(a.rows))
mem = [x for x in rows if re.sub(r'^chain>', '', x['reason']).startswith(('load_', 'lea_'))]
mach = ldmach.Machine(a.pe)
pe = pefile.PE(a.pe, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_BASERELOC']])
BASE = pe.OPTIONAL_HEADER.ImageBase
SECS = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.Characteristics,
         s.PointerToRawData, s.SizeOfRawData, s.Name.rstrip(b'\0').decode('latin1')) for s in pe.sections]
RELOC = []
for blk in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
    for e in blk.entries:
        if e.rva:
            RELOC.append(e.rva)
RELOC.sort()
CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
WIDTH = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
M64 = (1 << 64) - 1
RIP = re.compile(r'(byte|word|dword|qword) ptr \[rip \+ (0x[0-9a-f]+|\d+)\]')
SIGNED = ('movsx', 'movsxd')


def sec_of(rva):
    for va, size, ch, praw, sraw, nm in SECS:
        if va <= rva < va + size:
            return (va, ch, praw, sraw, nm)
    return None


def reloc_hit(lo, hi):
    i = bisect.bisect_left(RELOC, lo - 7)
    return i < len(RELOC) and RELOC[i] < hi


def raw_read(rva, n):
    """PE ファイル (生の raw データ) から rva の n バイトを読む。ldmach を通さない別経路の照合用。"""
    s = sec_of(rva)
    if s is None:
        return None
    va, ch, praw, sraw, nm = s
    off = rva - va
    if off + n > sraw:
        return None
    with open(a.pe, 'rb') as f:
        f.seek(praw + off)
        return f.read(n)


def load_const(row):
    """rip 相対読込の行 (def 命令) から (区分, 値, 幅, 理由)。区分 '実値化' 以外は値 None。"""
    rva = int(row['def'], 16) - BASE
    code = mach.read(rva, 16)
    ins = next(CS.disasm(code, rva + BASE), None)
    if ins is None:
        return ('未決', None, None, 'decode_fail')
    m = RIP.search(row['def_insn'] or '')
    if not m:
        return ('未決', None, None, 'no_rip_operand')
    width = WIDTH[m.group(1)]
    target = ins.address + ins.size + int(m.group(2), 0) - BASE
    s = sec_of(target)
    if s is None:
        return ('未決', None, width, 'no_section')
    if s[1] & 0x80000000:
        return ('未決', None, width, 'writable:' + s[4])
    if reloc_hit(target, target + width // 8):
        return ('未決', None, width, 'reloc:' + s[4])
    data = mach.read(target, width // 8) if s[4] == '.text' else raw_read(target, width // 8)
    if data is None or len(data) != width // 8:
        return ('未決', None, width, 'read_fail:' + s[4])
    if raw_read(target, width // 8) != data:
        return ('未決', None, width, 'verify_mismatch:' + s[4])
    v = int.from_bytes(data, 'little')
    if ins.mnemonic in SIGNED:
        if v >> (width - 1):
            v -= 1 << width
        v &= M64
    return ('実値化', v, width, 'load_global:' + s[4])


def conn_of(reason):
    base = re.sub(r'^chain>', '', reason)
    if base == 'load_global':
        return 'global_store'
    if base == 'load_stack':
        return 'stack_slot'
    if base == 'load_ptr':
        return 'ptr_mem'
    if base == 'lea_stack':
        return 'alloca'
    if base == 'lea_ptr':
        return 'gep'
    return 'other:' + base


out = []
for x in mem:
    r = dict(x)
    base = re.sub(r'^chain>', '', x['reason'])
    if base == 'load_global' and not x['reason'].startswith('chain>'):
        cls, val, width, why = load_const(x)
        r.update({'class': cls, 'value': val, 'width': width, 'why': why})
        if cls == '実値化':
            r['conn'] = 'const_read'
        else:
            key = why.split(':')[0]
            r['conn'] = {'writable': 'global_store', 'reloc': 'reloc_global'}.get(key, 'other:' + key)
    else:
        r.update({'class': '未決', 'value': None, 'width': None, 'why': base, 'conn': conn_of(x['reason'])})
    out.append(r)
json.dump(out, open(os.path.join(dirn, 'mem_class_rows.json'), 'w'), ensure_ascii=False, indent=1)

print('[mem-class] 対象 %d 件 (load_*/lea_*/chain>load_*)' % len(out))
cnt = collections.Counter(r['class'] for r in out)
print('  実値化   %d' % cnt['実値化'])
print('  復元不能 %d' % cnt['復元不能'])
print('  未決     %d' % cnt['未決'])
print('  未分類   %d' % (len(out) - cnt['実値化'] - cnt['復元不能'] - cnt['未決']))
print('[mem-class] 接続方式 × 区分 (件数)')
for k, v in sorted(collections.Counter((r['conn'], r['class']) for r in out).items()):
    print('  %-16s %-8s %d' % (k[0], k[1], v))
print('[mem-class] 実値化 (値・幅・読込先)')
for r in out:
    if r['class'] == '実値化':
        print('  %s %s value=0x%x width=%d %s' % (r['caller'], r['def_insn'], r['value'], r['width'], r['why']))
