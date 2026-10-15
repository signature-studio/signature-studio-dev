#!/usr/bin/env python3
"""対照 Gain の x64c 閉包 (CFG 降下) と gain_before_160.tsv (直接 call 閉包) の数え方の差を分類する (KH-37, #3064).

x64c.py (tools/flelift) は roots から制御フローの辺だけで降下し、call の即値先を次の探索対象にする。
TSV は .pdata 範囲内の直接 call/jmp を線形に拾う。両者の差は、TSV の各行を次の 4 種に分けて数える:
  hit            : x64c の閉包 (done) に入る関数
  iat_thunk      : jmp [rip+IAT] の thunk (x64c は imp 呼出として別扱い)
  tail_absorbed  : 親の call site が jmp で、x64c は他関数の本体として取り込む (閉包の関数として数えない)
  seh_landing_pad: 親の call site の命令が x64c の到達命令に無く、親の UNWIND_INFO の scope table の
                   JumpTarget (__except の着地点) と一致する。CFG の辺が無く、例外の unwind でだけ到達する
  site_unreached : 親の call site の命令が x64c の到達命令に無く、SEH 着地点でもない (0 件であることを期待)
  other          : 上記以外 (0 件であることを期待。出たら原因を調べる)
seh_landing_pad と site_unreached の行には、命令の直前の命令と、.text・データ中の参照数 (branch / 絶対・RVA) を付ける。
これは人手検証ではない。出力は機械的な分類である。

usage: gain_x64c_closure.py <HeartCore.core_64> <gain_before_160.tsv> <out_dir>
出力: <out_dir>/gain_x64c_closure.json (stdout にも 1 行 JSON)
"""
import json, os, struct, sys, csv

import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'flelift'))
import x64c as X  # noqa: E402

BASE = 0x180000000


def read_tsv(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            rows.append({'func': int(r['func_rva'], 16), 'size': int(r['size']),
                         'root': r['root_class'], 'parent': int(r['parent_rva'], 16) if r['parent_rva'] else None,
                         'site': int(r['call_site_rva'], 16) if r['call_site_rva'] else None})
    return rows


def main(corep, tsvp, outdir):
    os.makedirs(outdir, exist_ok=True)
    pe = pefile.PE(corep, fast_load=True)
    size_of_image = pe.OPTIONAL_HEADER.SizeOfImage
    rows = read_tsv(tsvp)
    roots = [BASE + r['func'] for r in rows if r['root']]
    ent = os.path.join(outdir, 'entries.json')
    json.dump({'roots': roots, 'calltgt': []}, open(ent, 'w'))

    X.IMG = BASE; X.SHIFT = 0; X.IMG_SIZE = size_of_image
    pei = X.PEInfo(corep)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True

    lift_out = os.path.join(outdir, 'x64c_lift')
    sys.argv = ['x64c.py', '--pe', corep, '--entries', ent, '--out', lift_out, '--closure', '1000',
                '--img', hex(BASE), '--shift', '0', '--img-size', hex(size_of_image)]
    X.main()
    meta = json.load(open(os.path.join(lift_out, 'lift_meta.json')))
    done = set(int(x, 16) for x in meta['functions'])
    known = set(done)

    thunks = {}
    reach_all = {}
    for e in sorted(done):
        f = X.FnLift(pei, e, known, md, thunks)
        f.descend()
        reach_all.update(f.insns)

    def is_iat_thunk(va):
        for i in md.disasm(pei.bytes_at(va, 8), va, 1):
            if i.mnemonic == 'jmp' and i.operands[0].type == X86_OP_MEM and i.operands[0].mem.base == X86_REG_RIP:
                return (va + i.size + i.operands[0].mem.disp) in pei.iat
        return False

    cls = {'hit': 0, 'iat_thunk': 0, 'tail_absorbed': 0, 'seh_landing_pad': 0, 'site_unreached': 0, 'other': 0}
    detail = {'iat_thunk': [], 'tail_absorbed': [], 'seh_landing_pad': [], 'site_unreached': [], 'other': []}
    for r in rows:
        fva = BASE + r['func']
        if fva in done:
            cls['hit'] += 1
            continue
        if is_iat_thunk(fva):
            cls['iat_thunk'] += 1
            detail['iat_thunk'].append('%x' % r['func'])
            continue
        if r['parent'] is None:
            cls['other'] += 1
            detail['other'].append({'func': '%x' % r['func'], 'site': None, 'mnem': 'root_not_in_closure'})
            continue
        sva = BASE + r['site']
        ins = reach_all.get(sva)
        if ins is not None and ins.mnemonic == 'jmp':
            cls['tail_absorbed'] += 1
            detail['tail_absorbed'].append('%x' % r['func'])
        elif ins is None:
            seh = [t for t in seh_targets(pei, r['parent']) if t['target'] == r['site']]
            if seh:
                cls['seh_landing_pad'] += 1
                detail['seh_landing_pad'].append({'func': '%x' % r['func'], 'parent': '%x' % r['parent'],
                                                  'site': '%x' % r['site'],
                                                  'scope': {k: '%x' % v for k, v in seh[0].items()}})
            else:
                cls['site_unreached'] += 1
                detail['site_unreached'].append({'func': '%x' % r['func'], 'parent': '%x' % r['parent'],
                                                 'site': '%x' % r['site']})
        else:
            cls['other'] += 1
            detail['other'].append({'func': '%x' % r['func'], 'site': '%x' % r['site'], 'mnem': ins.mnemonic})

    for d in detail['site_unreached'] + detail['seh_landing_pad']:
        sva = BASE + int(d['site'], 16)
        d['prev_insn'] = prev_insn(pei, md, sva)
        d['refs'] = scan_refs(pei, md, sva)
    summary = {'roots': len(roots), 'x64c_closure_functions': len(done), 'tsv_rows': len(rows),
               'classes': cls, 'detail': detail, 'x64c_lift_ninsn': meta['ninsn']}
    with open(os.path.join(outdir, 'gain_x64c_closure.json'), 'w') as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False))


