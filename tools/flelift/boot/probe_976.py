#!/usr/bin/env python3
# probe_976.py — #5337 [WIN-60]: f_976a90 → f_976b60 → f_410320 の rcx の出所を実行時に記録する probe を生成 C に入れる。
# 生成物 (work/boot/lift/*.c) だけを書き換える。repo の lift 出力は変えない。
# 使い方: python3 probe_976.py <lift_dir>   (既定 tools/flelift/work/boot/lift)
# 出力: [p976a90] (入口の global 0x976410・0x141d6b8・0x141d6c0)・[p976b60] (rcx・rdx)・[p410320] (rcx・rdx)。
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIFT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'boot', 'lift')
HOOKS = {
    'f_976a90': '  fprintf(stderr, "[p976a90] mem976410=0x%llx mem141d6b8=0x%llx mem141d6c0=0x%llx\\n", '
                '(unsigned long long)LD64(0x976410ULL), (unsigned long long)LD64(0x141d6b8ULL), (unsigned long long)LD64(0x141d6c0ULL));\n',
    'f_976b60': '  fprintf(stderr, "[p976b60] rcx=0x%llx rdx=0x%llx\\n", (unsigned long long)R[1], (unsigned long long)R[2]);\n',
    'f_410320': '  fprintf(stderr, "[p410320] rcx=0x%llx rdx=0x%llx\\n", (unsigned long long)R[1], (unsigned long long)R[2]);\n',
}


def main():
    n = {k: 0 for k in HOOKS}
    for path in sorted(glob.glob(os.path.join(LIFT, 'fle_lifted_s*.c'))):
        src = open(path).read()
        changed = False
        for name, ins in HOOKS.items():
            m = re.compile(r'^void %s\(void\) \{\n' % name, re.M).search(src)
            if not m:
                continue
            src = src[:m.end()] + ins + src[m.end():]
            n[name] += 1
            changed = True
        if changed:
            src = '#include <stdio.h>\n' + src
            open(path, 'w').write(src)
    for k, v in n.items():
        print(k, 'probed', v)
    if any(v != 1 for v in n.values()):
        sys.exit('expected exactly 1 definition per name, got %s' % n)


if __name__ == '__main__':
    main()
