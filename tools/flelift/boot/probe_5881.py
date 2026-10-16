#!/usr/bin/env python3
# probe_5881.py — #5881 [WIN-65]: (b) f_410320 の rax の実行時値と (c) f_6a7b70 の store のうち受け手 slot を覆うものを記録する probe。
# 生成 C (work/boot/lift/*.c) だけを書き換える。repo の lift 出力は変えない。
# 使い方: python3 probe_5881.py <lift_dir>   (既定 tools/flelift/work/boot/lift)
# 出力: [p410320] rax・rcx・rdx (mov rax, rcx の直後)。
#       [p6a7b70] slot・store の pc・書込み先 a・幅 n・entry の dst (R[1])・cnt (R[8])。
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIFT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'boot', 'lift')

HELPER = (
    '#include <stdio.h>\n'
    'static unsigned long long p6_d0, p6_c0;\n'
    'static void fle_p6_5881(unsigned long long a, unsigned n, unsigned pc) {\n'
    '  unsigned long long s[2] = {0x5ac308ULL, 0x976410ULL};\n'
    '  for (int i = 0; i < 2; i++)\n'
    '    if (a < s[i] + 8ULL && a + n > s[i])\n'
    '      fprintf(stderr, "[p6a7b70] slot=0x%llx pc=0x%x a=0x%llx n=%u dst=0x%llx cnt=0x%llx\\n", s[i], pc, a, n, p6_d0, p6_c0);\n'
    '}\n'
)
ENTRY_410320 = '  fprintf(stderr, "[p410320] rax=0x%llx rcx=0x%llx rdx=0x%llx\\n", (unsigned long long)R[0], (unsigned long long)R[1], (unsigned long long)R[2]);\n'
ENTRY_6A7B70 = '  p6_d0 = R[1]; p6_c0 = R[8];\n'


def patch_func(src, name, fn):
    m = re.compile(r'^void %s\(void\) \{\n' % name, re.M).search(src)
    if not m:
        return src, False
    end = src.index('\n}\n', m.end()) + 3
    return src[:m.start()] + fn(src[m.start():end]) + src[end:], True


def f410320(body):
    anchor = '  R[0] = (uint64_t)(R[1]);\n'
    assert body.count(anchor) == 1
    return body.replace(anchor, anchor + ENTRY_410320)


def f6a7b70(body):
    body = body.replace('L_6a7b70:;\n', 'L_6a7b70:;\n' + ENTRY_6A7B70, 1)
    # 各 store の直前で書込み先アドレスを記録する。pc 欄は store 番号 (k) を入れる。
    cnt = [0]

    def pre16(m):
        cnt[0] += 1
        return '  fle_p6_5881((uint64_t)(%s), 16, %d);\n' % (m.group(1), cnt[0]) + m.group(0)

    def pre4(m):
        cnt[0] += 1
        return '  fle_p6_5881((uint64_t)(R[1]), 4, %d);\n' % cnt[0] + m.group(0)

    body, k16 = re.subn(r'^  STX\((.*?), X\[0\]\);\n', pre16, body, flags=re.M)
    body, k4 = re.subn(r'^  ST32\(\(R\[1\]\), \(R\[2\] & 0xffffffff\)\);\n', pre4, body, flags=re.M)
    assert k16 >= 1 and k4 >= 1, (k16, k4)
    return body


def main():
    n = {'f_410320': 0, 'f_6a7b70': 0}
    for path in sorted(glob.glob(os.path.join(LIFT, 'fle_lifted_s*.c'))):
        src = open(path).read()
        changed = False
        for name, fn in (('f_410320', f410320), ('f_6a7b70', f6a7b70)):
            src2, ok = patch_func(src, name, fn)
            if ok:
                src = src2
                n[name] += 1
                changed = True
        if changed:
            src = HELPER + src
            open(path, 'w').write(src)
    for k, v in n.items():
        print(k, 'probed', v)
    if any(v != 1 for v in n.values()):
        sys.exit('expected exactly 1 definition per name, got %s' % n)


if __name__ == '__main__':
    main()
