"""simdtest.py — 生成 helper を「実機命令 (inline asm) vs wasm」で bit 突合する単体テスト (CAB-54)。

  python3 -m liftlib simd-test [--n 300] [--mnemonics a,b,..] [--from-ll x.ll ...] [--out DIR]

各 (mnemonic, 署名) について:
  1. kernels.lookup が返す Spec.asm を使い, x86-64 ネイティブで本物の命令を実行 (gcc inline asm)
  2. 生成 C (正規名) を emcc で wasm 化し node で実行
  3. 同一乱数入力で出力を bit 比較 (NaN 入力は除外; 出力 NaN のみの差は "nan-only" として別計上)
近似命令 (rcpps 等) は相対誤差 < 1.6*2^-12 で判定する (Intel 規格上限 1.5*2^-12 + 余裕)。
"""
import os
import random
import re
import struct
import subprocess
import sys

from . import gen, kernels
from .. import env

HERE = os.path.dirname(os.path.abspath(__file__))

F32_POOL = [0.0, -0.0, 1.0, -1.0, 0.5, 2.0, 3.0, -2.5, 1e-3, 123.456, -7.25, 65504.0, 1e10, -1e10, 3.4e38, -3.4e38,
            1.17549435e-38, 1e-40, -1e-40, 2147483520.0, 2147483648.0, -2147483648.0, 4294967296.0, 0.1, 0.3, 255.5, -255.5, 1e-7,
            float("inf"), float("-inf")]
F64_POOL = [0.0, -0.0, 1.0, -1.0, 0.5, 2.0, 3.0, -2.5, 1e-3, 123.456, -7.25, 1e100, -1e100, 1.7e308, -1.7e308,
            2.2250738585072014e-308, 5e-324, -5e-324, 2147483647.5, 2147483648.0, -2147483648.5, 9.3e18, -9.3e18, 1e19, 0.1, 0.3,
            1e-20, float("inf"), float("-inf")]


def domain(base):
    b = base[1:] if base.startswith("v") and len(base) > 2 else base
    if b in ("cvtps2pd", "cvtps2dq", "cvttps2dq", "cvtss2sd", "cvtss2si", "cvttss2si", "movshdup", "movsldup",
             "rcpps", "rsqrtps", "rcpss", "rsqrtss", "movmskps", "roundss", "roundps"):
        return "f32"
    if b in ("cvtpd2ps", "cvtpd2dq", "cvttpd2dq", "cvtsd2ss", "cvtsd2si", "cvttsd2si", "movmskpd", "movddup", "roundsd", "roundpd"):
        return "f64"
    if re.search(r"(ps|ss)$", b) and not b.startswith("ps") and not b.startswith("p"):
        return "f32"
    if re.search(r"(pd|sd)$", b) and not b.startswith("p") and not b.startswith("movlp") :
        return "f64"
    if b.startswith("fm") or b.startswith("fnm"):
        return "f32" if b.endswith(("ss", "ps")) else "f64"
    if b in ("movlps", "movhps", "movlpd", "movhpd", "movlhps", "movhlps", "unpcklps", "unpckhps", "unpcklpd", "unpckhpd",
             "shufps", "shufpd", "movss", "movsd", "movd", "movq", "movaps", "movapd", "movups", "movupd", "movdqa", "movdqu", "broadcastss"):
        return "raw"
    return "int"


def gen_in16(rng, dom):
    if dom == "f32":
        return b"".join(struct.pack("<f", rng.choice(F32_POOL) if rng.random() < 0.6 else rng.uniform(-1000, 1000) * 10 ** rng.uniform(-3, 3)) for _ in range(4))
    if dom == "f64":
        return b"".join(struct.pack("<d", rng.choice(F64_POOL) if rng.random() < 0.6 else rng.uniform(-1000, 1000) * 10 ** rng.uniform(-3, 3)) for _ in range(2))
    return bytes(rng.getrandbits(8) for _ in range(16))


class Form:
    def __init__(self, base, ret, args, spec, imm):
        self.base, self.ret, self.args, self.spec, self.imm = base, ret, args, spec, imm
        self.cname = "__asm_%s__%s%s" % (base, ret, "".join(args))


