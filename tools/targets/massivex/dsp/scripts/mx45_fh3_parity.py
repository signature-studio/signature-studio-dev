#!/usr/bin/env python3
"""MX-45 (#4161) 受入 1 の検証: C 移植 (tools/shimx/src/seh_fh3.c) と Python 正本 (mx39_funclet_reach.fh3_funclets_capped)
が、PE の全 FH3 FuncInfo で同じ funclet 集合を返すことを確かめる。

C 側は shimx.h (emscripten 依存) を含むので、seh_fh3.c の本体を無改変のままコピーし、
stdint 型だけを持つ shimx.h の代役を置いて clang -shared でビルドし、ctypes で呼ぶ。
usage: mx45_fh3_parity.py <pe> <out.json> [<c_src>]
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mx6_pdata_eh as P  # noqa: E402
from mx39_funclet_reach import FH3, fh3_funclets_capped  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..', '..'))
SEH_FH3 = os.path.join(REPO, 'tools', 'shimx', 'src', 'seh_fh3.c')


def section_view(pe, data):
    """RVA 添字の平坦バッファ。セクションの raw 部分だけを置き、それ以外は 0 (mx6_pdata_eh.make_rva_reader と同じ読み)。
    ヘッダ (RVA 0 側) を含む mapped image は使わない: 未マップ RVA の読みが C と Python で食い違うため。"""
    size = pe.OPTIONAL_HEADER.SizeOfImage
    buf = bytearray(size)
    for s in reversed(pe.sections):
        va, rs = s.VirtualAddress, s.SizeOfRawData
        raw = s.PointerToRawData
        n = min(rs, size - va, len(data) - raw)
        if n > 0:
            buf[va:va + n] = data[raw:raw + n]
    return bytes(buf)


def build_native(src):
    d = tempfile.mkdtemp(prefix='mx45-fh3-')
    shutil.copy(src, os.path.join(d, 'seh_fh3.c'))
    with open(os.path.join(d, 'shimx.h'), 'w') as f:
        f.write('#include <stdint.h>\n')
    so = os.path.join(d, 'libfh3.so')
    subprocess.run(['clang', '-O1', '-shared', '-fPIC', '-o', so, os.path.join(d, 'seh_fh3.c')], check=True)
    lib = ctypes.CDLL(so)
    lib.shimx_fh3_funclets.restype = ctypes.c_int
    lib.shimx_fh3_funclets.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32,
                                       ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
    return lib


def main(pe_path, out_path, src=SEH_FH3):
    pe = pefile.PE(pe_path, fast_load=False)
    data = open(pe_path, 'rb').read()
    rd = P.make_rva_reader(pe, data)
    img = section_view(pe, data)
    iat = P.walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    entries = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            entries[st] = (e, ui)

    def handler_is_fh3(h):
        code = rd(h, 6) or b''
        if code[:2] == b'\xff\x25':
            return iat.get(h + 6 + int.from_bytes(code[2:6], 'little', signed=True)) == FH3
        return False

    fis = set()
    for st, (e, ui) in entries.items():
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0' or not (b[0] >> 3) & (P.EHANDLER | P.UHANDLER):
            continue
        hdr = 4 + 2 * ((b[2] + 1) & ~1)
        hb = rd(ui + hdr, 8)
        if hb is None or not handler_is_fh3(int.from_bytes(hb[:4], 'little')):
            continue
        fis.add(int.from_bytes(hb[4:8], 'little'))

    lib = build_native(src)
    buf = (ctypes.c_uint32 * 4096)()
    c = Counter()
    mismatch = []
    for fi in sorted(fis):
        py = fh3_funclets_capped(rd, fi)
        n = lib.shimx_fh3_funclets(img, len(img), fi, buf, 4096)
        if py is None:
            c['py_rejected'] += 1
            if n != -1:
                c['py_rej_c_accept'] += 1
                mismatch.append({'fi': hex(fi), 'py': None, 'c': n})
            continue
        if n < 0:
            c['c_rejected_py_accept'] += 1
            mismatch.append({'fi': hex(fi), 'py': len(py), 'c': n})
            continue
        cs = set(buf[i] for i in range(min(n, 4096)))
        if n != len(py) or cs != py:
            c['set_mismatch'] += 1
            mismatch.append({'fi': hex(fi), 'py': len(py), 'c': n})
        else:
            c['equal'] += 1
    res = {'fh3_funcinfos': len(fis), 'counts': dict(c), 'mismatch_sample': mismatch[:20],
           'c_source': os.path.relpath(src, REPO) if src.startswith(REPO) else src}
    with open(out_path, 'w') as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))
    return 0 if not mismatch else 1


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
