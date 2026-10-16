#!/usr/bin/env python3
"""set_other 非 imm reg 台帳の 実値化 行の独立照合 (#3916 / M11-N198).

m11_setother_nonimm_cfg.py (CFG 到達定義を逆向きに追う) と別手法で照合する。
  手法: 関数を入口から具体実行し、probe (呼出し点) に届く全経路の値を集める。
    - 分岐条件が未知なら両方向を辿る (過大近似)。probe で値が未知の経路が 1 つでもあれば 判定不能。
    - 命令の意味は op_str の文字列だけで読む (capstone の regs_access / rw は使わない)。
    - 未対応の命令・step 上限・未知の flags は 判定不能 (PASS にしない)。
    - 値が未知の経路には、未知の源の類を付ける (入力引数 / スタック slot / メモリ読込 / call 戻り値 / その他)。
      類は判定を変えない (分類の追加だけ)。
使い方:
  python3 m11_setother_nonimm_cfg_verify.py --selftest         合成検査 (期待値と照合・ネガティブコントロール込み)
  python3 m11_setother_nonimm_cfg_verify.py ROWS.json --pe PE  nonimm_cfg_rows.json の 実値化 行を照合 (--all で全行)
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
STK = re.compile(r'\b(rsp|rbp|esp|ebp)\b')


def get(st, name):
    fam, w = REG[name]
    v = st.get(fam)
    return None if v is None else v & msk(w)


def famlab(st, fam):
    """fam が未知のときの源の類。入口から一度も書かれていない reg は 入力引数。"""
    if fam not in st:
        return '入力引数'
    return st.get('#' + fam, 'その他')


def oplab(st, ops):
    """ops のうち最初に未知となるオペランドの源の類。未知が無ければ その他。"""
    for o in ops:
        if o in REG:
            if get(st, o) is None:
                return famlab(st, REG[o][0])
        elif '[' in o:
            return 'スタック slot' if STK.search(o) else 'メモリ読込'
    return 'その他'


def put(st, name, v, lab='その他'):
    fam, w = REG[name]
    if w < 32 and v is not None:
        old = st.get(fam)
        if old is None:
            v = None
            if lab == 'その他':
                lab = famlab(st, fam)
        else:
            v = (old & ~msk(w)) | (v & msk(w))
    if v is None:
        st[fam] = None
        st['#' + fam] = lab
    else:
        st[fam] = v & msk(w) if w >= 32 else v
        st.pop('#' + fam, None)


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
        if mn not in ('je', 'jz', 'jne', 'jnz', 'js', 'jns'):
            return None
        r = fl[1]
        if r is None:
            return None
        if mn in ('js', 'jns'):
            return ((r >> (fl[2] - 1)) & 1 == 1) == (mn == 'js')
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


FAMS = {f for f, _ in REG.values()}


def atoms(*ss):
    """類の文字列 (原子を / で連結したもの) の和集合を、正規形 (ソート済み・重複なし) で返す。"""
    return '/'.join(sorted({a for s in ss if s for a in s.split('/')}))


def join(s1, f1, s2, f2):
    """併合: 同じ ip に届く 2 つの状態の上界を返す。値が一致しない reg・flags は未知にし、類は和集合にする。
    片方にだけある reg は、入口から書かれていなければ 入力引数。スタックの深さが違えば併合できないので Unsup。
    値の集合は有限 (int か未知) で、未知は戻らない。類の原子も有限なので、併合の列は必ず止まる。"""
    s1s, s2s = s1.get('__stk', ()), s2.get('__stk', ())
    if len(s1s) != len(s2s):
        raise Unsup('併合: スタックの深さが違う')
    out = {}
    for k in FAMS:
        if k not in s1 and k not in s2:
            continue
        a, b = s1.get(k), s2.get(k)
        if a is not None and a == b:
            out[k] = a
            continue
        la = None if a is not None else s1.get('#' + k, '入力引数' if k not in s1 else 'その他')
        lb = None if b is not None else s2.get('#' + k, '入力引数' if k not in s2 else 'その他')
        out[k] = None
        out['#' + k] = atoms(la, lb, 'その他' if a is not None and b is not None else None)
    for k in set(s1) | set(s2):
        if k.startswith('#') and k[1:] not in FAMS:
            out[k] = atoms(s1.get(k, 'その他'), s2.get(k, 'その他'))
    if s1s:
        slots = []
        for (v1, l1), (v2, l2) in zip(s1s, s2s):
            if v1 is not None and v1 == v2:
                slots.append((v1, None))
            else:
                slots.append((None, atoms(None if v1 is not None else (l1 or 'その他'),
                                          None if v2 is not None else (l2 or 'その他'),
                                          'その他' if v1 is not None and v2 is not None else None)))
        out['__stk'] = tuple(slots)
    return out, (f1 if f1 == f2 else None)


def run(insns, probe, fam, prune=False, stats=None, merge=False):
    """probe に届く全経路で fam の値を集める。値は int か None (未知)。
    戻り値: (vals, labs)。labs は値が未知の経路の源の類の集合。
    prune=True: 分岐先 (fork の先・ジャンプ先) に、同じ状態 (ip・レジスタ・flags・スタック) で再訪した経路を切る。
      切った先は初回訪問で既に辿られているので、値の集合は変わらない (健全)。
      切断の種類: 後方の再訪 = ループ、前方の再訪 = 未知分岐の合流 (diamond)。stats に件数を積む。
    merge=True: prune の代わりに、分岐先の到達を同じ ip の状態への併合 (join) にする。
      状態が増えた (併合で変わった) ときだけ再探索するので、有限回で止まる。併合後の状態は全到達状態の上界なので健全。
      値が一致しない reg は未知になる (未決にはならず判定不能)。カウンタの付くループは 1 周で未知になる (精度は落ちる)。"""
    idx = {x.address: i for i, x in enumerate(insns)}
    vals, labs, steps = set(), set(), 0
    stats = {} if stats is None else stats
    seen = set()
    joined = {}

    def cut(t, st, fl, src):
        if not prune:
            return False
        key = (t, tuple(sorted(st.items())), fl)
        if key not in seen:
            seen.add(key)
            return False
        k = '刈り込み(ループ)' if t <= src else '刈り込み(分岐の合流)'
        stats[k] = stats.get(k, 0) + 1
        return True

    def arrive(t, st, fl, src):
        """分岐先 t に状態 (st, fl) が届いた。続けるべき状態を返す。None なら、その先は辿らない。"""
        if not merge:
            return None if cut(t, st, fl, src) else (st, fl)
        if t not in joined:
            joined[t] = (dict(st), fl)
            return dict(st), fl
        ns, nf = join(joined[t][0], joined[t][1], st, fl)
        if ns == joined[t][0] and nf == joined[t][1]:
            stats['併合で停止'] = stats.get('併合で停止', 0) + 1
            return None
        joined[t] = (ns, nf)
        k = '併合(ループ)' if t <= src else '併合(分岐の合流)'
        stats[k] = stats.get(k, 0) + 1
        return dict(ns), nf

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
                if st.get(fam) is None:
                    labs.add(famlab(st, fam))
            x = insns[i]
            mn = x.mnemonic
            ops = [o.strip() for o in x.op_str.split(',')] if x.op_str else []
            if mn == 'ret':
                break
            if mn == 'nop':
                i += 1
                continue
            if mn == 'jmp':
                t = idx[int(ops[0], 0)]
                if merge:
                    r = arrive(t, st, fl, i)
                    if r is None:
                        break
                    st, fl = r
                    i = t
                    continue
                if cut(t, st, fl, i):
                    break
                i = t
                continue
            if mn.startswith('j'):
                tgt = idx[int(ops[0], 0)]
                c = cond(mn, fl)
                if c is None:
                    stats['未知分岐'] = stats.get('未知分岐', 0) + 1
                    if merge:
                        for t2 in (tgt, i + 1):
                            r = arrive(t2, st, fl, i)
                            if r is not None:
                                stack.append((t2, r[0], r[1]))
                        break
                    if not cut(tgt, st, fl, i):
                        stack.append((tgt, dict(st), fl))
                    if cut(i + 1, st, fl, i):
                        break
                    i += 1
                else:
                    i = tgt if c else i + 1
                continue
            if mn == 'call':
                for f in VOLATILE:
                    st[f] = None
                    st['#' + f] = 'call 戻り値'
                st['#flags'] = 'call 戻り値'
                fl = None
                i += 1
                continue
            if mn == 'push':
                if ops[0] not in REG:
                    raise Unsup('push ' + ops[0])
                v = get(st, ops[0])
                lab = None if v is not None else famlab(st, REG[ops[0]][0])
                st['__stk'] = st.get('__stk', ()) + ((v, lab),)
                i += 1
                continue
            if mn == 'pop':
                if ops[0] not in REG:
                    raise Unsup('pop ' + ops[0])
                stk = st.get('__stk', ())
                if not stk:
                    raise Unsup('pop で空スタック')
                st['__stk'] = stk[:-1]
                v, lab = stk[-1]
                put(st, ops[0], v, lab or 'その他')
                i += 1
                continue
            if mn == 'lea':
                dst = ops[0]
                if dst not in REG:
                    raise Unsup('lea メモリ宛先')
                put(st, dst, None, 'スタック slot' if STK.search(ops[-1]) else 'その他')
                i += 1
                continue
            if mn in ('mov', 'movabs'):
                dst, src = ops
                if dst not in REG:
                    i += 1
                    continue
                v = src_val(st, src, REG[dst][1])
                put(st, dst, v, 'その他' if v is not None else oplab(st, [src]))
                i += 1
                continue
            if mn in ALU or mn in ('cmp', 'test'):
                dst, src = ops
                if '[' in dst or '[' in src:
                    mem = dst if '[' in dst else src
                    lab = oplab(st, [mem])
                    if mn not in ('cmp', 'test') and dst in REG:
                        put(st, dst, None, lab)
                    fl = None
                    st['#flags'] = lab
                    i += 1
                    continue
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                a = get(st, dst)
                b = src_val(st, src, w)
                lab = oplab(st, [dst, src])
                if mn == 'cmp':
                    fl = ('cmp', a, b, w)
                    st['#flags'] = lab if a is None or b is None else 'その他'
                    i += 1
                    continue
                if mn == 'test':
                    fl = ('res', None if a is None or b is None else (a & b), w)
                    st['#flags'] = lab if fl[1] is None else 'その他'
                    i += 1
                    continue
                if dst == src and mn in ('xor', 'sub'):
                    r = 0
                elif a is None or b is None:
                    r = None
                else:
                    r = {'xor': a ^ b, 'sub': a - b, 'add': a + b, 'and': a & b, 'or': a | b}[mn] & msk(w)
                put(st, dst, r, lab)
                fl = ('res', r, w)
                st['#flags'] = lab if r is None else 'その他'
                i += 1
                continue
            if mn in ('inc', 'dec'):
                dst = ops[0]
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                a = get(st, dst)
                r = None if a is None else (a + (1 if mn == 'inc' else -1)) & msk(w)
                lab = oplab(st, [dst])
                put(st, dst, r, lab)
                fl = ('res', r, w)
                st['#flags'] = lab if r is None else 'その他'
                i += 1
                continue
            if mn in ('shl', 'sal', 'shr', 'sar') and len(ops) == 2 and ops[0] in REG:
                dst, src = ops
                w = REG[dst][1]
                a = get(st, dst)
                if src in REG:
                    if src != 'cl':
                        raise Unsup('シフト数 ' + src)
                    c = get(st, 'rcx')
                    c = None if c is None else c & (0x3f if w == 64 else 0x1f)
                else:
                    c = int(src, 0) & (0x3f if w == 64 else 0x1f)
                if a is None or c is None:
                    r = None
                elif mn == 'shr':
                    r = (a >> c) & msk(w)
                elif mn == 'sar':
                    s = a - (1 << w) if (a >> (w - 1)) & 1 else a
                    r = (s >> c) & msk(w)
                else:
                    r = (a << c) & msk(w)
                lab = oplab(st, [dst, src])
                put(st, dst, r, lab)
                fl = None
                st['#flags'] = lab if r is None else 'その他'
                i += 1
                continue
            if mn == 'not' and ops and ops[0] in REG:
                w = REG[ops[0]][1]
                a = get(st, ops[0])
                put(st, ops[0], None if a is None else (~a) & msk(w), oplab(st, [ops[0]]))
                i += 1
                continue
            if mn == 'imul' and len(ops) == 1:
                src = ops[0]
                if src in REG:
                    w = REG[src][1]
                    if w not in (32, 64):
                        raise Unsup('imul 1 オペランドの幅 %d' % w)
                    ax, dx = ('eax', 'edx') if w == 32 else ('rax', 'rdx')
                    a = get(st, ax)
                    b = get(st, src)
                    if a is None or b is None:
                        lab = oplab(st, [ax, src])
                        put(st, ax, None, lab)
                        put(st, dx, None, lab)
                    else:
                        sa = a - (1 << w) if (a >> (w - 1)) & 1 else a
                        sb = b - (1 << w) if (b >> (w - 1)) & 1 else b
                        p = sa * sb
                        put(st, ax, p & msk(w))
                        put(st, dx, (p >> w) & msk(w))
                else:
                    lab = oplab(st, [src])
                    put(st, 'eax', None, lab)
                    put(st, 'edx', None, lab)
                fl = None
                st['#flags'] = 'その他'
                i += 1
                continue
            if mn == 'imul' and len(ops) in (2, 3) and ops[0] in REG:
                dst, src = ops[0], ops[1]
                w = REG[dst][1]
                a = get(st, src) if len(ops) == 3 else get(st, dst)
                b = src_val(st, ops[2] if len(ops) == 3 else src, w)
                r = None if a is None or b is None else (a * b) & msk(w)
                lab = oplab(st, ops)
                put(st, dst, r, lab)
                fl = None
                st['#flags'] = lab if r is None else 'その他'
                i += 1
                continue
            if mn in ('cdq', 'cqo') and not ops:
                w = 64 if mn == 'cqo' else 32
                a = get(st, 'rax' if w == 64 else 'eax')
                put(st, 'rdx', None if a is None else (msk(w) if (a >> (w - 1)) & 1 else 0),
                    oplab(st, ['rax' if w == 64 else 'eax']))
                i += 1
                continue
            if mn == 'idiv' and ops and (ops[0] in REG and REG[ops[0]][1] == 32 or '[' in ops[0]):
                d = get(st, ops[0]) if ops[0] in REG else None
                ax = get(st, 'eax')
                dx = get(st, 'edx')
                if d is None or ax is None or dx is None:
                    lab = oplab(st, ['eax', 'edx', ops[0]])
                    put(st, 'eax', None, lab)
                    put(st, 'edx', None, lab)
                else:
                    n = ((dx << 32) | ax) - ((1 << 64) if (dx >> 31) & 1 else 0)
                    dv = d - (1 << 32) if (d >> 31) & 1 else d
                    if dv == 0:
                        raise Unsup('idiv 0 除算 (#DE)')
                    q = abs(n) // abs(dv) * (1 if (n < 0) == (dv < 0) else -1)
                    r = n - q * dv
                    if not -(1 << 31) <= q < (1 << 31):
                        raise Unsup('idiv 商のオーバーフロー (#DE)')
                    put(st, 'eax', q & msk(32))
                    put(st, 'edx', r & msk(32))
                fl = None
                st['#flags'] = 'その他'
                i += 1
                continue
            if mn == 'neg' and ops and ops[0] in REG:
                w = REG[ops[0]][1]
                a = get(st, ops[0])
                r = None if a is None else (-a) & msk(w)
                lab = oplab(st, [ops[0]])
                put(st, ops[0], r, lab)
                fl = ('res', r, w)
                st['#flags'] = lab if r is None else 'その他'
                i += 1
                continue
            if mn.startswith('set') and len(mn) > 3 and ops and ops[0] in REG:
                c = cond('j' + mn[3:], fl)
                put(st, ops[0], None if c is None else int(c), st.get('#flags', 'その他'))
                i += 1
                continue
            if mn in ('movzx', 'movsx', 'movsxd'):
                dst, src = ops
                if dst not in REG:
                    raise Unsup('メモリ宛先 ' + mn)
                w = REG[dst][1]
                if src not in REG:
                    put(st, dst, None, oplab(st, [src]))
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
                put(st, dst, v, 'その他' if v is not None else oplab(st, [src]))
                i += 1
                continue
            if mn in STRING_OPS and 'xmm' not in x.op_str:
                for f in ('rsi', 'rdi', 'rcx'):
                    st[f] = None
                    st['#' + f] = 'その他'
                i += 1
                continue
            if ops and ops[0].startswith('xmm'):
                if mn.startswith(('ucomis', 'comis')):
                    fl = None
                    st['#flags'] = 'その他'
                i += 1
                continue
            if mn.startswith('cvt') and ops and ops[0] in REG:
                put(st, ops[0], None, oplab(st, ops[1:]))
                i += 1
                continue
            if mn in XMOV and ops:
                if ops[0] in REG:
                    put(st, ops[0], None, oplab(st, ops[1:]))
                i += 1
                continue
            raise Unsup(mn)
    return vals, labs


def verify(insns, probe, fam, claim=None, prune=False, merge=False):
    """戻り値: (判定, 詳細)。判定は 実値化 / 未決 / PASS / FAIL / 判定不能 のいずれか。
    prune=True で step 上限の打ち切りを刈り込みで収束させる (既定は False = 従来の判定)。
    merge=True は prune の代わりに同じ ip の状態を併合する (run の説明を参照)。
    判定不能 (値が未知の経路) の詳細は末尾の '類=' に未知の源の類を付ける。"""
    stats = {}
    try:
        vals, labs = run(insns, probe, fam, prune, stats, merge)
    except (Unsup, Stop, KeyError, ValueError) as e:
        if isinstance(e, Stop) and (prune or merge):
            return '判定不能', '%s後も step 上限 (未知分岐 %d・%s %d)' % (
                '併合' if merge else '刈り込み', stats.get('未知分岐', 0),
                '併合' if merge else '刈り込み',
                sum(v for k, v in stats.items() if k.startswith('併合' if merge else '刈り込み')))
        return '判定不能', '%s: %s' % (type(e).__name__, e)
    if not vals:
        return '判定不能', 'probe に到達しない'
    if None in vals:
        cut_txt = ''
        if prune and stats.get('刈り込み(ループ)', 0) + stats.get('刈り込み(分岐の合流)', 0):
            cut_txt = ' (刈り込み ループ %d・分岐の合流 %d)' % (
                stats.get('刈り込み(ループ)', 0), stats.get('刈り込み(分岐の合流)', 0))
        if merge and stats.get('併合(ループ)', 0) + stats.get('併合(分岐の合流)', 0):
            cut_txt = ' (併合 ループ %d・分岐の合流 %d)' % (
                stats.get('併合(ループ)', 0), stats.get('併合(分岐の合流)', 0))
        return '判定不能', '値が未知の経路がある%s 類=%s' % (cut_txt, '/'.join(sorted(labs)))
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
        ('S1 shl ebx,3 (1→8)', 'bb01000000c1e3030fb6d3c3', 3, 'rdx', 0x8, 'PASS'),
        ('S1 ネガティブ (+1)', 'bb01000000c1e3030fb6d3c3', 3, 'rdx', 0x9, 'FAIL'),
        ('S2 neg ebx (5→0xfb 下位 8bit)', 'bb05000000f7db0fb6d3c3', 3, 'rdx', 0xfb, 'PASS'),
        ('S2 ネガティブ (0x05)', 'bb05000000f7db0fb6d3c3', 3, 'rdx', 0x5, 'FAIL'),
        ('S3 shr ebx,4 (0x80→0x8)', 'bb80000000c1eb040fb6d3c3', 3, 'rdx', 0x8, 'PASS'),
        ('S3 ネガティブ (0x80)', 'bb80000000c1eb040fb6d3c3', 3, 'rdx', 0x80, 'FAIL'),
        ('S4 shl ebx,cl (1<<4)', 'bb01000000b904000000d3e30fb6d3c3', 4, 'rdx', 0x10, 'PASS'),
        ('S4 ネガティブ (0x1)', 'bb01000000b904000000d3e30fb6d3c3', 4, 'rdx', 0x1, 'FAIL'),
        ('S5 sete (cmp 等しい→1)', 'bb00000000b90100000083f9010f94c30fb6d3c3', 5, 'rdx', 0x1, 'PASS'),
        ('S5 ネガティブ (0x0)', 'bb00000000b90100000083f9010f94c30fb6d3c3', 5, 'rdx', 0x0, 'FAIL'),
        ('S6 cvtsi2sd・mulss は整数 rbx を変えない', 'bb02000000f2480f2ac3f30f59c80fb6d3c3', 4, 'rdx', 0x2, 'PASS'),
        ('S6 ネガティブ (0x3)', 'bb02000000f2480f2ac3f30f59c80fb6d3c3', 4, 'rdx', 0x3, 'FAIL'),
        ('S7 ucomiss で flags 未知・両経路で 0x0/0x1', '31db0f2ec17405bb010000000fb6d3c3', 5, 'rdx', None, '未決'),
        ('S7 ネガティブ (claim 0x0)', '31db0f2ec17405bb010000000fb6d3c3', 5, 'rdx', 0x0, 'FAIL'),
        ('S8 jle 結果 flags (OF 不明) は両経路で 0x0/0x1', '31db85db7e05bb010000000fb6d3c3', 5, 'rdx', None, '未決'),
        ('S8 ネガティブ (claim 0x1)', '31db85db7e05bb010000000fb6d3c3', 5, 'rdx', 0x1, 'FAIL'),
        ('S9 imul ebx,ebx,5 (3*5=15)', 'bb030000006bdb050fb6d3c3', 3, 'rdx', 0xf, 'PASS'),
        ('S9 ネガティブ (0x10)', 'bb030000006bdb050fb6d3c3', 3, 'rdx', 0x10, 'FAIL'),
        ('S10 not ebx (0→0xff 下位 8bit)', 'bb00000000f7d30fb6d3c3', 3, 'rdx', 0xff, 'PASS'),
        ('S10 ネガティブ (0x00)', 'bb00000000f7d30fb6d3c3', 3, 'rdx', 0x0, 'FAIL'),
        ('I1 imul ebx 1 オペランド (eax=3*5 下位 15)', 'b803000000bb05000000f7ebc3', 3, 'rax', 0xf, 'PASS'),
        ('I1 ネガティブ (0x10)', 'b803000000bb05000000f7ebc3', 3, 'rax', 0x10, 'FAIL'),
        ('I2 imul ebx 1 オペランド (2^32 → edx=1)', 'b800000100bb00000100f7ebc3', 3, 'rdx', 0x1, 'PASS'),
        ('I2 ネガティブ (edx=0)', 'b800000100bb00000100f7ebc3', 3, 'rdx', 0x0, 'FAIL'),
        ('I3 imul ebx 符号 (-1*2 → edx=0xffffffff)', 'b8ffffffffbb02000000f7ebc3', 3, 'rdx', 0xffffffff, 'PASS'),
        ('I3 ネガティブ (edx=0)', 'b8ffffffffbb02000000f7ebc3', 3, 'rdx', 0x0, 'FAIL'),
        ('I4 imul rbx 1 オペランド (64bit 符号 → rdx=-1)', '48c7c0ffffffff48c7c302000000' '48f7ebc3', 3, 'rdx', 0xffffffffffffffff, 'PASS'),
        ('I4 ネガティブ (rdx=0)', '48c7c0ffffffff48c7c302000000' '48f7ebc3', 3, 'rdx', 0x0, 'FAIL'),
        ('I5 imul ebx 1 オペランド・eax 未知 → 判定不能', 'e800000000bb02000000f7ebc3', 3, 'rdx', None, '判定不能'),
        ('I6 imul メモリ 1 オペランド → 判定不能', 'b803000000f72d00000000c3', 2, 'rdx', None, '判定不能'),
        ('C1 cdq eax=-1 → edx=0xffffffff', 'b8ffffffff99c3', 2, 'rdx', 0xffffffff, 'PASS'),
        ('C1 ネガティブ (0x0)', 'b8ffffffff99c3', 2, 'rdx', 0x0, 'FAIL'),
        ('C2 cdq eax=1 → edx=0', 'b801000000' '99' 'c3', 2, 'rdx', 0x0, 'PASS'),
        ('C2 ネガティブ (0xffffffff)', 'b801000000' '99' 'c3', 2, 'rdx', 0xffffffff, 'FAIL'),
        ('C3 cqo rax=-1 → rdx=-1', '48c7c0ffffffff' '4899' 'c3', 2, 'rdx', 0xffffffffffffffff, 'PASS'),
        ('C3 ネガティブ (0xffffffff)', '48c7c0ffffffff' '4899' 'c3', 2, 'rdx', 0xffffffff, 'FAIL'),
        ('C4 cdq で eax 未知 → 判定不能', 'e800000000' '99' 'c3', 2, 'rdx', None, '判定不能'),
        ('D1 idiv: -7/2 → 余り -1 (edx)', 'b8f9ffffff' '99' 'bb02000000' 'f7fb' 'c3', 4, 'rdx', 0xffffffff, 'PASS'),
        ('D1 ネガティブ (余り 1 と誤る)', 'b8f9ffffff' '99' 'bb02000000' 'f7fb' 'c3', 4, 'rdx', 0x1, 'FAIL'),
        ('D2 idiv: 7/2 → 余り 1', 'b807000000' '99' 'bb02000000' 'f7fb' 'c3', 4, 'rdx', 0x1, 'PASS'),
        ('D2 ネガティブ (余り 0)', 'b807000000' '99' 'bb02000000' 'f7fb' 'c3', 4, 'rdx', 0x0, 'FAIL'),
        ('D3 idiv 除数が未知 → 判定不能', 'b807000000' '99' 'e800000000' 'f7f9' 'c3', 5, 'rdx', None, '判定不能'),
        ('D4 idiv 除数 0 → 判定不能', 'b807000000' '99' 'bb00000000' 'f7fb' 'c3', 5, 'rdx', None, '判定不能'),
        ('D5 idiv メモリ除数 → 商・余りは未知', 'b807000000' '99' '8b0d00000000' 'f77900' 'c3', 4, 'rdx', None, '判定不能'),
        ('E1 sar ebx,1 (-4 → -2, 下位 8bit 0xfe)', 'bbfcffffff' 'd1fb' '0fb6d3c3', 3, 'rdx', 0xfe, 'PASS'),
        ('E1 ネガティブ (0x7f)', 'bbfcffffff' 'd1fb' '0fb6d3c3', 3, 'rdx', 0x7f, 'FAIL'),
        ('E2 sar ebx,4 (0x80 → 0x8 、符号なし)', 'bb80000000c1fb040fb6d3c3', 3, 'rdx', 0x8, 'PASS'),
        ('E2 ネガティブ (0x0)', 'bb80000000c1fb040fb6d3c3', 3, 'rdx', 0x0, 'FAIL'),
    ]
    # 刈り込み (--prune) の検査: 同じ入力で prune の有無を比べる。
    #   P1 ループ (K2 と同じ循環・出口で rdx=1): prune 無し・有りとも 0x1 (PASS)。claim 0x0 は FAIL。
    #   P2 分岐 1 つ (K1 と同じ・両経路同値): prune 有りでも 0x0 (PASS)。
    #   P3 ループ内に未知分岐 (合流で刈る): prune 有りで PASS (rbx=5)、prune 無しは step 上限 (判定不能)。
    #   P4 無限ループ (出口なし): prune 有りでも step 上限に届かず 判定不能 (刈り込み)。
    prune_cases = [
        ('P1 ループ・刈り込み有り (rdx=1)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x1, 'PASS', True),
        ('P1 ネガティブ (刈り込み有り・claim 0x0)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x0, 'FAIL', True),
        ('P2 分岐 1 つ・刈り込み有り (両経路 0x0)', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x0, 'PASS', True),
        ('P2 ネガティブ (刈り込み有り・claim 0x1)', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x1, 'FAIL', True),
        ('P3 未知分岐を出口に持つループ・刈り込み有り (rbx=5)', 'bb05000000' 'e800000000' '7402' 'ebf7' 'c3', 4, 'rbx', 0x5, 'PASS', True),
        ('P3 ネガティブ (刈り込み有り・claim 0x6)', 'bb05000000' 'e800000000' '7402' 'ebf7' 'c3', 4, 'rbx', 0x6, 'FAIL', True),
        ('P3 ネガティブ (刈り込み無し → step 上限)', 'bb05000000' 'e800000000' '7402' 'ebf7' 'c3', 4, 'rbx', 0x5, '判定不能', False),
        ('P4 出口なしループ・刈り込み有り (rdx=0 で実値化)', '31d2' 'ebfe', 1, 'rdx', None, '実値化', True),
        ('P4 ネガティブ (刈り込み無し → step 上限で判定不能)', '31d2' 'ebfe', 1, 'rdx', None, '判定不能', False),
    ]
    bad = 0
    for name, hx, probe, fam, claim, expect in cases:
        insns = list(md.disasm(bytes.fromhex(hx), B))
        got, det = verify(insns, probe, fam, claim)
        ok = got == expect
        bad += not ok
        print('[selftest] %-44s 期待 %-6s 判定 %-6s %s %s' % (name, expect, got, det, 'OK' if ok else 'NG'))
    for name, hx, probe, fam, claim, expect, prune in prune_cases:
        insns = list(md.disasm(bytes.fromhex(hx), B))
        got, det = verify(insns, probe, fam, claim, prune)
        ok = got == expect
        bad += not ok
        print('[selftest] %-44s 期待 %-6s 判定 %-6s %s %s' % (name, expect, got, det, 'OK' if ok else 'NG'))
    # 併合 (--merge) の検査: 同じ ip の状態を値ごとに併合する。値が一致すれば保つ・違えば未知にする。
    #   M1 分岐 1 つ・両経路同値 (K1 と同じ): 併合でも 0x0 (PASS)。claim 0x1 は FAIL。
    #   M2 ループ内に未知分岐 (P3 と同じ・rbx は一定): 併合で収束して PASS (rbx=5)。claim 0x6 は FAIL。
    #   M3 出口なし無限ループ (P4 と同じ): 併合で同じ状態に戻り止まり、rdx=0 で実値化。
    #   M4 カウンタ付きループ (K2 と同じ・条件は確定): 確定分岐は併合の対象外で具体実行のまま PASS (rdx=1)。
    merge_cases = [
        ('M1 分岐 1 つ・併合 (両経路 0x0)', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x0, 'PASS'),
        ('M1 ネガティブ (併合・claim 0x1)', '31db83ff007405' '31d2' 'eb03' '90' '31d2' 'c3', 7, 'rdx', 0x1, 'FAIL'),
        ('M2 未知分岐を出口に持つループ・併合 (rbx=5)', 'bb05000000' 'e800000000' '7402' 'ebf7' 'c3', 4, 'rbx', 0x5, 'PASS'),
        ('M2 ネガティブ (併合・claim 0x6)', 'bb05000000' 'e800000000' '7402' 'ebf7' 'c3', 4, 'rbx', 0x6, 'FAIL'),
        ('M3 出口なしループ・併合 (rdx=0 で実値化)', '31d2' 'ebfe', 1, 'rdx', None, '実値化'),
        ('M3 ネガティブ (併合・claim 0x1 は FAIL)', '31d2' 'ebfe', 1, 'rdx', 0x1, 'FAIL'),
        ('M4 カウンタ付きループ・併合 (確定分岐は具体実行 rdx=1)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x1, 'PASS'),
        ('M4 ネガティブ (併合・claim 0x0)', '31db' '89da' '83c301' '83fb02' '75f6' 'c3', 5, 'rdx', 0x0, 'FAIL'),
    ]
    for name, hx, probe, fam, claim, expect in merge_cases:
        insns = list(md.disasm(bytes.fromhex(hx), B))
        got, det = verify(insns, probe, fam, claim, merge=True)
        ok = got == expect
        bad += not ok
        print('[selftest] %-44s 期待 %-6s 判定 %-6s %s %s' % (name, expect, got, det, 'OK' if ok else 'NG'))
    # 未知の源の類 (値が未知の経路の 類=)。PASS = 類が一致 / FAIL = 類が違う (ネガティブコントロール)。
    lab_cases = [
        ('L1 入力引数 (esi は入口で未知)', '89f30fb6d3c3', 2, 'rdx', '入力引数', 'PASS'),
        ('L1 ネガティブ (類を スタック slot と誤る)', '89f30fb6d3c3', 2, 'rdx', 'スタック slot', 'FAIL'),
        ('L2 スタック slot (mov rax,[rsp+8])', '488b442408' '4889c3' '0fb6d3c3', 3, 'rdx', 'スタック slot', 'PASS'),
        ('L2 ネガティブ (類を メモリ読込 と誤る)', '488b442408' '4889c3' '0fb6d3c3', 3, 'rdx', 'メモリ読込', 'FAIL'),
        ('L3 メモリ読込 (mov rax,[rbx])', '488b03' '4889c3' '0fb6d3c3', 3, 'rdx', 'メモリ読込', 'PASS'),
        ('L3 ネガティブ (類を 入力引数 と誤る)', '488b03' '4889c3' '0fb6d3c3', 3, 'rdx', '入力引数', 'FAIL'),
        ('L4 call 戻り値 (call 後の rax を rbx 経由)', 'e800000000' '4889c3' '0fb6d3c3', 3, 'rdx', 'call 戻り値', 'PASS'),
        ('L4 ネガティブ (類を スタック slot と誤る)', 'e800000000' '4889c3' '0fb6d3c3', 3, 'rdx', 'スタック slot', 'FAIL'),
        ('L5 その他 (ucomiss の flags 未知を setcc)', '0f2ec1' '0f94c3' '0fb6d3c3', 3, 'rdx', 'その他', 'PASS'),
        ('L5 ネガティブ (類を 入力引数 と誤る)', '0f2ec1' '0f94c3' '0fb6d3c3', 3, 'rdx', '入力引数', 'FAIL'),
    ]
    for name, hx, probe, fam, want, expect in lab_cases:
        insns = list(md.disasm(bytes.fromhex(hx), B))
        got, det = verify(insns, probe, fam, None)
        lab = det.split('類=', 1)[1] if '類=' in det else None
        st = 'PASS' if got == '判定不能' and lab == want else 'FAIL'
        ok = st == expect
        bad += not ok
        print('[selftest] %-44s 期待 %-6s 判定 %-6s 類 %s %s' % (name, expect, st, lab, 'OK' if ok else 'NG'))
    n = len(cases) + len(prune_cases) + len(merge_cases) + len(lab_cases)
    print('[selftest] %d 件 / 不一致 %d' % (n, bad))
    return bad


def real(rows_path, pe, all_rows=False, prune=False, merge=False):
    sys.path.insert(0, os.path.join(HERE, 'ldfix'))
    sys.path.insert(0, HERE)
    import ldmach
    import m11_argrecover as AR
    rows = [r for r in json.load(open(rows_path)) if all_rows or r['class'] == '実値化']
    print('[verify] 対象 %d 件 (all=%s)' % (len(rows), all_rows))
    if not rows:
        return 0
    mach = ldmach.Machine(pe)
    cnt = collections.Counter()
    kinds = collections.Counter()
    for r in rows:
        cva = int(r['caller'].split('_')[1], 16)
        tva = int(r['callee'].split('_')[1], 16)
        insns = AR.Fn(mach, cva).ins
        calls = [i for i, x in enumerate(insns) if x.mnemonic == 'call' and x.op_str.startswith('0x')
                 and int(x.op_str, 0) == tva]
        claim = None if r.get('value') is None else int(r['value'], 0)
        got, det = verify(insns, calls[r['k']], r['fam'], claim, prune, merge)
        cnt[got] += 1
        if got == '判定不能' and '類=' in det:
            kinds[det.split('類=', 1)[1]] += 1
        print('[verify] %s -> %s pos %d: %s %s' % (r['caller'], r['callee'], r['pos'], got, det))
    print('[verify] 集計 ' + ' '.join('%s %d' % (k, v) for k, v in sorted(cnt.items())))
    print('[verify] 値が未知の経路の類 (経路単位の集合) ' + ' '.join('%s %d' % (k, v) for k, v in sorted(kinds.items())))
    return cnt['FAIL']


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('rows', nargs='?')
    ap.add_argument('--pe')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--all', action='store_true', help='class によらず全行を照合する (claim なし)')
    ap.add_argument('--prune', action='store_true', help='同一状態の再訪 (ループ・分岐の合流) を刈り込む (既定は従来どおり)')
    ap.add_argument('--merge', action='store_true', help='分岐の合流を、同じ ip の状態の併合で収束させる (既定は従来どおり)')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    if not a.rows or not a.pe:
        ap.error('ROWS と --pe を指定する (合成検査は --selftest)')
    sys.exit(1 if real(a.rows, a.pe, a.all, a.prune, a.merge) else 0)
