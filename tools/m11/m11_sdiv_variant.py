#!/usr/bin/env python3
"""LD-62 (#1767): 0x417b70 の除算 1 箇所だけを udiv → sdiv に変えた m11 variant を作る。

入力: tools/m11/work/boot_final3.ll (m11 build の生成物。work-m11 素材で展開される)
出力: tools/m11/work/boot_final3_sdiv.ll と tools/liftdiff/work/m11_sdiv/target.json
      (target.json は targets/m11.json の name / ir だけを差し替えたもの)

変換は 1 行だけ。行番号 125366 の内容が期待どおりでなければ止まる (別 build の IR を誤って変えない)。
  python3 tools/m11/m11_sdiv_variant.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(HERE, 'work', 'boot_final3.ll')
DST = os.path.join(HERE, 'work', 'boot_final3_sdiv.ll')
TARGET_SRC = os.path.join(REPO, 'tools', 'liftdiff', 'targets', 'm11.json')
TARGET_DST_DIR = os.path.join(REPO, 'tools', 'liftdiff', 'work', 'm11_sdiv')
LINE = 125366
OLD = '  %29 = udiv i64 %28, %arg4\n'
NEW = '  %29 = sdiv i64 %28, %arg4\n'


def main():
    with open(SRC, encoding='utf-8', errors='replace', newline='') as f:
        lines = f.readlines()
    if lines[LINE - 1] != OLD:
        sys.exit('line %d が期待と違う: %r' % (LINE, lines[LINE - 1]))
    lines[LINE - 1] = NEW
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, 'w', encoding='utf-8', errors='replace', newline='') as f:
        f.writelines(lines)
    t = json.load(open(TARGET_SRC))
    t['name'] = 'm11_sdiv'
    t['ir'] = os.path.relpath(DST, REPO)
    os.makedirs(TARGET_DST_DIR, exist_ok=True)
    out = os.path.join(TARGET_DST_DIR, 'target.json')
    with open(out, 'w') as f:
        json.dump(t, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('wrote %s (line %d changed)' % (DST, LINE))
    print('wrote %s' % out)


if __name__ == '__main__':
    main()
