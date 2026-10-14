# #2131: ON の ON-only override を 1 つずつ外して unit 190 を見る (ov.o を毎回作り直す). 終了時に m11_ov.c を復元する.
import json, os, shutil, subprocess, sys
TOOL = sys.argv[1]; OUT = sys.argv[2]
SRC = os.path.join(TOOL, 'm11_ov.c'); ORIG = os.path.join(OUT, 'm11_ov.orig.c')
os.makedirs(OUT, exist_ok=True)
shutil.copy(SRC, ORIG)
src0 = open(ORIG).read()
env0 = dict(os.environ, M11_OV_CLASSCREATE='1', FL_WIN64_DIR=os.environ['FL_WIN64_DIR'], RETDEC_ROOT=os.environ['RETDEC_ROOT'], EMSDK=os.environ['EMSDK'])

def replace1(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)

VARIANTS = {
    # 413060 の C override を ON から外す (gate を M11_OV_413060 だけにする)
    'no413060': lambda s: replace1(s, '#if M11_OV_CLASSCREATE || M11_OV_413060\n/* function_413060', '#if M11_OV_413060\n/* function_413060'),
    # 41c130 の disp entry だけ外す (ON のまま)
    'no41c130': lambda s: replace1(s, '    case 0x41c130: return tr_41c130;', '    case 0x41c130: return 0;'),
    # 9b4b00 の disp entry だけ外す
    'no9b4b00': lambda s: replace1(s, '    case 0x9b4b00: return tr_9b4b00;', '    case 0x9b4b00: return 0;'),
    # 両方外す
    'no41c130_9b4b00': lambda s: replace1(replace1(s, '    case 0x41c130: return tr_41c130;', '    case 0x41c130: return 0;'), '    case 0x9b4b00: return tr_9b4b00;', '    case 0x9b4b00: return 0;'),
}
only = sys.argv[3].split(',') if len(sys.argv) > 3 else list(VARIANTS)
try:
    for tag in only:
        open(SRC, 'w').write(VARIANTS[tag](src0))
        ov = os.path.join(TOOL, 'work', 'obj', 'ov.o')
        if os.path.exists(ov): os.remove(ov)
        b = subprocess.run(['bash', 'm11_build.sh'], cwd=TOOL, env=env0, capture_output=True, text=True, timeout=400)
        if b.returncode != 0:
            print(tag, 'BUILD FAIL', b.stdout[-200:], b.stderr[-200:], flush=True); continue
        out = os.path.join(OUT, tag + '.json')
        s = subprocess.run(['node', 'trap_triage/survey_units.mjs', out], cwd=TOOL, env=dict(env0, SV_RAW='1'), capture_output=True, text=True, timeout=400)
        line = [l for l in s.stdout.splitlines() if 'SURVEY_UNITS' in l]
        rows = {r['unit']: r for r in json.load(open(out))}
        print(tag, line[-1] if line else 'NO SUMMARY', 'unit190=' + str(rows[190]['kind']), flush=True)
finally:
    shutil.copy(ORIG, SRC)
    print('restored m11_ov.c', flush=True)
