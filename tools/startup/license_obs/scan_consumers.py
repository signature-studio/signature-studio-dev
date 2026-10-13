#!/usr/bin/env python3
"""byte[0x14f84a8] (登録フラグ) の全 read/write サイトを FLEngine_x64.dll 全関数から機械的に列挙する。

方法: .pdata の全関数 (peidx.Image.funcs) を capstone で逆アセンブルし、
  (a) RIP 相対で 0x14f84a8 を直接参照する命令、
  (b) 唯一のポインタ 0x15e0698 を読む命令と、その直後 [reg] への byte 演算 (test/and/or/mov)
を拾う。test+jcc は条件成立側 (bit セット側) / 不成立側を分けて、各側の線形パス上の文字列リテラルを付ける。
出力: results/flag_sites.json (機械可読) と results/FLAG_SITES.md (自動生成)。
再現: python3 tools/startup/license_obs/scan_consumers.py
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import Image, rip_target  # noqa: E402

FLAG = 0x14f84a8
SLOT = 0x15e0698
WRITER_FN = 0x10c7cd0
GSLOT = 0x15e4790
GOFF = 0xd0
PATH_INSNS = 45


def getstr(im, va):
    try:
        b = im.read(va, 200)
    except Exception:
        return None
    s = ''
    for i in range(0, len(b) - 1, 2):
        c = b[i] | (b[i + 1] << 8)
        if c == 0:
            break
        if 32 <= c < 0x3100:
            s += chr(c)
        else:
            s = None
            break
    if s and len(s) >= 3:
        return s
    m = re.match(rb'[\x20-\x7e]{4,}', b)
    return m.group().decode() if m else None


def path_strings(im, ins, start_idx):
    out = []
    for i in ins[start_idx:start_idx + PATH_INSNS]:
        if i.mnemonic == 'lea':
            t = rip_target(i)
            if t and t not in (SLOT, FLAG):
                s = getstr(im, t)
                if s:
                    out.append(s[:90])
        if i.mnemonic in ('ret', 'jmp'):
            break
    return out


JCC = {'ja': ('>', False), 'jbe': ('>', True), 'jae': ('>=', False), 'jb': ('>=', True),
       'je': ('==', False), 'jne': ('==', True)}


def holds(op, imm, val):
    return {'>': val > imm, '>=': val >= imm, '==': val == imm}[op]


def grade_site(im, ins, k):
    """mov r,[GSLOT]; mov r,[r]; mov r,[r+0xd0]; (cmp|mov|...) byte ptr [r] ... を gradeChar アクセスとして拾う"""
    a = ins[k + 1:k + 4]
    if len(a) < 3 or not (a[0].mnemonic == 'mov' and re.search(r'\[r\w+\]$', a[0].op_str)
                          and a[1].mnemonic == 'mov' and f'+ 0x{GOFF:x}]' in a[1].op_str):
        return None
    reg = a[1].op_str.split(',')[0]
    site = {'func': 0, 'load': ins[k].address}
    site['seq'] = [f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[k + 1:k + 7]]
    for q in range(k + 3, min(k + 7, len(ins))):
        x = ins[q]
        if f'byte ptr [{reg}]' not in x.op_str:
            continue
        if x.mnemonic == 'cmp' and x.op_str.startswith('byte ptr'):
            imm = int(x.op_str.split(',')[-1], 16)
            jx = ins[q + 1]
            if jx.mnemonic in JCC:
                op, neg = JCC[jx.mnemonic]
                tgt = int(jx.op_str, 16)
                tidx = next((u for u, w in enumerate(ins) if w.address == tgt), None)
                fall = path_strings(im, ins, q + 2)
                taken = path_strings(im, ins, tidx) if tidx is not None else []
                site.update(rw='read', op=f'cmp imm 0x{imm:02x}', jcc=jx.mnemonic, cmp_op=op, cmp_imm=imm, taken_if_negated=neg)
                # 条件 (gradeChar op imm) が成り立つ側のパス
                site['path_cond_true'], site['path_cond_false'] = (taken, fall) if not neg else (fall, taken)
                site['at_0x40'] = 'cond_true' if holds(op, imm, 0x40) else 'cond_false'
                site['at_0x41'] = 'cond_true' if holds(op, imm, 0x41) else 'cond_false'
                return site
            site.update(rw='read', op=f'cmp imm 0x{imm:02x} (jcc: {jx.mnemonic})')
            return site
        if x.mnemonic == 'mov' and x.op_str.startswith('byte ptr'):
            site.update(rw='write', op='store')
            return site
        site.update(rw='read', op=f'{x.mnemonic} {x.op_str}')
        for j in range(q + 1, min(q + 4, len(ins))):
            y = ins[j]
            mm = re.match(r'(?:al|eax|rax), (0x[0-9a-f]+|\d+)$', y.op_str) if y.mnemonic == 'cmp' else None
            if not mm or ins[j + 1].mnemonic not in JCC:
                continue
            imm = int(mm.group(1), 0)
            jx = ins[j + 1]
            op, neg = JCC[jx.mnemonic]
            tgt = int(jx.op_str, 16)
            tidx = next((u for u, w in enumerate(ins) if w.address == tgt), None)
            fall = path_strings(im, ins, j + 2)
            taken = path_strings(im, ins, tidx) if tidx is not None else []
            site.update(op=f'movzx; cmp imm 0x{imm:02x}', jcc=jx.mnemonic, cmp_op=op, cmp_imm=imm, taken_if_negated=neg)
            site['path_cond_true'], site['path_cond_false'] = (taken, fall) if not neg else (fall, taken)
            site['at_0x40'] = 'cond_true' if holds(op, imm, 0x40) else 'cond_false'
            site['at_0x41'] = 'cond_true' if holds(op, imm, 0x41) else 'cond_false'
            break
        return site
    return None


def classify(op_str):
    m = re.match(r'(?:byte ptr \[(\w+)\]|(\w+), byte ptr \[(\w+)\])', op_str)
    return m


def main():
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    im = Image()
    n_insn = 0
    n_func = 0
    direct = []
    sites = []
    grade = []
    for lo, hi, ins in im.iter_insns():
        n_func += 1
        n_insn += len(ins)
        for k, i in enumerate(ins):
            tg = rip_target(i)
            if tg == FLAG:
                direct.append({'func': lo, 'addr': i.address, 'insn': f'{i.mnemonic} {i.op_str}'})
            if tg == GSLOT and i.mnemonic == 'mov' and i.op_str.startswith('r'):
                g = grade_site(im, ins, k)
                if g:
                    g['func'] = lo
                    grade.append(g)
            if tg != SLOT or i.mnemonic != 'mov' or not i.op_str.startswith('r'):
                continue
            reg = i.op_str.split(',')[0]
            site = {'func': lo, 'load': i.address, 'seq': [f'{x.address:x} {x.mnemonic} {x.op_str}' for x in ins[k + 1:k + 5]]}
            kind = None
            for q in range(k + 1, min(k + 5, len(ins))):
                x = ins[q]
                if f'byte ptr [{reg}]' not in x.op_str:
                    continue
                if x.mnemonic in ('and', 'or') and x.op_str.startswith('byte ptr'):
                    kind = ('write', f'{x.mnemonic} 0x{int(x.op_str.split(",")[-1], 16):02x}', int(x.op_str.split(',')[-1], 16))
                elif x.mnemonic == 'mov' and x.op_str.startswith('byte ptr'):
                    kind = ('write', 'store', None)
                else:
                    kind = ('read', f'{x.mnemonic} {x.op_str}', None)
                    for j in range(q + 1, min(q + 4, len(ins))):
                        y = ins[j]
                        mm = re.match(r'(al|cl|dl|rax|rcx), (0x[0-9a-f]+|\d+)$', y.op_str) if y.mnemonic == 'test' else None
                        if mm:
                            mask = int(mm.group(2), 0)
                            jx = ins[j + 1] if j + 1 < len(ins) else None
                            jc = jx.mnemonic if jx and jx.mnemonic in ('je', 'jne') else None
                            kind = ('read', f'test mask 0x{mask:02x}', mask)
                            site['jcc'] = jc
                            if jc:
                                tgt = int(jx.op_str, 16)
                                tidx = next((u for u, w in enumerate(ins) if w.address == tgt), None)
                                fall = path_strings(im, ins, j + 2)
                                taken = path_strings(im, ins, tidx) if tidx is not None else []
                                if jc == 'je':
                                    site['bit_set_path'], site['bit_clear_path'] = fall, taken
                                else:
                                    site['bit_set_path'], site['bit_clear_path'] = taken, fall
                            break
                        if y.mnemonic in ('setne', 'sete', 'and', 'cmp'):
                            kind = ('read', f'{x.mnemonic} ... {y.mnemonic} {y.op_str}', None)
                            break
                break
            if kind is None:
                for q in range(k + 1, min(k + 3, len(ins))):
                    if ins[q].mnemonic in ('and', 'cmp') and 'rip' in ins[q].op_str:
                        kind = ('read', f'{ins[q].mnemonic} {ins[q].op_str}', None)
                        break
            if kind is None:
                kind = ('other', None, None)
            site['rw'], site['op'], site['mask'] = kind
            site['strings_near'] = []
            if site['rw'] == 'read':
                for x in ins[max(0, k - 14):k + 40]:
                    if x.mnemonic == 'lea':
                        t = rip_target(x)
                        if t and t not in (SLOT, FLAG):
                            s = getstr(im, t)
                            if s and s[:90] not in site['strings_near']:
                                site['strings_near'].append(s[:90])
            sites.append(site)
    summary = {
        'image': os.path.basename(im.path), 'image_size': len(im.raw), 'functions_scanned': n_func,
        'instructions_scanned': n_insn,
        'direct_refs_to_flag': direct,
        'slot_loads': len(sites),
        'reads': sum(1 for s in sites if s['rw'] == 'read'),
        'writes': sum(1 for s in sites if s['rw'] == 'write'),
        'other': sum(1 for s in sites if s['rw'] == 'other'),
        'read_funcs': sorted({s['func'] for s in sites if s['rw'] == 'read'}),
        'write_funcs': sorted({s['func'] for s in sites if s['rw'] == 'write'}),
    }
    # 初期値 (.data 上の静的バイト) とスロットの中身
    summary['flag_initial_byte'] = im.read(FLAG, 1).hex()
    summary['slot_value'] = '0x%x' % int.from_bytes(im.read(SLOT, 8), 'little')
    summary['grade_slot_loads'] = len(grade)
    summary['grade_reads'] = sum(1 for g in grade if g.get('rw') == 'read')
    summary['grade_writes'] = sum(1 for g in grade if g.get('rw') == 'write')
    out = {'summary': summary, 'sites': sites, 'grade_sites': grade}
    json.dump(out, open(os.path.join(outdir, 'flag_sites.json'), 'w'), indent=1, ensure_ascii=False, default=hex)

    md = ['<!-- 自動生成: python3 tools/startup/license_obs/scan_consumers.py (人手編集禁止) -->', '',
          '# byte[0x14f84a8] 全サイト (FLEngine_x64.dll 26.1.7)', '']
    md.append(f"- 走査: 関数 {n_func} / 命令 {n_insn} / 直接参照(0x14f84a8) {len(direct)} / ポインタ 0x15e0698 ロード {len(sites)} "
              f"(read {summary['reads']} / write {summary['writes']} / other {summary['other']})")
    md.append(f"- 静的初期バイト = `{summary['flag_initial_byte']}`、スロット値 = `{summary['slot_value']}`")
    md += ['', '## write サイト', '', '| 関数 | ロード VA | 操作 |', '|---|---|---|']
    for s in sites:
        if s['rw'] == 'write':
            md.append(f"| `0x{s['func']:x}` | `0x{s['load']:x}` | {s['op']} |")
    md += ['', '## read サイト (bit セット側 / クリア側の線形パス上の文字列)', '',
           '| 関数 | ロード VA | 検査 | jcc | bit セット側の文字列 | bit クリア側の文字列 |', '|---|---|---|---|---|---|']
    for s in sites:
        if s['rw'] != 'read':
            continue
        st = ' / '.join(s.get('bit_set_path', [])[:4]).replace('|', '¦')
        cl = ' / '.join(s.get('bit_clear_path', [])[:4]).replace('|', '¦')
        md.append(f"| `0x{s['func']:x}` | `0x{s['load']:x}` | {s['op']} | {s.get('jcc') or '-'} | {st} | {cl} |")
    md += ['', '## gradeChar (`[[[0x15e4790]]+0xd0]` の 1 バイト) の全サイト', '',
           f"- 0x15e4790 ロード後に `+0xd0` を辿る形: {len(grade)} (read {summary['grade_reads']} / write {summary['grade_writes']})",
           '- `条件` は gradeChar に対する比較。`@0x40` = 未登録 ("Update registration" 状態) のとき実行される側、`@0x41` = 登録 (tier A) のとき実行される側', '',
           '| 関数 | ロード VA | 操作 | 条件 | @0x40 (未登録) で実行される側の文字列 | @0x41 (登録) で実行される側の文字列 |', '|---|---|---|---|---|---|']
    for g in grade:
        if g.get('rw') == 'write':
            md.append(f"| `0x{g['func']:x}` | `0x{g['load']:x}` | write | - | | |")
            continue
        if 'cmp_op' in g:
            cond = f"gradeChar {g['cmp_op']} 0x{g['cmp_imm']:02x}"
            p40 = ' / '.join(g['path_cond_true' if g['at_0x40'] == 'cond_true' else 'path_cond_false'][:3]).replace('|', '¦')
            p41 = ' / '.join(g['path_cond_true' if g['at_0x41'] == 'cond_true' else 'path_cond_false'][:3]).replace('|', '¦')
        else:
            cond, p40, p41 = '-', '', ''
        md.append(f"| `0x{g['func']:x}` | `0x{g['load']:x}` | {g.get('op')} | {cond} | {p40} | {p41} |")
    open(os.path.join(outdir, 'FLAG_SITES.md'), 'w').write('\n'.join(md) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('read_funcs', 'write_funcs', 'direct_refs_to_flag')}),
          'direct', len(direct), 'elapsed %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
