#!/usr/bin/env python3
"""lift IR の外部 declare を shimx の定義署名 (data/sigs.json) へ正規化する IR pass (SHX-T7, #173)。

  sig_normalize.py <in.ll> <out.ll> [--sigs data/sigs.json] [--report out.json] [--strict]

背景: RetDec は HANDLE/enum/REFCLSID を i64、別 API では ptr/i32 と declare が揺れる。shimx の定義と wasm 署名が
食い違うと wasm-ld は "function signature mismatch" を警告し、実行時に trap する (acmMetrics ほか 5 件, REPORT §4)。

方式 (呼出 site には触らない):
  IR が declare する名前 N が shimx に在り署名が違う場合、
    - declare @N を shimx 署名の declare に置換 (NAME.1 / NAME_D1 形式の重複 declare は削除し基名 declare を補う)
    - IR 内の @N の全参照 (call / 関数ポインタ) を adapter `@__shx_sig_N` へ向ける
    - adapter は IR 側署名で定義し、引数を shimx 署名へ変換して基名を呼び、戻り値を IR 側署名へ戻す
  変換: 整数 ↔ 整数 (trunc/zext), 整数 ↔ ptr (inttoptr/ptrtoint), float ↔ double。余る引数は捨て、足りない引数は 0。
  未対応 (float ↔ 整数, 構造体/vector, 可変長) は書換えず report の unresolved に出す。--strict なら exit 1。
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
from gen_sigs import split_args, ptype, ATTRS  # noqa: E402

INT_BITS = {'i1': 1, 'i8': 8, 'i16': 16, 'i32': 32, 'i64': 64}
FLT = ('float', 'double')
ZERO = {'ptr': 'null', 'float': '0.000000e+00', 'double': '0.000000e+00'}
LINK_WORDS = {'dso_local', 'hidden', 'protected', 'default', 'external', 'ccc', 'fastcc', 'local_unnamed_addr', 'unnamed_addr'}
DECL = re.compile(r'^declare\s+(?P<pre>[^@\n]*?)@(?P<name>[\w.$-]+)\((?P<args>.*)\)(?P<post>[^\n]*)$', re.M)
DUP = [re.compile(r'^([A-Za-z_]\w*)\.(\d+)$'), re.compile(r'^([A-Za-z_]\w*)_D(\d+)$')]


def zero(t):
    return ZERO.get(t, '0')


def convert(src_t, dst_t, val, tmp):
    """(命令列, 結果値) を返す。変換不能なら None。tmp は一意名生成関数"""
    if src_t == dst_t:
        return [], val
    if src_t in INT_BITS and dst_t in INT_BITS:
        op = 'trunc' if INT_BITS[src_t] > INT_BITS[dst_t] else 'zext'
        r = tmp()
        return ['  %s = %s %s %s to %s' % (r, op, src_t, val, dst_t)], r
    if src_t in INT_BITS and dst_t == 'ptr':
        r = tmp()
        return ['  %s = inttoptr %s %s to ptr' % (r, src_t, val)], r
    if src_t == 'ptr' and dst_t in INT_BITS:
        r = tmp()
        return ['  %s = ptrtoint ptr %s to %s' % (r, val, dst_t)], r
    if (src_t, dst_t) == ('float', 'double'):
        r = tmp()
        return ['  %s = fpext float %s to double' % (r, val)], r
    if (src_t, dst_t) == ('double', 'float'):
        r = tmp()
        return ['  %s = fptrunc double %s to float' % (r, val)], r
    return None


def parse_decl(m):
    toks = [t for t in m.group('pre').split() if t not in LINK_WORDS and t not in ATTRS]
    if not toks:
        return None
    args = m.group('args').strip()
    params = [ptype(p) for p in split_args(args)] if args else []
    return {'ret': toks[-1], 'params': params}


def make_adapter(name, target, d, s):
    """IR 側署名 d の adapter 定義文字列。変換不能なら None"""
    cnt = [0]

    def tmp():
        cnt[0] += 1
        return '%%t%d' % cnt[0]
    body, call_args = [], []
    for i, st in enumerate(s['params']):
        if i < len(d['params']):
            c = convert(d['params'][i], st, '%%a%d' % i, tmp)
            if c is None:
                return None
            body += c[0]
            call_args.append('%s %s' % (st, c[1]))
        else:
            call_args.append('%s %s' % (st, zero(st)))
    plist = ', '.join('%s %%a%d' % (t, i) for i, t in enumerate(d['params']))
    out = ['define %s @__shx_sig_%s(%s) {' % (d['ret'], name, plist)] + body
    call = 'call %s @%s(%s)' % (s['ret'], target, ', '.join(call_args))
    if d['ret'] == 'void':
        out += ['  ' + call, '  ret void']
    elif s['ret'] == 'void':
        out += ['  ' + call, '  ret %s %s' % (d['ret'], zero(d['ret']))]
    else:
        r = tmp()
        out.append('  %s = %s' % (r, call))
        c = convert(s['ret'], d['ret'], r, tmp)
        if c is None:
            return None
        out += c[0]
        out.append('  ret %s %s' % (d['ret'], c[1]))
    out.append('}')
    return '\n'.join(out)


def wasm_ty(t):
    """wasm32 でのスロット型 (i1/i8/i16/i32/ptr は i32 に潰れる)。wasm-ld が比較するのはこの粒度"""
    if t in ('i64', 'float', 'double', 'void'):
        return t
    return 'i32' if t in INT_BITS or t == 'ptr' else t


def wasm_sig(sig):
    return (wasm_ty(sig['ret']), tuple(wasm_ty(t) for t in sig['params']))


def unsupported(sig):
    return any(t == '...' or t.startswith(('%', '<', '{', '[')) or t == 'i128' for t in sig['params'] + [sig['ret']])


def normalize(src, sigs):
    defined = set(re.findall(r'^define\s+[^@\n]*@([\w.$-]+)\(', src, re.M))
    decls = {}
    for m in DECL.finditer(src):
        d = parse_decl(m)
        if d:
            decls.setdefault(m.group('name'), (m, d))
    report = {'normalized': [], 'dup_merged': [], 'unresolved': []}
    adapters, edits, renames, add_decls = [], [], {}, {}
    for name, (m, d) in sorted(decls.items()):
        if name in defined or name.startswith('llvm.'):
            continue
        target, dup = name, False
        if name not in sigs:
            for rx in DUP:
                mm = rx.match(name)
                if mm and mm.group(1) in sigs:
                    target, dup = mm.group(1), True
                    break
            else:
                continue
        s = sigs[target]
        if not dup and wasm_sig(d) == wasm_sig(s):
            continue
        if unsupported(d) or unsupported(s):
            report['unresolved'].append({'name': name, 'ir': d, 'shimx': s, 'why': 'unsupported type'})
            continue
        ad = make_adapter(name, target, d, s)
        if ad is None:
            report['unresolved'].append({'name': name, 'ir': d, 'shimx': s, 'why': 'no conversion'})
            continue
        adapters.append(ad)
        renames[name] = '__shx_sig_' + name
        sdecl = 'declare %s @%s(%s)' % (s['ret'], target, ', '.join(s['params']))
        edits.append((m.start(), m.end(), ''))
        if target not in decls or not dup:
            add_decls[target] = sdecl
        if dup:
            report['dup_merged'].append({'name': name, 'base': target, 'ir': d, 'shimx': s})
        else:
            report['normalized'].append({'name': name, 'ir': d, 'shimx': s})
    if not adapters:
        return src, report
    for a, b, rep in sorted(edits, reverse=True):
        src = src[:a] + rep + src[b:]
    alt = '|'.join(re.escape(n) for n in sorted(renames, key=len, reverse=True))
    src = re.sub(r'@(' + alt + r')(?![\w.$-])', lambda mt: '@' + renames[mt.group(1)], src)
    src = src.rstrip('\n') + '\n' + ''.join('\n' + v for v in add_decls.values()) + '\n\n' + '\n\n'.join(adapters) + '\n'
    return src, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('out')
    ap.add_argument('--sigs', default=os.path.join(ROOT, 'data', 'sigs.json'))
    ap.add_argument('--report')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    sigs = json.load(open(a.sigs))
    src = open(a.ir, errors='replace').read()
    out, rep = normalize(src, sigs)
    open(a.out, 'w').write(out)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[sig_normalize] %s: 正規化 %d (adapter) + 重複統合 %d / 未解決 %d -> %s' % (
        os.path.basename(a.ir), len(rep['normalized']), len(rep['dup_merged']), len(rep['unresolved']), a.out))
    for n in rep['normalized'] + rep['dup_merged']:
        print('    %-28s IR (%s) %s -> shimx (%s) %s' % (n['name'], ', '.join(n['ir']['params']), n['ir']['ret'],
                                                         ', '.join(n['shimx']['params']), n['shimx']['ret']))
    for n in rep['unresolved']:
        print('    UNRESOLVED %-20s %s' % (n['name'], n['why']))
    return 1 if (a.strict and rep['unresolved']) else 0


if __name__ == '__main__':
    sys.exit(main())
