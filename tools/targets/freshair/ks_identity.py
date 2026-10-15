#!/usr/bin/env python3
"""SlateCore (Fresh Air) と HeartCore (Kilohearts) の同名 snapin Dsp 実装の同一性を機械語で比較する (FA-5 / #52)。

RTTI で `<ns>::XDsp` の vtable を両バイナリから引き、各仮想関数を capstone で逆アセンブルして正規化し、
slot 総当たり (vtable 形が違う: KH 20 slot / SlateCore 17 slot) で最良一致を取る。

正規化レベル (厳しい順)
  E  : 命令列の完全一致。rip 相対 / call・jmp 先 / 絶対アドレス即値だけを抽象化 (構造体 offset・即値・レジスタは残す)
  R  : E からさらに数値 (disp・即値) を全て落とす。レジスタ名は残す
  M  : mnemonic 列のみ
類似度は M 列の difflib.SequenceMatcher ratio。

usage: ks_identity.py <HeartCore.core_64> <SlateCore.core_64> <out.json>
"""
import sys, re, json, struct, difflib, collections
import pefile
import capstone

NUM = re.compile(r'0x[0-9a-f]+')
RIP = re.compile(r'\[rip [+-] 0x[0-9a-f]+\]')
DSP = re.compile(r'\.\?AV\w*Dsp@\w+@@')


