#!/usr/bin/env python3
"""mac x86_64 スライスの関数単位解析 (win_funcs.py の mac 版)。

関数境界 = LC_FUNCTION_STARTS。位置非依存ハッシュで framework / 固有を cross-plugin 判定。
出力: work/mac_unique.json {relpath: {...}}   (対象: Plugins/Fruity の全 Mach-O の x86_64 スライス)
"""
import os, sys, json, struct, hashlib, re, collections
from multiprocessing import Pool
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'icall', 'disp_size'))
import dispfix as DF      # CAB-229: capstone の disp_size は 66 prefix 付き disp32 で 2 を返す (D9)
WORK = os.path.join(HERE, '..', 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_MAC_DIR  # noqa: E402
ROOT = os.path.join(FL_MAC_DIR, 'pkg_extract', 'payload_out', 'Applications', 'FL Studio 2026.app', 'Contents', 'Resources', 'FL', 'Plugins', 'Fruity')
FP_RE = re.compile(r'^v?(add|sub|mul|div|sqrt|min|max|rcp|rsqrt|fmadd|fmsub|fnmadd|fnmsub|hadd|dp)(ss|sd|ps|pd)$')


def uleb(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7f) << s
        s += 7
        if not x & 0x80:
            return r, i


def x86_slice(d):
    if struct.unpack_from('>I', d, 0)[0] == 0xcafebabe:
        n = struct.unpack_from('>I', d, 4)[0]
        for i in range(n):
            cpu, sub, off, sz, al = struct.unpack_from('>iiIII', d, 8 + 20 * i)
            if cpu == 0x01000007:
                return d[off: off + sz]
        return None
    if struct.unpack_from('<I', d, 0)[0] == 0xfeedfacf and struct.unpack_from('<i', d, 4)[0] == 0x01000007:
        return d
    return None


def analyze(path):
    d = open(path, 'rb').read()
    sl = x86_slice(d)
    if sl is None:
        return path, None
    ncmds = struct.unpack_from('<I', sl, 16)[0]
    off = 32
    text_seg = None
    fs = None
    secs = []
    for _ in range(ncmds):
        cmd, csz = struct.unpack_from('<II', sl, off)
        if cmd == 0x19:
            segname = sl[off + 8: off + 24].rstrip(b'\0').decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', sl, off + 24)
            nsect = struct.unpack_from('<I', sl, off + 64)[0]
            if segname == '__TEXT':
                text_seg = (vmaddr, fileoff)
            so = off + 72
            for _s in range(nsect):
                sn = sl[so: so + 16].rstrip(b'\0').decode()
                sg = sl[so + 16: so + 32].rstrip(b'\0').decode()
                addr, sz, foff = struct.unpack_from('<QQI', sl, so + 32)
                secs.append((sg, sn, addr, sz, foff))
                so += 80
        elif cmd == 0x26:
            fs = struct.unpack_from('<II', sl, off + 8)
        off += csz
    if not fs or not text_seg:
        return path, None
    tsec = [s for s in secs if s[0] == '__TEXT' and s[1] == '__text'][0]
    tva, tsz, tfo = tsec[2], tsec[3], tsec[4]
    blob = sl[fs[0]: fs[0] + fs[1]]
    i = 0
    addr = text_seg[0]
    starts = []
    while i < len(blob):
        v, i = uleb(blob, i)
        if v == 0:
            break
        addr += v
        starts.append(addr)
    starts = [s for s in starts if tva <= s < tva + tsz]
    starts.sort()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    res = []
    for k, b in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else tva + tsz
        raw = sl[tfo + (b - tva): tfo + (e - tva)]
        norm = bytearray(raw)
        nfp = ninsn = 0
        for ins in md.disasm(raw, b):
            ninsn += 1
            mn = ins.mnemonic
            o = ins.address - b
            if FP_RE.match(mn):
                nfp += 1
            if (mn == 'call' or mn.startswith('j')) and ins.imm_size == 4:
                tgt = ins.operands[0].imm
                if not (b <= tgt < e):
                    for q in range(ins.imm_offset, ins.imm_offset + 4):
                        norm[o + q] = 0
                continue
            dsp = DF.disp_span(ins)
            if dsp and dsp[1] == 4:
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        for q in range(dsp[0], dsp[0] + 4):
                            norm[o + q] = 0
                        break
        res.append([b - tva, e - b, hashlib.sha1(bytes(norm)).hexdigest()[:12], ninsn, nfp])
    return path, res


def main():
    paths = []
    for dp, dn, fn in os.walk(ROOT):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p) or os.path.getsize(p) < 4096:
                continue
            with open(p, 'rb') as fh:
                m = fh.read(4)
            if m in (b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe'):
                paths.append(p)
    print('mach-o files', len(paths))
    raw = os.path.join(WORK, 'mac_funcs_raw.json')
    if os.path.exists(raw) and '--reuse' in sys.argv:
        out = json.load(open(raw))
    else:
        out = {}
        with Pool(14) as pool:
            for p, r in pool.imap_unordered(analyze, paths):
                if r is not None:
                    out[os.path.relpath(p, ROOT)] = r
        json.dump(out, open(raw, 'w'))
    # cross-plugin classification restricted to FPC main dylibs (name ends with _x64.dylib in plugin root)
    mains = [k for k in out if k.count('/') == 2 and k.endswith('_x64.dylib')]
    cnt = collections.Counter()
    for k in mains:
        for h in {x[2] for x in out[k]}:
            cnt[h] += 1
    FW = max(10, int(0.10 * len(mains)))
    summary = {}
    for k, fl in out.items():
        is_main = k in mains
        fw = sh = un = ufn = ufp = 0
        for (rva, sz, h, ni, nfp) in fl:
            c = cnt.get(h, 0) if is_main else 0
            if is_main and c >= FW:
                fw += sz
            elif is_main and c > 2:
                sh += sz
            else:
                un += sz
                ufn += 1
                ufp += nfp
        summary[k] = {'main': is_main, 'nfunc': len(fl), 'bytes': sum(x[1] for x in fl), 'fw_bytes': fw,
                      'shared_bytes': sh, 'uniq_bytes': un, 'uniq_funcs': ufn, 'uniq_fp': ufp}
    json.dump(summary, open(os.path.join(WORK, 'mac_unique.json'), 'w'))
    print('main dylibs', len(mains), 'framework threshold >=', FW, '->', os.path.join(WORK, 'mac_unique.json'))


if __name__ == '__main__':
    main()
