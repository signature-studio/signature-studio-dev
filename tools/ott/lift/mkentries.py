#!/usr/bin/env python3
"""mkentries.py cov.json out.json: native coverage (call target RVA 集合) + VST 入口 root から lifter 入力を作る"""
import json, sys
c = json.load(open(sys.argv[1]))
roots = [0x18011d400, 0x180120af0, 0x180120800, 0x18011ec20]
json.dump({'roots': roots, 'calltgt': c['calltgt']}, open(sys.argv[2], 'w'))
print('[mkentries] roots', len(roots), 'calltgt', len(c['calltgt']))
