#!/usr/bin/env python3
"""prefix_matrix.py — capstone の disp_size / disp_offset / imm_* 誤報告を prefix × opcode map × modrm 形式の全組合せで再現・定量化する (CAB-229 要件1)

オラクル = 構築時に既知の位置: raw = prefix* [REX] opcode-bytes modrm [sib] disp imm-filler を自分で組むので、
modrm / disp の真の位置は構築から決まる (capstone の値は使わない)。capstone が構築通りに decode したこと
(capstone modrm_offset が構築位置に一致し、命令長が disp 終端以上) を採用条件にする。
補助オラクル: --objdump N は binutils objdump (capstone/LLVM と別実装) の命令長が一致するかを N 件サンプル検証する。

usage: python3 prefix_matrix.py [--quick] [--jobs 12] [--objdump 20000] [--json results/prefix_matrix.json]
"""
import argparse, collections, itertools, json, os, subprocess, sys, tempfile
from multiprocessing import Pool
import capstone
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dispfix as D

DISP32 = bytes.fromhex('44332211')            # 0x11223344
DISP8 = bytes([0xF8])                         # -8
IMMFILL = bytes.fromhex('a1a2a3a4a5a6a7a8')
OPC_SKIP_1B = set([0x0F, 0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65, 0x66, 0x67, 0xF0, 0xF2, 0xF3, 0xC4, 0xC5, 0x62, 0x8F, 0xA0, 0xA1, 0xA2, 0xA3] + list(range(0x40, 0x50)))

# modrm 形式: (name, modrm byte (reg=0), sib or None, disp bytes, 真の disp_size)
FORMS = [
    ('rip',        0x05, None, DISP32, 4),
    ('base+d8',    0x40, None, DISP8, 1),
    ('base+d32',   0x80, None, DISP32, 4),
    ('sib+d8',     0x44, 0x24, DISP8, 1),
    ('sib+d32',    0x84, 0x24, DISP32, 4),
    ('sib-nobase', 0x04, 0x25, DISP32, 4),      # [disp32] (SIB base=101 mod=00)
    ('base',       0x00, None, b'', 0),         # disp 無し (誤報告で非 0 を返さないこと)
]
REXES = [b'', b'\x40', b'\x41', b'\x44', b'\x48', b'\x4c', b'\x4f']


def legacy_combos():
    """5 群 (66 / F2|F3 / F0 / 67 / seg) の直積 + 逆順 (置き順違い)。"""
    out = set()
    for p66, pf, plock, p67, pseg in itertools.product([b'', b'\x66'], [b'', b'\xf2', b'\xf3'], [b'', b'\xf0'], [b'', b'\x67'], [b'', b'\x64']):
        parts = [p66, pf, plock, p67, pseg]
        out.add(b''.join(parts))
        out.add(b''.join(reversed(parts)))
    return sorted(out, key=lambda b: (len(b), b))


def opcode_spaces(quick):
    """(map label, enc, map no, bytes before opcode, opcode byte)"""
    ops = []
    q1 = [0x01, 0x03, 0x81, 0x83, 0x89, 0x8B, 0x8D, 0xC7, 0xF7, 0xFF, 0x63, 0x69, 0x6B, 0xD9, 0xDD, 0x00, 0x88, 0xC6, 0xF6, 0xFE, 0x84, 0x87, 0x3B, 0x8F]
    q2 = [0x10, 0x11, 0x28, 0x29, 0x2F, 0x2E, 0x51, 0x54, 0x57, 0x58, 0x59, 0x5A, 0x6F, 0x7F, 0x6E, 0x7E, 0xD6, 0xEB, 0xEF, 0xB6, 0xBE, 0xAF, 0x1F, 0xA3, 0xBA, 0xC2, 0xC6, 0x12, 0x13, 0x16, 0xAE, 0xC7, 0xB1, 0xC1, 0x40, 0x01, 0x0D, 0x18]
    q3 = [0x00, 0x17, 0x1C, 0x20, 0x30, 0x38, 0x40, 0xF0, 0xF1, 0xDC, 0x2A]
    q4 = [0x08, 0x0A, 0x0F, 0x14, 0x16, 0x20, 0x21, 0x44, 0x63]
    for o in (q1 if quick else range(256)):
        if o not in OPC_SKIP_1B:
            ops.append(('1B', 'legacy', 0, b'', o))
    for o in (q2 if quick else range(256)):
        ops.append(('0F', 'legacy', 1, b'\x0f', o))
    for o in (q3 if quick else range(256)):
        ops.append(('0F38', 'legacy', 2, b'\x0f\x38', o))
    for o in (q4 if quick else range(256)):
        ops.append(('0F3A', 'legacy', 3, b'\x0f\x3a', o))
    return ops