def seh_targets(pei, func_rva):
    """親関数の UNWIND_INFO (UNW_FLAG_EHANDLER・chain なし) の C scope table を読む。
    戻り値は各 entry の {begin, end, handler, target} (RVA)。target は __except の着地点 (CFG の辺が無い)。"""
    img = pei.img
    for (b, _e, u) in pei.pdata:
        if b == BASE + func_rva:
            break
    else:
        return []
    flags = img[u] >> 3
    if not (flags & 1) or (flags & 4):
        return []
    p = u + 4 + ((img[u + 2] + 1) // 2) * 4
    n = struct.unpack_from('<I', img, p + 4)[0]
    out = []
    for k in range(n):
        bg, en, hd, tg = struct.unpack_from('<IIII', img, p + 8 + 16 * k)
        out.append({'begin': bg, 'end': en, 'handler': hd, 'target': tg})
    return out


def prev_insn(pei, md, va):
    for back in range(1, 16):
        code = pei.bytes_at(va - back, back + 1)
        for i in md.disasm(code, va - back, 1):
            if i.address + i.size == va:
                return '%x: %s %s' % (i.address - BASE, i.mnemonic, i.op_str)
    return None


def scan_refs(pei, md, sva):
    """sva への参照数: (a) .text 内の即値 branch/call (.pdata 範囲の線形走査) (b) 4B RVA・8B VA のデータ参照。"""
    rva = sva - BASE
    branch = 0
    for (b, e, _u) in pei.pdata:
        for i in md.disasm(pei.bytes_at(b, e - b), b, 0):
            if i.operands and i.operands[0].type == X86_OP_IMM and (i.mnemonic == 'call' or i.mnemonic[0] == 'j'):
                if i.operands[0].imm == sva:
                    branch += 1
    img = pei.img
    data4 = img.count(struct.pack('<I', rva))
    data8 = img.count(struct.pack('<Q', sva))
    return {'branch_imm': branch, 'data_rva4': data4, 'data_va8': data8}


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