class Pe:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = open(path, 'rb').read()
        self.secs = {s.Name.rstrip(b'\0').decode(): s for s in self.pe.sections}
        t = self.secs['.text']
        self.t_lo, self.t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
        pd = self.secs['.pdata']
        raw = self.data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
        ents = []
        for i in range(len(raw) // 12):
            b, e, u = struct.unpack_from('<III', raw, i * 12)
            if b:
                try:
                    ch = (self.rva_bytes(u & ~1, 1)[0] >> 3) & 4
                except StopIteration:
                    ch = 0
                ents.append((b, e, ch))
        ents.sort()
        # UNW_FLAG_CHAININFO(4) の連続チャンクを親関数へ併合 (closure.py と同じ。非連続 (cold 分離) チャンクは併合しない)
        self.fn = {}
        last = None
        for b, e, ch in ents:
            if ch and last is not None and self.fn[last] == b:
                self.fn[last] = e
            else:
                self.fn[b] = e
                last = b
        self.starts = sorted(self.fn)
        self.img_hi = self.base + max(s.VirtualAddress + s.Misc_VirtualSize for s in self.pe.sections)
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = False

    def rva_bytes(self, rva, n):
        s = next(s for s in self.pe.sections if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize)
        o = s.PointerToRawData + rva - s.VirtualAddress
        return self.data[o:o + n]

    def disasm(self, va):
        rva = va - self.base
        if rva in self.fn:
            size = self.fn[rva] - rva
            return list(self.md.disasm(self.rva_bytes(rva, size), va)), True
        # leaf (pdata 無し): ret で、かつ前方分岐先を越えたら終了
        out, far = [], va
        for ins in self.md.disasm(self.rva_bytes(rva, 4096), va):
            out.append(ins)
            if ins.mnemonic.startswith('j'):
                m = re.fullmatch(r'0x([0-9a-f]+)', ins.op_str)
                if m and int(m.group(1), 16) > ins.address:
                    far = max(far, int(m.group(1), 16))
            if ins.mnemonic in ('ret', 'int3') and ins.address + ins.size > far:
                break
            if len(out) > 1500:
                break
        return out, False

    def norm(self, ins_list):
        e, r, m = [], [], []
        lo, hi = self.base, self.img_hi
        for i in ins_list:
            mn, op = i.mnemonic, i.op_str
            if mn == 'call' and re.fullmatch(r'0x[0-9a-f]+', op):
                op = 'F'
            elif mn.startswith('j') and re.fullmatch(r'0x[0-9a-f]+', op):
                op = 'J'
            op = RIP.sub('[rip+G]', op)

            def absaddr(mm):
                v = int(mm.group(0), 16)
                return 'A' if lo <= v < hi else mm.group(0)
            op = NUM.sub(absaddr, op)
            e.append(mn + ' ' + op)
            r.append(mn + ' ' + NUM.sub('N', op))
            m.append(mn)
        return e, r, m


def vtables(path, tmpjson):
    import subprocess, os
    rw = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kilohearts', 'scripts', 'rtti_walk.py')
    subprocess.run([sys.executable, rw, path, tmpjson], check=True, stderr=subprocess.DEVNULL)
    return json.load(open(tmpjson))


def main(kh_path, sc_path, out):
    import tempfile, os
    td = tempfile.mkdtemp()
    kh, sc = Pe(kh_path), Pe(sc_path)
    kv = vtables(kh_path, os.path.join(td, 'k.json'))
    sv = vtables(sc_path, os.path.join(td, 's.json'))
    cache = {}

    def get(pe, va, tag):
        key = (tag, va)
        if key not in cache:
            ins, pd = pe.disasm(va)
            cache[key] = (len(ins), sum(i.size for i in ins), pe.norm(ins), pd)
        return cache[key]

    classes = sorted(n for n in sv if DSP.fullmatch(n) and n in kv)
    res = {}
    for n in classes:
        ks, ss = kv[n][0]['slots'], sv[n][0]['slots']
        kf = [get(kh, int(v, 16), 'k') for v in ks]
        sf = [get(sc, int(v, 16), 's') for v in ss]
        pairs = []
        for i, a in enumerate(kf):
            for j, b in enumerate(sf):
                if a[0] < 6 or b[0] < 6:
                    continue
                if max(a[0], b[0]) > 2.5 * min(a[0], b[0]):
                    continue
                if a[2][0] == b[2][0]:
                    rm = 1.0
                else:
                    rm = difflib.SequenceMatcher(None, a[2][2], b[2][2], autojunk=False).ratio()
                pairs.append((rm, i, j))
        pairs.sort(reverse=True)
        used_k, used_s, best = set(), set(), []
        for rm, i, j in pairs:
            if i in used_k or j in used_s:
                continue
            used_k.add(i); used_s.add(j)
            best.append({'kh_slot': i, 'sc_slot': j, 'kh_va': ks[i], 'sc_va': ss[j],
                         'kh_ninsn': kf[i][0], 'sc_ninsn': sf[j][0], 'kh_bytes': kf[i][1], 'sc_bytes': sf[j][1],
                         'ratio_M': round(rm, 4),
                         'exact_E': kf[i][2][0] == sf[j][2][0], 'exact_R': kf[i][2][1] == sf[j][2][1],
                         'exact_M': kf[i][2][2] == sf[j][2][2]})
        # process: KH slot 14 <-> SlateCore slot 12 (vtable 形差 +2 slot。Gain 609/446 B・Compressor 1724/1664 B が既知の process)
        def cmp(i, j):
            if i >= len(kf) or j >= len(sf):
                return None
            a, b = kf[i], sf[j]
            r = {}
            for lvl, k in (('E', 0), ('R', 1), ('M', 2)):
                r['ratio_' + lvl] = round(difflib.SequenceMatcher(None, a[2][k], b[2][k], autojunk=False).ratio(), 4)
                r['exact_' + lvl] = a[2][k] == b[2][k]
            r.update(kh_slot=i, sc_slot=j, kh_va=ks[i], sc_va=ss[j], kh_ninsn=a[0], sc_ninsn=b[0], kh_bytes=a[1], sc_bytes=b[1])
            return r
        # SlateCore 側は命令数 3 以上の slot のうち M 比が最大の slot を process 候補にする (固定 slot 12 は process でないクラスがある)
        cands = [(cmp(14, j), j) for j in range(len(sf)) if sf[j][0] >= 3]
        cands = [c for c, _ in cands if c]
        proc = max(cands, key=lambda c: (c['ratio_M'], c['ratio_E'])) if cands else None
        fixed = cmp(14, 12)
        res[n] = {'kh_nslots': len(ks), 'sc_nslots': len(ss), 'process_pair': proc, 'fixed_slot12': fixed, 'pairs': best}
    json.dump(res, open(out, 'w'), indent=1)

    print('class'.ljust(22), 'kh_B'.rjust(6), 'sc_B'.rjust(6), 'kh_n'.rjust(5), 'sc_n'.rjust(5), ' ratioE ratioR ratioM  exactE/R/M')
    tot = collections.Counter()
    for n, r in res.items():
        p = r['process_pair']
        name = re.match(r'\.\?AV(\w+)Dsp@', n).group(1)
        if not p:
            print(name.ljust(22), 'no slot')
            continue
        print(name.ljust(22), str(p['kh_bytes']).rjust(6), str(p['sc_bytes']).rjust(6), str(p['kh_ninsn']).rjust(5),
              str(p['sc_ninsn']).rjust(5), f"  {p['ratio_E']:.3f}  {p['ratio_R']:.3f}  {p['ratio_M']:.3f}   ",
              int(p['exact_E']), int(p['exact_R']), int(p['exact_M']))
        tot['n'] += 1
        for l in 'ERM':
            tot['exact_' + l] += p['exact_' + l]
        tot['ratioM>=0.9'] += p['ratio_M'] >= 0.9
        tot['ratioM>=0.7'] += p['ratio_M'] >= 0.7
        tot['sameB'] += p['kh_bytes'] == p['sc_bytes']
    for b in (x for r in res.values() for x in r['pairs']):
        tot['allpairs'] += 1
        tot['allpairs_exactE'] += b['exact_E']; tot['allpairs_exactM'] += b['exact_M']
    print(dict(tot))


if __name__ == '__main__':
    main(*sys.argv[1:4])
