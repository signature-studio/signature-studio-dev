#!/usr/bin/env python3
"""LD-147 (#3180): Win32 BOOL の import 戻り値を IR で `i1` 受けし `sext i1→i64` で rax に入れる型決定 (D25 候補) の実測。

tools/ott/work/ott.ll (旧 RetDec chain の産物。読取専用) は書き換えず、--out の下に複製・1 行変更版・target JSON を作る。

  python3 bool_sext_probe.py enum [--ir PATH]                 # call i1 @ の列挙 (静的)
  python3 bool_sext_probe.py variants --out DIR [--ir PATH]   # orig / hf_zext / all_zext の複製と target JSON
  python3 bool_sext_probe.py run --out DIR                    # liftdiff run を各 variant に実行 (所要秒を記録)
  python3 bool_sext_probe.py rax --out DIR                    # native と wasm の rax を case ごとに比べる
"""
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
IR_DEFAULT = os.path.join(REPO, 'tools', 'ott', 'work', 'ott.ll')
TARGET_BASE = os.path.join(REPO, 'tools', 'liftdiff', 'targets', 'ott_old.json')
LIFTDIFF = os.path.join(REPO, 'tools', 'liftdiff', 'liftdiff.py')
FNS = '0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc'
VARIANTS = ['orig', 'hf_zext', 'all_zext']

# Win32 のドキュメント上の戻り値型が BOOL の API (ott.ll の call i1 @ の全名)。
BOOL_APIS = {'IsDebuggerPresent', 'IsProcessorFeaturePresent', 'TerminateProcess', 'HeapFree', 'FreeLibrary',
             'TlsSetValue', 'GetStringTypeW', 'WriteFile', 'GetConsoleMode', 'WriteConsoleW', 'CloseHandle'}

CALL_RE = re.compile(r'^\s*(%[\w.\-]+) = call i1 @([\w.$]+)\(')
DEF_RE = re.compile(r'^define\b.*?@([\w.$]+)\(')
SEXT_RE = re.compile(r'^(\s*%[\w.\-]+ = )sext i1 (%[\w.\-]+) to i64(\s*)$')


def read_ir(path):
    with open(path, encoding='utf-8') as f:
        return f.read().split('\n')


def enum_calls(lines):
    out = []
    func = None
    for i, line in enumerate(lines):
        m = DEF_RE.match(line)
        if m:
            func = m.group(1)
        m = CALL_RE.match(line)
        if not m:
            continue
        res, callee = m.group(1), m.group(2)
        use = None
        for j in range(i + 1, len(lines)):
            if lines[j].startswith('define '):
                break
            if re.search(re.escape(res) + r'(?![\w.\-])', lines[j]):
                use = (j + 1, lines[j].strip())
                break
        op = None
        if use:
            mm = re.search(r'= (sext|zext|icmp|trunc|select)\b', use[1])
            op = mm.group(1) if mm else use[1].split()[0]
        out.append({'line': i + 1, 'func': func, 'callee': callee, 'res': res, 'use_line': use and use[0],
                    'use_op': op, 'use_text': use and use[1]})
    return out


def sext_targets(lines, calls):
    """call i1 の結果を直接 `sext i1 → i64` している行 (行番号 → callee)。"""
    out = {}
    for c in calls:
        if not c['use_line']:
            continue
        line = lines[c['use_line'] - 1]
        m = SEXT_RE.match(line)
        if m and m.group(2) == c['res']:
            out[c['use_line']] = c['callee']
    return out


def cmd_enum(a):
    lines = read_ir(a.ir)
    calls = enum_calls(lines)
    print('call i1 @ 件数: %d (呼出しを含む関数 %d 件)' % (len(calls), len({c['func'] for c in calls})))
    print('line\tfunc\tcallee\tresult\tfirst_use_line\tfirst_use_op\tBOOL_API')
    for c in calls:
        print('%d\t%s\t%s\t%s\t%s\t%s\t%s' % (c['line'], c['func'], c['callee'], c['res'], c['use_line'],
                                           c['use_op'], 'yes' if c['callee'] in BOOL_APIS else 'NO'))
    non_bool = [c['callee'] for c in calls if c['callee'] not in BOOL_APIS]
    print('BOOL 以外の戻り値の call i1: %d 件 %s' % (len(non_bool), non_bool))
    st = sext_targets(lines, calls)
    print('call i1 の結果を直接 sext i1→i64 する行: %d 件 %s' % (len(st), sorted(st.items())))


