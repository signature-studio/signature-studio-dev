#!/usr/bin/env python3
"""IPP shim ジェネレータ: 420 名 × 署名 → thunk / 関数表 / 署名 JSON を生成し、署名を呼出箇所実績で検算する。

入力 : ../work/flengine_ipp_names.json (420 名), data/callsite_evidence.json (sigscan.py), ../src/ipp_*.c と impl/*.c (実装済み検出)
出力 : gen/ipp_proto.h       全 420 名の C プロトタイプ (実装側はこれを include → コンパイラが署名を検査)
       gen/ipp_shim_tab.c    MS x64 レジスタブロック → 型付き実装呼出の thunk (実装済み) / fail-soft stub (未実装) + 名前表
       data/ipp_sigs.json    署名表 (IR pass / 将来の実装者向け): 420 名の ret/params/ABI スロット/確度/根拠
       data/sigs_summary.json 件数・確度・検算結果
usage: python3 gen_shim.py"""
import json, os, re, subprocess, sys, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__)); IPP = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, IPP)
import sigs

# C 型 → ABI クラス。MS x64: 値渡し struct は 1/2/4/8B なら整数レジスタ、それ以外は呼出側コピーへのポインタ。
SCALAR = {'int': 'i', 'Ipp32s': 'i', 'Ipp32u': 'u', 'unsigned int': 'u', 'Ipp8u': 'b', 'Ipp16s': 'h', 'Ipp16u': 'H', 'Ipp64s': 'q',
          'Ipp32f': 'f', 'float': 'f', 'Ipp64f': 'd', 'double': 'd', 'Ipp16sc': 's4', 'Ipp32fc': 's8', 'Ipp32sc': 's8', 'IppiSize': 's8', 'IppiPoint': 's8',
          'Ipp64fc': 'r16', 'Ipp64sc': 'r16', 'IppiRect': 'r16'}
FLOATCLS = ('f', 'd')
CTYPE_OF = {'i': 'int', 'u': 'unsigned', 'b': 'Ipp8u', 'h': 'Ipp16s', 'H': 'Ipp16u', 'q': 'Ipp64s'}


def parse_params(s):
    out = []
    for p in [x.strip() for x in s.split(',') if x.strip()]:
        if '*' in p or '[' in p:
            nm = re.search(r'(\w+)\s*(\[.*)?$', p).group(1); out.append(('p', p, nm))
        else:
            t, nm = p.rsplit(None, 1); t = re.sub(r'\bconst\b', '', t).strip()
            if t not in SCALAR: raise ValueError(f'unknown type {t!r} in {s!r}')
            out.append((SCALAR[t], p, nm))
    return out


def observed(ev, k):
    """スロット k に書込みが観測された種別の集合 (半数近い呼出箇所で観測 = 0.4 以上)。"""
    s = ev['sites']; o = set()
    if ev['gp'][k] >= 0.4 * s: o.add('gp')
    if ev['xmm'][k] >= 0.4 * s: o.add('xmm')
    return o


def check_against_evidence(params, ev):
    """('agree'|'weak'|'conflict'|'nodata', 理由)。weak = 期待より観測が少ないだけ(引数が既にレジスタにある等で未観測の可能性)。conflict = 型/個数が食い違う。"""
    if not ev or ev['sites'] < 2: return 'nodata', ''
    exp = ['xmm' if c in FLOATCLS else 'gp' for c, _, _ in params]; n = len(exp); why = []; hard = False
    for k in range(4):
        o = observed(ev, k); e = exp[k] if k < n else None
        if e is None:
            if o: why.append(f'slot{k}: 期待 引数なし / 観測 {sorted(o)}'); hard = True
        elif e in o: continue
        elif o: why.append(f'slot{k}: 期待 {e} / 観測 {sorted(o)}'); hard = True
        else: why.append(f'slot{k}: 期待 {e} / 観測なし(gp={ev["gp"][k]} xmm={ev["xmm"][k]} of {ev["sites"]})')
    exp_stack = max(0, n - 4)
    obs_stack = max([w + 1 for w, c in enumerate(ev['stack']) if c >= 0.4 * ev['sites']] or [0])
    if obs_stack > exp_stack: why.append(f'stack: 期待 {exp_stack} / 観測 {obs_stack}'); hard = True
    elif obs_stack < exp_stack: why.append(f'stack: 期待 {exp_stack} / 観測 {obs_stack} (下限値)')
    if not why: return 'agree', ''
    if hard and ev['sites'] < 5: return 'weak', '; '.join(why) + f' [低サンプル: {ev["sites"]} 箇所]'
    return ('conflict' if hard else 'weak'), '; '.join(why)


