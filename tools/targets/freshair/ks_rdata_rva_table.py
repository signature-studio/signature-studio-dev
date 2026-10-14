#!/usr/bin/env python3
"""value 17 関数の RVA 候補語 (rva_pair) が RVA テーブルか整数定数かを切り分ける (#2052)。

- rva_pair 語 (SC/KH とも .rdata 内の RVA・絶対ポインタでない) が指す先を読む。
- RVA テーブルなら、指す先の先頭から RVA dword (上位 32 bit が 0 かつセクション範囲内) が連続して並ぶ。
  連続長 run >= 2 を RVA テーブルとする。run の定義は先頭 dword から数えた連続長 (最大 16)。
- 指す先が RVA テーブルでない組は、RVA 差分による正規化の対象にならない (配置差で説明できない)。
  その組は整数定数 (または RVA でない別データ) として扱い、指す先の 8 B の一致を見る。
- 出力: 組ごとの run (SC/KH)、分類 (table / const)、指す先 8 B の一致、関数ごとの件数。
- --sensitivity: 分類器の陽性対照。.rdata を 32 B 境界で走査し、先頭ブロックの run で 3 区分 (0 / 1 / >=2) を数える。
usage: ks_rdata_rva_table.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <out.json>
       ks_rdata_rva_table.py --sensitivity <PE>
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_closure_share import rip_data
from ks_rdata_value import sec_of

CAP = 16
RUN_TABLE = 2


def is_rva(pe, v):
    return v != 0 and v >> 32 == 0 and sec_of(pe, v) is not None


def rva_run(pe, rva):
    """指す先の先頭から、RVA dword の連続長 (最大 CAP)。"""
    raw = pe.rva_bytes(rva, 4 * CAP)
    n = 0
    for v in struct.unpack('<%dI' % (len(raw) // 4), raw[:4 * (len(raw) // 4)]):
        if not is_rva(pe, v):
            break
        n += 1
    return n


def main(kp, sp, cls_json, out):
    kh, sc = Pe(kp), Pe(sp)
    rc = json.load(open(cls_json))
    tot = collections.Counter()
    funcs = {}
    for s, info in sorted(rc.items()):
        if info['cls'] != 'value':
            continue
        a = rip_data(sc, int(s, 16), 32)
        b = rip_data(kh, int(info['kh_va'], 16), 32)
        c = collections.Counter()
        for x, y in zip(a, b):
            xs, ys = struct.unpack('<4Q', x), struct.unpack('<4Q', y)
            for p, q in zip(xs, ys):
                if p == q:
                    continue
                sx, sy = sec_of(sc, p), sec_of(kh, q)
                sx = sx if sx and sx[0] == '.rdata' else None
                sy = sy if sy and sy[0] == '.rdata' else None
                if not (sx and sy and not sx[3] and not sy[3]):
                    continue
                c['rva_pair'] += 1
                rx, ry = rva_run(sc, sx[2]), rva_run(kh, sy[2])
                c['sc_run0' if rx == 0 else 'sc_run_table'] += 1
                c['kh_run0' if ry == 0 else 'kh_run_table'] += 1
                if rx >= RUN_TABLE or ry >= RUN_TABLE:
                    c['table_pair'] += 1
                else:
                    c['const_pair'] += 1
                    tx = sc.rva_bytes(sx[2], 8)
                    ty = kh.rva_bytes(sy[2], 8)
                    c['const_target8_eq' if tx == ty else 'const_target8_ne'] += 1
        funcs[s] = dict(kh_va=info['kh_va'], counts=dict(c))
        tot.update(c)
        print(s, dict(c))
    res = dict(sorted(tot.items()))
    print(json.dumps(res, sort_keys=True))
    json.dump(dict(summary=res, funcs=funcs), open(out, 'w'), indent=1, sort_keys=True)


class _Raw:
    """.text/.pdata を要求しない読み取り専用の PE 窓 (rva_run が使う属性だけ)。"""

    def __init__(self, path):
        import pefile
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = open(path, 'rb').read()
        self.secs = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}

    def rva_bytes(self, rva, n):
        s = next(s for s in self.pe.sections if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize)
        o = s.PointerToRawData + rva - s.VirtualAddress
        return self.data[o:o + n]


def sensitivity(path):
    pe = _Raw(path)
    rd = pe.secs['.rdata']
    lo, hi = rd.VirtualAddress, rd.VirtualAddress + rd.Misc_VirtualSize
    c = collections.Counter()
    for rva in range(lo, hi, 32):
        r = rva_run(pe, rva)
        c['run0' if r == 0 else 'run1' if r == 1 else 'run>=2'] += 1
    print(json.dumps(dict(path=os.path.basename(path), blocks=sum(c.values()), **dict(sorted(c.items()))), sort_keys=True))


if __name__ == '__main__':
    if sys.argv[1] == '--sensitivity':
        sensitivity(sys.argv[2])
    else:
        main(*sys.argv[1:5])
