#!/usr/bin/env python3
"""fa_cmp.py FN_VA[,FN_VA...] [--n N] [--seed S] [--mod work/fa_route/fa_route.cjs]
Fresh Air SlateCore の関数を native (fa_nat と同じ ottnat 経路) と wasm (fa_route.cjs) で同一入力実行し、xmm0 の bit を比較する。
入力: xmm0 = 乱数 double (fa_nat と同じ seed 規約)、rcx..r9 = 0x400 バイトのヒープ確保ポインタ (native は N.alloc、wasm は _malloc)。
出力: 1 行 JSON。各 VA ごとに {n, match, mismatch, native_err, wasm_err, first}。"""
import sys, os, json, random, struct, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(T, 'ott', 'native'))
import ottnat as N

FA = os.environ.get('FA_CORE', os.path.join(T, 'targets', 'freshair', 'work', 'win', 'Fresh Air', 'C__ProgramData_Slate Digital', 'Fresh Air', 'SlateCore.core_64'))
MOD = os.path.join(T, 'icall', 'work', 'fa_route', 'fa_route.cjs')
# ICALL-51: SlateCore の security cookie (VA) と、UCRT が enc(NULL)=cookie で埋める encoded slot (.data の zero-fill 部)。
COOKIE_VA = 0x18125eaa8
ENC_SLOTS = [0x1813068d0, 0x1813068f8, 0x181306900, 0x181306908, 0x181306910, 0x1813072b0,
             0x1813073f0, 0x1813073f8, 0x181307400, 0x181307408, 0x181307410, 0x181307418]
# ICALL-81 (#2695): 0x180da6e60 は rcx = S の構造体が要る。S+0x10 = A (A+0x199c = 件数、A+0x19a4 を inc する)、
# S+0xb8 = 要素配列 B (要素 stride 0x100138)。件数 0 なら loop を飛ばして出口 (cookie 検査) へ。件数は FA_LOOP_N (既定 0)。
# 他の VA は従来どおり rcx..r9 = 0x400 B の確保のみ (結果を変えないため、初期化は VA ごとの表で切り替える)。
LOOP_VA = 0x180da6e60
LOOP_STRIDE = 0x100138
LOOP_CNT = int(os.environ.get('FA_LOOP_N', '0'))


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def ptr_norm(h):
    # ICALL-79 (#2674): xmm0 が x86-64 のユーザ空間アドレス (0 < v < 2^47) なら bit を比べず PTR に畳む。
    # native と wasm はヒープの基底が違うため、ポインタを返す関数は bit が必ず食い違う (0x18105d9fc)。
    # 正規化された double は上位 16bit が 0 にならないので、この範囲は実質ポインタ由来。subnormal は誤って PTR になりうる。
    # 両側が (0, 2^47) にあると整数どうしでも PTR に畳まれ、ポインタと非ポインタ整数の食い違いも一致扱いになる。
    # FA_PTR_NORM=0 で従来の bit 比較に戻す (負の対照)。
    if os.environ.get('FA_PTR_NORM', '1') == '0' or h.startswith('ERR'):
        return h
    return 'PTR' if 0 < int(h, 16) < (1 << 47) else h


def blk_xmm0_out():
    # ICALL-78 (#2508): BLK+0x88 = ott_xmm0 が読む出力スロット。ott_run は入力 xmm0 を BLK+0x28 にだけ置くので、
    # xmm0 を素通しする関数 (native は入力のまま返す) で出力が未初期化の 0 になる。native と同じく入力で初期化してから呼ぶ。
    blk = json.load(open(os.path.join(T, 'icall', 'work', 'rt_freshair-core', 'map.json')))['blk']
    return blk - 0x180000000 + 0x30000000 + 0x88


# ICALL-81 (#2695): 要素の state 0 は 0x180da41a0 (64 B 節点の lock-free キュー読み出し) を呼ぶ。
# 先頭節点 (node[0] = (B+0xbf)&~63) の next が nil (0x4001) でないと空判定に進まず spin する (件数 1 で hang)。
# 空キュー (node[0].next = nil・head/tail = 0) にすると 0 を返して要素を飛ばす。
NIL_NODE = 0x4001


def init_native(va):
    gpr = [N.alloc(0x400) for _ in range(4)]
    if va == LOOP_VA:
        A = N.alloc(0x2000); B = N.alloc(max(LOOP_CNT, 1) * LOOP_STRIDE + 0x200)
        N.wr(gpr[0] + 0x10, struct.pack('<Q', A))
        N.wr(gpr[0] + 0xb8, struct.pack('<Q', B))
        N.wr(A + 0x199c, struct.pack('<I', LOOP_CNT))
        N.wr((B + 0xbf) & ~63, struct.pack('<I', NIL_NODE))
    return tuple(gpr)


