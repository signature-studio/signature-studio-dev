#!/usr/bin/env python3
"""間接呼出の到達先候補 (データ参照あり関数) を root に加えた推移閉包 (#537)。 lift/plugin_closure.py は変更しない。

  closure_indirect.py [--out-dir DIR]     前提: sampler_e2e.sh 実行済み (work/closure, work/winfuncs, work/fw_hash_counts.json) + `source sampler/env.sh`

定義 (plugin_closure.py と同じ語彙):
  base      = plugin_closure.py の閉包 (vtable override entry から `call/jmp rel32` の BFS。 ハッシュが 13 DLL 以上の関数は frontier で止める)
  root      = 非共通 (ハッシュの出現 DLL 数 < 13) の `.pdata` 関数のうち、base に無く、関数開始 VA が .pdata 以外の節 (コード節含む) に
              節先頭から 8 バイト整列の qword として載っているもの (unreached_unique.py と同じ定義)
  total     = base ∪ root から `call/jmp rel32` で到達する非共通関数 (BFS、framework は frontier で止める)
  callee    = total − base − root (root から直接呼出でだけ到達する関数)
  lea 残    = total の関数が `lea reg,[rip+X]` で開始 VA を取っている非共通関数のうち total に無いもの (関数ポインタをコードで取る経路。 root には加えない。 情報のみ)
検査 (全て満たさなければ exit 1):
  C1 正の対照: entry だけから BFS した結果が work/closure/block*.json の ranges と完全一致 (BFS 実装が plugin_closure.py と同じ)
  C2 root 数・バイトが work/sampler/unreached.json の dataref_funcs / dataref_bytes と一致 (unreached_unique.py と同一定義の再計算。 独立検算は C4)
  C3 total ⊆ 非共通関数 (framework を lift 対象に混ぜない) かつ base ⊆ total
  C4 別算法: 関数バイト列の E8/E9 rel32 を全オフセットで拾う過大近似 (命令境界を見ない) で閉包を取り、capstone 版 total ⊆ 過大近似版
出力: work/sampler/indirect/block<B>.ranges.txt (total の ranges、lift 入力)、work/sampler/indirect.json、stdout の表
"""
import argparse, json, os, re, struct, sys
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(P, '..', 'shared'))
import targets  # noqa: E402
from paths import FL_WIN64_DIR  # noqa: E402

FWTHR = 13
WORK = os.path.join(P, 'work')
JMPCALL = re.compile(rb'[\xe8\xe9]', re.S)


