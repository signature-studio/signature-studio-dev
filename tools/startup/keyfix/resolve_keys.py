#!/usr/bin/env python3
"""resolve_keys.py — low-key 112 エントリの実キー解決 (keyflow2 を全ソース関数に適用)。

出力: work/resolved_keys.json
  { "<hive>|<name>|<source>": {"key": ..., "conf": "確定|推定", "how": ..., "site": ...} }

確定の条件:
  * op の key が関数内リテラル / UStrAsg(リテラル) / UStrCat3(リテラル+リテラル) で完全解決
  * かつ nil-key の場合は同一関数内の前方に GetKeyHandle/OpenKey/OpenKeyRO のリテラルがある
推定: 'General\'+[obj+0x10] の obj 部が未解決 (実行時文字列) など
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keyflow2 import resolve_func, full_key

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = '/home/ubuntu/work/webstudio/tools/startup/vreg/data/seed.json'

NAME2VA = {
    'RenderOptions.save': 0xeeac20, 'RenderOptions.load': 0xeec630,
    'LoadSettings': 0x11a57c0, 'SaveSettings': 0x11af7e0,
    'LoadBrowserToolbars': 0x11a36e0, 'Reg.readKey': 0x8e6150, 'Reg.writeKey': 0x8e6020,
    'Paths.sharedData': 0x652e60,
}


def src_va(src):
    src = src.split(';')[0].strip()
    if src in NAME2VA:
        return NAME2VA[src]
    if src.startswith('FUN_'):
        return int(src[4:], 16)
    return None


def main():
    seed = json.load(open(SEED))
    low = [e for e in seed['entries'] if e.get('key') is None]
    # 関数ごとに一度だけ解決
    vacache = {}
    for e in low:
        for s in e['source']:
            va = src_va(s)
            if va and va not in vacache:
                vacache[va] = resolve_func(va)
    # op index: (func_va -> ops)
    out = {}
    stats = collections.Counter()
    for e in low:
        name_l = e['name'].lower()
        cands = []
        for s in e['source']:
            va = src_va(s)
            r = vacache.get(va)
            if not r:
                continue
            for o in r['ops']:
                v = o.get('value')
                if isinstance(v, str) and v.lower() == name_l:
                    fk = full_key(o, r['default_ctx'])
                    cands.append((s, o, fk))
        if not cands:
            # 値名が r9 (ReadStr) 等で取れない場合: 値名一致 op 無し
            out['%s|%s|%s' % (e['hive'], e['name'], e['source'][0])] = {
                'key': None, 'conf': '推定', 'how': 'value-name op not found in source ops'}
            stats['nomatch'] += 1
            continue
        # 最も多い解を探す (同一関数内の複数 site)
        keys = collections.Counter(c[2] for c in cands)
        best, cnt = keys.most_common(1)[0]
        conf = '確定'
        how = []
        if best is None or '?(' in best or '<' in (best or ''):
            conf = '推定'
        if best and best.lower().startswith('software\\image-line\\fl studio 26') and ' ?(' not in best:
            pass
        # ctx 由来 (nil-key) は同一関数内の前方リテラル根拠を添える
        s0, o0, _ = cands[0]
        if o0.get('key_nil'):
            how.append('key=nil → 同一関数内の前方 GetKeyHandle/OpenKey "%s"' % o0.get('ctx_at_call'))
        else:
            how.append('key 引数を関数内で解決 (%s)' % o0.get('key'))
        if 'General\\' in (o0.get('key') or '') or (o0.get('ctx_at_call') or '').lower().startswith('software\\image-line\\fl studio 26'):
            how.append('基底=Software\\Image-Line\\FL Studio 26 (0x1104fe0 が起動時に OpenKey / 0x11c71b0 同一関数実証)')
        out['%s|%s|%s' % (e['hive'], e['name'], e['source'][0])] = {
            'key': best, 'conf': conf, 'how': '; '.join(how),
            'site': o0['call'], 'method': o0['method'], 'matches': cnt, 'cands': dict(keys)}
        stats[conf] += 1
    json.dump(out, open(os.path.join(HERE, 'work', 'resolved_keys.json'), 'w'), ensure_ascii=False, indent=1)
    print('resolved:', dict(stats), 'of', len(low))
    # サマリ: キー別件数
    kc = collections.Counter(v['key'] for v in out.values())
    for k, c in kc.most_common():
        print('%3d  %s' % (c, k))


if __name__ == '__main__':
    main()
