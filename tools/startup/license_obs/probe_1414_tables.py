#!/usr/bin/env python3
"""#1414 受入 1: 関数ポインタ表 T1 (0x11740f5〜・42 件) と T2 (0x1378820〜・826 件) の基底を指す参照を、
近傍まで含めて静的に全件走査する (読取専用)。

既存の probe_1027.py は表の先頭アドレスの完全一致だけを見た。本 probe は次を追加で見る:
  (a) .text の命令の rip 相対先・即値・disp が、表の範囲 ±NEAR バイト以内に入る命令 (vtable 風の +0x10 等)
  (b) 素材イメージ全体 (ヘッダ・.data・.rdata・.pdata 含む) の 8 バイトの値 (全 8 通りのオフセット) が、
      表の範囲 ±NEAR 以内を指す箇所 (データ中のポインタ)
  (c) 間接 call (`call qword [...]`) を 0x10c7cd0 内で全件列挙し、メモリ operand の形 (base・index・disp) を分類する
  (d) g1 のスロット 0x15e14a8 を rip 相対で読む 42 箇所の使い方 (書込み・比較・コピー) を分類する
  (e) --dyn: 6 入力で実行された間接 call の、object 先頭値 ([reg]) が表の範囲に入るかを記録する

usage: python probe_1414_tables.py --dyn --write   (要 FL_WIN64_DIR・venv: tools/startup/license_obs/env.sh)
出力: results/probe_1414_tables.json (--write 時)
"""
import array, json, os, re, struct, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from capstone.x86 import X86_OP_MEM  # noqa: E402
from peidx import Image, rip_target  # noqa: E402

TABLES = {
    'T1': (0x11740f5, 42),
    'T2': (0x1378820, 826),
}
NEAR = 0x100
DISP = 0x10c7cd0
HEX = re.compile(r'0x[0-9a-f]+')


def ranges():
    out = {}
    for name, (lo, n) in TABLES.items():
        hi = lo + n * 8
        out[name] = (lo - NEAR, hi + NEAR)
    return out


def in_any(v, rs):
    for name, (lo, hi) in rs.items():
        if lo <= v < hi:
            return name
    return None


def text_refs(img, rs):
    hits = []
    for lo, hi, insns in img.iter_insns():
        for ins in insns:
            cands = []
            t = rip_target(ins)
            if t is not None:
                cands.append(('rip', t))
            for h in HEX.findall(ins.op_str):
                v = int(h, 16)
                cands.append(('imm', v))
                if img.base <= v:
                    cands.append(('rva_as_va', v))
                cands.append(('rva', v + img.base))
            for kind, v in cands:
                name = in_any(v, rs)
                if name and not ins.mnemonic.startswith('j'):
                    hits.append({'at': hex(ins.address), 'kind': kind, 'value': hex(v), 'table': name,
                                 'insn': f'{ins.mnemonic} {ins.op_str}'})
    return hits


def data_ptrs(img, rs):
    raw = img.raw
    hits = []
    for off in range(8):
        n = (len(raw) - off) // 8
        arr = array.array('Q', raw[off:off + n * 8])
        for i, v in enumerate(arr):
            name = in_any(v, rs)
            if name:
                fo = off + i * 8
                hits.append({'file_off': hex(fo), 'value': hex(v), 'table': name})
    return hits


def classify_indirect(img):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    fn = [f for f in img.funcs if f[0] == DISP][0]
    sites = []
    for ins in md.disasm(img.read(fn[0], fn[1] - fn[0]), fn[0]):
        if ins.mnemonic == 'call' and not ins.op_str.startswith('0x'):
            m = ins.operands[0].mem if ins.operands and ins.operands[0].type == X86_OP_MEM else None
            if m is None:
                sites.append({'at': hex(ins.address), 'form': 'reg', 'op': ins.op_str})
                continue
            base = md.reg_name(m.base) if m.base else '-'
            idx = md.reg_name(m.index) if m.index else '-'
            sites.append({'at': hex(ins.address), 'form': 'mem', 'base': base, 'index': idx,
                          'scale': m.scale, 'disp': hex(m.disp), 'op': ins.op_str})
    return sites


G1_SLOT = 0x15e14a8