def vex_spaces(quick):
    ops = []
    oc = [0x10, 0x11, 0x28, 0x29, 0x58, 0x59, 0x6F, 0x7F, 0x2F, 0xEF, 0x18, 0x19, 0x13, 0xF7, 0x2E, 0x12, 0x77] if quick else list(range(256))
    for pp in range(4):
        for L in (0, 1):
            for o in oc:
                ops.append(('VEX2' + ('+pp66' if pp == 1 else ''), 'vex2', 1, bytes([0xC5, 0xF8 | (L << 2) | pp]), o))                   # R=1 vvvv=1111
    for mm in (1, 2, 3):
        for pp in range(4):
            for W in (0, 1):
                for o in oc:
                    ops.append(('VEX3' + ('+pp66' if pp == 1 else ''), 'vex3', mm, bytes([0xC4, 0xE0 | mm, 0x78 | (W << 7) | pp]), o))   # RXB=111 vvvv=1111 L=0
    for mm in (1, 2, 3, 5, 6):
        for pp in range(4):
            for W in (0, 1):
                for o in oc:
                    ops.append(('EVEX' + ('+pp66' if pp == 1 else ''), 'evex', mm, bytes([0x62, 0xF0 | mm, 0x7C | (W << 7) | pp, 0x08]), o))  # vvvv=1111 bit2=1, V'=1
    return ops


def build(leg, rex, space, form, reg):
    lab, enc, mp, pre_op, op = space
    nm, modrm, sib, disp, dsz = form
    modrm = (modrm & 0xC7) | (reg << 3)
    if enc != 'legacy':
        if rex or any(b in (0x66, 0xF2, 0xF3, 0xF0) for b in leg):      # VEX/EVEX の前に REX/66/F2/F3/lock は不可
            return None
        head = leg + pre_op + bytes([op])
    else:
        head = leg + rex + pre_op + bytes([op])
    mo = len(head)
    raw = head + bytes([modrm]) + (bytes([sib]) if sib is not None else b'') + disp
    disp_off = mo + 1 + (1 if sib is not None else 0)
    return raw + IMMFILL, dict(modrm_off=mo, disp_off=disp_off if dsz else None, disp_size=dsz, disp_end=disp_off + dsz)


