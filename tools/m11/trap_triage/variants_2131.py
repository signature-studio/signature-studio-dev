# #2131: unit 190 の ON 限定の trap を、同一メモリ状態 (unit 189 直後・SP 一致) の下で ON 専用の処理ごとに切り分ける variant を作る.
#   usage (tools/m11 で実行): FL_WIN64_DIR=... RETDEC_ROOT=... EMSDK=... python3 trap_triage/variants_2131.py <out_root>
#   各 variant を <out_root>/<name>/ に build (m11_boot.cjs・.wasm・m11_image.bin) し, m11_ov.c は終了時に元へ戻す.
#   続けて lockstep_2131.mjs を LS_FORCEB=1 で走らせる (例: LS_FORCEB=1 LS_A=<off> LS_B=<out_root>/vz LS_CKPT=189 LS_MAX=190 node trap_triage/lockstep_2131.mjs).
#   variant の意味:
#     vdisp  : 41c130・9b4b00 の disp entry を外す
#     v413   : 413060 の C override を外す (gate を M11_OV_413060 のみに)
#     vnc    : 410360 の m11_vcall で shortcut 以外の ICALL_AT dispatch を外す (M11_NOVCALL=1)。shortcut (target == R(0x10070)) 内の icall 計数 (icall_bump 2 回) は残る
#     vall   : vdisp + v413 + vnc (shortcut 内の icall 計数は残るため、vall からは計数の必要性は判定できない)
#     vx     : vdisp + v413 + 410360 の本体を `return inst;` だけにする (VMT 読みと icall 計数を両方外す)
#     vy     : vdisp + v413 + 410360 の VMT 読み `Q(Q(inst)-0x50)` だけ残し, icall 計数は外す
#     vz     : vdisp + v413 + 410360 の icall 計数 (m11_vcall の shortcut 内の icall_bump 2 回) だけ残し, VMT 読みは外す
import os, shutil, subprocess, sys

TOOL = os.getcwd()
OUT = sys.argv[1]
SRC = os.path.join(TOOL, 'm11_ov.c')
ORIG = os.path.join(OUT, 'm11_ov.orig.c')
os.makedirs(OUT, exist_ok=True)
shutil.copy(SRC, ORIG)
src = open(ORIG).read()


def rep(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)


def disp(s):
    s = rep(s, '    case 0x41c130: return tr_41c130;', '    case 0x41c130: return 0;')
    return rep(s, '    case 0x9b4b00: return tr_9b4b00;', '    case 0x9b4b00: return 0;')


def gate413(s):
    return rep(s, '#if M11_OV_CLASSCREATE || M11_OV_413060\n/* function_413060', '#if M11_OV_413060\n/* function_413060')


VCALL = '    m11_vcall(0x41037d, Q(Q(inst) - 0x50), inst);\n    return inst;'
V = {
    'vdisp': (disp(src), {}),
    'v413': (gate413(src), {}),
    'vnc': (src, {'M11_NOVCALL': '1'}),
    'vall': (gate413(disp(src)), {'M11_NOVCALL': '1'}),
    'vx': (rep(gate413(disp(src)), VCALL, '    return inst;'), {}),
    'vy': (rep(gate413(disp(src)), VCALL, '    (void)Q(Q(inst) - 0x50);\n    return inst;'), {}),
    'vz': (rep(gate413(disp(src)), VCALL, '    m11_vcall(0x41037d, R(0x10070), inst);\n    return inst;'), {}),
}
try:
    for name, (text, extra) in V.items():
        open(SRC, 'w').write(text)
        ov = os.path.join(TOOL, 'work', 'obj', 'ov.o')
        if os.path.exists(ov):
            os.remove(ov)
        r = subprocess.run(['bash', 'm11_build.sh'], cwd=TOOL, env=dict(os.environ, M11_OV_CLASSCREATE='1', **extra), capture_output=True, text=True)
        print(name, 'build rc', r.returncode, flush=True)
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        for f in ['m11_boot.cjs', 'm11_boot.cjs.wasm', 'm11_image.bin']:
            shutil.copy(os.path.join(TOOL, 'work', f), os.path.join(d, f))
finally:
    shutil.copy(ORIG, SRC)
    print('restored m11_ov.c', flush=True)
