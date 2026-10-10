#!/usr/bin/env python3
"""crt_nat.py — CAB-138: CRT 初期化相当 (api-set 遅延解決) 入りの native 参照ランナ。

entry_nat.py を runner として再利用し (scenario schema / fork 隔離 / alloc replay は同一)、
libottnatcrt.so (crtinit/crt_native.c — ott_native.c 無改変 include + loader 系 IAT 差し替え) に
載せ替える。OTT_CRTINIT=0 で IAT 差し替えを skip → 旧 fail-fast (陰性対照) を再現。

usage: crt_nat.py --out RESULT.json [--scen SCEN.json] [--replay ALOG.json] [--cov COV.json] [--only NAME]...
"""
import sys, os, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'entry'))
import entry_nat as E                       # runner 本体 (SO 差し替えのみ)

E.SO = os.path.join(HERE, '..', 'work', 'crtlift', 'libottnatcrt.so')   # lift_crt.sh の産物 (常に現行ビルド)


def load_lib():
    lib = E.load_lib()                      # DLL 敷設 + editor ctor patch + segv handler
    if os.environ.get('OTT_CRTINIT', '1') != '0':
        lib.ott_crt_init_tables()           # encoded slot を enc(NULL)=cookie に事前初期化
        n = lib.ott_crt_patch()
        assert n >= 4, 'IAT patch failed (%d)' % n
    return lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--scen', default=None)
    ap.add_argument('--replay', default=None)
    ap.add_argument('--cov', default=None)
    ap.add_argument('--only', action='append', default=[])
    a = ap.parse_args()
    if a.scen:
        scens = json.load(open(a.scen))
    else:
        sys.path.insert(0, os.path.join(HERE, '..', 'entry'))
        import entry_scen
        scens = [{'name': n, 'steps': s} for n, s in entry_scen.scen_list()]
    if a.only:
        scens = [s for s in scens if s['name'] in a.only]
    replay_map = json.load(open(a.replay)) if a.replay else None
    load_lib()
    am = E.LIB.ott_am_addr()
    results, insn, calltgt, per_scen = {}, set(), set(), {}
    for scen in scens:
        r_fd, w_fd = os.pipe()
        pid = os.fork()
        replay = replay_map.get(scen['name']) if replay_map else None
        if pid == 0:
            os.close(r_fd)
            try:
                E.child_main(scen, am, bool(a.cov), replay, w_fd)
            except BaseException:
                os._exit(3)
        os.close(w_fd)
        chunks = []
        while True:
            ch = os.read(r_fd, 1 << 20)
            if not ch:
                break
            chunks.append(ch)
        os.close(r_fd)
        _, st = os.waitpid(pid, 0)
        if st != 0:
            results[scen['name']] = {'ok': False, 'status': st >> 8}
            print('[crt_nat] %-16s CRASH st=%d' % (scen['name'], st >> 8))
            continue
        d = json.loads(b''.join(chunks))
        d['result']['ok'] = True
        results[scen['name']] = d['result']
        if a.cov and 'insn' in d:
            insn.update(d['insn'])
            calltgt.update(d.get('calltgt', []))
            per_scen[scen['name']] = d['insn']
        print('[crt_nat] %-16s ok calls=%d obj=%s' % (scen['name'], len(d['result']['calls']),
                                                      'yes' if d['result'].get('obj') else 'no'))
    out = {'scenarios': results}
    if a.cov:
        out['cov'] = {'insn': sorted(insn), 'calltgt': sorted(calltgt), 'per_scen': per_scen}
    json.dump(out, open(a.out, 'w'))
    if a.cov:
        json.dump(out['cov'], open(a.cov, 'w'))   # lift 入力用に coverage 単体でも出力
    print('[crt_nat] wrote %s (%d scenarios)' % (a.out, len(results)))


if __name__ == '__main__':
    main()
