#!/usr/bin/env python3
"""MSVC C++ plugin DLL (Hardcore / Effector engine) の DSP 閉包: CreatePlugInstance → ctor が書く vptr → vtable の仮想関数 → 直接呼出の到達集合。
plugin_closure.py は Delphi の vtable (win_abi.json) 前提のため、C++ 用のエントリ抽出をここで行う (PLG-F6-2 #545)。

手順:
  1. export `CreatePlugInstance` から `jmp rel32` / `call rel32` を depth 3 まで辿り、`lea R, [rip+d]` の直後に `mov [X+0], R` (vptr 書込) がある vtable を seed にする
  2. vtable = `.rdata` 内の「.text を指す qword」の連続で、うち .pdata の開始 VA を指すものが 1 本以上あるもの (最小 MINRUN 本)。
     unwind 情報の無い leaf (`ret 0` / `xor eax,eax` のスロット) は .pdata に無いので、連続の判定には含め、閉包の関数には数えない (leaf_slots)
  3. 到達集合 (BFS): `call/jmp rel32` で .pdata 関数を辿る。 関数内の `lea R, [rip+d]` が別の vtable の先頭を指すなら、その vtable の全スロットも加える
     (= その class を生成しうる。 over-approximate)。 間接呼出 (call [reg+disp] / IAT) は件数のみ記録
出力 (stdout JSON): seeds / vtables / 閉包 関数数・バイト数 / 間接呼出数 / IAT 呼出数 / .pdata 全体に対する割合。 --ranges で RetDec ranges を書く。
usage: closure_cpp.py <block> [--ranges OUT.txt] [--json OUT.json]
"""
import argparse, json, os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_REG_RIP

MINRUN = 2
SEED_DEPTH = int(os.environ.get('CLOSURE_CPP_SEED_DEPTH', '3'))   # NC 用に環境変数で変更可


def load(block):
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % block), fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    pd = [s for s in pe.sections if s.Name.startswith(b'.pdata')][0].get_data()
    ends = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1) and e > b:
            ends[base + b] = base + e
    return pe, base, img, ends


def vtables(pe, base, img, ends):
    """.rdata 内で .text を指す qword の連続 (うち .pdata 開始 VA が 1 本以上) → {先頭 VA: [slot VA...]}"""
    rd = [s for s in pe.sections if s.Name.startswith(b'.rdata')][0]
    lo, hi = base + rd.VirtualAddress, base + rd.VirtualAddress + rd.Misc_VirtualSize
    q = lambda va: struct.unpack_from('<Q', img, va - base)[0]
    tx = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    t_lo, t_hi = base + tx.VirtualAddress, base + tx.VirtualAddress + tx.Misc_VirtualSize
    out, i = {}, lo
    while i <= hi - 8:
        j = i
        while j <= hi - 8 and t_lo <= q(j) < t_hi:
            j += 8
        slots = [q(k) for k in range(i, j, 8)]
        if len(slots) >= MINRUN and any(x in ends for x in slots):
            out[i] = slots
            i = j
        else:
            i += 8
    return out


