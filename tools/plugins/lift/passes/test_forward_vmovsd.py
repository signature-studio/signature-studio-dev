#!/usr/bin/env python3
"""ir5_patch.py の forward_vmovsd_store (#2017) の回帰テスト。
store 形 __asm_vmovsd(i64 %old, i128 %v) の後で、支配される読み戻し (%old) だけを
trunc i128 %v to i64 へ置換し、支配されない use は残すこと。 宛先 alloca に store があれば何もしないこと。
  python3 test_forward_vmovsd.py [ir5_patch.py のパス]   → 既定は同じ dir の ir5_patch.py
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'ir5_patch.py')
BODY = "\n".join([
    "define i64 @f(i128 %v) {",
    "entry:",
    "  %1 = alloca i64",
    "  %10 = load i64, ptr %1",
    "  %c = icmp eq i64 %10, 0",
    "  br i1 %c, label %a, label %b",
    "a:",
    "  call void @__asm_vmovsd(i64 %10, i128 %v), !insn.addr !5",
    "  %x = and i64 %10, 1",
    "  ret i64 %x",
    "b:",
    "  %y = and i64 %10, 2",
    "  ret i64 %y",
    "}",
])
STORED = BODY.replace("  %1 = alloca i64\n", "  %1 = alloca i64\n  store i64 5, ptr %1\n")


def run(mod, body):
    lines = body.split("\n")
    n = mod._forward_vmovsd_fn(lines)
    return n, "\n".join(lines).split("\n")


def main():
    spec = importlib.util.spec_from_file_location('ir5_patch', PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    n, out = run(m, BODY)
    ok = (n == 1
          and "  %vmovsd_fwd_10 = trunc i128 %v to i64, !insn.addr !5" in out
          and "  %x = and i64 %vmovsd_fwd_10, 1" in out
          and "  %y = and i64 %10, 2" in out
          and "  %c = icmp eq i64 %10, 0" in out
          and "  %10 = load i64, ptr %1" in out
          and not any("@__asm_vmovsd(" in ln for ln in out))
    n2, out2 = run(m, STORED)
    ok2 = n2 == 0 and out2 == STORED.split("\n")
    print('[test_forward_vmovsd] %s n=%d / negative(store あり) %s n=%d (%s)'
          % ('PASS' if ok else 'FAIL', n, 'PASS' if ok2 else 'FAIL', n2, PATH))
    return 0 if ok and ok2 else 1


if __name__ == '__main__':
    sys.exit(main())
