#!/usr/bin/env python3
"""#5406 (LD-268) 受入 2: fvm 42 件を this のフィールドを埋めた疑似オブジェクト (blob vmtf) で再実行し、遷移を実測する。
使い方: python3 tools/liftdiff/ld5406_fvm_fill.py [batch jsonl]  (既定 work/m11/batch_sample_800.jsonl・出力は work/m11/ld5406_fill.jsonl)
入力の fvm case (関数 VA・fvm_arg・旧 outcome) は batch jsonl から読む。既存の blob (vmt) は変えず、vmtf を SPECIAL_BLOBS に足すだけ。
vmtf: arena+0x1000 (this) の先頭 0x100 byte の各 qword を arena+0x3000 (内部オブジェクト) へのポインタにし、
arena+0x3000 の先頭 qword は VMT (arena+0x2000) を指す。VMT slot は make_blob_vmt と同じ仮 proc。
"""
import json
import os
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldlib import cases, compare  # noqa: E402
from ldlib.session import Session  # noqa: E402


def make_blob_vmtf(size=cases.BLOB_SIZE):
    buf = bytearray(size)
    fix = []
    for off in range(0x1000, 0x1100, 8):
        buf[off:off + 8] = (0x3000).to_bytes(8, 'little')
        fix.append(off)
    buf[0x1000:0x1008] = (0x2000).to_bytes(8, 'little')
    buf[0x3000:0x3008] = (0x2000).to_bytes(8, 'little')
    fix.append(0x3000)
    for off in range(0x3008, 0x3100, 8):
        buf[off:off + 8] = (0x3000).to_bytes(8, 'little')
        fix.append(off)
    for k in range(cases.VMT_SLOTS):
        buf[0x2000 + 8 * k:0x2000 + 8 * k + 8] = (cases.LD_FAKEPROC_BASE + (cases.LD_VMT_IDX0 + k) * cases.LD_FAKEPROC_SZ).to_bytes(8, 'little')
    return bytes(buf), fix


cases.SPECIAL_BLOBS['vmtf'] = make_blob_vmtf


def fvm_line_blob(va, arg, sig, blob, trace=True):
    kinds = cases.kinds_of(sig['params'])
    toks = []
    for i, k in enumerate(kinds):
        if k == 'd':
            toks.append('d:0x%x' % cases.FP_D[i % 4])
        elif k == 'f':
            toks.append('f:0x%x' % cases.FP_F[i % 4])
        elif i == arg:
            toks.append('i:a:0x%x' % cases.PTR_SLOTS[0])
        else:
            toks.append('i:0x%x' % cases.SMALL[i])
    ext = (' tr=1 wsig=' + ','.join(sig['wsig'])) if sig.get('wsig') else ''
    return 'id=%x:fvm%d fn=%x blob=%s args=%s trace=%d xfill=1 sig=%s rt=%s%s' % (
        va, arg, va, blob, ','.join(toks), 1 if trace else 0, ','.join(sig['params']), sig['ret'], ext)


def main(path):
    fvm = []
    for line in open(path):
        r = json.loads(line)
        for c in r['cases']:
            if c.get('pattern') == 'fvm':
                fvm.append((int(r['function']['va'], 16), c['fvm_arg'], c['outcome']))
    print('fvm cases', len(fvm))
    sess = Session(os.path.join(HERE, 'targets', 'm11.json'), build=False, shards=1, timeout=10.0, trace=True)
    nat, was = sess.make_runners()
    old = collections.Counter(o for _, _, o in fvm)
    new = collections.Counter()
    trans = collections.Counter()
    out = open(os.path.join(HERE, 'work', 'm11', 'ld5406_fill.jsonl'), 'w')
    try:
        for va, arg, old_o in fvm:
            name = sess.fn_name(va)
            sig = sess.sigs.get(name)
            msig = cases.machine_sig(va, sig)
            sigs = sess.sigs if msig is sig else dict(sess.sigs, **{name: msig})
            line = fvm_line_blob(va, arg, msig, 'vmtf', trace=sess.trace)
            ids = ['%x:fvm%d' % (va, arg)]
            n = nat.run_cases([line], ids)[0]
            if n.get('status') in ('timeout', 'hang', 'crash'):
                w = {'id': ids[0], 'status': 'hang', 'detail': 'skipped (native timeout)', 'calls': [], 'mem': []}
            else:
                w = was.run_cases([line], ids)[0]
            try:
                c = compare.compare_case(n, w, sess.ctx, sigs, sess.stub_info, sess.thunks())
            except Exception as e:
                c = {'outcome': 'hang', 'compare_error': repr(e)[:120]}
            new[c['outcome']] += 1
            trans[(old_o, c['outcome'])] += 1
            out.write(json.dumps({'va': hex(va), 'arg': arg, 'old': old_o, 'new': c['outcome'],
                                  'native': n.get('status'), 'wasm': w.get('status'),
                                  'wasm_detail': c.get('wasm_detail', ''), 'fault': n.get('fault')}) + '\n')
            print('%x fvm%d %-14s -> %-14s native=%s wasm=%s' % (va, arg, old_o, c['outcome'], n.get('status'), w.get('status')), flush=True)
    finally:
        out.close()
        nat.close(); was.close()
    print('OLD', dict(old))
    print('NEW', dict(new))
    for (a, b), v in sorted(trans.items(), key=lambda x: -x[1]):
        print('TRANS %-14s -> %-14s %d' % (a, b, v))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'm11', 'batch_sample_800.jsonl'))
