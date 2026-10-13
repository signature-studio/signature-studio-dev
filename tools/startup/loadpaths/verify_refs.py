#!/usr/bin/env python3
"""verify_refs.py — loadpaths.json の静的根拠 (関数・文字列参照・呼出辺) を FLEngine_x64.dll で機械照合する (ST-T14 / #39)。

stdlib のみ。逆アセンブラは使わず、次の 3 つを PE から直接数える:
  1. 関数境界 = .pdata (RUNTIME_FUNCTION) の BeginAddress/EndAddress
  2. 文字列参照 = .text 内の RIP 相対 `lea/mov r, [rip+disp32]` (REX? 8D|8B modrm(mod=00,rm=101)) の参照先が UTF-16LE または ASCII の NUL 終端リテラルと一致
  3. 呼出辺 = .text 内の `E8 rel32` の呼出先が callee の関数先頭
照合内容 (loadpaths.json):
  - groups[].readers[].va が関数先頭であること
  - claims[] = {va, refs[]}: 関数 va が refs の各文字列を参照すること
  - calls[] = [caller, callee]: caller 関数の中に callee への直接 call があること

usage: verify_refs.py <FLEngine_x64.dll> [spec.json]   exit 0 = 全件一致 / 1 = 不一致あり
"""
import bisect
import json
import os
import re
import struct
import sys


class PE:
    def __init__(self, data):
        self.d = data
        pe = struct.unpack_from('<I', data, 0x3C)[0]
        assert data[pe:pe + 4] == b'PE\0\0'
        nsec = struct.unpack_from('<H', data, pe + 6)[0]
        optsz = struct.unpack_from('<H', data, pe + 20)[0]
        opt = pe + 24
        assert struct.unpack_from('<H', data, opt)[0] == 0x20B, 'PE32+ ではない'
        self.base = struct.unpack_from('<Q', data, opt + 24)[0]
        dd = opt + 112
        exc_rva, exc_sz = struct.unpack_from('<II', data, dd + 8 * 3)
        self.secs = []
        so = opt + optsz
        for i in range(nsec):
            name, vsz, va, rsz, raw, _r, _l, _n, _nl, ch = struct.unpack_from('<8sIIIIIIHHI', data, so + 40 * i)
            self.secs.append((name.rstrip(b'\0').decode(), va, max(vsz, rsz), raw, rsz, ch))
        ex = self.rva2off(exc_rva)
        funcs = []
        for i in range(exc_sz // 12):
            b, e, _u = struct.unpack_from('<III', data, ex + 12 * i)
            funcs.append((b, e))
        funcs.sort()
        self.funcs = funcs
        self.starts = [b for b, _ in funcs]

    def rva2off(self, rva):
        for _n, va, sz, raw, rsz, _ch in self.secs:
            if va <= rva < va + sz:
                return raw + (rva - va) if rva - va < rsz else None
        return None

    def func_of(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]:
            return self.funcs[i]
        return None

    def literal(self, rva):
        off = self.rva2off(rva)
        if off is None:
            return set()
        out = set()
        w = bytearray()
        for k in range(0, 600, 2):
            c = self.d[off + k:off + k + 2]
            if len(c) < 2 or c == b'\0\0':
                break
            w += c
        if w:
            try:
                out.add(bytes(w).decode('utf-16le'))
            except UnicodeDecodeError:
                pass
        a = self.d[off:off + 300]
        e = a.find(b'\0')
        if e > 0:
            try:
                out.add(a[:e].decode('latin-1'))
            except UnicodeDecodeError:
                pass
        return out

    def scan(self):
        """戻り (strrefs: {func_begin_rva: set(literal)}, calls: {func_begin_rva: set(callee_rva)})"""
        strrefs, calls = {}, {}
        rx = re.compile(rb'(?=([\x40-\x4f]?[\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]))', re.S)
        for name, va, _sz, raw, rsz, ch in self.secs:
            if not ch & 0x20000000:
                continue
            blob = self.d[raw:raw + rsz]
            for m in rx.finditer(blob):
                i, ln = m.start(), len(m.group(1))
                if i + ln + 4 > len(blob):
                    continue
                disp = struct.unpack_from('<i', blob, i + ln)[0]
                rva = va + i
                f = self.func_of(rva)
                if not f:
                    continue
                strrefs.setdefault(f[0], set()).update(self.literal(rva + ln + 4 + disp))
            i = blob.find(b'\xe8')
            while i >= 0 and i + 5 <= len(blob):
                rel = struct.unpack_from('<i', blob, i + 1)[0]
                rva = va + i
                f = self.func_of(rva)
                if f:
                    calls.setdefault(f[0], set()).add(rva + 5 + rel)
                i = blob.find(b'\xe8', i + 1)
        return strrefs, calls


def main(argv):
    dll = argv[1]
    spec = json.load(open(argv[2] if len(argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loadpaths.json')))
    pe = PE(open(dll, 'rb').read())
    to_rva = lambda s: int(s, 16) - pe.base
    strrefs, calls = pe.scan()
    starts = set(pe.starts)
    fails = []
    n_readers = n_refs = n_calls = 0
    for g in spec['groups']:
        for r in g['readers']:
            n_readers += 1
            if to_rva(r['va']) not in starts:
                fails.append(f"reader {g['id']} {r['va']}: 関数先頭でない")
    for c in spec['claims']:
        b = to_rva(c['va'])
        if b not in starts:
            fails.append(f"claim {c['va']}: 関数先頭でない")
            continue
        have = strrefs.get(b, set())
        for s in c['refs']:
            n_refs += 1
            if s not in have:
                fails.append(f"claim {c['va']}: 文字列 {s!r} を参照していない")
    for caller, callee in spec['calls']:
        n_calls += 1
        if to_rva(callee) not in starts:
            fails.append(f"call {caller}->{callee}: callee が関数先頭でない")
        elif to_rva(callee) not in calls.get(to_rva(caller), set()):
            fails.append(f"call {caller}->{callee}: 直接 call が無い")
    print(json.dumps({'functions_pdata': len(pe.funcs), 'readers': n_readers, 'claims': len(spec['claims']), 'string_refs': n_refs,
                      'call_edges': n_calls, 'fail': len(fails)}, ensure_ascii=False))
    for f in fails:
        print('FAIL', f)
    return 1 if fails else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv))