def g1_refs(img):
    out = {'write': [], 'cmp': [], 'mov_read': []}
    for lo, hi, insns in img.iter_insns():
        for i, ins in enumerate(insns):
            if rip_target(ins) != G1_SLOT:
                continue
            reg = ins.op_str.split(',')[0].strip()
            for nx in insns[i + 1:i + 12]:
                if f'[{reg}]' not in nx.op_str and f'[{reg} ' not in nx.op_str:
                    continue
                first = nx.op_str.split(',')[0]
                row = {'func': hex(lo), 'at': hex(nx.address), 'insn': f'{nx.mnemonic} {nx.op_str}'}
                if nx.mnemonic in ('cmp', 'test'):
                    out['cmp'].append(row)
                elif nx.mnemonic not in ('lea',) and first.strip().startswith(f'dword ptr [{reg}]'):
                    out['write'].append(row)
                else:
                    out['mov_read'].append(row)
                break
    return {k: {'count': len(v), 'sites': v} for k, v in out.items()}


def run_dyn(img, rs):
    from unicorn import UC_HOOK_CODE
    import unicorn.x86_const as C
    from emu_reg import Emu, Reg
    from run_cases import seed_license
    from probe_1414 import CASES, indirect_sites
    out = []
    for name, kw, cl in CASES:
        r = Reg()
        seed_license(r, **kw)
        e = Emu(r)
        e.setup_globals()
        e.init_units()
        vt = {}
        for addr, size, op, md in indirect_sites(img):
            def cb(uc, a, s, ud, addr=addr, size=size, op=op, md=md):
                k = hex(addr)
                if op.type != X86_OP_MEM:
                    vt.setdefault(k, {}).setdefault('reg', 0)
                    vt[k]['reg'] += 1
                    return
                m = op.mem
                regname = md.reg_name(m.base) if m.base else None
                if regname is None or regname == 'rip':
                    return
                base = uc.reg_read(getattr(C, 'UC_X86_REG_' + regname.upper()))
                try:
                    obj_vt = struct.unpack('<Q', bytes(uc.mem_read(base, 8)))[0]
                except Exception:
                    obj_vt = None
                hit = in_any(obj_vt, rs) if obj_vt is not None else None
                d = vt.setdefault(k, {'n': 0, 'vtable_in_T': {}})
                d['n'] += 1
                key = hit or 'none'
                d['vtable_in_T'][key] = d['vtable_in_T'].get(key, 0) + 1
                if hit:
                    d.setdefault('vtable_values', []).append(hex(obj_vt))
            e.uc.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)
        st = e.run(cl=cl)
        executed = {k: v for k, v in vt.items() if isinstance(v, dict) and v.get('n')}
        hits = {k: v for k, v in executed.items() if v.get('vtable_values')}
        out.append({'case': name, 'status': st if st == 'ok' else st[:120], 'sites_seen': len(executed),
                    'sites_with_vtable_in_T': len(hits),
                    'vtable_values_in_T': sorted({x for v in hits.values() for x in v['vtable_values']})})
    return out


def main():
    rs = ranges()
    img = Image()
    text = text_refs(img, rs)
    data = data_ptrs(img, rs)
    sites = classify_indirect(img)
    forms = Counter((s['form'], s.get('base', '-'), s.get('index', '-')) for s in sites)
    res = {
        'tables': {k: {'lo': hex(lo), 'n': n, 'hi': hex(lo + 8 * n), 'near': NEAR} for k, (lo, n) in TABLES.items()},
        'text_refs_near': text,
        'data_ptrs_near': data,
        'indirect_sites_0x10c7cd0': len(sites),
        'indirect_forms': {'|'.join(map(str, k)): v for k, v in forms.most_common()},
        'indirect_sites': sites,
        'g1_refs': g1_refs(img),
    }
    print('g1 slot refs:', {k: v['count'] for k, v in res['g1_refs'].items()})
    print('text refs near tables:', len(text), '| data ptrs near tables:', len(data))
    for h in text[:40]:
        print('  TEXT', h)
    for h in data[:40]:
        print('  DATA', h)
    print('indirect sites in 0x10c7cd0:', len(sites))
    for k, v in forms.most_common():
        print('  form', k, v)
    if '--dyn' in sys.argv:
        res['dyn_vtable'] = run_dyn(img, rs)
        for d in res['dyn_vtable']:
            print('DYN', d)
    if '--write' in sys.argv:
        os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
        with open(os.path.join(HERE, 'results', 'probe_1414_tables.json'), 'w') as f:
            json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
