#!/usr/bin/env python3
"""set_other 非 imm reg 台帳の 実値化 行の独立照合 (#3916 / M11-N198).

m11_setother_nonimm_cfg.py (CFG 到達定義を逆向きに追う) と別手法で照合する。
  手法: 関数を入口から具体実行し、probe (呼出し点) に届く全経路の値を列挙する。
    - 分岐条件が未知なら両方向を辿る (過大近似)。probe で値が未知の経路が 1 つでもあれば 判定不能。
    - 命令の意味は op_str の文字列だけで読む (capstone の regs_access / rw は使わない)。
    - 未対応の命令・step 上限・未知の flags は 判定不能 (PASS にしない)。
使い方:
  python3 m11_setother_nonimm_cfg_verify.py --selftest         合成検査 (期待値と照合・ネガティブコントロール込み)
  python3 m11_setother_nonimm_cfg_verify.py ROWS.json --pe PE  nonimm_cfg_rows.json の 実値化 行を照合
"""
import argparse, collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_STEPS = 200000


class Unsup(Exception):
    pass


class Stop(Exception):
    pass


def msk(w):
    return (1 << w) - 1


REG = {}
for fam, names in (('rax', ('rax', 'eax', 'ax', 'al')), ('rbx', ('rbx', 'ebx', 'bx', 'bl')),
                   ('rcx', ('rcx', 'ecx', 'cx', 'cl')), ('rdx', ('rdx', 'edx', 'dx', 'dl')),
                   ('rsi', ('rsi', 'esi', 'si', 'sil')), ('rdi', ('rdi', 'edi', 'di', 'dil')),
                   ('rbp', ('rbp', 'ebp', 'bp', 'bpl')), ('rsp', ('rsp', 'esp', 'sp', 'spl'))):
    for nm, w in zip(names, (64, 32, 16, 8)):
        REG[nm] = (fam, w)
for n in range(8, 16):
    for suf, w in (('', 64), ('d', 32), ('w', 16), ('b', 8)):
        REG['r%d%s' % (n, suf)] = ('r%d' % n, w)
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
IMM = re.compile(r'-?(0x[0-9a-fA-F]+|\d+)$')
ALU = ('xor', 'sub', 'add', 'and', 'or')
STRING_OPS = ('stosb', 'stosw', 'stosd', 'stosq', 'movsb', 'movsw', 'movsd', 'movsq', 'lodsb', 'lodsw', 'lodsd', 'lodsq',
              'scasb', 'scasw', 'scasd', 'scasq', 'cmpsb', 'cmpsw', 'cmpsd', 'cmpsq')
XMOV = ('movdqa', 'movdqu', 'movaps', 'movups', 'movapd', 'movupd', 'movq', 'movd', 'movss', 'movsd',
        'pxor', 'xorps', 'xorpd', 'punpcklqdq', 'pshufd', 'paddd', 'paddq', 'psrldq', 'pslldq')


def get(st, name):
    fam, w = REG[name]
    v = st.get(fam)
    return None if v is None else v & msk(w)


def put(st, name, v):
    fam, w = REG[name]
    if v is None:
        st[fam] = None
    elif w >= 32:
        st[fam] = v & msk(w)
    else:
        old = st.get(fam)
        st[fam] = None if old is None else (old & ~msk(w)) | (v & msk(w))


def src_val(st, s, w):
    if s in REG:
        return get(st, s)
    if '[' in s:
        return None
    if IMM.match(s):
        return int(s, 0) & msk(w)
    raise Unsup('operand ' + s)


def cond(mn, fl):
    if fl is None:
        return None
    if fl[0] == 'res':
        if mn not in ('je', 'jz', 'jne', 'jnz'):
            raise Unsup('結果 flags で ' + mn)
        r = fl[1]
        if r is None:
            return None
        return (r == 0) if mn in ('je', 'jz') else (r != 0)
    _, a, b, w = fl
    if a is None or b is None:
        return None
    a &= msk(w)
    b &= msk(w)
    sa = a - (1 << w) if (a >> (w - 1)) & 1 else a
    sb = b - (1 << w) if (b >> (w - 1)) & 1 else b
    t = {'je': a == b, 'jz': a == b, 'jne': a != b, 'jnz': a != b,
         'jb': a < b, 'jc': a < b, 'jnae': a < b, 'jae': a >= b, 'jnb': a >= b, 'jnc': a >= b,
         'ja': a > b, 'jnbe': a > b, 'jbe': a <= b, 'jna': a <= b,
         'jl': sa < sb, 'jnge': sa < sb, 'jge': sa >= sb, 'jnl': sa >= sb,
         'jg': sa > sb, 'jnle': sa > sb, 'jle': sa <= sb, 'jng': sa <= sb}
    if mn not in t:
        raise Unsup(mn)
    return t[mn]


