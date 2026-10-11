#!/usr/bin/env python3
"""複数 .ll から関数を抽出して 1 モジュールに統合する (globals/declares は dedupe)。
usage: mkrun_merge.py out.ll <in.ll>:<fnVAhex>[:<rename>] ...
"""
import re, sys

out_path = sys.argv[1]
specs = []
for a in sys.argv[2:]:
    parts = a.split(':')
    specs.append((parts[0], int(parts[1], 16), parts[2] if len(parts) > 2 else None))

header, meta, globs, gdecl, decls = [], [], [], [], []
seen_g, seen_d = set(), set()
bodies = []
next_meta = [0]
for src, fnva, rename in specs:
    lines = open(src).read().splitlines()
    if not header:
        header = [l for l in lines if l.startswith(('source_filename', 'target'))]
    # per-source メタデータリナンバー (同一 id がモジュール間で衝突するため)
    idmap = {}
    for l in lines:
        m = re.match(r'^!(\d+) = !\{i64 (\d+)\}', l.strip())
        if m:
            old = m.group(1)
            if old not in idmap:
                idmap[old] = str(next_meta[0])
                next_meta[0] += 1
    for l in lines:
        m = re.match(r'^!(\d+) = !\{i64 (\d+)\}', l.strip())
        if m:
            meta.append('!%s = !{i64 %s}' % (idmap[m.group(1)], m.group(2)))
            continue
        m = re.match(r'^@([\w.]+)\s*=\s*(?:local_unnamed_addr\s+|unnamed_addr\s+)?(global|constant|external)', l)
        if m:
            is_def = m.group(2) != 'external'
            if not is_def or ('__authstub_' not in m.group(1) and 'mx_harness_' not in m.group(1)):
                if m.group(1) not in seen_g:
                    seen_g.add(m.group(1))
                    (globs if is_def else gdecl).append(l)
            continue
        if l.startswith('declare') and '__authstub_' not in l:
            key = re.sub(r'\s+', ' ', l)
            if key not in seen_d:
                seen_d.add(key)
                decls.append(l)
    want = 'function_%x(' % fnva
    s = next(i for i, l in enumerate(lines) if l.startswith('define') and want in l)
    e = next(i for i in range(s, len(lines)) if lines[i].startswith('}'))
    seg = lines[s:e + 1]
    if idmap:
        seg = [re.sub(r'!insn\.addr !(\d+)\b',
                      lambda mm: '!insn.addr !' + idmap.get(mm.group(1), mm.group(1)), ln)
               for ln in seg]
    if rename:
        seg[0] = seg[0].replace('@function_%x(' % fnva, '@%s(' % rename, 1)
    bodies.append('\n'.join(seg))

gdecl += [
    '@__authstub_str_len0 = external global i64 ; harness C (LF1/LF7)',
    '@__authstub_doc_root = external global i64 ; harness C (LF5/LF6)',
    '@__authstub_dbl_ret0 = external global i128 ; harness C (LF2)',
]
# meta 重複排除 (順序維持)
seen_m = set()
meta_u = []
for l in meta:
    if l not in seen_m:
        seen_m.add(l)
        meta_u.append(l)
res = header + globs + gdecl + decls + [''] + bodies + [''] + meta_u + ['']
open(out_path, 'w').write('\n'.join(res))
print('mkrun_merge: %s (%d fns, %d lines)' % (out_path, len(specs), len(res)))
