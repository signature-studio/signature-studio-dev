#!/usr/bin/env python3
"""hybrid boot の途中失敗 unit を詳細に捕まえる (CAB-233)。

  python3 tests/boot_probe.py [target] [--mode entry|hybrid] [--from N] [--to M] [--full]

既定: flelift / hybrid。unit 単位フェーズの各 unit 結果を 1 行で出し、
失敗 unit は fault addr / 直近の import 呼出 (ファイル系) を出す。
--full で失敗 unit の完全な case JSON を work/tmp/ に書く。
"""
import json, os, sys, struct, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
from ldlib.session import Session
from ldlib.boot import read_inittable_units, _peek_u64


def _peek_hex(r, tok, n):
    r._send('PEEK %s %d' % (tok, n))
    r.p.stdin.flush()
    v = r._recv(30)
    return v[:2 * n] if v else ''


def main():
    tgt = 'targets/flelift.json'
    mode, a_from, a_to, full = 'hybrid', None, None, False
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == '--mode':
            mode = argv[i + 1]; i += 2
        elif argv[i] == '--from':
            a_from = int(argv[i + 1]); i += 2
        elif argv[i] == '--to':
            a_to = int(argv[i + 1]); i += 2
        elif argv[i] == '--full':
            full = True; i += 1
        elif not argv[i].startswith('--'):
            tgt = argv[i]; i += 1
        else:
            i += 1

    sess = Session(tgt, shards=1, build=False, trace=False)
    t = sess.t
    units = read_inittable_units(sess.pe, int(t['init_table_rva'], 16))
    print('[boot] InitTable: %d units (mode=%s)' % (len(units), mode))
    r = sess.runner_native() if hasattr(sess, 'runner_native') else None
    if r is None:
        from ldlib.runners import Runner
        r = Runner('native', ['setarch', '-R', os.path.join(ROOT, 'work/ld_native'), t['pe']],
                   sess.init_lines('native'), timeout=60.0)

    k = 0
    if mode in ('entry', 'hybrid'):
        ep = sess.pe.base + sess.pe.pe.OPTIONAL_HEADER.AddressOfEntryPoint
        res = r.run_cases(['id=ep fn=%x blob=- args=i:0x%x,i:0x1,i:0x0 keep=1' % (ep, sess.pe.base)], ['ep'])[0]
        k = _peek_u64(r, 'i:0x11eac98')
        print('[entry] status=%s InitCount=%d detail=%s' % (res.get('status'), k, (res.get('detail') or '')[:100]))
        if mode == 'entry':
            r.close(); return
    start = a_from if a_from is not None else (k + 1)
    end = a_to if a_to is not None else len(units)
    fails = []
    for i in range(start, min(end, len(units))):
        if units[i] == 0:
            continue
        if _peek_u64(r, 'i:0x%x' % (units[i] - sess.pe.base)) == 0:
            continue
        res = r.run_cases(['id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i])], ['u%d' % i])[0]
        st = res.get('status')
        if st != 'ok':
            fails.append((i, res))
            print('[fail] unit #%d (init %#x): %s %s' % (i, units[i], st, json.dumps(res.get('fault') or {})))
            det = (res.get('detail') or '')
            print('        detail: %s' % det[:200])
            # 直近のファイル系 import 呼出
            calls = res.get('calls') or []
            fc = [c for c in calls if c['n'] in ('CreateFileW', 'CreateFileA', 'ReadFile', 'CreateFileMappingW', 'MapViewOfFile', 'GetFileSize', 'SetFilePointer', 'FindFirstFileW', 'LoadLibraryW', 'LoadLibraryExW')]
            print('        file-ish calls: %d / total %d' % (len(fc), len(calls)))
            for c in calls:
                print('          %-28s a=[%s] r=%s' % (c['n'], ','.join(x[2:] for x in c['a'][:4]), c['r'][2:]))
            for c in fc[-24:]:
                print('          %-22s a=%s' % (c['n'], [x for x in c['a'][:3]]))
                if c['n'] in ('CreateFileW', 'FindFirstFileW') and c['a'][0]:
                    hx = _peek_hex(r, c['a'][0], 128)
                    try:
                        s = bytes.fromhex(hx).decode('utf-16le', 'replace').split('\x00')[0]
                    except Exception:
                        s = '?'
                    print('             path: %r' % s)
            if full:
                json.dump(res, open(os.path.join(ROOT, 'work/tmp/probe_u%d.json' % i), 'w'))
    print('[boot] 失敗 unit: %s' % [f[0] for f in fails])
    r.close()


if __name__ == '__main__':
    main()