def enumerate_forms(bases=None, from_decls=None):
    """検証対象の (base, ret, args) を列挙。from_decls があればその宣言のみ。"""
    forms, seen = [], set()
    if from_decls is not None:
        cand = [(d.base, d.ret, d.args) for d in from_decls]
    else:
        cand = []
        for b in bases:
            for r, a in gen._REP_SIGS:
                cand.append((b, r, a))
    for (b, r, a) in cand:
        key = (b, r, tuple(a))
        if key in seen:
            continue
        seen.add(key)
        if "y" in a or r == "y" or "?" in a or r == "?":
            continue
        sp = kernels.lookup(b, r, a)
        if sp is None or sp.asm is None:
            continue
        for imm in (sp.imms if sp.imms else [None]):
            forms.append(Form(b, r, list(a), sp, imm))
    return forms


def native_src(forms):
    out = ['#include <stdint.h>', '#include <stdio.h>', '#include <stdlib.h>', '#include <string.h>',
           'typedef unsigned char u8; typedef uint32_t u32; typedef uint64_t u64;',
           'typedef unsigned char v128 __attribute__((vector_size(16)));', '']
    for k, f in enumerate(forms):
        sp = f.spec
        body = ['static void n_%d(const u8* in, u8* out) {' % k, '  v128 r; memset(&r, 0, 16); u32 rr32 = 0; u64 rr64 = 0; (void)r; (void)rr32; (void)rr64;']
        for i, t in enumerate(f.args):
            if t == "x":
                body.append('  v128 p%d; memcpy(&p%d, in + %d, 16);' % (i, i, 16 * i))
            elif t == "d":
                body.append('  u32 p%d; memcpy(&p%d, in + %d, 4);' % (i, i, 16 * i))
            elif t == "q":
                body.append('  u64 p%d; memcpy(&p%d, in + %d, 8);' % (i, i, 16 * i))
        outs, ins = [], []
        for tok in sp.ops.split():
            nm, c = tok.split(":", 1)
            var = {"rr": "rr32" if f.ret == "d" else "rr64"}.get(nm, nm)
            if c[0] in "+=":
                outs.append('[%s] "%sx"(%s)' % (nm, c[0], var) if c[1:] == "x" else '[%s] "%sr"(%s)' % (nm, c[0], var))
            else:
                ins.append('[%s] "%s"(%s)' % (nm, c, var))
        asm = sp.asm.replace("$$IMM", "$%d" % (f.imm if f.imm is not None else 0))
        body.append('  __asm__ volatile("%s" : %s : %s);' % (asm, ", ".join(outs), ", ".join(ins)))
        res = sp.result
        if res in ("rr",):
            if f.ret == "d":
                body.append('  memset(out, 0, 16); memcpy(out, &rr32, 4);')
            else:
                body.append('  memset(out, 0, 16); memcpy(out, &rr64, 8);')
        else:
            body.append('  memcpy(out, &%s, 16);' % res)
        body.append('}')
        out += body
    out.append('typedef void (*fn_t)(const u8*, u8*);')
    out.append('static fn_t tab[] = {' + ", ".join("n_%d" % k for k in range(len(forms))) + '};')
    out.append('''int main(int argc, char** argv) {
  FILE* fi = fopen(argv[1], "r"); FILE* fo = fopen(argv[2], "w");
  char line[8192];
  while (fgets(line, sizeof line, fi)) {
    int k; char hex[4096]; if (sscanf(line, "%d %4095s", &k, hex) != 2) continue;
    u8 in[64]; memset(in, 0, sizeof in);
    for (int i = 0; hex[2*i] && hex[2*i+1]; i++) { unsigned v; sscanf(hex + 2*i, "%2x", &v); in[i] = v; }
    u8 o[16]; tab[k](in, o);
    for (int i = 0; i < 16; i++) fprintf(fo, "%02x", o[i]);
    fprintf(fo, "\\n");
  }
  return 0;
}''')
    return "\n".join(out)