def write_variant(lines, out_lines, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))


def cmd_variants(a):
    os.makedirs(a.out, exist_ok=True)
    sha = hashlib.sha256(open(a.ir, 'rb').read()).hexdigest()
    print('source %s sha256=%s' % (a.ir, sha))
    lines = read_ir(a.ir)
    calls = enum_calls(lines)
    st = sext_targets(lines, calls)
    sets = {'orig': {}, 'hf_zext': {k: v for k, v in st.items() if v == 'HeapFree'}, 'all_zext': st}
    base = json.load(open(TARGET_BASE))
    for v in VARIANTS:
        ir_out = os.path.join(a.out, 'ott_%s.ll' % v)
        new = list(lines)
        for ln in sets[v]:
            m = SEXT_RE.match(new[ln - 1])
            new[ln - 1] = m.group(1) + 'zext i1 ' + m.group(2) + ' to i64' + m.group(3)
        write_variant(lines, new, ir_out)
        changed = [d for d in difflib.unified_diff(lines, new, lineterm='', n=0) if d[:1] in '+-' and d[:3] not in ('+++', '---')]
        print('variant %-9s 変更行 %d 件 (%s) -> %s' % (v, len(changed) // 2, ', '.join('%d:%s' % (k, sets[v][k]) for k in sorted(sets[v])) or '-', ir_out))
        t = dict(base)
        t['name'] = 'ld147_%s' % v
        t['desc'] = 'LD-147 (#3180) 実測用の複製。ott_old と同一の lift・stub。ir のみ複製 (variant=%s)' % v
        t['ir'] = ir_out
        json.dump(t, open(os.path.join(a.out, 'target_%s.json' % v), 'w'), indent=2, ensure_ascii=False)
    print('tools/ott/work/ott.ll は書き換えていない (sha256 は上記)')


def cmd_run(a):
    for v in VARIANTS:
        t0 = time.time()
        js = os.path.join(a.out, 'target_%s.json' % v)
        res = os.path.join(a.out, 'res_%s.json' % v)
        p = subprocess.run([sys.executable, LIFTDIFF, 'run', js, '--fn', FNS, '--pattern', 'vm0,u16', '--notrace',
                            '--json', res], cwd=os.path.join(REPO, 'tools', 'liftdiff'), capture_output=True, text=True)
        print('run %-9s rc=%d wall=%.2fs -> %s' % (v, p.returncode, time.time() - t0, res))
        if p.returncode:
            print(p.stdout[-2000:], p.stderr[-2000:])


def cmd_rax(a):
    rows = []
    for v in VARIANTS:
        data = json.load(open(os.path.join(a.out, 'res_%s.json' % v)))
        for f in data:
            for c in f['cases']:
                raw = c.get('raw') or {}
                n = (raw.get('native') or {}).get('rax')
                w = (raw.get('wasm') or {}).get('rax')
                rows.append((v, f['function']['va'], c['pattern'], c['outcome'], n, w))
    print('variant\tfunction\tpattern\toutcome\tnative_rax\twasm_rax\trax_same')
    for v, va, p, oc, n, w in rows:
        same = 'NA' if n is None or w is None else ('yes' if n == w else 'no')
        print('%s\t%s\t%s\t%s\t%s\t%s\t%s' % (v, va, p, oc, n, w, same))
    for v in VARIANTS:
        sel = [r for r in rows if r[0] == v and r[4] is not None and r[5] is not None]
        print('%s: rax 比較 %d case / 不一致 %d case' % (v, len(sel), sum(1 for r in sel if r[4] != r[5])))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('enum'); p.add_argument('--ir', default=IR_DEFAULT)
    p = sp.add_parser('variants'); p.add_argument('--ir', default=IR_DEFAULT); p.add_argument('--out', required=True)
    p = sp.add_parser('run'); p.add_argument('--out', required=True)
    p = sp.add_parser('rax'); p.add_argument('--out', required=True)
    a = ap.parse_args()
    {'enum': cmd_enum, 'variants': cmd_variants, 'run': cmd_run, 'rax': cmd_rax}[a.cmd](a)


if __name__ == '__main__':
    main()
