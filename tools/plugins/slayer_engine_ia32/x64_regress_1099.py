#!/usr/bin/env python3
"""x64_regress_1099.py: x64 出力が x87 の変更で変わらないことを確かめる (#1099)。

  python3 x64_regress_1099.py <before_root> [N=8]

素材 (fl-win64 の extracted/*_PE.bin のうち machine 0x8664) をサイズ順に N 本取り、EntryPoint を root、
closure 2 で x64c を 2 回 (before = <before_root>/tools/ott/lift/x64c.py、after = この worktree) 実行して
ott_lifted.c と lift_meta.json を cmp する。 before_root は origin/main を git archive で展開した dir。
作業ファイルは work/x64_regress/ (gitignore 対象)。 依存: pefile・capstone・FL_WIN64_DIR。
"""
import filecmp, glob, json, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
before = os.path.abspath(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 8
fl = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'ott', 'lift'))
import pefile  # noqa: E402

cands = []
for p in glob.glob(os.path.join(fl, 'extracted', '*_PE.bin')):
    pe = pefile.PE(p, fast_load=True)
    if pe.FILE_HEADER.Machine == 0x8664:
        cands.append((os.path.getsize(p), p, pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.AddressOfEntryPoint))
cands.sort()
work = os.path.join(HERE, 'work', 'x64_regress')
shutil.rmtree(work, ignore_errors=True)
same = 0
for size, p, ep in cands[:N]:
    name = os.path.basename(p)[:-7]
    ej = os.path.join(work, name + '.json')
    os.makedirs(work, exist_ok=True)
    json.dump({'roots': [ep], 'calltgt': []}, open(ej, 'w'))
    outs = {}
    for tag, x64c in (('before', os.path.join(before, 'tools', 'ott', 'lift', 'x64c.py')),
                      ('after', os.path.join(ROOT, 'tools', 'ott', 'lift', 'x64c.py'))):
        od = os.path.join(work, tag, name)
        r = subprocess.run([sys.executable, x64c, '--pe', p, '--entries', ej, '--out', od, '--closure', '2'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit('[x64-regress] FAIL %s %s: %s' % (tag, name, r.stderr[-400:]))
        outs[tag] = od
    c1 = filecmp.cmp(os.path.join(outs['before'], 'ott_lifted.c'), os.path.join(outs['after'], 'ott_lifted.c'), shallow=False)
    c2 = filecmp.cmp(os.path.join(outs['before'], 'lift_meta.json'), os.path.join(outs['after'], 'lift_meta.json'), shallow=False)
    m = json.load(open(os.path.join(outs['after'], 'lift_meta.json')))
    nfn = len(m['functions'])
    ok = c1 and c2
    same += ok
    print('[x64-regress] %s size %d B root 0x%x functions %d insns %d ott_lifted.c %s lift_meta.json %s' % (
        name, size, ep, nfn, m['ninsn'], 'same' if c1 else 'DIFF', 'same' if c2 else 'DIFF'))
print('[x64-regress] same %d/%d' % (same, min(N, len(cands))))
