#!/usr/bin/env python3
"""consumers.py — リポジトリ内で capstone の disp_size / disp_offset / imm_* / modrm_offset / mem.disp に依存するコードの棚卸し (CAB-229 要件2)

  区分 A: disp_size / disp_offset を読む   → D9 の直接被害 (66 prefix / VEX2.pp66 の disp32 命令で disp_size=2)
  区分 B: imm_offset / imm_size / modrm_offset を読む → matrix・実バイナリ実測で誤り 0 (補正不要)
  区分 C: mem.disp の値だけを使う (rip 相対 target = address+size+mem.disp) → 値は全 case 正しい (補正不要)
git 追跡ファイル + 未追跡 (tools/ 配下の .py/.sh/.js/.mjs/.ts/.c) を走査し、work/ と node_modules は除外。
usage: consumers.py [--json results/consumers.json] [--md results/consumers.md]
"""
import argparse, collections, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PAT = {
    'A': re.compile(r'\.disp_size\b|\.disp_offset\b|\bdisp_size\s*[=!]=|\bdisp_offset\s*[=!]='),
    'B': re.compile(r'\.imm_offset\b|\.imm_size\b|\.modrm_offset\b'),
    'C': re.compile(r'\.mem\.disp\b|\bm\.disp\b|\bmm\.disp\b'),
}
EXTS = ('.py', '.sh', '.js', '.mjs', '.ts', '.c', '.cpp', '.h')
CAPSTONE_HINT = re.compile(r'capstone|Cs\(|CS_ARCH_X86|CS_MODE_64')


def files():
    out = subprocess.run(['git', '-C', REPO, 'ls-files', '-co', '--exclude-standard', 'tools'], capture_output=True, text=True).stdout.split('\n')
    for f in out:
        if not f.endswith(EXTS) or '/work/' in f or 'node_modules' in f or f.startswith('tools/icall/disp_size/'):
            continue
        yield f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(HERE, 'results', 'consumers.json'))
    ap.add_argument('--md', default=os.path.join(HERE, 'results', 'consumers.md'))
    a = ap.parse_args()
    R = {}
    for f in files():
        try:
            txt = open(os.path.join(REPO, f), errors='replace').read()
        except OSError:
            continue
        if not CAPSTONE_HINT.search(txt):
            continue
        hits = collections.defaultdict(list)
        for ln, line in enumerate(txt.split('\n'), 1):
            if line.lstrip().startswith('#') or 'sys.path' in line:
                continue
            for k, pat in PAT.items():
                if pat.search(line):
                    hits[k].append(ln)
        if hits:
            R[f] = {k: v for k, v in hits.items()}
    os.makedirs(os.path.dirname(a.json), exist_ok=True)
    json.dump(R, open(a.json, 'w'), indent=1)
    A = {f: v['A'] for f, v in R.items() if 'A' in v}
    B = {f: v['B'] for f, v in R.items() if 'B' in v}
    C = {f: v['C'] for f, v in R.items() if 'C' in v}
    md = ['# capstone disp 依存コード棚卸し (consumers.py, 自動生成)', '',
          '| 区分 | 意味 | ファイル数 | 補正要否 |', '|---|---|--:|---|',
          '| A | `disp_size`/`disp_offset` を読む | %d | **要** (D9 直接被害) |' % len(A),
          '| B | `imm_offset`/`imm_size`/`modrm_offset` を読む | %d | 否 (実測で誤り 0) |' % len(B),
          '| C | `mem.disp` 値のみ (rip target 等) | %d | 否 (値は全 case 正) |' % len(C), '']
    md += ['## 区分 A (disp_size / disp_offset)', '', '| ファイル | 行 |', '|---|---|']
    for f, v in sorted(A.items()):
        md.append('| `%s` | %s |' % (f, ', '.join(map(str, v))))
    md += ['', '## 区分 B (imm_* / modrm_offset)', '', '| ファイル | 行 |', '|---|---|']
    for f, v in sorted(B.items()):
        md.append('| `%s` | %s |' % (f, ', '.join(map(str, v[:12])) + (' …' if len(v) > 12 else '')))
    md += ['', '## 区分 C (mem.disp 値のみ) — ファイル一覧', '']
    md.append(', '.join('`%s`' % f for f in sorted(C)))
    open(a.md, 'w').write('\n'.join(md) + '\n')
    print('A: %d files / B: %d files / C: %d files' % (len(A), len(B), len(C)))
    for f, v in sorted(A.items()):
        print('  A', f, v)


if __name__ == '__main__':
    main()