def compute(block):
    """→ (out dict, closure {VA: size}, ends, seeds_vt)"""
    class a: pass
    a.block = block
    pe, base, img, ends = load(a.block)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    t_lo = base + text.VirtualAddress
    code = lambda lo, hi: img[lo - base: hi - base]
    VT = vtables(pe, base, img, ends)
    vt_heads = set(VT)
    # vtable が先頭 slot の手前から始まる (RTTI 直後に抽象 slot 等) 場合に備え、lea の飛び先が vtable の内部 (先頭ではない) なら
    # その vtable を含める。 slot 境界は問わない
    def vt_of(va):
        for h, s in VT.items():
            if h <= va < h + 8 * len(s):
                return h
        return None

    exp = {s.name: s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    cpi = base + exp[b'CreatePlugInstance']
    fstart = lambda va: max((s for s in ends if s <= va < ends[s]), default=None)

    def scan(f):
        """f の命令を (call/jmp rel32 先, lea rip 先, 間接 call, iat call, vptr 書込 (lea 元 vtable)) に分解"""
        res = {'calls': [], 'leas': [], 'ind': 0, 'iat': 0, 'vptr': []}
        lea_reg = {}
        for ins in md.disasm(code(f, ends[f]), f):
            mn = ins.mnemonic
            if mn in ('call', 'jmp') and ins.operands:
                o = ins.operands[0]
                if o.type == 2:
                    t = o.imm
                    if t in ends and not (f <= t < ends[f]):
                        res['calls'].append(t)
                    elif mn == 'jmp' and t not in ends:
                        s = fstart(t)
                        if s is not None and s != f:
                            res['calls'].append(s)
                elif o.type == X86_OP_MEM:
                    if o.mem.base == X86_REG_RIP:
                        res['iat'] += 1
                    elif mn == 'call':
                        res['ind'] += 1
                elif mn == 'call':
                    res['ind'] += 1
            elif mn == 'lea' and len(ins.operands) == 2 and ins.operands[1].type == X86_OP_MEM and ins.operands[1].mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + ins.operands[1].mem.disp
                res['leas'].append(tgt)
                lea_reg[ins.operands[0].reg] = tgt
            elif mn == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == X86_OP_MEM \
                    and ins.operands[1].type == X86_OP_REG and ins.operands[1].reg in lea_reg:
                res['vptr'].append(lea_reg[ins.operands[1].reg])
        return res

    cache = {}
    sc = lambda f: cache.setdefault(f, scan(f))

    # 1. seed: CreatePlugInstance から depth SEED_DEPTH で辿り、vptr 書込の vtable を集める
    # export は .pdata に無い `jmp rel32` サンクのことがある (Hardcore / Effector engine とも)。 飛び先を seed にする
    first = next(md.disasm(code(cpi, cpi + 16), cpi))
    if cpi not in ends and first.mnemonic == 'jmp' and first.operands[0].type == 2:
        cpi_seed = first.operands[0].imm
    else:
        cpi_seed = cpi
    seeds_vt, seen, frontier = [], {cpi_seed}, [cpi_seed]
    for _ in range(SEED_DEPTH + 1):
        nxt = []
        for f in frontier:
            if f not in ends:
                continue
            r = sc(f)
            for t in r['vptr']:
                h = vt_of(t)
                if h is not None and h not in seeds_vt:
                    seeds_vt.append(h)
            for c in r['calls']:
                if c not in seen:
                    seen.add(c)
                    nxt.append(c)
        frontier = nxt
    # 2-3. BFS
    entries = {}
    for h in seeds_vt:
        # 先頭 slot より手前を指していた場合に備え、lea の飛び先 (vptr) 以降の slot を採る
        for s in VT[h]:
            entries[s] = 'vtable@0x%x' % h
    closure, queue, used_vt = {}, list(entries), set(seeds_vt)
    ind = iat = 0
    while queue:
        f = queue.pop()
        if f in closure or f not in ends:
            continue
        closure[f] = ends[f] - f
        r = sc(f)
        ind += r['ind']
        iat += r['iat']
        queue.extend(r['calls'])
        for t in r['leas']:
            h = vt_of(t)
            if h is not None and h not in used_vt:
                used_vt.add(h)
                queue.extend(VT[h])
    # 閉包に含まれない vtable slot (= 閉包外で生成される class) は件数だけ
    ranges = ['0x%x-0x%x' % (f, ends[f] - 1) for f in sorted(closure)]
    out = {'block': a.block, 'export': hex(cpi), 'seed_vtables': [hex(h) for h in seeds_vt],
           'seed_vtable_slots': {hex(h): len(VT[h]) for h in seeds_vt},
           'leaf_slots_not_in_pdata': len({x for h in used_vt for x in VT[h] if x not in ends}),
           'vtables_found': len(VT), 'vtables_in_closure': len(used_vt),
           'entries': len(entries), 'closure_funcs': len(closure), 'closure_bytes': sum(closure.values()),
           'pdata_funcs': len(ends), 'pdata_bytes': sum(e - s for s, e in ends.items()),
           'indirect_call_sites': ind, 'iat_call_sites': iat}
    out['ranges'] = ranges
    return out, closure, ends, seeds_vt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('block', type=int)
    ap.add_argument('--ranges')
    ap.add_argument('--json')
    a = ap.parse_args()
    out, closure, ends, seeds_vt = compute(a.block)
    if a.ranges:
        open(a.ranges, 'w').write(','.join(out['ranges']))
    if a.json:
        json.dump(out, open(a.json, 'w'))
    print(json.dumps({k: v for k, v in out.items() if k != 'ranges'}, indent=1))
    # 測定が成立しなかったら非 0 (seed の vtable が 1 本も取れない / 閉包が空 / .pdata より大きい)
    if not seeds_vt or not closure or len(closure) > len(ends):
        print('closure_cpp: FAIL: seed_vtables=%d closure_funcs=%d pdata_funcs=%d' % (len(seeds_vt), len(closure), len(ends)), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