def implemented_names():
    os.makedirs('/tmp/opencode', exist_ok=True); names = set()
    files = sorted(glob.glob(f'{IPP}/src/ipp_*.c')) + sorted(glob.glob(f'{HERE}/impl/*.c'))
    for f in files:
        subprocess.run(['gcc', '-c', '-O0', '-I', f'{IPP}/src', '-o', '/tmp/opencode/_shim_nm.o', f], check=True, capture_output=True)
        out = subprocess.run(['nm', '-g', '--defined-only', '/tmp/opencode/_shim_nm.o'], capture_output=True, text=True).stdout
        names |= set(re.findall(r'\sT\s(ipp\w+)', out))
    return names


def build():
    names = sorted(n for n in json.load(open(f'{IPP}/work/flengine_ipp_names.json'))['x86_64'] if n.startswith('ipp'))
    assert len(names) == 420, len(names)
    evid = json.load(open(f'{HERE}/data/callsite_evidence.json'))
    impl = implemented_names()
    rows = []
    for n in names:
        d = sigs.derive(n)
        if d is None:
            rows.append({'name': n, 'known': False, 'impl': n in impl, 'conf': 'U', 'family': 'unknown'}); continue
        ret, ps, fam = d; params = parse_params(ps)
        status, why = check_against_evidence(params, evid.get(n))
        # 確度: A = 実装済み (コンパイラが実装の型と照合; 24 関数は実 IPP と実行比較)。B+ = 規則 + 呼出実績が一致(weak 含む)。B- = 規則のみ(実績なし)。X = 実績と矛盾
        conf = 'A' if n in impl else ('X' if status == 'conflict' else 'B+' if status in ('agree', 'weak') else 'B-')
        rows.append({'name': n, 'known': True, 'impl': n in impl, 'ret': ret, 'params_c': ps, 'family': fam, 'conf': conf, 'evidence': status, 'evidence_note': why,
                     'params': [{'cls': c, 'decl': p, 'name': nm, 'slot': i, 'reg': (['rcx', 'rdx', 'r8', 'r9'][i] if c not in FLOATCLS else f'xmm{i}') if i < 4 else f'stack+{(i - 4) * 8:#x}'}
                                for i, (c, p, nm) in enumerate(params)],
                     'call_sites_win': (evid.get(n) or {}).get('sites', 0)})
    return names, rows



def ptr_type(decl):
    """ポインタ仮引数宣言から名前を除いた型 (キャスト用)。"""
    return re.sub(r'\s*\b\w+\s*$', '', decl).strip()


def decode_expr(cls, decl, slot):
    w = f'b->xmm[{slot}]' if (cls in FLOATCLS and slot < 4) else (f'b->gp[{slot}]' if slot < 4 else f'STK({slot - 4})')
    t = re.sub(r'\bconst\b', '', decl.rsplit(None, 1)[0]).strip() if cls != 'p' else None
    if cls == 'p': return f'({ptr_type(decl)})IPP_GUEST_PTR({w})'
    if cls == 'i': return f'(int)(int32_t){w}'
    if cls == 'u': return f'(unsigned)(uint32_t){w}'
    if cls == 'b': return f'(Ipp8u){w}'
    if cls == 'h': return f'(Ipp16s){w}'
    if cls == 'H': return f'(Ipp16u){w}'
    if cls == 'q': return f'(Ipp64s){w}'
    if cls == 'f': return f'ipp_f32({w})'
    if cls == 'd': return f'ipp_f64({w})'
    if cls in ('s4', 's8'): return f'DEC_STRUCT({t}, {w})'
    if cls == 'r16': return f'(*(const {t}*)IPP_GUEST_PTR({w}))'
    raise ValueError(cls)


PROTO_HEAD = """/* generated by tools/ipp/shim/gen_shim.py -- 編集禁止。420 名の IPP 関数プロトタイプ (署名表 sigs.py 由来)。
   実装側 (tools/ipp/src の ipp_ 接頭辞 .c と shim/impl の .c) はこれを include するか、同一宣言を持つこと (型が食い違えばコンパイルエラー = 署名検査)。 */
#pragma once
#include <stdint.h>
typedef int IppStatus; typedef float Ipp32f; typedef double Ipp64f; typedef uint8_t Ipp8u; typedef int16_t Ipp16s; typedef uint16_t Ipp16u;
typedef int32_t Ipp32s; typedef uint32_t Ipp32u; typedef int64_t Ipp64s;
typedef struct { Ipp32f re, im; } Ipp32fc; typedef struct { Ipp64f re, im; } Ipp64fc; typedef struct { Ipp16s re, im; } Ipp16sc;
typedef struct { Ipp32s re, im; } Ipp32sc; typedef struct { Ipp64s re, im; } Ipp64sc;
typedef struct { int width, height; } IppiSize; typedef struct { int x, y; } IppiPoint; typedef struct { int x, y, width, height; } IppiRect;
"""