# wasm 側は同じ構造体を linear memory に作る (ポインタは 8 B 格納・下位 32 bit が wasm アドレス)。
MK_JS = (
    "const LOOP_VA = %d, LOOP_STRIDE = %d, LOOP_CNT = %d;\n"
    "function mk(va) {\n"
    "  const g = [0, 1, 2, 3].map(() => BigInt(mod._malloc(0x400)));\n"
    "  if (va === LOOP_VA) {\n"
    "    const S = Number(g[0]), A = mod._malloc(0x2000), Bn = Math.max(LOOP_CNT, 1) * LOOP_STRIDE + 0x200, B = mod._malloc(Bn);\n"
    "    for (const p of [S, A, Number(g[1]), Number(g[2]), Number(g[3])]) mod.HEAPU8.fill(0, p, p + 0x400);\n"
    "    mod.HEAPU8.fill(0, A, A + 0x2000); mod.HEAPU8.fill(0, B, B + Bn);\n"
    "    const d = new DataView(mod.HEAPU8.buffer);\n"
    "    d.setBigUint64(S + 0x10, BigInt(A), true); d.setBigUint64(S + 0xb8, BigInt(B), true);\n"
    "    d.setUint32(A + 0x199c, LOOP_CNT, true);\n"
    "    d.setUint32((B + 0xbf) & ~63, %d, true);\n"
    "  }\n"
    "  return g;\n"
    "}\n" % (LOOP_VA, LOOP_STRIDE, LOOP_CNT, NIL_NODE)
)


def wasm_run(vas, xs):
    js = tempfile.NamedTemporaryFile('w', suffix='.cjs', delete=False, dir=os.environ.get('TMPDIR'))
    js.write(
        "const m = require(%r);\n"
        "const vas = %s, xs = %s;\n"
        "m().then((mod) => {\n"
        "%s"
        "  const out = {};\n"
        "  mod._ott_data_install();\n"
        "  for (const va of vas) {\n"
        "    out[va] = [];\n"
        "    for (const x of xs) {\n"
        "      try {\n"
        "        const g = mk(va);\n"
        "        const dv = new DataView(new ArrayBuffer(8)); dv.setFloat64(0, x);\n"
        "        new DataView(mod.HEAPU8.buffer).setBigUint64(%d, dv.getBigUint64(0), true);\n"
        "        mod._ott_run(0x30000000 + (va - 0x180000000), g[0], g[1], g[2], g[3], dv.getBigUint64(0), 0n, 0n, 0n);\n"
        "        out[va].push(BigInt.asUintN(64, mod._ott_xmm0()).toString(16).padStart(16, '0'));\n"
        "      } catch (e) { out[va].push('ERR:' + String(e).slice(0, 60)); }\n"
        "    }\n"
        "  }\n"
        "  console.log(JSON.stringify(out));\n"
        "});\n" % (MOD, json.dumps(vas), json.dumps(xs), MK_JS, blk_xmm0_out()))
    js.close()
    r = subprocess.run(['node', js.name], capture_output=True, text=True, cwd=T)
    os.unlink(js.name)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}


def main():
    vas = [int(v, 16) for v in sys.argv[1].split(',')]
    n = arg('--n', 8); seed = arg('--seed', 3)
    random.seed(seed)
    xs = [random.uniform(-4.0, 4.0) for _ in range(n)]
    N.load(FA)
    if os.environ.get('FA_HEAP_FILL'):
        N._lib.ott_set_heap_fill(int(os.environ['FA_HEAP_FILL'], 0))
    if os.environ.get('FA_ENC_INIT') == '1':
        N.enc_slots(COOKIE_VA, ENC_SLOTS)
    nat = {}
    for va in vas:
        nat[va] = []
        for x in xs:
            try:
                gpr = init_native(va)
                _, x0 = N.call(va, gpr=gpr, xmm=(N.f64b(x),))
                nat[va].append('%016x' % x0)
            except Exception as e:
                nat[va].append('ERR:' + str(e)[:60])
    w = wasm_run([hex(v) for v in vas], xs)
    res = []
    for va in vas:
        nv = [ptr_norm(h) for h in nat[va]]; wv = [ptr_norm(h) for h in w.get(hex(va), [])]
        pairs = list(zip(nv, wv))
        match = sum(1 for a, b in pairs if a == b and not a.startswith('ERR'))
        mism = [(i, a, b) for i, (a, b) in enumerate(pairs) if a != b]
        res.append({'va': hex(va), 'n': len(pairs), 'match': match, 'mismatch': len(mism),
                    'native_err': sum(1 for a in nv if a.startswith('ERR')),
                    'wasm_err': sum(1 for b in wv if b.startswith('ERR')),
                    'first': mism[:2]})
    print(json.dumps(res))


if __name__ == '__main__':
    main()
