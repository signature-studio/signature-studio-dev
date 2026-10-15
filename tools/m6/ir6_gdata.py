#!/usr/bin/env python3
# M6 #7: @global_var_* の全定義を DLL 実データ (VA-shift 済み) に差し替える IR pass.
# 出力: argv[2]
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
DATAB = 0x30000000

def fn(n):
    return '@global_var_' + n

def main():
    src, dst = sys.argv[1], sys.argv[2]
    W = Bin(WINF)
    text = open(src).read()
    names = sorted(set(re.findall(r"@global_var_([0-9a-f]+)\b", text)))
    print('[gdata] global refs:', len(names))

    def read_bytes(rva, sz):
        b = W.read_at(rva, sz)
        if b is None:
            b = bytes(sz)
        if len(b) < sz:
            b = b + bytes(sz - len(b))
        return b

    def to_llvm(b):
        # 'c"..."'-string 形の [N x i8] initializer:
        esc = ''
        for v in b:
            if v in (0x22, 0x5c):
                esc += chr(v) if 32 <= v < 127 and v not in (34, 92) else '\\%02x' % v
            elif 32 <= v < 127 and v not in (34, 92):
                esc += chr(v)
            else:
                esc += chr(v) if 32 <= v < 127 and v not in (34, 92) else '\\%02x' % v
        return '"' + esc + '"'

    ln = text.split('\n')
    out = []
    i = replaced = 0
    while i < len(ln):
        l = ln[i]
        m = re.match(r"^(@global_var_([0-9a-f]+)) = .*$", l)
        if m:
            va = int(m.group(2), 16)
            rva = va - DATAB
            tm = re.match(r"@[\w.$-]+ = (local_unnamed_addr )?(?:\w+ )?(\w+) ", l)
            t = tm.group(2) if tm else 'i8'
            sz = 8
            msz = re.search(r"\[(\d+) x (i8|i16|i32|i64|i128)\]", l)
            if msz:
                mul = dict(i8=1, i16=2, i32=4, i64=8, i128=16)[msz.group(2)]
                sz = int(msz.group(1)) * mul
            else:
                if t == 'i8': sz = 1
                elif t == 'i16': sz = 2
                elif t == 'i32': sz = 4
                elif t == 'i64': sz = 8
                elif t == 'i128': sz = 16
                elif t == 'i256': sz = 32
            b = read_bytes(rva, sz)
            out.append('%s = constant [%d x i8] ' % (m.group(1), sz) + ('c' + to_llvm(b)))
            replaced += 1
            i += 1
            continue
        out.append(l)
        i += 1
    text2 = '\n'.join(out)
    have = set(re.findall(r"(?m)^@global_var_([0-9a-f]+) = ", text2))
    add = []
    for nm in names:
        if nm in have:
            continue
        va = int(nm, 16)
        rva = va - DATAB
        b = read_bytes(rva, 8)
        add.append(fn(nm) + ' = global [8 x i8] c' + to_llvm(b))
    text2 = text2.rstrip() + '\n' + '\n'.join(add) + '\n'
    print('[gdata] replaced:', replaced, ' added:', len(add))
    for s2 in text2.split('\n')[14:17]:
        print('  ~', s2[:94])
    open(dst, 'w').write(text2)

if __name__ == '__main__':
    main()
