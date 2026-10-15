#!/usr/bin/env python3
"""ir5_patch.py の lower_asm_store が movntps を store へ復元すること (#1581 / 2e2f1dfe) の回帰テスト。
  python3 test_movntps_store.py [ir5_patch.py のパス]   → 既定は同じ dir の ir5_patch.py
  修復前の版 (例: 0d9b5385 の ir5_patch.py) を渡すと movntps の call が残るため不合格になる (ネガティブコントロール)。
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'ir5_patch.py')
BODY = "\n".join([
    "  %a = load i128, ptr %p",
    "  call void @__asm_movntps(i128 %a, i128 %v)",
    "  call void @__asm_movups.2(i128 %a, i128 %v)",
    "  call void @__asm_pxor(i128 %a, i128 %v)",
])


def main():
    spec = importlib.util.spec_from_file_location('ir5_patch', PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    blocks, n = m.lower_asm_store({'f': BODY})
    out = blocks['f'].split('\n')
    ok = (n == 2
          and out.count('  store i128 %v, ptr %p') == 2
          and not any('@__asm_movntps(' in ln for ln in out)
          and '  call void @__asm_pxor(i128 %a, i128 %v)' in out)
    print('[test_movntps_store] %s n=%d (%s)' % ('PASS' if ok else 'FAIL', n, PATH))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