class Pe:
    def __init__(self, blk, cnt):
        fn = 'block%05d_PE.bin' % blk
        self.pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', fn), fast_load=True)
        pe = self.pe
        self.base = pe.OPTIONAL_HEADER.ImageBase
        pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
        pdata = pd.get_data()[:pd.Misc_VirtualSize]
        self.ends = {}
        for i in range(len(pdata) // 12):
            b, e, u = struct.unpack_from('<III', pdata, 12 * i)
            if b and not (u & 1):
                self.ends[b] = e
        text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
        self.tb, self.tv = text.get_data(), text.VirtualAddress
        fj = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % blk)))
        self.hmap = {x[0]: x[2] for x in fj['funcs']}
        self.fw = lambda f: cnt.get(self.hmap.get(f), 0) >= FWTHR if self.hmap.get(f) is not None else False
        self.nonfw = {f[0] for f in fj['funcs'] if cnt.get(f[2], 0) < FWTHR and f[0] in self.ends}
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        self._code = {}

    def body(self, f):
        return self.tb[f - self.tv: self.ends[f] - self.tv]

    def edges(self, f):
        """capstone で `call/jmp rel32` の到達先 (別 .pdata 関数) と、lea [rip+X] の到達先を返す"""
        if f in self._code:
            return self._code[f]
        calls, leas = set(), set()
        for ins in self.md.disasm(self.body(f), self.base + f):
            if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == 2:
                t = ins.operands[0].imm - self.base
                if t in self.ends and not (f <= t < self.ends[f]):
                    calls.add(t)
            elif ins.mnemonic == 'lea' and len(ins.operands) == 2:
                o = ins.operands[1]
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + o.mem.disp - self.base
                    if t in self.ends:
                        leas.add(t)
        self._code[f] = (calls, leas)
        return self._code[f]

    def edges_bytescan(self, f):
        b = self.body(f)
        out = set()
        for m in JMPCALL.finditer(b):
            o = m.start()
            if o + 5 > len(b):
                continue
            t = f + o + 5 + struct.unpack_from('<i', b, o + 1)[0]
            if t in self.ends and not (f <= t < self.ends[f]):
                out.add(t)
        return out

    def bfs(self, roots, edge):
        seen, fw_front, q = set(), set(), list(roots)
        while q:
            f = q.pop()
            if f in seen or f not in self.ends:
                continue
            if self.fw(f):
                fw_front.add(f)
                continue
            seen.add(f)
            q.extend(edge(f))
        return seen, fw_front

    def dataref(self):
        vals = []
        for s in self.pe.sections:
            if s.Name.rstrip(b'\0') == b'.pdata' or not (s.Characteristics & 0x40 or s.Characteristics & 0x20):
                continue
            d = s.get_data()[:s.Misc_VirtualSize]
            n = len(d) // 8
            if n > 0:
                vals.append(np.frombuffer(d[:8 * n], dtype='<u8'))
        allv = np.unique(np.concatenate(vals)) if vals else np.array([], dtype='<u8')
        return lambda rvas: {r for r, h in zip(rvas, np.isin(np.array([self.base + r for r in rvas], dtype='<u8'), allv)) if h}

    def size(self, fs):
        return sum(self.ends[f] - f for f in fs)

    def ranges(self, fs):
        return ['0x%x-0x%x' % (self.base + f, self.base + self.ends[f] - 1) for f in sorted(fs)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(WORK, 'sampler'))
    a = ap.parse_args()
    cnt = json.load(open(os.path.join(WORK, 'fw_hash_counts.json')))
    unr = json.load(open(os.path.join(WORK, 'sampler', 'unreached.json')))
    os.makedirs(os.path.join(a.out_dir, 'indirect'), exist_ok=True)
    out, bad = {}, []
    print('| プラグイン | base 関数 / B | root (データ参照あり) 関数 / B | callee (root からの直接呼出) 関数 / B | **total 関数 / B** | 非共通に占める total (関数 % / B %) | frontier 関数 / B | lea 残 関数 / B | 非共通のうち未到達 関数 / B |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
    for name, blk, _ in targets.SHELLS:
        x = Pe(blk, cnt)
        clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % blk)))
        entries = [int(v, 16) - x.base for v in clo['entries'].values()]
        base_ref = {int(r.split('-')[0], 16) - x.base for r in clo['ranges']}
        base, _ = x.bfs(entries, lambda f: x.edges(f)[0])
        c1 = base == base_ref and len(base) > 0
        cand = sorted(x.nonfw - base)
        roots = x.dataref()(cand) if cand else set()
        total, front = x.bfs(list(base) + sorted(roots), lambda f: x.edges(f)[0])
        callee = total - base - roots
        leas = set()
        for f in total:
            leas |= x.edges(f)[1]
        lea_res = {f for f in leas if f in x.nonfw and f not in total}
        rest = x.nonfw - total
        u = unr[name]
        c2 = len(roots) == u['dataref_funcs'] and x.size(roots) == u['dataref_bytes']
        c3 = total <= x.nonfw and base <= total and roots <= total
        over, _ = x.bfs(list(base | roots), x.edges_bytescan)
        c4 = total <= over
        for tag, ok in (('C1 base 再現', c1), ('C2 root = unreached.json', c2), ('C3 total ⊆ 非共通 / base ⊆ total', c3), ('C4 capstone ⊆ byte 走査', c4)):
            if not ok:
                bad.append('%s: %s' % (name, tag))
        open(os.path.join(a.out_dir, 'indirect', 'block%05d.ranges.txt' % blk), 'w').write(','.join(x.ranges(total)))
        out[name] = {'block': blk, 'nonfw_funcs': len(x.nonfw), 'nonfw_bytes': x.size(x.nonfw),
                     'base_funcs': len(base), 'base_bytes': x.size(base), 'root_funcs': len(roots), 'root_bytes': x.size(roots),
                     'callee_funcs': len(callee), 'callee_bytes': x.size(callee), 'total_funcs': len(total), 'total_bytes': x.size(total),
                     'frontier_funcs': len(front), 'frontier_bytes': x.size(front), 'lea_residual_funcs': len(lea_res), 'lea_residual_bytes': x.size(lea_res),
                     'unreached_funcs': len(rest), 'unreached_bytes': x.size(rest),
                     'bytescan_total_funcs': len(over), 'bytescan_total_bytes': x.size(over), 'checks': {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4}}
        o = out[name]
        f = lambda k: '%s / %s' % (format(o[k + '_funcs'], ','), format(o[k + '_bytes'], ','))
        print('| %s | %s | %s | %s | **%s** | %.1f / %.1f | %s | %s | %s |' % (
            name, f('base'), f('root'), f('callee'), f('total'), 100.0 * o['total_funcs'] / o['nonfw_funcs'], 100.0 * o['total_bytes'] / o['nonfw_bytes'],
            f('frontier'), f('lea_residual'), f('unreached')))
    tot = {k: sum(v[k] for v in out.values()) for k in ('base_funcs', 'base_bytes', 'root_funcs', 'root_bytes', 'callee_funcs', 'callee_bytes', 'total_funcs', 'total_bytes')}
    out['_sum'] = tot
    print('| 計 | %s / %s | %s / %s | %s / %s | **%s / %s** | | | | |' % tuple(format(tot[k], ',') for k in (
        'base_funcs', 'base_bytes', 'root_funcs', 'root_bytes', 'callee_funcs', 'callee_bytes', 'total_funcs', 'total_bytes')))
    json.dump(out, open(os.path.join(a.out_dir, 'indirect.json'), 'w'), indent=1)
    for b in bad:
        print('FAIL', b, file=sys.stderr)
    print('closure_indirect: %s' % ('FAIL %d' % len(bad) if bad else 'PASS 4 checks x %d plugins' % len(targets.SHELLS)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
