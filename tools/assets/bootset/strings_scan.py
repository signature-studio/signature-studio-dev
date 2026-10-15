#!/usr/bin/env python3
"""FLEngine_x64.dll (win) / FLEngine_x64.dylib (mac x86_64 slice) からパス/拡張子文字列を抽出し、資産ツリーと照合する。

出力: work/engine_strings.json  {win:{ascii:[...],utf16:[...]}, mac:{...}}
"""
import re, sys, json, os, struct
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); WORK = os.path.join(ROOT, 'work')
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR, REPO_ROOT
WIN = os.path.join(FL_WIN64_DIR, 'extracted/block00031_PE.bin')
MAC = os.path.join(REPO_ROOT, 'tools/m2/work/FLEngine_x86_64.dylib')

def ascii_strings(b, minlen=4):
    return [m.group().decode('latin1') for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, b)]

def utf16_strings(b, minlen=4):
    out = []
    for m in re.finditer(rb'(?:[\x20-\x7e]\x00){%d,}' % minlen, b):
        out.append(m.group().decode('utf-16-le'))
    return out

def main():
    res = {}
    for nm, p in (('win', WIN), ('mac', MAC)):
        if not os.path.exists(p):
            continue
        b = open(p, 'rb').read()
        res[nm] = dict(size=len(b), ascii=ascii_strings(b), utf16=utf16_strings(b))
        print(nm, len(b), len(res[nm]['ascii']), len(res[nm]['utf16']))
    json.dump(res, open(os.path.join(WORK, 'engine_strings.json'), 'w'))
main()
