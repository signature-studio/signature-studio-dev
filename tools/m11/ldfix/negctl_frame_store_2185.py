#!/usr/bin/env python3
"""negctl_frame_store_2185.py — audit_frame_store_verdict.py の主要検査のネガティブコントロール (#2185 / WORKFLOW §5)。

判定器本体は変更せず、effect() を 1 命令だけ差し替えて main() を再実行し、DROP / LIVE-IN 判定が変わることを確認する。
  ctrl          : 差し替えなし (基準)
  drop10628bc   : 10628a0 の store 10628bc mov word [rbp+0x4e], ax を無効化 (store なし扱い)
  fake412160    : 412160 の読み 41217d の直前 412176 (lea r13, ...) を DEF (store) 扱い

使い方: python3 negctl_frame_store_2185.py PE.bin AUDIT.json F4.json OUT.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_frame_store_verdict as A  # noqa: E402

MODES = {
    'ctrl': {},
    'drop10628bc': {0x10628bc: None},
    'fake412160': {0x412176: 'DEF'},
}


def run(mode, pe, audit, f4, out):
    orig = A.effect
    patch = MODES[mode]

    def patched(cs, esc, ins, slot):
        if ins.address in patch:
            return patch[ins.address]
        return orig(cs, esc, ins, slot)

    A.effect = patched
    try:
        sys.argv = ['audit_frame_store_verdict.py', pe, audit, f4, out]
        A.main()
    finally:
        A.effect = orig
    d = json.load(open(out))
    return dict(mode=mode, by_verdict=d['by_verdict'], site_by_verdict=d['site_by_verdict'],
                fn_verdict={fn: d['verdict'][fn] for fn in ('10628a0', '13105d0', 'c38bd0', '412160')},
                fn_sites={fn: [(s['addr'], s['verdict'], s.get('why')) for s in d['sites'] if s.get('fn') == fn]
                          for fn in ('10628a0', '412160')})


def main():
    pe, audit, f4, out = sys.argv[1:5]
    res = []
    tmp = out + '.tmp.json'
    for mode in MODES:
        res.append(run(mode, pe, audit, f4, tmp))
    os.remove(tmp)
    json.dump(res, open(out, 'w'), indent=1, ensure_ascii=False)
    for r in res:
        print(r['mode'], r['by_verdict'], r['site_by_verdict'], r['fn_verdict'])


if __name__ == '__main__':
    main()
