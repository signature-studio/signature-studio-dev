#!/usr/bin/env python3
"""fw_sigfix.py — call site ↔ define 署名整合 (m11 sigfix の一般化; chunked decode の cross-chunk 不一致解消).

背景: 8 chunk + round2/3 の分離 decode では, 呼出側 chunk が callee を declare (推定署名) 扱いにし,
定義側 chunk は prologue から parameter promote したため, call site の引数個数/型/戻り型が
define と食い違う (実測: 引数不一致 ~8.3k site / 戻り不一致 4.6k site / call site 総数 34,088)。

修復規約 (native 機械語の意味を保持; 変換はすべて「命令」として直前に挿入する):
* 引数不足   → 直前に BLK load を挿入して渡す (icall_rewrite の ABI_SPILL が全 dcall site で
               rcx/rdx/r8/r9/xmm0-3 を BLK+8..+0x40 に store 済み = レジスタ引数の正本)。
               5 引数目以降 (stack 引数) は BLK 未対応ゆえ 0 を渡す (既知制約)。
* 引数過剰   → 末尾から削除 (define が読まない引数)。
* 型不一致   → zext / trunc / bitcast / inttoptr / ptrtoint 命令を挿入
               (ptr↔i64 は正確, 整数幅変換は RetDec の幅推定差の近似 — REPORT に明記)。
* 戻り型不一致 → call の戻り型を define に合わせ, 旧型の値を変換命令で再結成 (uses は無改変)。

  python3 fw_sigfix.py IN.ll OUT.ll [--report r.json]
"""
import argparse, json, re


def split_args(s):
    parts, depth, last = [], 0, 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(s[last:i])
            last = i + 1
    parts.append(s[last:])
    return [p.strip() for p in parts if p.strip()]


TYRE = re.compile(r'^(i\d+\*|%[\w.$]+\*|i\d+|float|double|ptr|void)\b')
BLK = 9048064
SLOT = (8, 0x10, 0x18, 0x20)          # rcx, rdx, r8, r9
XSLOT = (0x28, 0x30, 0x38, 0x40)      # xmm0..3 low64
INTS = ('i64', 'i32', 'i16', 'i8', 'i1')


def ptype_of(p):
    m = TYRE.match(p)
    return m.group(1) if m else 'i64'


def norm_ty(t):
    return 'ptr' if (t.endswith('*') or t == 'ptr') else t


ATTR_RE = re.compile(r'^(nonnull|nocapture|readonly|writeonly|returned|immarg|nofree|noundef|align \d+|dereferenceable\(\d+\)|dereferenceable_or_null\(\d+\))\s+')


