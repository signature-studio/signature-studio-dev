#!/usr/bin/env python3
"""comis_flags.py ([PLG-F3-34] #3242) の回帰テスト。
  (a) IR 変換: slot を持つ関数の非 VEX comis は反映 (呼出し消滅 + fcmp/store)、slot の無い関数・VEX は残す。
  (b) 述語の照合: pass が出す fcmp (ult / ueq / uno) の真偽を、ホスト x86-64 の comiss/ucomiss/comisd/ucomisd の
      実機 flag と全入力で突き合わせる (独立算法の検算)。ネガティブコントロール: 述語を 1 つ壊すと FAIL する。
usage: python3 tools/plugins/lift/passes/test_comis_flags.py
"""
import math, os, platform, shutil, struct, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import comis_flags  # noqa: E402

SLOT_FN = """define i64 @function_1(i64 %arg1) local_unnamed_addr {
entry:
  %cf.0.reg2mem = alloca i1
  %zf.0.reg2mem = alloca i1
  %x = call i128 @__asm_movaps(i128 %1)
  call void @__asm_comiss(i128 %x, i128 %y)
  %cf.0.reload = load i1, ptr %cf.0.reg2mem
  %zf.0.reload = load i1, ptr %zf.0.reg2mem
  %r = or i1 %cf.0.reload, %zf.0.reload
  ret i64 0
}
"""
NOSLOT_FN = """define i64 @function_2(i64 %arg1) local_unnamed_addr {
entry:
  %15 = xor i1 0, 0
  call void @__asm_ucomisd(i128 %a, i128 %b)
  %r = or i1 %15, %15
  ret i64 0
}
"""
VEX_FN = """define i64 @function_3(i64 %arg1) local_unnamed_addr {
entry:
  %cf.0.reg2mem = alloca i1
  %zf.0.reg2mem = alloca i1
  call void @__asm_vcomisd(i128 %a, i64 %b)
  ret i64 0
}
"""
DECLS = """declare void @__asm_comiss(i128, i128) local_unnamed_addr
declare void @__asm_ucomisd(i128, i128) local_unnamed_addr
declare void @__asm_vcomisd(i128, i64) local_unnamed_addr
"""


def run_pass(text):
    d = tempfile.mkdtemp()
    try:
        src, dst = os.path.join(d, 'in.ll'), os.path.join(d, 'out.ll')
        with open(src, 'w') as f:
            f.write(text)
        sys.argv = ['comis_flags.py', src, dst]
        comis_flags.main()
        with open(dst) as f:
            return f.read()
    finally:
        shutil.rmtree(d)


class TestRewrite(unittest.TestCase):
    def test_slot_function_reflects_and_removes_call(self):
        out = run_pass(DECLS + SLOT_FN)
        self.assertNotIn('call void @__asm_comiss(', out)
        self.assertIn('fcmp ult float', out)
        self.assertIn('fcmp ueq float', out)
        self.assertIn('store i1 %cfl', out)
        self.assertNotIn('declare void @__asm_comiss(', out)

    def test_no_slot_function_keeps_call_and_decl(self):
        out = run_pass(DECLS + NOSLOT_FN)
        self.assertIn('call void @__asm_ucomisd(i128 %a, i128 %b)', out)
        self.assertIn('declare void @__asm_ucomisd(', out)
        self.assertNotIn('fcmp', out)

    def test_vex_is_out_of_scope(self):
        out = run_pass(DECLS + VEX_FN)
        self.assertIn('call void @__asm_vcomisd(i128 %a, i64 %b)', out)
        self.assertIn('declare void @__asm_vcomisd(', out)


# --- (b) 述語の照合 (host x86-64 の実機 flag と pass の fcmp 式) ---

WORDS32 = [0x00000000, 0x80000000, 0x3F800000, 0xBF800000, 0x40000000, 0x7F800000, 0xFF800000,
           0x7FC00000, 0x7F800001, 0x00000001, 0x3F000000]
WORDS64 = [0x0000000000000000, 0x8000000000000000, 0x3FF0000000000000, 0xBFF0000000000000,
           0x4000000000000000, 0x7FF0000000000000, 0xFFF0000000000000, 0x7FF8000000000000,
           0x7FF0000000000001, 0x0000000000000001, 0x3FE0000000000000]

