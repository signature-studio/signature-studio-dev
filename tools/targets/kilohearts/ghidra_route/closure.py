#!/usr/bin/env python3
"""未関数化 callee の閉包を decompile 集合として確定する (KH-31 #1989)。

  closure.py <name> <out_dir> <core.pe> [max_iter=30]

手順 (不動点反復):
  1. 初期集合 S = ghidra_to_c.SNAPINS[name] の exports + also。
  2. S のうち未 decompile の VA を DecompEach.java (-noanalysis) で decompile し、<out_dir>/<va>.c を作る。
  3. 成功した .c の本文から呼出先を集める: FUN_<va> / thunk_FUN_<va> (jmp thunk の飛び先) / func_0x000<va>。
     IAT thunk (ghidra_to_c.THUNK) と STUB (ghidra_to_c.STUB) は閉包に入れない (Win API 扱い・規則は converter 側)。
  4. 新規 VA が 0 件になったら止める (不動点)。FAIL が 1 件でも残れば exit 1 (閉包は確定していない)。
出力: <out_dir>/closure_<name>.json (funcs・also・failed・excluded・iterations)。
環境: GHIDRA_HOME (必須)・JAVA_HOME_21 (既定 temurin-21)。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ghidra_to_c as g  # noqa: E402

SCRIPTS = HERE.parent / 'scripts' / 'ghidra'
CALLEE = re.compile(r'\b(?:FUN_|thunk_FUN_)([0-9a-f]{8,9})\b|\bfunc_0x000([0-9a-f]{9})\b')


def refs(path):
    out = set()
    for m in CALLEE.finditer(Path(path).read_text()):
        out.add(int(m.group(1) or m.group(2), 16))
    return out


def decompile(ghidra_home, jdk, core, out_dir, vas, log):
    env = dict(os.environ, JAVA_HOME=jdk, JAVA_TOOL_OPTIONS='-Xmx10g')
    env['PATH'] = jdk + '/bin:' + env.get('PATH', '')
    proj = out_dir / 'proj_closure'
    proj.mkdir(parents=True, exist_ok=True)
    cmd = [ghidra_home + '/support/analyzeHeadless', str(proj), 'kh_closure', '-import', core,
           '-noanalysis', '-scriptPath', str(SCRIPTS), '-postScript', 'DecompEach.java', str(out_dir)]
    cmd += ['0x%x' % v for v in vas] + ['-deleteProject']
    with open(log, 'a') as lf:
        rc = subprocess.run(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT).returncode
    status = {}
    for line in (out_dir / 'summary.tsv').read_text().splitlines()[1:]:
        cols = line.split('\t')
        status[int(cols[0], 16)] = cols[4]
    return rc, status


def main():
    name, out_dir, core = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    max_iter = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    ghidra_home = os.environ.get('GHIDRA_HOME', '')
    if not ghidra_home or not (Path(ghidra_home) / 'support' / 'analyzeHeadless').exists():
        raise SystemExit('GHIDRA_HOME が無い (fail-closed)')
    jdk = os.environ.get('JAVA_HOME_21', '/usr/lib/jvm/temurin-21-jdk-amd64')
    cfg = g.SNAPINS[name]
    exports = set(cfg['exports'])
    excluded = set(g.THUNK) | set(g.STUB)
    known = set(cfg['exports']) | set(cfg.get('also', []))
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / 'closure_ghidra.log'
    status, excl_hit, per_iter = {}, set(), []
    it = 0
    while True:
        todo = sorted(v for v in known if v not in status)
        if not todo:
            break
        it += 1
        if it > max_iter:
            raise SystemExit('閉包が %d 回で不動点に達しない (fail-closed)' % max_iter)
        rc, st = decompile(ghidra_home, jdk, core, out_dir, todo, log)
        for v in todo:
            status[v] = st.get(v, 'MISSING')
        new = set()
        for v in todo:
            if status[v] == 'OK':
                new |= refs(out_dir / ('%x.c' % v))
        excl_hit |= {x for x in new if x in excluded}
        new -= known
        new -= excluded
        known |= new
        per_iter.append({'iter': it, 'decompiled': len(todo), 'new_callees': len(new), 'ghidra_rc': rc})
        print('iter %d: decompile %d (ghidra rc %d), 新規 callee %d, 集合 %d' % (it, len(todo), rc, len(new), len(known)), flush=True)
    failed = sorted(v for v, s in status.items() if s != 'OK')
    funcs = sorted(known)
    res = {
        'name': name,
        'funcs': ['0x%x' % v for v in funcs],
        'also': ['0x%x' % v for v in funcs if v not in exports],
        'failed': ['0x%x' % v for v in failed],
        'excluded_refs': ['0x%x' % v for v in sorted(excl_hit)],
        'iterations': it,
        'per_iter': per_iter,
    }
    (out_dir / ('closure_%s.json' % name)).write_text(json.dumps(res, indent=1))
    print('closure %s: %d 関数 (also %d), 反復 %d, FAIL %d, 除外 %d 件参照' % (
        name, len(funcs), len(funcs) - len(exports), it, len(failed), len(excl_hit)))
    if failed:
        print('FAIL: ' + ' '.join('0x%x=%s' % (v, status[v]) for v in failed))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
