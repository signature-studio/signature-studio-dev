#!/usr/bin/env python3
"""gen_verdict.py — FLE-2 boot/survey を liftdiff FORMAT v1 JSONL で記録する。

比較対象 (route 間差分):
  native 側 = RetDec route baseline (tools/m11/work/shimx_link/baseline/m11_boot.survey.json,
              m11 sx 純リンク + soft。ok 800 / oob 50 / halt0 44 / closure外 46 / abort 1 / noproc 1)
  wasm 側   = x64c route (本 ticket。boot/survey 実測 = results/survey.json + survey_seg_*.jsonl)

出力: results/verdict_boot.jsonl (1 行 = 1 unit, FORMAT.md v1 §3 のキー + x- 拡張タグ)
  - 全 942 unit を行化 (verdict = match|mismatch|unexec)。差分 unit のみ cases[].diffs を持つ。
  - 先頭行に boot 連鎖 (sequential init) の比較行を付与 (function.va = 0x1376820, tag x-boot_chain)。

usage: python3 gen_verdict.py [--pe PE]
"""
import argparse, bisect, glob, json, os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'shared'))
from paths import FL_WIN64_DIR, REPO_ROOT

HERE = os.path.dirname(os.path.abspath(__file__))
FLE = os.path.dirname(HERE)
PE_DEF = f'{FL_WIN64_DIR}/extracted/block00031_PE.bin'
BASELINE = f'{REPO_ROOT}/tools/m11/work/shimx_link/baseline/m11_boot.survey.json'
IMG = 0x400000
PKG = 0x13768b0

# baseline kind -> 比較正規化 (x64c cls との組で outcome を決める)
def norm_base(kind):
    return {'closure_outside': 'closure_outside', 'abort': 'abort', 'noproc': 'noproc',
            'ok': 'ok', 'oob': 'oob', 'halt0': 'halt0'}.get(kind, kind)

def norm_x64(cls):
    return {'ok': 'ok', 'oob': 'oob', 'halt0': 'halt0', 'unlifted': 'unlifted',
            'empty': 'empty', 'noproc': 'noproc'}.get(cls, cls)

