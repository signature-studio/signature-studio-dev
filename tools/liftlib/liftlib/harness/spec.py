"""spec.py — 差分ハーネスの「context spec」(JSON) から乱数シナリオ (テキスト) を生成する。

spec 例 (FA gain; 詳細は tools/liftlib/specs/*.json):
  {
   "name": "fa_gain_process", "func": "0x180afe090", "wasm_func": "function_180afe090",
   "scenarios": 400, "steps": 1, "seed": 1,
   "vars": [ {"name": "n", "gen": {"mix": [[0.5, {"choice": [0,1,2,3,7,16,31,64]}], [0.5, {"int": [1,128]}]]}}, ...,
             {"name": "prev", "expr": "tgt if kind < .2 else ..."} ],
   "args": [ {"ptr": "this"}, {"ptr": "ctx"} ],               # MS x64 のスロット順; {"int": expr} {"f32": expr} {"f64": expr}
   "buffers": { "this": {"size": 256, "fields": [ {"off": "0x90", "ptr": "P"}, {"off": "0xb0", "type": "u8", "gen": {"var": "first"}} ]},
                "L": {"size": "4*n+8", "fill": {"type": "f32", "count": "n", "gen": {"sample": 1}}, "every_step": true} }
  }
gen の種類: 数値 / {"var"} / {"choice":[..]} / {"int":[lo,hi]} / {"unif":[lo,hi]} / {"loguni":[lo,hi]} (符号ランダム)
            / {"sample":1} (音声サンプル風: 0, ±非正規, ±10^U(-4,4)) / {"mix":[[w,gen],..]} / {"expr":"python 式"} / {"bits32":1}
フィールド: {"off","type"(f32,f64,u8,u16,u32,u64,i32),"gen","every_step"} | {"off","ptr":buf,"poff":0,"every_step"}
サイズ/count は式 (vars 参照)。buffers はスレッド間で共有される状態 (steps>1 では every_step 以外のフィールドは保持)。
"""
import math
import random
import struct


def _num(x):
    if isinstance(x, str):
        return int(x, 0)
    return int(x)


class Ctx:
    def __init__(self, rng):
        self.rng = rng
        self.vars = {}

    def env(self):
        rng = self.rng

        def f32(x):
            return struct.unpack("<f", struct.pack("<f", x))[0]

        def bits(x):
            return struct.unpack("<I", struct.pack("<f", x))[0]

        def fromb(b):
            return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]
        e = dict(math=math, rnd=lambda lo, hi: rng.uniform(lo, hi), choice=lambda l: rng.choice(l), f32=f32, bits=bits,
                 fromb=fromb, int=int, abs=abs, min=min, max=max, rint=lambda lo, hi: rng.randint(lo, hi))
        e.update(self.vars)
        return e

    def ev(self, x):
        if isinstance(x, (int, float)):
            return x
        if isinstance(x, str):
            try:
                return int(x, 0)
            except ValueError:
                return eval(x, {"__builtins__": {}}, self.env())
        raise ValueError(x)

    def gen(self, g, typ=None):
        r = self.rng
        if isinstance(g, (int, float)):
            return g
        if isinstance(g, str):
            return self.ev(g)
        if "var" in g:
            return self.vars[g["var"]]
        if "choice" in g:
            return r.choice(g["choice"])
        if "int" in g:
            return r.randint(g["int"][0], g["int"][1])
        if "unif" in g:
            return r.uniform(g["unif"][0], g["unif"][1])
        if "loguni" in g:
            lo, hi = g["loguni"]
            return r.choice([-1, 1]) * 10 ** r.uniform(lo, hi)
        if "sample" in g:
            x = r.random()
            if x < 0.05:
                return 0.0
            if x < 0.10:
                return struct.unpack("<f", struct.pack("<I", r.randrange(1, 0x7FFFFF)))[0]
            if x < 0.15:
                return -struct.unpack("<f", struct.pack("<I", r.randrange(1, 0x7FFFFF)))[0]
            return r.choice([-1, 1]) * 10 ** r.uniform(-4, 4)
        if "mix" in g:
            tot = sum(w for w, _ in g["mix"])
            x = r.random() * tot
            for w, gg in g["mix"]:
                x -= w
                if x <= 0:
                    return self.gen(gg, typ)
            return self.gen(g["mix"][-1][1], typ)
        if "expr" in g:
            return self.ev(g["expr"])
        if "bits32" in g:
            return r.getrandbits(32)
        raise ValueError("unknown gen %r" % (g,))