def run(insns, probe, fam):
    """probe に届く全経路で fam の値を集める。値は int か None (未知)。"""
    idx = {x.address: i for i, x in enumerate(insns)}
    vals, steps = set(), 0
    stack = [(0, {}, None)]
    while stack:
        i, st, fl = stack.pop()
        while True:
            steps += 1
            if steps > MAX_STEPS:
                raise Stop('step 上限')
            if i >= len(insns):
                raise Unsup('関数末尾を越えた')
            if i == probe:
                vals.add(st.get(fam))
            x = insns[i]
            mn = x.mnemonic
            ops = [o.strip() for o in x.op_str.split(',')] if x.op_str else []
            if mn == 'ret':
                break
            if mn == 'nop':
                i += 1
                continue
            if mn == 'jmp':
                i = idx[int(ops[0], 0)]
                continue
            if mn.startswith('j'):
                tgt = idx[int(ops[0], 0)]
                c = cond(mn, fl)
                if c is None:
                    stack.append((tgt, dict(st), fl))
                    i += 1
                else:
                    i = tgt if c else i + 1
                continue
            if mn == 'call':
                for f in VOLATILE:
                    st[f] = None
                fl = None
                i += 1
                continue
            if mn == 'push':
                if ops[0] not in REG:
                    raise Unsup('push ' + ops[0])
                st['__stk'] = st.get('__stk', ()) + (get(st, ops[0]),)
                i += 1
                continue
            if mn == 'pop':
                if ops[0] not in REG:
                    raise Unsup('pop ' + ops[0])
                stk = st.get('__stk', ())
                if not stk:
                    raise Unsup('pop で空スタック')
                st['__stk'] = stk[:-1]
                put(st, ops[0], stk[-1])
                i += 1
                continue
            if mn == 'lea':
                dst = ops[0]
                if dst not in REG:
                    raise Unsup('lea メモリ宛先')
                put(st, dst, None)
                i += 1
                continue
            if mn in ('mov', 'movabs'):
                dst, src = ops
                if dst not in REG:
                    i += 1
                    continue
                put(st, dst, src_val(st, src, REG[dst][1]))
                i += 1
                continue
            if mn in ALU or mn in ('cmp', 'test'):
                dst, src = ops
                if '[' in dst or '[' in src:
                    if mn not in ('cmp', 'test') and dst in REG:
                        put(st, dst, None)
                    fl = None
                    i += 1
                    continue
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                a = get(st, dst)
                if mn == 'cmp':
                    fl = ('cmp', a, src_val(st, src, w), w)
                    i += 1
                    continue
                b = src_val(st, src, w)
                if mn == 'test':
                    fl = ('res', None if a is None or b is None else (a & b), w)
                    i += 1
                    continue
                if dst == src and mn in ('xor', 'sub'):
                    r = 0
                elif a is None or b is None:
                    r = None
                else:
                    r = {'xor': a ^ b, 'sub': a - b, 'add': a + b, 'and': a & b, 'or': a | b}[mn] & msk(w)
                put(st, dst, r)
                fl = ('res', r, w)
                i += 1
                continue
            if mn in ('inc', 'dec'):
                dst = ops[0]
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                a = get(st, dst)
                r = None if a is None else (a + (1 if mn == 'inc' else -1)) & msk(w)
                put(st, dst, r)
                fl = ('res', r, w)
                i += 1
                continue
            if mn in ('movzx', 'movsx', 'movsxd'):
                dst, src = ops
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                if src not in REG:
                    put(st, dst, None)
                    i += 1
                    continue
                sw = REG[src][1]
                sv = get(st, src)
                if sv is None:
                    v = None
                elif mn == 'movzx':
                    v = sv & msk(sw)
                else:
                    sv &= msk(sw)
                    if (sv >> (sw - 1)) & 1:
                        sv -= 1 << sw
                    v = sv & msk(w)
                put(st, dst, v)
                i += 1
                continue
            if mn in STRING_OPS and 'xmm' not in x.op_str:
                for f in ('rsi', 'rdi', 'rcx'):
                    st[f] = None
                i += 1
                continue
            if mn in XMOV and ops:
                if ops[0] in REG:
                    put(st, ops[0], None)
                i += 1
                continue
            raise Unsup(mn)
    return vals


