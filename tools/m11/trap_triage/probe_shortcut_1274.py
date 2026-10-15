# #1274: unit 190 の ON 限定 oob を、410360 の m11_vcall shortcut (target == R(0x10070)) の切り分けで再現する.
#   usage (tools/m11 で実行。m11_gen_ir2.sh 済みであること): FL_WIN64_DIR=... RETDEC_ROOT=... EMSDK=... python3 trap_triage/probe_shortcut_1274.py <out_dir>
#   各変種で work/obj/ov.o を作り直して m11_build.sh → 全 942 unit の survey (SV_RAW=1). m11_ov.c は finally で元へ戻す.
#   変種:
#     off       : M11_OV_CLASSCREATE=0 (基準)
#     on        : M11_OV_CLASSCREATE=1 (既定の ON: shortcut で icall_bump を 2 回呼ぶ)
#     on_nw     : ON。shortcut の icall_bump 2 回を「表へ書かない」関数 icall_bump_nw 1 回に置換 (呼出しは残す)
#     on_fill00 : on_nw に加え、icall_bump_nw が自分の 512B 局所領域を 0x00 で埋める
#     on_fillA5 : on_nw に加え、同じ 512B 領域を 0xA5 で埋める
#     on_dummy  : ON。呼ばれない関数 dummy_unused_1274 を 1 つ足す (関数番号のずれの対照)
#     on_fix912 : ON + M11_FIX_912=1 (#912 の IR 修復を有効化)
import json, os, shutil, subprocess, sys

TOOL = os.getcwd()
OUT = os.path.abspath(sys.argv[1])
SRC = os.path.join(TOOL, 'm11_ov.c')
os.makedirs(OUT, exist_ok=True)
ORIG = os.path.join(OUT, 'm11_ov.orig.c')
shutil.copy(SRC, ORIG)
src = open(ORIG).read()
SHORT_OLD = ("    if (target == R(0x10070)) {\n        icall_bump(&g_isite, site, 0);\n"
             "        icall_bump(&g_itgt, 0x410070u, 0);\n        return self;\n    }")
SHORT_NW = "    if (target == R(0x10070)) {\n        icall_bump_nw(site);\n        return self;\n    }"
ANCHOR = "static u64 m11_vcall(u32 site, u64 target, u64 self) {"


def rep(s, old, new):
    assert s.count(old) == 1, old[:60]
    return s.replace(old, new)


def nw_fn(fill):
    if fill is None:
        body = "    (void)site;\n"
    else:
        body = ("    volatile unsigned char pad[512];\n"
                "    for (int i = 0; i < 512; i++) pad[i] = %s;\n    (void)site;\n" % fill)
    return "static __attribute__((noinline)) void icall_bump_nw(u32 site) {\n" + body + "}\n"


def variant_nw(fill):
    s = rep(src, SHORT_OLD, SHORT_NW)
    return rep(s, ANCHOR, nw_fn(fill) + ANCHOR)


VARIANTS = [
    ('off', src, {'M11_OV_CLASSCREATE': '0'}),
    ('on', src, {'M11_OV_CLASSCREATE': '1'}),
    ('on_nw', variant_nw(None), {'M11_OV_CLASSCREATE': '1'}),
    ('on_fill00', variant_nw('0x00'), {'M11_OV_CLASSCREATE': '1'}),
    ('on_fillA5', variant_nw('0xA5'), {'M11_OV_CLASSCREATE': '1'}),
    ('on_dummy', rep(src, ANCHOR, "static __attribute__((noinline)) void dummy_unused_1274(u32 s) { (void)s; }\n" + ANCHOR),
     {'M11_OV_CLASSCREATE': '1'}),
    ('on_fix912', src, {'M11_OV_CLASSCREATE': '1', 'M11_FIX_912': '1'}),
]


def stack_init(path):
    b = open(path, 'rb').read()
    pos = 8

    def leb(p):
        r = s = 0
        while True:
            x = b[p]; p += 1; r |= (x & 0x7f) << s; s += 7
            if not x & 0x80:
                return r, p
    while pos < len(b):
        sid = b[pos]; pos += 1
        sz, pos = leb(pos)
        if sid == 6:
            _, p = leb(pos)
            p += 2  # valtype, mut
            assert b[p] == 0x41
            v, _ = leb(p + 1)
            return v
        pos += sz
    raise SystemExit('no global section')


def survey(name):
    js = os.path.join(OUT, name + '.json')
    env = dict(os.environ, SV_RAW='1')
    r = subprocess.run(['node', 'trap_triage/survey_units.mjs', js], cwd=TOOL, env=env,
                       capture_output=True, text=True, timeout=600)
    line = [l for l in r.stdout.splitlines() if l.startswith('SURVEY_UNITS')]
    per = json.load(open(js))
    rows = per if isinstance(per, list) else list(per.values())
    return (line[0][len('SURVEY_UNITS '):] if line else 'NO_SUMMARY'), {x['unit']: x['kind'] for x in rows}


res = {}
try:
    for name, text, env_extra in VARIANTS:
        open(SRC, 'w').write(text)
        ov = os.path.join(TOOL, 'work', 'obj', 'ov.o')
        if os.path.exists(ov):
            os.remove(ov)
        extra = dict(env_extra)
        if name == 'on':
            extra['M11_LINK_MAP'] = os.path.join(OUT, 'on_map.txt')
        r = subprocess.run(['bash', 'm11_build.sh'], cwd=TOOL, env=dict(os.environ, **extra),
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise SystemExit('build %s rc=%d' % (name, r.returncode))
        summ, kinds = survey(name)
        res[name] = kinds
        print(name, summ, flush=True)
finally:
    shutil.copy(ORIG, SRC)

base = res['off']
for name in res:
    ch = [f'{u}:{base[u]}->{k}' for u, k in sorted(res[name].items()) if base.get(u) != k]
    print(f'OFF->{name}: ' + (' '.join(ch) if ch else 'none'))
print('unit190:', {n: res[n].get(190) for n in res})

m = os.path.join(OUT, 'on_map.txt')
if os.path.exists(m):
    for line in open(m):
        if any(s in line for s in ('(.data.g_isite)', '(.data.g_itgt)', '(.bss.g_isite_e)', '(.bss.g_isite_h)',
                                   '(.bss.g_itgt_e)', '(.bss.g_itgt_h)')):
            print('map:', line.split()[0], line.split()[1], line.split()[2], line.split()[3])
print('wasm global 0 (__stack_pointer) init = 0x%x' % stack_init(os.path.join(TOOL, 'work', 'm11_boot.cjs.wasm')))
