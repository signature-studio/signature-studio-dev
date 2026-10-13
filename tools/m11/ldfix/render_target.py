#!/usr/bin/env python3
"""render_target.py — targets/*.json の ${FL_WIN64_DIR} 等を展開して work/targets/ に書く。

使い方: python3 render_target.py targets/m11_ldfix.json   # 出力先パスを stdout に 1 行
liftdiff の target JSON は環境変数を展開しないため、e2e スクリプトがこの出力を liftdiff に渡す。
変数は tools/shared/paths.py と同じ (環境変数優先・未設定時は既定値)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
import paths  # noqa: E402


def main():
    src = sys.argv[1]
    s = open(src, encoding='utf-8').read()
    for k, v in paths.ALL.items():
        s = s.replace('${%s}' % k, v)
    if '${' in s:
        sys.exit('render_target: 未展開の変数が残っている: %s' % src)
    out_dir = os.path.join(HERE, 'work', 'targets')
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, os.path.basename(src))
    open(dst, 'w', encoding='utf-8').write(s)
    print(dst)


main()