def emit_probes():
    os.makedirs(f'{HERE}/test/gen', exist_ok=True)
    t = ['/* generated by gen_shim.py -- ABI デコーダ検証用プローブ thunk (本番 thunk と同じ decode_expr で生成)。実装 (probe_*) は test/shim_selftest.c */',
         '#include "../../src/ipp_shim.h"', '#include "../../gen/ipp_proto.h"', '#include <string.h>', '#include <stdint.h>',
         'static inline float ipp_f32(uint64_t w) { uint32_t u = (uint32_t)w; float f; memcpy(&f, &u, 4); return f; }',
         'static inline double ipp_f64(uint64_t w) { double d; memcpy(&d, &w, 8); return d; }',
         '#define DEC_STRUCT(T, W) ({ T v_; uint64_t w_ = (W); memcpy(&v_, &w_, sizeof v_); v_; })',
         '#define STK(i) (((const uint64_t *)(uintptr_t)b->stk)[i])']
    for n, ret, ps in sigs.PROBES: t.append(f'{ret} {n}({ps});')
    for n, ret, ps in sigs.PROBES:
        params = parse_params(ps)
        args = ', '.join(decode_expr(c, d, i) for i, (c, d, _) in enumerate(params))
        body = f'b->rax = (uint64_t)(uint32_t){n}({args});' if ret == 'IppStatus' else f'b->rax = IPP_TO_GUEST({n}({args}));'
        t.append(f'static void blk_{n}(IppBlk *b) {{ {body} b->xmm0ret = 0; }}')
    t.append('void (*const ipp_probe_blk[])(IppBlk *) = {' + ', '.join(f'blk_{n}' for n, _, _ in sigs.PROBES) + '};')
    t.append(f'const int ipp_probe_count = {len(sigs.PROBES)};')
    open(f'{HERE}/test/gen/probe_thunks.c', 'w').write('\n'.join(t) + '\n')