def wasm_src(forms):
    decls = {}
    for f in forms:
        decls[f.cname] = f
    # 正規名で helper を生成
    class D:
        pass
    ds = []
    for nm, f in decls.items():
        d = gen.Decl("__asm_%s" % f.base, {"x": "i128", "q": "i64", "d": "i32", "b": "i8", "v": "void"}[f.ret],
                     [{"x": "i128", "q": "i64", "d": "i32", "b": "i8"}[t] for t in f.args])
        ds.append(d)
    c, rep = gen.emit_c(ds, use_names="canon")
    out = [c, '#include <emscripten.h>']
    for k, f in enumerate(forms):
        body = ['EMSCRIPTEN_KEEPALIVE void w_%d(const u8* in, u8* out) {' % k]
        argl = []
        for i, t in enumerate(f.args):
            if t == "x":
                body.append('  u128 a%d; memcpy(&a%d, in + %d, 16);' % (i, i, 16 * i))
                argl.append("a%d" % i)
            elif t == "d":
                body.append('  u32 a%d; memcpy(&a%d, in + %d, 4);' % (i, i, 16 * i))
                argl.append("a%d" % i)
            elif t == "q":
                body.append('  u64 a%d; memcpy(&a%d, in + %d, 8);' % (i, i, 16 * i))
                argl.append("a%d" % i)
            elif t == "b":
                argl.append(str(f.imm if f.imm is not None else 0))
        call = "%s(%s)" % (f.cname, ", ".join(argl))
        body.append('  memset(out, 0, 16);')
        if f.ret == "x":
            body.append('  u128 r = %s; memcpy(out, &r, 16);' % call)
        elif f.ret == "d":
            body.append('  u32 r = %s; memcpy(out, &r, 4);' % call)
        elif f.ret == "q":
            body.append('  u64 r = %s; memcpy(out, &r, 8);' % call)
        body.append('}')
        out += body
    return "\n".join(out)


NODE_RUNNER = r'''
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(process.argv[2])();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const inp = M._malloc(256), outp = M._malloc(64);
const res = [];
for (const ln of lines) {
  const [ks, hex] = ln.split(' ');
  const k = parseInt(ks);
  M.HEAPU8.fill(0, inp, inp + 256);
  for (let i = 0; i < hex.length / 2; i++) M.HEAPU8[inp + i] = parseInt(hex.substr(2 * i, 2), 16);
  M['_w_' + k](inp, outp);
  let s = '';
  for (let i = 0; i < 16; i++) s += M.HEAPU8[outp + i].toString(16).padStart(2, '0');
  res.push(s);
}
fs.writeFileSync(process.argv[4], res.join('\n') + '\n');
'''


def _nan32(b4):
    x = struct.unpack("<I", b4)[0]
    return (x & 0x7F800000) == 0x7F800000 and (x & 0x7FFFFF) != 0


def _nan64(b8):
    x = struct.unpack("<Q", b8)[0]
    return (x & 0x7FF0000000000000) == 0x7FF0000000000000 and (x & 0xFFFFFFFFFFFFF) != 0


def compare_form(f, a, b):
    """a=native hex, b=wasm hex -> 'exact' | 'nan-only' | 'approx-ok' | 'mismatch'"""
    A, B = bytes.fromhex(a), bytes.fromhex(b)
    if A == B:
        return "exact"
    if not f.spec.exact:
        ok = True
        for i in range(4):
            x = struct.unpack("<f", A[4 * i:4 * i + 4])[0]
            y = struct.unpack("<f", B[4 * i:4 * i + 4])[0]
            if x != x and y != y:
                continue
            if x == y:
                continue
            if x in (float("inf"), float("-inf")) or y in (float("inf"), float("-inf")):
                ok = ok and (x == y)
                continue
            if abs(x - y) > 1.6 * 2 ** -12 * max(abs(x), abs(y)) + 1e-38:
                ok = False
        return "approx-ok" if ok else "mismatch"
    # NaN のみの差: 4B/8B レーン単位で両方 NaN なら nan-only
    for w, isnan in ((4, _nan32), (8, _nan64)):
        okl = True
        for i in range(0, 16, w):
            if A[i:i + w] != B[i:i + w] and not (isnan(A[i:i + w]) and isnan(B[i:i + w])):
                okl = False
        if okl:
            return "nan-only"
    return "mismatch"


