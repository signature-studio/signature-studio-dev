#!/usr/bin/env python3
"""12 shell の Gen_Render VA / instance size を DLL から実測して stdout に TSV (block name gen_va instance_size)。
 usage: gr_targets.py   (FL_WIN64_DIR 要。 inventory/win_abi.py の scan を再利用)
 対象 12 本は synth/targets.py の shell から導出する。 Gen_Render が無い shell があれば exit 1。
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'inventory'))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'shared'))
import win_abi  # noqa: E402

blocks = subprocess.check_output([sys.executable, os.path.join(HERE, '..', 'targets.py'), 'shell'], text=True).split()
if len(blocks) != 12:
    sys.exit('shell が 12 本でない: %d' % len(blocks))
rc = 0
for b in blocks:
    r = win_abi.scan('block%05d_PE.bin' % int(b))
    va = r.get('impl', {}).get('Gen_Render')
    if not va or not r.get('instance_size'):
        print('Gen_Render / instance_size 不明: %s' % b, file=sys.stderr)
        rc = 1
        continue
    print('%s\t%s\t%s\t%d' % (b, r['info']['short'].replace(' ', '_'), va, r['instance_size']))
sys.exit(rc)
