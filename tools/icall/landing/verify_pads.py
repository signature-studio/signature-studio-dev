#!/usr/bin/env python3
"""verify_pads.py — landing pad IR 片の native vs wasm 差分検証 driver (CAB-227).

  python3 verify_pads.py --pe <PE> --fragments work/fle_fragments.json \
      --meta work/pads_meta.json --ir work/pads_verify.ll --out work/verify [--max N]

手法 (liftdiff の共有コア + ランナプロトコル / docs/FORMAT.md 準拠):
- native : 自前ランナ rt/lp_native.c (ld_core.h 共有)。pad VA の実機械語を
           rbp = 親フレーム (arena), 非 live-in レジスタ = 0 で実行。
           pad 内の直接 call 先 callee は entry を `31 c0 c3` (xor eax,eax; ret) に patch し、
           TRACESET (INT3) で (VA, rcx, rdx, r8, r9) を記録。
           間接 call (`call [rbx-0x20]`) は case 側で用意した合成 VMT の slot 値 (固定 T) 経由で
           実行 → 同様に patch + TRACESET。
- wasm   : tools/liftdiff ldlib/build_wasm.py で pads_verify.ll を計装→emcc。
           ld_runner.mjs が `function_<padVA>` を sig="i64,i64,i64,i64,i64" で呼出す。
           IR の callee は ret 0 スタブ定義 (entry 計装で (VA, args) を記録)。
- 比較  : status / rax / 関数 entry トレース列 (引数は delta 正規化) / arena 差分。
- 出力  : FORMAT.md §3 形式の JSONL + サマリ。
"""
import argparse
import json
import os
import subprocess
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import REPO_ROOT as REPO  # noqa: E402
LIFTDIFF = REPO + '/tools/liftdiff'
sys.path.insert(0, LIFTDIFF)

import pefile


