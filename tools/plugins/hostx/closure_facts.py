#!/usr/bin/env python3
"""PLG-X (#210) Delphi 殻 9 本 (Wrapper×2 / Patcher×2 / ReWired / MIDI Out / Razer Chroma / Video Player / ZGE 殻) の lift 前提を実測する。
  1. DSP 閉包の規模 (work/closure/block*.json; lift/plugin_closure.py の出力)
  2. 閉包が発行する Dispatcher ID / host vtable slot (inventory/host_calls.py の scan を閉包 ranges に限定)
  3. 殻全体 (framework 共通を除く固有関数) の Dispatcher ID の distinct 数 (閉包外の経路を含む = 実装済み機能の上限の目安)
  4. 殻内の Delphi クラス名 (RTTI の Pascal 文字列; 長さバイト一致のもののみ) のうち意味のある名前の数
  5. 双子 (Effects 版 / Generators 版) の閉包ハッシュ重なり
出力: work/hostx/facts.json と stdout の Markdown 表。
"""
import os, sys, json, collections, re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, 'inventory'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402
import host_calls  # noqa: E402

EXT = os.path.join(FL_WIN64_DIR, 'extracted')
WORK = os.path.join(P, 'work')
OUTD = os.path.join(WORK, 'hostx')

PLUGINS = [
    ('Fruity Wrapper (Effects)', 19091),
    ('Fruity Wrapper (Generators)', 23676),
    ('Patcher (Effects)', 19220),
    ('Patcher (Generators)', 24155),
    ('ReWired', 24161),
    ('MIDI Out', 23918),
    ('Razer Chroma', 19244),
    ('Fruity Video Player', 23674),
    ('ZGameEditor Visualizer (殻)', 19304),
]
TWINS = [(19091, 23676), (19220, 24155)]
ENGINE_PAIRS = [(18976, 23605), (23605, 18976), (22444, 18976), (18976, 22444)]
CLS_RE = re.compile(rb'(?<=[\x04-\x40])T[A-Za-z][A-Za-z0-9_]{2,40}')


def closure_info(block):
    c = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % block)))
    rs = []
    for r in c['ranges']:
        a, b = r.split('-')
        rs.append((int(a, 16), int(b, 16)))
    return c, rs


def host_facts(block, ranges):
    fn = 'block%05d_PE.bin' % block
    _, res = host_calls.scan(fn)
    pe = pefile.PE(os.path.join(EXT, fn), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    unique = json.load(open(os.path.join(WORK, 'win_unique.json')))

    def inside(rva):
        va = base + rva
        return any(a <= va < b for a, b in ranges)
    ids, slots, ids_all = collections.Counter(), collections.Counter(), collections.Counter()
    for rva, disp, ident in res:
        if disp == 0:
            ids_all['dyn' if ident is None else ident] += 1
        if not inside(rva):
            continue
        slots[disp] += 1
        if disp == 0:
            ids['dyn' if ident is None else ident] += 1
    hs = json.load(open(os.path.join(P, 'framework', 'hostshim', 'hs_ids.json')))['ids']
    imm = {k: v for k, v in ids.items() if k != 'dyn'}
    imm_all = {k for k in ids_all if k != 'dyn'}
    return {'ids_closure': {str(k): v for k, v in sorted(ids.items(), key=lambda x: str(x[0]))},
            'slot_disps_closure': {hex(k): v for k, v in sorted(slots.items())},
            'sites_closure': sum(slots.values()), 'dyn_id_sites_closure': ids.get('dyn', 0),
            'ids_closure_not_in_hs_ids': sorted(str(k) for k in imm if str(k) not in hs),
            'imm_ids_dll_taint_scan': len(imm_all), 'dyn_id_sites_dll_taint_scan': ids_all.get('dyn', 0),
            'imm_ids_dll_not_in_hs_ids': sorted(str(k) for k in imm_all if str(k) not in hs)}


def class_names(block):
    d = open(os.path.join(EXT, 'block%05d_PE.bin' % block), 'rb').read()
    names = set()
    for m in CLS_RE.finditer(d):
        s = m.group(0)
        if d[m.start() - 1] == len(s):
            names.add(s.decode('latin1'))
    kw = re.compile(r'Host|VST|Plug|Wrapper|Patch|ReWire|Razer|Chroma|Midi|Video|Zge|ZGE|GL|Ndi|Spout', re.I)
    pick = sorted(n for n in names if kw.search(n))
    return {'n_pascal_T_names': len(names), 'keyword_names': pick[:40], 'n_keyword_names': len(pick)}


def hash_overlap(a, b):
    # 閉包関数の位置非依存ハッシュ (inventory/win_funcs.py の winfuncs: funcs=[rva, size, hash, ...]) の重なり
    def hs(block, rs):
        base = pefile.PE(os.path.join(EXT, 'block%05d_PE.bin' % block), fast_load=True).OPTIONAL_HEADER.ImageBase
        j = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % block)))
        return [x[2] for x in j['funcs'] if any(r0 <= base + x[0] <= r1 for r0, r1 in rs)]
    ca, ra = closure_info(a)
    cb, rb = closure_info(b)
    ha, hb = hs(a, ra), hs(b, rb)
    sa, sb = set(ha), set(hb)
    return {'a': a, 'b': b, 'closure_funcs_a': len(ha), 'closure_funcs_b': len(hb), 'common_distinct_hash': len(sa & sb),
            'a_only_hash': len(sa - sb), 'b_only_hash': len(sb - sa)}


def engine_overlap(a, b):
    # C++ engine 同士の全 .pdata 関数の位置非依存ハッシュの重なり (バイト加重: a の関数のうち b に同ハッシュがある割合)
    ja = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % a)))['funcs']
    jb = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % b)))['funcs']
    hb = {x[2] for x in jb}
    ba = sum(x[1] for x in ja)
    bc = sum(x[1] for x in ja if x[2] in hb)
    return {'a': a, 'b': b, 'funcs_a': len(ja), 'funcs_b': len(jb), 'bytes_a': ba, 'a_funcs_found_in_b': sum(1 for x in ja if x[2] in hb),
            'a_bytes_found_in_b': bc, 'a_bytes_ratio': round(bc / ba, 4) if ba else None}


def main():
    os.makedirs(OUTD, exist_ok=True)
    out = {}
    for name, blk in PLUGINS:
        c, rs = closure_info(blk)
        f = {'block': blk, 'closure_funcs': c['unique_funcs'], 'closure_bytes': c['unique_bytes'],
             'frontier_funcs': c['framework_frontier_funcs'], 'frontier_bytes': c['framework_frontier_bytes'],
             'vcall': c['indirect_vcall'], 'ptr_or_vt0': c['indirect_ptr_or_vt0'], 'iat_calls': c['iat_calls'],
             'entries': c['entries']}
        f['host'] = host_facts(blk, rs)
        f['classes'] = class_names(blk)
        f['dll_strings'] = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % blk)))['dll_strings']
        out[name] = f
        print('done', name, file=sys.stderr)
    tw = []
    for a, b in TWINS:
        try:
            tw.append(hash_overlap(a, b))
        except Exception as e:  # winfuncs の形式差は記録して続行
            tw.append({'a': a, 'b': b, 'error': repr(e)})
    eng = [engine_overlap(a, b) for a, b in ENGINE_PAIRS]
    json.dump({'plugins': out, 'twins': tw, 'engines': eng}, open(os.path.join(OUTD, 'facts.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({'plugins': out, 'twins': tw, 'engines': eng}, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