def strip_ty(tok):
    """型接頭辞 + 引数属性 (nonnull 等) を落とし, 値を返す"""
    s = tok.strip()
    if '%' in s:
        # %name より前はすべて型/属性 (値名に空白は入らない)
        return s[s.rindex('%'):]
    s = TYRE.sub('', s, count=1).strip() if TYRE.match(s) else s
    while True:
        s2 = ATTR_RE.sub('', s)
        if s2 == s:
            break
        s = s2
    return s.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report')
    a = ap.parse_args()
    lines = open(a.src, errors='replace').read().split('\n')
    dret, dparams = {}, {}
    cur = None
    for line in lines:
        if line.startswith('define '):
            m = re.match(r'define (.+?) @function_([0-9a-f]+)\(([^)]*)\)', line)
            cur = m.group(2) if m else None
            if cur:
                dret[cur] = m.group(1)
                dparams[cur] = [ptype_of(p) for p in split_args(m.group(3))]
            continue
        if cur is not None and line.startswith('}'):
            cur = None
    uid = [0]

    def fresh():
        uid[0] += 1
        return '%%sf%d' % uid[0]

    # 各 block 先頭でクリアする値型表現 (命令の結果型を追跡)
    types = {}

    def coerce(v, have, want, pre, ind, bind=None):
        """have 型の値 v → want 型。変換命令を pre に積み, 最終 value (%名) を返す。
        bind 指定時は最終命令の destination を bind にする。定数はそのまま返す。"""
        have, want = norm_ty(have), norm_ty(want)

        def emit(ty, rhs):
            t = bind or fresh()
            pre.append('%s%s = %s' % (ind, t, rhs))
            types[t] = ty
            return t

        if have == want:
            return v
        # 中間型を標準化
        if have == 'ptr':
            p1 = emit('i64', 'ptrtoint ptr %s to i64' % v)
            have = 'i64'
            v = p1
        if want == 'ptr':
            if have in ('i64', 'i32', 'i16', 'i8', 'i1'):
                if have != 'i64':
                    z = emit('i64', 'zext %s %s to i64' % (have, v))
                    v = z
                return emit('ptr', 'inttoptr i64 %s to ptr' % v)
            if have in ('float', 'double'):
                f = emit('i64', 'fptosi %s %s to i64' % (have, v))
                return emit('ptr', 'inttoptr i64 %s to ptr' % f)
            return 'null'
        # 整数/浮動間
        if have in ('float', 'double') or want in ('float', 'double'):
            if want in ('float', 'double') and have in ('float', 'double'):
                if (have == 'double') != (want == 'double'):
                    op = 'fpext' if want == 'double' else 'fptrunc'
                    return emit(want, '%s %s %s to %s' % (op, have, v, want))
                return v
            if have in ('float', 'double'):
                i = emit('i64', 'fptosi %s %s to i64' % (have, v))
                if want == 'i64':
                    return i
                return coerce(i, 'i64', want, pre, ind)
            # int → float/double
            if want == 'double' and have == 'i64':
                return emit('double', 'sitofp i64 %s to double' % v)
            if want == 'float' and have == 'i32':
                return emit('float', 'sitofp i32 %s to float' % v)
            if have == 'i128':
                i = emit('i64', 'trunc i128 %s to i64' % v)
                return emit(want, 'sitofp i64 %s to %s' % (i, want))
            i = coerce(v, have, 'i64', pre, ind)
            return emit(want, 'sitofp i64 %s to %s' % (i, want))
        # 整数間
        if have == 'i128' and want != 'i128':
            v = emit('i64', 'trunc i128 %s to i64' % v)
            have = 'i64'
        if want == 'i128':
            return emit('i128', 'zext %s %s to i128' % (have if have in INTS else 'i64', v))
        if have == want:
            return v
        op = 'trunc' if INTS.index(want) > INTS.index(have) else 'zext'
        return emit(want, '%s %s %s to %s' % (op, have, v, want))

    n_arity = n_type = n_ret = 0
    out = []
    for l in lines:
        if l.startswith('define '):
            types = {}
        if 'call ' in l and '@function_' in l and not l.lstrip().startswith('declare'):
            ind = l[:len(l) - len(l.lstrip())]
            m = re.match(r'^(\s*)(?:%([\w.-]+) = )?call (.+?) @function_([0-9a-f]+)\(', l)
            if m and m.group(4) in dret:
                nm = m.group(4)
                old_ret, res = m.group(3), m.group(2)
                new_ret = dret[nm]
                j = l.index('@function_' + nm + '(')
                start = j + len('@function_' + nm)
                depth, k = 0, start
                for k in range(start, len(l)):
                    if l[k] == '(':
                        depth += 1
                    elif l[k] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                tail = l[k + 1:]
                args = split_args(l[start + 1:k])
                want_ps = dparams[nm]
                pre = []
                post = []
                newargs = []
                nfp = 0
                for pos, wt0 in enumerate(want_ps):
                    wt = norm_ty(wt0)
                    floaty = wt in ('float', 'double', 'i128')
                    if pos < len(args):
                        av = args[pos]
                        at_m = TYRE.match(av)
                        if at_m:
                            at = norm_ty(at_m.group(1))
                            bare = strip_ty(av)
                            if bare == 'null':
                                if wt == 'ptr':
                                    newargs.append('ptr null')
                                elif wt in INTS:
                                    newargs.append('%s 0' % wt0)
                                else:
                                    newargs.append('%s 0.0' % wt0)
                            elif bare.lstrip('-').isdigit():
                                if wt == 'ptr':
                                    newargs.append('ptr inttoptr (i64 %s to ptr)' % bare)
                                elif wt in INTS:
                                    newargs.append('%s %s' % (wt0, bare))
                                else:
                                    vv = coerce(bare, 'i64', wt, pre, ind)
                                    newargs.append('%s %s' % (wt0, vv))
                            else:
                                vv = coerce(bare, at, wt, pre, ind)
                                newargs.append('%s %s' % (wt0, vv))
                        else:
                            # 生値 (%x 等) — 既知型表から
                            ht = types.get(av, 'i64')
                            vv = coerce(av, ht, wt, pre, ind)
                            newargs.append('%s %s' % (wt0, vv))
                    else:
                        # 引数不足: BLK から補う
                        if floaty:
                            slot = XSLOT[nfp] if nfp < 4 else None
                            if slot:
                                v = fresh()
                                pre.append('%s%s = load i64, ptr inttoptr (i64 %d to ptr)' % (ind, v, BLK + slot))
                                types[v] = 'i64'
                                if wt == 'double':
                                    t2 = fresh()
                                    pre.append('%s%s = bitcast i64 %s to double' % (ind, t2, v))
                                    types[t2] = 'double'
                                    newargs.append('double %s' % t2)
                                elif wt == 'float':
                                    p1 = fresh()
                                    pre.append('%s%s = trunc i64 %s to i32' % (ind, p1, v))
                                    types[p1] = 'i32'
                                    t2 = fresh()
                                    pre.append('%s%s = bitcast i32 %s to float' % (ind, t2, p1))
                                    types[t2] = 'float'
                                    newargs.append('float %s' % t2)
                                else:
                                    t2 = fresh()
                                    pre.append('%s%s = zext i64 %s to i128' % (ind, t2, v))
                                    types[t2] = 'i128'
                                    newargs.append('i128 %s' % t2)
                                continue
                            newargs.append('ptr null' if wt0 == 'ptr' else ('%s 0' % wt0))
                        elif pos < 4:
                            v = fresh()
                            pre.append('%s%s = load i64, ptr inttoptr (i64 %d to ptr)' % (ind, v, BLK + SLOT[pos]))
                            types[v] = 'i64'
                            vv = coerce(v, 'i64', wt, pre, ind)
                            newargs.append('%s %s' % (wt0, vv))
                        else:
                            newargs.append('ptr null' if wt0 == 'ptr' else ('%s 0' % wt0))
                    if floaty:
                        nfp += 1
                l2 = l[:start + 1] + ', '.join(newargs) + ')' + tail
                if norm_ty(old_ret) != norm_ty(new_ret):
                    l2 = l2.replace('call %s @function_%s(' % (old_ret, nm), 'call %s @function_%s(' % (new_ret, nm), 1)
                    if res:
                        if norm_ty(new_ret) == 'void':
                            l2 = l2.replace('%%%s = call' % res, 'call', 1)
                            if norm_ty(old_ret) == 'ptr':
                                post.append('%s%%%s = inttoptr i64 0 to ptr' % (ind, res))
                                types[res] = 'ptr'
                            else:
                                orr = old_ret if old_ret in INTS else 'i64'
                                post.append('%s%%%s = add %s 0, 0' % (ind, res, orr))
                                types[res] = orr
                        else:
                            nv = fresh()
                            l2 = l2.replace('%%%s = call' % res, '%s = call' % nv, 1)
                            types[nv] = norm_ty(new_ret)
                            coerce(nv, new_ret, old_ret, post, ind, bind='%' + res)
                        n_ret += 1
                if len(args) != len(want_ps):
                    n_arity += 1
                else:
                    n_type += 1
                out.extend(pre)
                out.append(l2)
                out.extend(post)
                continue
        out.append(l)
    open(a.dst, 'w').write('\n'.join(out))
    rep = {'arity_fixed': n_arity, 'type_only': n_type, 'ret_fixed': n_ret}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[sigfix]', json.dumps(rep))


if __name__ == '__main__':
    main()