def wasm_layout(wasm_cjs, node):
    r = subprocess.run([node, LIFTDIFF + '/rt/ld_runner.mjs', wasm_cjs, '-', '0', '0', '--layout'],
                       capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise SystemExit('layout failed: %s %s' % (r.stdout[-500:], r.stderr[-500:]))
    return json.loads(r.stdout.strip().splitlines()[-1])


def run_runner(cmd, lines, timeout=600):
    p = subprocess.run(cmd, input='\n'.join(lines) + '\nQUIT\n', capture_output=True, text=True, timeout=timeout)
    out = []
    for l in p.stdout.splitlines():
        l = l.strip()
        if l.startswith('{'):
            out.append(json.loads(l))
    return out, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--fragments', required=True)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--ir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--skip-build', action='store_true')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    fragdoc = json.load(open(a.fragments))
    meta = json.load(open(a.meta))
    pads = {m['va']: m for m in meta['pads']}
    frags = {('%s' % ('0x%x' % f['va_lo'])): f for f in fragdoc['fragments']}

    pe = pefile.PE(a.pe, fast_load=True)
    image_base = pe.OPTIONAL_HEADER.ImageBase

    exec_pads = [f for f in fragdoc['fragments'] if f['kind'] == 'dtor_pad']
    if a.max:
        exec_pads = exec_pads[:a.max]
    print('exec-verify pads: %d' % len(exec_pads))

    # ---- callee 集合 (patch + TRACESET)
    callees = set()
    for f in exec_pads:
        for dc in f['direct_calls']:
            callees.add(dc)
    ICALL_T = int(meta['icall_target_for_verify'], 16)
    callees.add(ICALL_T)
    print('callees (patch+TRACESET):', [hex(c) for c in sorted(callees)])

    # ---- wasm build (tools/liftdiff ldlib を library 利用; work dir は自ディレクトリ配下)
    wasm_cjs = os.path.join(a.out, 'ld_wasm.cjs')
    if not a.skip_build or not os.path.exists(wasm_cjs):
        sys.path.insert(0, LIFTDIFF)
        import ldlib.build_wasm as BW
        tjson = os.path.join(a.out, 'target.json')
        # initial_memory: ld_wasm.c の静的領域 (arena 1MB + heap 96MB + g_inbuf 192MB・CAB-233 で
        # 8MB→192MB) + stack 8MB + initial heap 16MB が 331,529,392 B 必要 → 256MiB では link 失敗
        json.dump({'name': 'lpads227', 'pe': a.pe, 'ir': os.path.abspath(a.ir), 'image': None,
                   'wasm_origin': '0x0', 'global_base': 0x40000, 'initial_memory': 0x14000000},
                  open(tjson, 'w'))
        t = BW.load_target(tjson)
        t['work'] = os.path.abspath(a.out)
        BW.build(t, force=not a.skip_build)
        assert os.path.exists(wasm_cjs), 'wasm build failed'
    node = '/opt/emsdk/node/22.16.0_64bit/bin/node'
    if not os.path.exists(node):
        node = subprocess.run(['bash', '-c', 'ls /opt/emsdk/node/*/bin/node | head -1'], capture_output=True, text=True).stdout.strip()
    lay = wasm_layout(wasm_cjs, node)
    arena_w = int(lay['arena'], 16)
    arena_size = int(lay['arena_size'], 16)
    heap_w = int(lay['heap'], 16)
    heap_size = int(lay['heap_size'], 16)
    delta = 0x10000000          # arena/heap の native 側配置ずれ (image 0x400000..0x1cc0000 と衝突しない大値)
    print('wasm layout: arena=%s heap=%s delta=0x%x' % (lay['arena'], lay['heap'], delta))

    # ---- blob (arena layout)
    FRAME_AT = 0x100
    OBJ_AT = 0x40
    VMT_AT = 0x80
    blob = bytearray(max(0x400, FRAME_AT + 0x400))
    blob[OBJ_AT:OBJ_AT + 8] = VMT_AT.to_bytes(8, 'little')          # obj[0] = VMT (arena 内, FIX 対象)
    blob[VMT_AT - 0x20:VMT_AT - 0x20 + 8] = ICALL_T.to_bytes(8, 'little')  # VMT[-0x20] = 固定 target (生値)
    fix_offsets = []
    trset = sorted(callees)

    def blob_q(off, v, fix=False):
        blob[off:off + 8] = v.to_bytes(8, 'little')
        if fix:
            fix_offsets.append(off)

    def mk_cases(f):
        """pad 1 個 → case 行 (3 pattern: full / flag=0 / obj=0)"""
        insns = {i['va']: i for i in f['insns']}
        flag_off = obj_off = None
        for i in f['insns']:
            if i['mn'] == 'cmp' and 'byte' in i['op'] and 'rbp' in i['op']:
                flag_off = int(i['op'].split('+')[1].split(']')[0].strip(), 16)
            if i['mn'] == 'mov' and i['op'].startswith('rax, qword ptr [rbp'):
                obj_off = int(i['op'].split('+')[1].split(']')[0].strip(), 16)
        if flag_off is None or obj_off is None:
            return None
        flen = (f['frame_max'] or 0) + 16
        b = bytearray(blob)
        fo = FRAME_AT + obj_off
        b[fo:fo + 8] = (OBJ_AT).to_bytes(8, 'little')       # FIX で arena base 加算
        fix = [fo, OBJ_AT]
        b[VMT_AT - 0x20:VMT_AT - 0x20 + 8] = ICALL_T.to_bytes(8, 'little')   # 生値 (image VA, FIX なし)
        bhex = b.hex()
        base = 'fn=%s blob=fr args=i:a:%#x,i:0,i:0,i:0,i:0 sig=i64,i64,i64,i64,i64 rt=i64 trace=1' % (
            '%x' % f['va_lo'], FRAME_AT)
        patches = {'full': [], 'flag0': [], 'obj0': []}
        patches['full'] = ['p=a:%#x:01' % (FRAME_AT + flag_off)]
        patches['flag0'] = ['p=a:%#x:00' % (FRAME_AT + flag_off)]
        patches['obj0'] = ['p=a:%#x:01' % (FRAME_AT + flag_off),
                           'p=a:%#x:q=0' % (FRAME_AT + obj_off)]
        out = []
        for k, pp in patches.items():
            out.append('BLOB fr ' + bhex)
            out.append('FIX fr ' + ','.join('%x' % x for x in fix))
            out.append('CASE id=%s:%s %s %s' % ('%x' % f['va_lo'], k, base, ' '.join(pp)))
        return out

    # ---- 共通ヘッダ行
    # reraise (0x411ea0) は pad 末尾の noreturn call: `pop rax; xor eax,eax; ret` で
    # pad の戻り番号を捨てて trampoline へ直接戻る (wasm IR 側は call 後 ret で等価)。
    RERAISE = 0x411ea0
    patches = []
    for c in sorted(callees):
        patches.append('0x%x:%s' % (c - image_base, '5831c0c3' if c == RERAISE else '31c0c3'))
    proto_head = ['LAYOUT %x %x %x %x %x' % (delta, arena_w, arena_size, heap_w, heap_size),
                  'PATCHSET ' + ';'.join(patches),
                  'TRACESET ' + ','.join('%x' % v for v in trset),
                  'SNAPSHOT']

    # ---- native
    native_cmd = [os.path.join(HERE, 'work/lp_native'), a.pe]
    nlines = list(proto_head)
    cases = []
    for f in exec_pads:
        cl = mk_cases(f)
        if cl:
            cases.append(f)
            nlines.extend(cl)
    print('cases: %d pads × 3 = %d' % (len(cases), len(cases) * 3))
    nres, nproc = run_runner(native_cmd, nlines)
    json.dump(nres, open(os.path.join(a.out, 'native_cases.json'), 'w'), indent=0)
    ok = [r for r in nres if r.get('status') == 'ok']
    print('native: cases=%d ok=%d fail=%d' % (len(nres), len(ok), len(nres) - len(ok)))
    for r in nres:
        if r.get('status') != 'ok':
            print('  native fail:', r.get('id'), r.get('status'), r.get('detail', '')[:80])

    # ---- wasm
    wasm_cmd = [node, LIFTDIFF + '/rt/ld_runner.mjs', wasm_cjs, '-', '0', '%x' % delta]
    wlines = list(proto_head)
    for f in cases:
        cl = mk_cases(f)
        wlines.extend(cl)
    wres, wproc = run_runner(wasm_cmd, wlines)
    json.dump(wres, open(os.path.join(a.out, 'wasm_cases.json'), 'w'), indent=0)
    ok = [r for r in wres if r.get('status') == 'ok']
    print('wasm: cases=%d ok=%d fail=%d' % (len(wres), len(ok), len(wres) - len(ok)))
    for r in wres[:6]:
        if r.get('status') != 'ok':
            print('  wasm fail:', r.get('id'), r.get('status'), r.get('detail', '')[:120])

    # ---- compare
    sys.path.insert(0, LIFTDIFF)
    from ldlib.compare import Ctx
    wstack = (0, 0)
    ctx = Ctx(delta, [(arena_w, arena_w + arena_size), (heap_w, heap_w + heap_size)], wstack)
    wmap = {r['id']: r for r in wres if 'id' in r}
    jsonl = open(os.path.join(a.out, 'verdicts.jsonl'), 'w')
    verdict = collections.Counter()
    diff_examples = []
    for n in nres:
        if 'id' not in n:
            continue
        w = wmap.get(n['id'])
        rec = {'liftdiff_version': 1, 'target': 'lpads227', 'case': n['id'],
               'native_status': n.get('status'), 'wasm_status': w.get('status') if w else '?',
               'outcome': 'both_fault', 'diffs': {}}
        if n.get('status') != 'ok' or not w or w.get('status') != 'ok':
            verdict[rec['outcome']] += 1
            rec['outcome'] = 'native_fault' if n.get('status') != 'ok' else 'wasm_trap'
            verdict[rec['outcome']] += 0
            jsonl.write(json.dumps(rec) + '\n')
            continue
        diffs = {}
        # rax
        if int(n['rax'], 16) != int(w['rax'], 16):
            diffs['ret'] = {'native': n['rax'], 'wasm': w['rax']}
        # trace ( callee entry 列; pad 自身の entry は wasm 計装のみが記録するので両側から除去。
        # 引数は delta 正規化, a4 以降は比較しない: pad は stack 引数を使わない)
        fn_va = int(n['fn'], 16)
        tn = [t for t in n.get('trace', []) if int(t[0], 16) != fn_va]
        tw = [t for t in w.get('trace', []) if int(t[0], 16) != fn_va]
        if len(tn) != len(tw):
            diffs['trace_len'] = {'native': len(tn), 'wasm': len(tw)}
        else:
            for i, (en, ew) in enumerate(zip(tn, tw)):
                if int(en[0], 16) != int(ew[0], 16):
                    diffs.setdefault('trace_va', []).append({'index': i, 'native': en[0], 'wasm': ew[0]})
                    break
                for pos in range(4):
                    vn, vw = int(en[2 + pos], 16), int(ew[2 + pos], 16)
                    if not ctx.eq(vn, vw, 64):
                        diffs.setdefault('trace_arg', []).append(
                            {'index': i, 'va': en[0], 'pos': pos, 'native': hex(vn), 'wasm': hex(vw)})
                        break
                else:
                    continue
                break
        # mem
        if n.get('mem') != w.get('mem'):
            diffs['mem'] = {'native_blocks': len(n.get('mem', [])), 'wasm_blocks': len(w.get('mem', []))}
        rec['diffs'] = diffs
        rec['outcome'] = 'equal' if not diffs else 'diff'
        verdict[rec['outcome']] += 1
        if diffs and len(diff_examples) < 8:
            diff_examples.append(rec)
        jsonl.write(json.dumps(rec) + '\n')
    jsonl.close()
    # FORMAT.md §3 関数単位ロールアップ (verdict: match = 全 case equal)
    by_fn = collections.defaultdict(list)
    for ln in open(os.path.join(a.out, 'verdicts.jsonl')):
        r = json.loads(ln)
        va = r['case'].split(':')[0]
        by_fn[va].append(r)
    with open(os.path.join(a.out, 'verdicts_fn.jsonl'), 'w') as ff:
        for va, rows in sorted(by_fn.items()):
            outcomes = {r['outcome'] for r in rows}
            fverdict = 'match' if outcomes == {'equal'} else 'mismatch'
            ff.write(json.dumps({
                'liftdiff_version': 1, 'target': 'lpads227',
                'function': {'va': '0x' + va, 'name': 'function_' + va, 'kind': 'landing_pad'},
                'verdict': fverdict,
                'cases': [{'id': r['case'], 'outcome': r['outcome'], 'diffs': r.get('diffs', {})} for r in rows],
            }) + '\n')
    nf = collections.Counter()
    for ln in open(os.path.join(a.out, 'verdicts_fn.jsonl')):
        nf[json.loads(ln)['verdict']] += 1
    print('function verdicts:', dict(nf))
    print('verdicts:', dict(verdict))
    for r in diff_examples:
        print('  DIFF', r['case'], json.dumps(r['diffs'])[:200])
    json.dump({'verdicts': dict(verdict), 'pads': len(cases), 'cases': len(nres)},
              open(os.path.join(a.out, 'summary.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
