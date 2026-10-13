#!/usr/bin/env python3
"""x64c の no_wasm_definition 関数 (RTL 帯) の正体を PE から静的に分類する (#410).

usage: thunk_classify.py <block00031_PE.bin> <flelift_batch.jsonl> [--lo 0x401000] [--hi 0x456e98]
batch.jsonl は liftdiff batch の出力。verdict=unexec かつ unexec_reason=no_wasm_definition の VA を対象にし、
各関数の先頭命令が jmp [rip+disp32] (FF 25, import thunk) かを調べ、飛び先 IAT のヒント名 (DLL!関数名) で数える。
"""
import argparse, collections, json, struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe'); ap.add_argument('batch')
    ap.add_argument('--lo', default='0x401000'); ap.add_argument('--hi', default='0x456e98')
    a = ap.parse_args()
    lo, hi = int(a.lo, 16), int(a.hi, 16)

    d = open(a.pe, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    base = struct.unpack_from('<Q', d, pe + 24 + 24)[0]
    imp_rva = struct.unpack_from('<I', d, pe + 24 + 112 + 8)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + optsz + i * 40
        vs, va, rs, rp = struct.unpack_from('<IIII', d, o + 8)
        secs.append((va, vs, rp, rs))

    def off(rva):
        for sva, vs, rp, rs in secs:
            if sva <= rva < sva + max(vs, rs):
                return rp + rva - sva
        raise ValueError('rva %#x not in image' % rva)

    def cstr(rva):
        o = off(rva)
        return d[o:d.index(b'\0', o)]

    names = {}
    p = off(imp_rva)
    while True:
        oft, _, _, nm, ft = struct.unpack_from('<IIIII', d, p)
        if nm == 0:
            break
        dll = cstr(nm).decode()
        t = off(oft or ft)
        i = 0
        while True:
            v = struct.unpack_from('<Q', d, t + 8 * i)[0]
            if v == 0:
                break
            if v >> 63:
                names[ft + 8 * i] = '%s!ord%d' % (dll, v & 0xffff)
            else:
                names[ft + 8 * i] = '%s!%s' % (dll, cstr(v + 2).decode())
            i += 1
        p += 20

    vas = []
    for l in open(a.batch):
        r = json.loads(l)
        va = int(r['function']['va'], 16)
        if lo <= va < hi and r.get('verdict') == 'unexec' and r.get('unexec_reason') == 'no_wasm_definition':
            vas.append(va)

    kind = collections.Counter(); who = collections.Counter(); ins = collections.Counter()
    for va in vas:
        rva = va - base
        o = off(rva)
        if d[o:o + 2] == b'\xff\x25':
            disp = struct.unpack_from('<i', d, o + 2)[0]
            kind['jmp [rip+IAT] (import thunk)'] += 1
            who[names.get(rva + 6 + disp, 'UNKNOWN')] += 1
        else:
            kind['other: ' + d[o:o + 2].hex()] += 1
    print('no_wasm_definition in [%#x,%#x): %d' % (lo, hi, len(vas)))
    for k, v in kind.most_common():
        print('  %s %d' % (k, v))
    print('  distinct import slots: %d' % len(who))
    for k, v in who.most_common(12):
        print('    %4d %s' % (v, k))


if __name__ == '__main__':
    main()