def outcome_of(nb, nx):
    """FORMAT §3 outcome 語彙: equal|diff|wasm_trap|native_fault|both_fault (wasm=x64c, native=RetDec baseline)。"""
    if nb == nx:
        return 'equal' if nb == 'ok' else 'both_fault'
    if nb == 'ok':
        return 'wasm_trap'          # baseline 完走 / x64c 異常
    if nx == 'ok':
        return 'native_fault'       # baseline 異常 / x64c 完走
    return 'diff'                   # 両方異常で種類違い

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', default=PE_DEF)
    ap.add_argument('--baseline', default=BASELINE)
    ap.add_argument('--out', default=os.path.join(HERE, 'results', 'verdict_boot.jsonl'))
    a = ap.parse_args()

    import pefile
    pe = pefile.PE(a.pe)
    img = pe.get_memory_mapped_image()
    def q(va): return struct.unpack_from('<Q', img, va - IMG)[0]
    cnt = struct.unpack_from('<I', img, PKG - IMG)[0]
    units_arr = q(PKG + 8)
    proc = [q(units_arr + 16 * i) for i in range(cnt)]

    # ---- x64c 側: survey_seg_*.jsonl の最終行を採用 (merge_survey.py と同一規則) ----
    x64 = {}
    for p in sorted(glob.glob(os.path.join(HERE, 'results', 'survey_seg_*.jsonl'))) + \
             glob.glob(os.path.join(HERE, 'results', 'survey_units.jsonl')):
        for line in open(p, errors='replace'):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                x64[int(rec[0])] = norm_x64(rec[1])
            except Exception:
                continue
    # empty は jsonl に出ない (runner が continue) ので補完する:
    #   seg JSON の details (seg_283 のみ存在) + 消去法 (jsonl 無し & noproc(941) 以外 = empty)。
    #   seg_0 は timeout 消滅で .json のみ無いが、jsonl 全行が生きているため消去法で確定する。
    for p in glob.glob(os.path.join(HERE, 'results', 'survey_seg_*.json')):
        try:
            det = json.load(open(p)).get('survey', {}).get('details') or []
        except Exception:
            continue
        for rec in det:
            if rec[1] == 'empty':
                x64[int(rec[0])] = 'empty'
    NOPROC_IDX = 941     # 実測: proc==0 は index 941 のみ (PE units_arr 全件走査より)
    x64[NOPROC_IDX] = 'noproc'
    for i in range(cnt):
        if i not in x64:
            x64[i] = 'empty'
    # ---- baseline 側 (m11 per_unit は 1-based) ----
    base_doc = json.load(open(a.baseline))
    base = {}
    for rec in base_doc['per_unit']:
        base[rec['unit'] - 1] = norm_base(rec['kind'])

    rows = []
    n_match = n_mis = n_unexec = 0
    cls_matrix = {}
    # ---- boot 連鎖 (sequential) 行 ----
    rows.append({
        'liftdiff_version': 1, 'target': 'flelift-boot',
        'function': {'va': hex(0x1376820), 'name': 'fle_boot_chain_sequential',
                     'sig': {'ret': 'i64', 'params': ['i64', 'i64', 'i64'], 'defined': True}},
        'verdict': 'mismatch',
        'tags': [{'tag': 'x-boot_chain', 'confidence': 'high',
                  'evidence': 'RetDec baseline: 17 unit 完走後 unit#18 (0x455790) dispatch で OOB '
                              '(_UStrAsg alloca 縮退)。x64c: unit#17 (0x454090, i=16) の body 内 '
                              'DynArraySetLength (0x414ad0 @ 0x45440a) の旧 block FreeMem が FastMM invalid pointer → '
                              'System.@Error → @RaiseExcept → RaiseException(0xEEDFADE)。unit#18 は未到達。'}],
        'cases': [{'id': 'boot:seq', 'pattern': 'dllmain_attach',
                   'outcome': 'diff', 'native_status': 'units17_done_then_oob_at_18',
                   'wasm_status': 'raise_0xeedfade_in_unit17',
                   'diffs': {'ret': {'native': 'stopped_at_unit18', 'wasm': 'stopped_in_unit17'}}}],
        'leaf': False,
        'static': {'machine': {'ins': 0}, 'ir': {}},
        'x-boot': {'units_dispatched': 17, 'units_completed_x64c': 16,
                   'mm_table_after': {'getmem': '0x407a50', 'freemem': '0x407e20', 'realloc': '0x408040'},
                   'getmem_calls': 59, 'freemem_calls': 1, 'virtualalloc': '1 call / 1310704 B'}
    })
    # ---- survey 行 (942) ----
    for i in range(cnt):
        nx = x64.get(i)
        nb = base.get(i)
        if nx is None or nb is None:
            n_unexec += 1
            rows.append({
                'liftdiff_version': 1, 'target': 'flelift-boot',
                'function': {'va': hex(proc[i]), 'name': 'unit_%d' % (i + 1),
                             'sig': {'ret': 'i64', 'params': [], 'defined': True}},
                'verdict': 'unexec', 'unexec_reason': 'x-_missing_side',
                'tags': [], 'cases': [], 'leaf': True,
                'static': {'machine': {'ins': 0}, 'ir': {}},
                'x-unit': {'index0': i, 'x64c': nx, 'baseline': nb}})
            continue
        oc = outcome_of(nb, nx)
        cls_matrix[(nb, nx)] = cls_matrix.get((nb, nx), 0) + 1
        if oc == 'equal':
            n_match += 1
            rows.append({
                'liftdiff_version': 1, 'target': 'flelift-boot',
                'function': {'va': hex(proc[i]), 'name': 'unit_%d' % (i + 1),
                             'sig': {'ret': 'i64', 'params': [], 'defined': True}},
                'verdict': 'match', 'tags': [],
                'cases': [{'id': 'unit%d:iso' % i, 'pattern': 'isolated_init',
                           'outcome': 'equal', 'native_status': nb, 'wasm_status': nx}],
                'leaf': True, 'static': {'machine': {'ins': 0}, 'ir': {}},
                'x-unit': {'index0': i, 'baseline': nb, 'x64c': nx}})
        else:
            n_mis += 1
            rows.append({
                'liftdiff_version': 1, 'target': 'flelift-boot',
                'function': {'va': hex(proc[i]), 'name': 'unit_%d' % (i + 1),
                             'sig': {'ret': 'i64', 'params': [], 'defined': True}},
                'verdict': 'mismatch',
                'tags': [{'tag': 'x-route_diff', 'confidence': 'high',
                          'evidence': 'baseline=%s x64c=%s' % (nb, nx)}],
                'cases': [{'id': 'unit%d:iso' % i, 'pattern': 'isolated_init',
                           'outcome': oc, 'native_status': nb, 'wasm_status': nx,
                           'diffs': {'ret': {'native': nb, 'wasm': nx}}}],
                'leaf': True, 'static': {'machine': {'ins': 0}, 'ir': {}},
                'x-unit': {'index0': i, 'baseline': nb, 'x64c': nx}})

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('[gen_verdict] rows=%d (boot 1 + survey %d) match=%d mismatch=%d unexec=%d -> %s'
          % (len(rows), cnt, n_match, n_mis, n_unexec, a.out))
    print('[gen_verdict] class matrix (baseline -> x64c):')
    for (nb, nx), c in sorted(cls_matrix.items(), key=lambda kv: -kv[1]):
        print('  %-16s -> %-10s %4d' % (nb, nx, c))
    # 集計 (両側 ok 以外の一致/不一致サマリ)
    by_outcome = {}
    for (nb, nx), c in cls_matrix.items():
        by_outcome[outcome_of(nb, nx)] = by_outcome.get(outcome_of(nb, nx), 0) + c
    print('[gen_verdict] outcome:', by_outcome)

if __name__ == '__main__':
    main()