C_SRC = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
int main(void) {
  unsigned kind; unsigned long long a, b;
  while (scanf("%u %llx %llx", &kind, &a, &b) == 3) {
    unsigned char cf, zf, pf;
    if (kind < 2) {
      float fa, fb; uint32_t ua = (uint32_t)a, ub = (uint32_t)b; memcpy(&fa, &ua, 4); memcpy(&fb, &ub, 4);
      if (kind == 0) __asm__ volatile("comiss %[b], %[a]\n\tsetb %[cf]\n\tsete %[zf]\n\tsetp %[pf]\n\t"
          : [cf]"=q"(cf), [zf]"=q"(zf), [pf]"=q"(pf) : [a]"x"(fa), [b]"x"(fb) : "cc");
      else __asm__ volatile("ucomiss %[b], %[a]\n\tsetb %[cf]\n\tsete %[zf]\n\tsetp %[pf]\n\t"
          : [cf]"=q"(cf), [zf]"=q"(zf), [pf]"=q"(pf) : [a]"x"(fa), [b]"x"(fb) : "cc");
    } else {
      double da, db; memcpy(&da, &a, 8); memcpy(&db, &b, 8);
      if (kind == 2) __asm__ volatile("comisd %[b], %[a]\n\tsetb %[cf]\n\tsete %[zf]\n\tsetp %[pf]\n\t"
          : [cf]"=q"(cf), [zf]"=q"(zf), [pf]"=q"(pf) : [a]"x"(da), [b]"x"(db) : "cc");
      else __asm__ volatile("ucomisd %[b], %[a]\n\tsetb %[cf]\n\tsete %[zf]\n\tsetp %[pf]\n\t"
          : [cf]"=q"(cf), [zf]"=q"(zf), [pf]"=q"(pf) : [a]"x"(da), [b]"x"(db) : "cc");
    }
    printf("%d %d %d\n", cf & 1, zf & 1, pf & 1);
  }
  return 0;
}
'''


def flags_formula(fa, fb, cf_pred, zf_pred, pf_pred):
    """LLVM fcmp 述語 (ult/ueq/uno/olt/oeq) の真偽。 NaN は Python の比較と別に明示する。"""
    nan = math.isnan(fa) or math.isnan(fb)
    tbl = {
        'ult': (fa < fb) or nan, 'ueq': (fa == fb) or nan, 'uno': nan,
        'olt': (fa < fb), 'oeq': (fa == fb),
    }
    return (int(tbl[cf_pred]), int(tbl[zf_pred]), int(tbl[pf_pred]))


def unpack(kind, bits):
    if kind in (0, 1):
        return struct.unpack('<f', struct.pack('<I', bits))[0]
    return struct.unpack('<d', struct.pack('<Q', bits))[0]


def native_check(preds=('ult', 'ueq', 'uno')):
    """返り値: (総数, 不一致数)。 gcc が無い・x86-64 でない時は None。"""
    if platform.machine() not in ('x86_64', 'AMD64') or not shutil.which('gcc'):
        return None
    d = tempfile.mkdtemp()
    try:
        c, exe = os.path.join(d, 'c.c'), os.path.join(d, 'comis')
        with open(c, 'w') as f:
            f.write(C_SRC)
        subprocess.run(['gcc', '-O0', '-o', exe, c], check=True)
        cases = []
        for kind in range(4):
            words = WORDS32 if kind < 2 else WORDS64
            for a in words:
                for b in words:
                    cases.append((kind, a, b))
        inp = ''.join('%d %x %x\n' % cse for cse in cases)
        got = subprocess.run([exe], input=inp, capture_output=True, text=True, check=True).stdout.split('\n')
        assert len([x for x in got if x]) == len(cases), 'native 出力の行数が入力と一致しない'
        print('[native] cases=%d preds=%s' % (len(cases), '/'.join(preds)), file=sys.stderr)
        bad = 0
        for (kind, a, b), line in zip(cases, got):
            want = tuple(int(x) for x in line.split())
            fa, fb = unpack(kind, a), unpack(kind, b)
            if flags_formula(fa, fb, *preds) != want:
                bad += 1
        return len(cases), bad
    finally:
        shutil.rmtree(d)


class TestFlagSemantics(unittest.TestCase):
    def test_native_matches_pass_predicates(self):
        r = native_check()
        if r is None:
            self.skipTest('x86-64 の gcc が無い')
        total, bad = r
        self.assertEqual(bad, 0, '不一致 %d / %d' % (bad, total))

    def test_negative_control_ordered_cf_fails(self):
        r = native_check(preds=('olt', 'ueq', 'uno'))
        if r is None:
            self.skipTest('x86-64 の gcc が無い')
        total, bad = r
        self.assertGreater(bad, 0, 'NC: ordered 述語 (olt) は NaN で CF が合わないはず (実測 %d / %d)' % (bad, total))


if __name__ == '__main__':
    unittest.main(verbosity=2)