def worker(args):
    legs, quick = args
    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    cs.detail = True
    R = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    keep = []
    cnt = 0
    for space in opcode_spaces(quick) + vex_spaces(quick):
        lab, enc = space[0], space[1]
        for leg in legs:
            for rex in (REXES if enc == 'legacy' else [b'']):
                has66 = 0x66 in leg
                rexw = bool(rex and rex[0] & 8)
                osz = 'opsize16' if (has66 and not rexw) else ('rexw+66' if has66 else 'no66')
                for form in FORMS:
                    for reg in ((0, 2, 5, 7) if form[0] == 'rip' else (0, 2)):
                        b = build(leg, rex, space, form, reg)
                        if b is None:
                            continue
                        raw, tr = b
                        ins = next(cs.disasm(raw, 0x1000), None)
                        if ins is None:
                            continue
                        if ins.modrm_offset != tr['modrm_off']:
                            R['_skipped']['modrm_offset_mismatch' if ins.modrm_offset else 'no_modrm'] += 1
                            continue
                        if ins.size < tr['disp_end']:
                            R['_skipped']['short'] += 1
                            continue
                        key = '%s|%s|%s' % (form[0], osz, lab)
                        C = R[key]
                        C['n'] += 1
                        if ins.disp_size != tr['disp_size']:
                            C['cs_disp_size_err'] += 1
                            if len(ex[key]) < 3:
                                ex[key].append((raw[:ins.size].hex(), '%s %s' % (ins.mnemonic, ins.op_str), 'cs_disp_size=%d true=%d' % (ins.disp_size, tr['disp_size'])))
                        if tr['disp_size'] and ins.disp_offset != tr['disp_off']:
                            C['cs_disp_off_err'] += 1
                        if not tr['disp_size'] and ins.disp_size:
                            C['cs_phantom_disp'] += 1
                        timm = ins.size - tr['disp_end']
                        if timm > 0:
                            C['has_imm'] += 1
                            if ins.imm_size != timm:
                                C['cs_imm_size_err'] += 1
                            if ins.imm_offset != tr['disp_end']:
                                C['cs_imm_off_err'] += 1
                        elif ins.imm_size:
                            C['cs_phantom_imm'] += 1
                        for op in ins.operands:
                            if op.type == CS_OP_MEM and tr['disp_size'] in (1, 4) and enc != 'evex':
                                truth = int.from_bytes(raw[tr['disp_off']:tr['disp_off'] + tr['disp_size']], 'little', signed=True)
                                C['memdisp_checked'] += 1
                                if op.mem.disp != truth:
                                    C['cs_memdisp_value_err'] += 1
                                break
                        lay = D.layout(raw[:ins.size])                       # 表引き版 (capstone modrm_offset 不使用)
                        if lay.modrm_offset != tr['modrm_off']:
                            C['fx_modrm_err'] += 1
                        if (lay.disp_size, lay.disp_offset) != (tr['disp_size'], tr['disp_off']):
                            C['fx_layout_err'] += 1
                            if len(ex['fx|' + key]) < 3:
                                ex['fx|' + key].append((raw[:ins.size].hex(), (lay.disp_size, lay.disp_offset), (tr['disp_size'], tr['disp_off'])))
                        if D.disp_span(ins) != ((tr['disp_off'], tr['disp_size']) if tr['disp_size'] else None):
                            C['fx_span_err'] += 1
                        cnt += 1
                        if cnt % 40 == 0 and len(keep) < 3000:
                            keep.append((raw[:ins.size].hex(), ins.size))
    return {k: dict(v) for k, v in R.items()}, dict(ex), keep