def _pack(typ, v):
    if typ == "f32":
        return struct.pack("<f", float(v))
    if typ == "f64":
        return struct.pack("<d", float(v))
    if typ == "u8":
        return struct.pack("<B", int(v) & 0xFF)
    if typ == "u16":
        return struct.pack("<H", int(v) & 0xFFFF)
    if typ in ("u32", "i32"):
        return struct.pack("<I", int(v) & 0xFFFFFFFF)
    if typ in ("u64", "i64"):
        return struct.pack("<Q", int(v) & 0xFFFFFFFFFFFFFFFF)
    if typ == "bits32":
        return struct.pack("<I", int(v) & 0xFFFFFFFF)
    raise ValueError(typ)


def build(spec, n=None, seed=None):
    """シナリオ文字列を返す (S/B/P/A/C/U/UP/E 行)。"""
    n = n or spec.get("scenarios", 100)
    seed = spec.get("seed", 1) if seed is None else seed
    steps = spec.get("steps", 1)
    out = []
    if spec.get("abi") == "ms_pos":           # LIFTLIB-5: 引数レジスタを位置対応で割り当てる (leaf spec のみ)
        out.append("M pos")
    fixed_seq = spec.get("sequence")          # 明示ステップ列 (vars 上書き) があればシナリオ 0 として固定実行
    nsc = n + (1 if fixed_seq else 0)
    for si in range(nsc):
        rng = random.Random((seed << 20) ^ si)
        ctx = Ctx(rng)
        seq = fixed_seq if (fixed_seq and si == 0) else None
        nst = len(seq) if seq else steps
        out.append("S %d" % si)
        bufstate = {}
        for st in range(nst):
            ctx.vars = {}
            ov = seq[st] if seq else {}
            for v in spec.get("vars", []):
                if v["name"] in ov:
                    val = ov[v["name"]]
                    ctx.vars[v["name"]] = ctx.ev(val) if isinstance(val, str) else val
                elif "expr" in v:
                    ctx.vars[v["name"]] = ctx.ev(v["expr"])
                else:
                    ctx.vars[v["name"]] = ctx.gen(v["gen"])
            ptr_lines = []
            for name, b in spec["buffers"].items():
                if st == 0:
                    bufstate[name] = bytearray(max(int(ctx.ev(b["size"])), 1))
                data = bufstate[name]
                upd = []
                if "fill" in b and (st == 0 or b.get("every_step", True)):
                    f = b["fill"]
                    cnt = int(ctx.ev(f["count"]))
                    tsz = len(_pack(f["type"], 0))
                    for i in range(cnt):
                        data[i * tsz:(i + 1) * tsz] = _pack(f["type"], ctx.gen(f["gen"], f["type"]))
                    upd.append((0, bytes(data[:cnt * tsz])))
                for fd in b.get("fields", []):
                    if st > 0 and not fd.get("every_step", False):
                        continue
                    off = int(ctx.ev(fd["off"]))
                    if "ptr" in fd:
                        ptr_lines.append(("P" if st == 0 else "UP", name, off, fd["ptr"], int(ctx.ev(fd.get("poff", 0)))))
                        continue
                    typ = fd.get("type", "u32")
                    bs = _pack(typ, ctx.gen(fd["gen"], typ))
                    data[off:off + len(bs)] = bs
                    upd.append((off, bs))
                if st == 0:
                    out.append("B %s %d %s" % (name, len(data), bytes(data).hex()))
                else:
                    for (o, bs) in upd:
                        out.append("U %s %d %s" % (name, o, bs.hex()))
            for (op, nm, off, dn, doff) in ptr_lines:
                out.append("%s %s %d %s %d" % (op, nm, off, dn, doff))
            if st == 0:
                for i, a in enumerate(spec["args"]):
                    k = list(a.keys())[0]
                    if k == "ptr":
                        out.append("A %d ptr %s" % (i, a["ptr"]))
                    elif k == "int":
                        out.append("A %d i %x" % (i, int(ctx.ev(a["int"])) & 0xFFFFFFFFFFFFFFFF))
                    elif k == "f32":
                        out.append("A %d f32 %x" % (i, struct.unpack("<I", struct.pack("<f", float(ctx.ev(a["f32"]))))[0]))
                    elif k == "f64":
                        out.append("A %d f64 %x" % (i, struct.unpack("<Q", struct.pack("<d", float(ctx.ev(a["f64"]))))[0]))
            out.append("C")
        out.append("E")
    return "\n".join(out) + "\n"