def run(bases=None, from_decls=None, n=200, out_dir=None, seed=1, verbose=True):
    out_dir = out_dir or os.path.join(os.getcwd(), "work", "simdtest")
    os.makedirs(out_dir, exist_ok=True)
    forms = enumerate_forms(bases, from_decls)
    rng = random.Random(seed)
    with open(os.path.join(out_dir, "n.c"), "w") as fh:
        fh.write(native_src(forms))
    with open(os.path.join(out_dir, "w.c"), "w") as fh:
        fh.write(wasm_src(forms))
    with open(os.path.join(out_dir, "run.mjs"), "w") as fh:
        fh.write(NODE_RUNNER)
    # vectors
    vec = []
    for k, f in enumerate(forms):
        dom = domain(f.base)
        for _ in range(n):
            blob = b""
            for i, t in enumerate(f.args):
                if t == "x":
                    blob += gen_in16(rng, dom)
                elif t == "d":
                    if dom == "f32":
                        blob += struct.pack("<f", rng.choice(F32_POOL) if rng.random() < 0.6 else rng.uniform(-100, 100)) + bytes(12)
                    else:
                        blob += struct.pack("<I", rng.getrandbits(32) if dom != "int" or f.base.startswith("cvtsi2") is False else rng.choice([0, 1, 0xFFFFFFFF, 0x80000000, 12345, rng.getrandbits(32)])) + bytes(12)
                elif t == "q":
                    if dom == "f64":
                        blob += struct.pack("<d", rng.choice(F64_POOL) if rng.random() < 0.6 else rng.uniform(-100, 100)) + bytes(8)
                    else:
                        blob += struct.pack("<Q", rng.getrandbits(64)) + bytes(8)
                elif t == "b":
                    blob += b""
                if t != "b" and len(blob) % 16:
                    blob += bytes(16 - len(blob) % 16)
            vec.append((k, blob))
    with open(os.path.join(out_dir, "vec.txt"), "w") as fh:
        for k, blob in vec:
            fh.write("%d %s\n" % (k, blob.hex()))
    # build
    r = subprocess.run(["gcc", "-O1", "-mavx2", "-mfma", "-o", os.path.join(out_dir, "n"), os.path.join(out_dir, "n.c")],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("native build failed:\n" + r.stderr[:3000])
    emcc = ["emcc", "-w", "-O1", "-ffp-contract=off", "-frounding-math", "-fno-fast-math", "-I", HERE,
            os.path.join(out_dir, "w.c"), "-sMODULARIZE=1", "-sENVIRONMENT=node", "-sALLOW_MEMORY_GROWTH=1",
            "-sEXPORTED_RUNTIME_METHODS=HEAPU8", "-sEXPORTED_FUNCTIONS=_malloc,_free," + ",".join("_w_%d" % k for k in range(len(forms))),
            "--no-entry", "-o", os.path.join(out_dir, "w.js")]
    r = env.run(emcc, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("emcc failed:\n" + r.stderr[:3000])
    os.replace(os.path.join(out_dir, "w.js"), os.path.join(out_dir, "w.cjs"))
    subprocess.run([os.path.join(out_dir, "n"), os.path.join(out_dir, "vec.txt"), os.path.join(out_dir, "out_native.txt")], check=True)
    r = env.run(["node", os.path.join(out_dir, "run.mjs"), os.path.join(out_dir, "w.cjs"), os.path.join(out_dir, "vec.txt"),
                        os.path.join(out_dir, "out_wasm.txt")], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("node failed:\n" + r.stderr[:3000])
    nat = open(os.path.join(out_dir, "out_native.txt")).read().split()
    was = open(os.path.join(out_dir, "out_wasm.txt")).read().split()
    stat = {}
    for (k, blob), a, b in zip(vec, nat, was):
        f = forms[k]
        key = (f.base, f.ret, "".join(f.args), f.imm)
        st = stat.setdefault(key, dict(exact=0, nan_only=0, approx_ok=0, mismatch=0, ex=None, form=f))
        c = compare_form(f, a, b)
        st[c.replace("-", "_")] += 1
        if c == "mismatch" and st["ex"] is None:
            st["ex"] = (blob.hex(), a, b)
    return forms, stat


def summarize(stat):
    by = {}
    for (base, ret, args, imm), s in stat.items():
        d = by.setdefault((base, ret, args), dict(exact=0, nan_only=0, approx_ok=0, mismatch=0, ex=None))
        for k in ("exact", "nan_only", "approx_ok", "mismatch"):
            d[k] += s[k]
        if s["ex"] and d["ex"] is None:
            d["ex"] = s["ex"]
    return by