def objdump_check(keep, n):
    """binutils objdump で命令長が capstone と一致するか。48 byte slot = 命令 + NOP 埋め。slot 先頭と slot+size が共に命令境界で、間に境界が無ければ一致。"""
    sample = keep[::max(1, len(keep) // n)][:n]
    blob = bytearray()
    for h, size in sample:
        blob += (bytes.fromhex(h) + b'\x90' * 48)[:48]
    d = '/tmp/opencode' if os.path.isdir('/tmp/opencode') else None
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False, dir=d) as f:
        f.write(blob)
        path = f.name
    out = subprocess.run(['objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64', path], capture_output=True, text=True).stdout
    os.unlink(path)
    S = {}
    for ln in out.splitlines():
        p = ln.split('\t')
        if len(p) >= 3 and p[2].strip() and p[0].strip().endswith(':'):
            try:
                S[int(p[0].strip()[:-1], 16)] = p[2].strip()
            except ValueError:
                pass
    ok = bad = invalid = 0
    bad_ex = []
    for k, (h, size) in enumerate(sample):
        s = k * 48
        if '(bad)' in S.get(s, ''):
            invalid += 1                    # objdump が不正 prefix 組合せ等として拒否 (capstone は受理) — 比較対象外
        elif s in S and (s + size) in S and not any((s + j) in S for j in range(1, size)):
            ok += 1
        else:
            bad += 1
            if len(bad_ex) < 5:
                bad_ex.append(h)
    return dict(checked=len(sample), length_agree=ok, length_disagree=bad, objdump_rejects_as_bad=invalid, examples=bad_ex)


def lib_sha():
    import hashlib, glob
    cands = glob.glob(os.path.join(os.path.dirname(capstone.__file__), 'lib', 'libcapstone*')) + glob.glob(os.environ.get('LIBCAPSTONE_PATH', '/nonexistent') + '/libcapstone.so*')
    return hashlib.sha256(open(os.path.realpath(cands[0]), 'rb').read()).hexdigest()[:12] if cands else '?'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true', help='opcode を代表のみに絞る (数十秒)')
    ap.add_argument('--jobs', type=int, default=12)
    ap.add_argument('--objdump', type=int, default=0)
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    legs = legacy_combos()
    chunks = [(legs[i::a.jobs * 2], a.quick) for i in range(a.jobs * 2)]
    with Pool(a.jobs) as p:
        parts = p.map(worker, chunks)
    R = collections.defaultdict(collections.Counter)
    EX = {}
    keep = []
    for r, e, k in parts:
        for key, c in r.items():
            R[key].update(c)
        for key, v in e.items():
            EX[key] = (EX.get(key, []) + v)[:3]
        keep += k
    tot = collections.Counter()
    by_osz = collections.defaultdict(collections.Counter)
    by_form = collections.defaultdict(collections.Counter)
    by_map = collections.defaultdict(collections.Counter)
    for key, c in R.items():
        if key == '_skipped':
            continue
        form, osz, mp = key.split('|')
        tot.update(c); by_osz[osz].update(c); by_form[(form, osz)].update(c); by_map[(mp, osz)].update(c)
    print('capstone.__version__ = %s  module = %s  lib sha256 = %s' % (capstone.__version__, os.path.dirname(capstone.__file__), lib_sha()))
    print('採用 case: %d  skip: %s' % (tot['n'], dict(R.get('_skipped', {}))))
    hdr = '%-10s %9s %11s %9s %8s %9s %9s %8s %8s %8s'
    print(hdr % ('opsize', 'n', 'cs_size_err', 'cs_off_err', 'phantom', 'imm_sz_e', 'imm_of_e', 'fx_span', 'fx_lay', 'fx_modrm'))
    for k, c in sorted(by_osz.items()):
        print(hdr % (k, c['n'], c['cs_disp_size_err'], c['cs_disp_off_err'], c['cs_phantom_disp'], c['cs_imm_size_err'], c['cs_imm_off_err'], c['fx_span_err'], c['fx_layout_err'], c['fx_modrm_err']))
    print('mem.disp 値 検証 %d 件 / capstone 値誤り %d 件' % (tot['memdisp_checked'], tot['cs_memdisp_value_err']))
    print('\n-- 形式 × opsize (disp_size 誤り / n):')
    for (f, o), c in sorted(by_form.items()):
        print('  %-11s %-9s %7d / %-7d' % (f, o, c['cs_disp_size_err'], c['n']))
    print('-- opcode map 別 (opsize16 と VEX/EVEX の pp=66 のみ。disp_size 誤り / n):')
    for (m, o), c in sorted(by_map.items()):
        if o == 'opsize16' or '+pp66' in m:
            print('  %-6s %-9s %7d / %-7d' % (m, o, c['cs_disp_size_err'], c['n']))
    res = dict(capstone_version_attr=capstone.__version__, capstone_lib_sha256_12=lib_sha(), n=tot['n'], skipped=dict(R.get('_skipped', {})),
               by_opsize={k: dict(c) for k, c in by_osz.items()},
               by_form={'%s|%s' % k: dict(c) for k, c in by_form.items()},
               by_map={'%s|%s' % k: dict(c) for k, c in by_map.items()},
               memdisp_checked=tot['memdisp_checked'], memdisp_value_err=tot['cs_memdisp_value_err'],
               examples={k: v for k, v in EX.items() if not k.startswith('fx|')},
               fixer_mismatch_examples={k: v for k, v in EX.items() if k.startswith('fx|')})
    if a.objdump:
        res['objdump'] = objdump_check(keep, a.objdump)
        print('objdump 命令長照合:', res['objdump'])
    fx_bad = sum(c['fx_span_err'] + c['fx_layout_err'] + c['fx_modrm_err'] for c in by_osz.values())
    print('dispfix 不一致 合計:', fx_bad)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump(res, open(a.json, 'w'), indent=1, ensure_ascii=False)
    return 0 if fx_bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
