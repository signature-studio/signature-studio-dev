#!/usr/bin/env python3
"""wasm_trap (OOB) case の個別化 — f_410360 (TObject.Free 系) カスケードの切り分け (CAB-233).

  python3 tests/cascade_410360.py [batch.jsonl] [--md out.md]

各関数 (root = dispatch された VA) の wasm_trap case を次に分類する:
  self_native_fail  native も同じ case で落ちた (比較不能 = 実行不能側)
  trap_upstream     native は ok、wasm は import 呼出列 (calls[]) の時点で先に乖離したうえで trap
                     (乖離点の種類 = call_name / call_arg / call_ret / native_extra / wasm_extra)
  trap_direct       native は ok、wasm は import 呼出列まで一致した状態で OOB に到達
                     (乖離なし = その関数連鎖自身の欠陥。wasm_detail の JS trap chain
                      で innermost frame を出し、f_410360 経由かどうかを区別する)

batch は raw.trace を保持しない (KEEP_RAW_ALL オフ) ため、乖離判定は import 呼出列
(calls = ld_stub 呼出ログ、native/wasm 同一応答モデル) で行う。
"""
import json, sys, collections


def chain(detail):
    """wasm_detail の '<' 連鎖から f_ VA 列を抽出 (先頭 = innermost)。"""
    out = []
    for part in (detail or '').split('<'):
        part = part.strip()
        if '.f_' in part:
            out.append(part.split('.f_', 1)[1])
    return out


def callsig(c):
    return (c['n'], tuple(c['a'][:4]), c.get('r'))


def first_div(nc, wc):
    """import 呼出列の最初の不一致を (種類, 値, index) で返す。"""
    for i in range(max(len(nc), len(wc))):
        ns = callsig(nc[i]) if i < len(nc) else None
        ws = callsig(wc[i]) if i < len(wc) else None
        if ns == ws:
            continue
        if ns is None:
            return ('wasm_extra_call', ws, i)
        if ws is None:
            return ('native_extra_call', ns, i)
        if ns[0] != ws[0]:
            return ('call_name', (ns[0], ws[0]), i)
        if ns[1] != ws[1]:
            return ('call_arg', (ns[0], ns[1], ws[1]), i)
        return ('call_ret', (ns[0], ns[2], ws[2]), i)
    return (None, None, None)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'work/flelift/batch_closure_hybrid.jsonl'
    md = None
    if '--md' in sys.argv:
        md = sys.argv[sys.argv.index('--md') + 1]
    cls = collections.Counter()
    roots = collections.defaultdict(collections.Counter)
    div_kind = collections.Counter()
    div_va = collections.Counter()
    chain410360 = collections.Counter()
    innermost = collections.Counter()
    n_case = 0
    for l in open(path):
        if not l.strip():
            continue
        r = json.loads(l)
        root = int(r['function']['va'], 16)
        for cs in r.get('cases', []):
            if cs.get('outcome') != 'wasm_trap':
                continue
            n_case += 1
            ch = chain(cs.get('wasm_detail'))
            innermost['f_' + ch[0] if ch else '?'] += 1
            if '410360' in ch:
                chain410360['%s<%s' % (ch[0], ch[1] if len(ch) > 1 else '-')] += 1
            nstat, wstat = cs.get('native_status'), cs.get('wasm_status')
            if nstat != 'ok':
                c = 'self_native_fail'
            else:
                nc = ((cs.get('raw') or {}).get('native') or {}).get('calls') or []
                wc = ((cs.get('raw') or {}).get('wasm') or {}).get('calls') or []
                kind, va, idx = first_div(nc, wc)
                if kind is None:
                    c = 'trap_direct' if '410360' in ch else 'trap_direct_other'
                else:
                    c = 'trap_upstream'
                    div_kind[kind] += 1
                    if isinstance(va, tuple):
                        div_va[str(va)[:60]] += 1
            cls[c] += 1
            roots[root][c] += 1
    lines = []
    lines.append('wasm_trap case 個別化 (f_410360 カスケード) — %s' % path.split('/')[-1])
    lines.append('trap case 計 %d / 関数 %d' % (n_case, len(roots)))
    lines.append('')
    lines.append('分類 (case):')
    for k, v in cls.most_common():
        lines.append('  %-20s %5d' % (k, v))
    lines.append('')
    lines.append('innermost trap frame 上位 (wasm JS trap chain):')
    for k, v in innermost.most_common(10):
        lines.append('  %-24s %5d' % (k, v))
    lines.append('')
    lines.append('乖離点の種類 (trap_upstream 内):')
    for k, v in div_kind.most_common():
        lines.append('  %-22s %5d' % (k, v))
    lines.append('')
    lines.append('乖離内容 上位:')
    for k, v in div_va.most_common(10):
        lines.append('  %-64s %5d' % (k, v))
    lines.append('')
    lines.append('f_410360 経由の OOB 地点 (innermost < 呼び出し元) 上位:')
    for k, v in chain410360.most_common(8):
        lines.append('  f_%-30s %5d' % (k, v))
    lines.append('')
    lines.append('trap 多発 root 関数 上位 (dispatch された VA / case 数):')
    rt = sorted(((sum(c.values()), va) for va, c in roots.items()), reverse=True)
    for n, va in rt[:12]:
        lines.append('  0x%-10x %5d  %s' % (va, n, dict(roots[va])))
    out = '\n'.join(lines)
    print(out)
    if md:
        open(md, 'w').write(out + '\n')


if __name__ == '__main__':
    main()