def verify(insns, probe, fam, claim=None):
    """戻り値: (判定, 詳細)。判定は 実値化 / 未決 / PASS / FAIL / 判定不能 のいずれか。"""
    try:
        vals = run(insns, probe, fam)
    except (Unsup, Stop, KeyError, ValueError) as e:
        return '判定不能', '%s: %s' % (type(e).__name__, e)
    if not vals:
        return '判定不能', 'probe に到達しない'
    if None in vals:
        return '判定不能', '値が未知の経路がある'
    if len(vals) > 1:
        return ('FAIL' if claim is not None else '未決'), '経路で値が違う: ' + ','.join(hex(v) for v in sorted(vals))
    v = vals.pop()
    if claim is None:
        return '実値化', hex(v)
    return ('PASS' if v == claim else 'FAIL'), 'claim %s / 実測 %s' % (hex(claim), hex(v))


def selftest():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    B = 0x1000
    cases = [
        # (名前, 機械語, probe の命令 index, fam, claim, 期待)
        ('K0 xor ebx; movzx edx,bl (直線)', '31db0fb6d3c3', 2, 'rdx', 0x0, 'PASS'),
        ('K0 ネガティブ (+1)', '31db0fb6d3c3', 2, 'rdx', 0x1, 'FAIL'),
        ('K1 未知分岐の両経路で同値', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x0, 'PASS'),
        ('K1 ネガティブ (+1)', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x1, 'FAIL'),
        ('K2 循環 (rdx は 1 周目 0・2 周目 1 → 出口で 1)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x1, 'PASS'),
        ('K2 ネガティブ (値 0 と誤る)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x0, 'FAIL'),
        ('K3 部分書込 (旧値未知)', '31db' '660fb6d3' 'c3', 2, 'rdx', 0x0, '判定不能'),
        ('K4 call を挟む分岐 (callee が ZF を変えうる)', '31db' '83fb00' 'e800000000' '7405' 'bb01000000' '0fb6d3' 'c3', 6, 'rdx', None, '未決'),
        ('K4 ネガティブ (call 挟む・claim 0x0)', '31db' '83fb00' 'e800000000' '7405' 'bb01000000' '0fb6d3' 'c3', 6, 'rdx', 0x0, 'FAIL'),
        ('K4 対照 (call なし・ZF 確定で 0x0)', '31db' '83fb00' '7405' 'bb01000000' '0fb6d3' 'c3', 5, 'rdx', None, '実値化'),
    ]
    bad = 0
    for name, hx, probe, fam, claim, expect in cases:
        insns = list(md.disasm(bytes.fromhex(hx), B))
        got, det = verify(insns, probe, fam, claim)
        ok = got == expect
        bad += not ok
        print('[selftest] %-44s 期待 %-6s 判定 %-6s %s %s' % (name, expect, got, det, 'OK' if ok else 'NG'))
    print('[selftest] %d 件 / 不一致 %d' % (len(cases), bad))
    return bad


def real(rows_path, pe):
    sys.path.insert(0, os.path.join(HERE, 'ldfix'))
    sys.path.insert(0, HERE)
    import ldmach
    import m11_argrecover as AR
    rows = [r for r in json.load(open(rows_path)) if r['class'] == '実値化']
    print('[verify] 実値化 行 %d 件' % len(rows))
    if not rows:
        return 0
    mach = ldmach.Machine(pe)
    cnt = collections.Counter()
    for r in rows:
        cva = int(r['caller'].split('_')[1], 16)
        tva = int(r['callee'].split('_')[1], 16)
        insns = AR.Fn(mach, cva).ins
        calls = [i for i, x in enumerate(insns) if x.mnemonic == 'call' and x.op_str.startswith('0x')
                 and int(x.op_str, 0) == tva]
        got, det = verify(insns, calls[r['k']], r['fam'], int(r['value'], 0))
        cnt[got] += 1
        print('[verify] %s -> %s pos %d: %s %s' % (r['caller'], r['callee'], r['pos'], got, det))
    print('[verify] 集計 ' + ' '.join('%s %d' % (k, v) for k, v in sorted(cnt.items())))
    return cnt['FAIL']


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('rows', nargs='?')
    ap.add_argument('--pe')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    if not a.rows or not a.pe:
        ap.error('ROWS と --pe を指定する (合成検査は --selftest)')
    sys.exit(1 if real(a.rows, a.pe) else 0)