def emit(names, rows):
    emit_probes()
    os.makedirs(f'{HERE}/gen', exist_ok=True)
    pr = [PROTO_HEAD]
    for r in rows:
        if not r['known']: continue
        pr.append(f"{r['ret']} {r['name']}({r['params_c'] or 'void'});")
    open(f'{HERE}/gen/ipp_proto.h', 'w').write('\n'.join(pr) + '\n')
    t = ['/* generated by tools/ipp/shim/gen_shim.py -- 編集禁止。MS x64 レジスタブロック -> 型付き実装呼出 thunk と 420 名の表。 */',
         '#include "../src/ipp_shim.h"', '#include "ipp_proto.h"', '#include <string.h>', '#include <stdint.h>',
         'static inline float ipp_f32(uint64_t w) { uint32_t u = (uint32_t)w; float f; memcpy(&f, &u, 4); return f; }',
         'static inline double ipp_f64(uint64_t w) { double d; memcpy(&d, &w, 8); return d; }',
         '#define DEC_STRUCT(T, W) ({ T v_; uint64_t w_ = (W); memcpy(&v_, &w_, sizeof v_); v_; })',
         '#define STK(i) (((const uint64_t *)(uintptr_t)b->stk)[i])', '']
    for r in rows:
        if not (r['known'] and r['impl']): continue
        args = ', '.join(decode_expr(p['cls'], p['decl'], p['slot']) for p in r['params'])
        call = f"{r['name']}({args})"
        if r['ret'] == 'void': body = f'{call};'
        elif r['ret'] == 'IppStatus': body = f'b->rax = (uint64_t)(uint32_t){call};'
        else: body = f'b->rax = IPP_TO_GUEST({call});'
        used = 'b' if r['params'] or True else ''
        t.append(f"static void blk_{r['name']}(IppBlk *b) {{ {body} b->xmm0ret = 0; }}")
    t += ['', 'const IppShimEntry ipp_shim_table[] = {']
    for r in rows:
        k = r['known']
        sig = f"{r['ret']} {r['name']}({r['params_c']})" if k else ''
        t.append(f"  {{\"{r['name']}\", " + (f"blk_{r['name']}" if (k and r['impl']) else '0') + f", \"{r['conf']}\", {1 if r['impl'] else 0}, {len(r['params']) if k else -1}, \"{sig}\"}},")
    t += ['};', 'const int ipp_shim_table_count = (int)(sizeof ipp_shim_table / sizeof *ipp_shim_table);']
    open(f'{HERE}/gen/ipp_shim_tab.c', 'w').write('\n'.join(t) + '\n')
    out = {'abi': 'MS x64: arg i<4 -> rcx/rdx/r8/r9 (整数/ポインタ/8B以下struct) or xmm0..3 (float/double); i>=4 -> stack word i-4 ([rsp+0x20+8*(i-4)] at call); >8B struct は呼出側コピーへのポインタ; 戻り: IppStatus=eax, ポインタ=rax',
           'entries': [{k: v for k, v in r.items()} for r in rows]}
    json.dump(out, open(f'{HERE}/data/ipp_sigs.json', 'w'), indent=1, ensure_ascii=False)
    c = collections.Counter(r['conf'] for r in rows); fam = collections.Counter(r['family'] for r in rows)
    ev = collections.Counter(r.get('evidence') for r in rows)
    impl = [r for r in rows if r['impl']]
    summ = {'names': len(rows), 'thunks_typed(impl)': len(impl), 'stubs(fail-soft)': len(rows) - len(impl), 'unknown_sig': c.get('U', 0), 'confidence': dict(c), 'evidence_check': dict(ev),
            'families': dict(fam),
            'win_called_names': sum(1 for r in rows if r.get('call_sites_win')),
            'weak': [r['name'] for r in rows if r.get('evidence') == 'weak'], 'conflict': [r['name'] for r in rows if r.get('evidence') == 'conflict'],
            'stub_with_output_handles(hazard)': [r['name'] for r in rows if not r['impl'] and re.search(r'InitAlloc|GetSize|GetBuf|GetStateSize|Init_|Init64f', r['name'])]}
    import csv
    used = {r['name']: (r['used_win'] == '1', r['used_mac_x86'] == '1' or r['used_mac_arm64'] == '1') for r in csv.DictReader(open(f'{IPP}/data/ipp_matrix.csv'))}
    HAND = {'ippi', 'fir', 'iir', 'siggen', 'explicit', 'reorder', 'fft', 'control', 'mem-set'}
    nonA = [r for r in rows if not r['impl']]
    summ['union_used_239'] = sum(1 for n in used if any(used[n])); summ['union_used_impl'] = sum(1 for r in rows if r['impl'] and any(used[r['name']]))
    summ['detail'] = {
        'A(impl)': len(impl),
        'B+ agree': sum(1 for r in nonA if r['conf'] == 'B+' and r['evidence'] == 'agree'),
        'B+ weak(型一致・引数の一部が実績で未観測)': sum(1 for r in nonA if r['conf'] == 'B+' and r['evidence'] == 'weak'),
        'B- 実績なし かつ 使用集合239内(mac のみ呼出 or 低サンプル)': sum(1 for r in nonA if r['conf'] == 'B-' and any(used[r['name']])),
        'B- 実績なし かつ どの platform からも呼ばれない': sum(1 for r in nonA if r['conf'] == 'B-' and not any(used[r['name']])),
        'rule-derived(non-A)': sum(1 for r in nonA if r['family'] not in HAND), 'hand-written(non-A)': sum(1 for r in nonA if r['family'] in HAND)}
    summ['hand_written_unverified_in_239'] = [r['name'] for r in nonA if r['family'] in HAND and r['conf'] != 'B+' and any(used[r['name']])]
    summ['hand_written_nonA_total'] = [r['name'] for r in nonA if r['family'] in HAND]
    json.dump(summ, open(f'{HERE}/data/sigs_summary.json', 'w'), indent=1, ensure_ascii=False)
    return summ

if __name__ == '__main__':
    names, rows = build()
    summ = emit(names, rows)
    print(json.dumps({k: v for k, v in summ.items() if k not in ('families', 'weak', 'stub_with_output_handles(hazard)')}, ensure_ascii=False))
    c = collections.Counter(r['conf'] for r in rows); ev = collections.Counter(r.get('evidence') for r in rows)
    print('confidence', dict(c)); print('evidence', dict(ev))
    for r in rows:
        if r['conf'] in ('X', 'U') or r.get('evidence') == 'conflict':
            print(r['conf'], r['name'], '|', r.get('params_c', ''), '|', r.get('evidence_note', ''))
