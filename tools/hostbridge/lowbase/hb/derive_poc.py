#!/usr/bin/env python3
"""derive_poc.py — tools/hostbridge/poc/run_poc.mjs (65 項目検収の PoC 部 28 check) から lowbase 版を機械的に派生する.
  元ファイルは無改変. 置換するのは (1) import/HERE を絶対パス化 (2) WORK を env LB_WORK (3) module cjs 経路 (4) directBaseline の固定 VA (0x306xxxxx) を LB_ARENA 相対へ.
  置換が 1 つでも当たらなければ失敗 (poc 側の変更に追従できていない合図).
usage: derive_poc.py OUT.mjs"""
import sys, os
POC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'poc'))
s = open(os.path.join(POC, 'run_poc.mjs')).read()
R = [
 ("import { ModuleTable, HostBridge, THUNK_BASE } from './hb_bridge.mjs';", "import { ModuleTable, HostBridge, THUNK_BASE } from '%s/hb_bridge.mjs';" % POC),
 ("import { makeOttDesc } from './ott_module.mjs';", "import { makeOttDesc } from '%s/ott_module.mjs';" % POC),
 ("const HERE = path.dirname(fileURLToPath(import.meta.url));\nconst WORK = path.join(HERE, '../work');", "const HERE = '%s';\nconst WORK = process.env.LB_WORK;\nconst LB_ARENA = Number(process.env.LB_ARENA);" % POC),
 ("const ott = makeOttDesc();", "const ott = makeOttDesc({ cjs: path.join(WORK, 'ott_hb.cjs') });"),
 ("const OBJ = 0x30600000, BUF = 0x30620000, U8 = mod.HEAPU8", "const OBJ = LB_ARENA + 0x10000, BUF = LB_ARENA + 0x30000, U8 = mod.HEAPU8"),
 ("const IN_A = 0x30610000, OU_A = 0x30611000, n = N;", "const IN_A = LB_ARENA + 0x20000, OU_A = LB_ARENA + 0x21000, n = N;"),
 ("(各 instance の linear memory = 864 MiB 予約)", "(各 instance の linear memory = ${process.env.LB_INIT_MIB} MiB initial, lowbase)"),
]
for a, b in R:
    assert a in s, 'run_poc.mjs が変わった: ' + a[:60]
    s = s.replace(a, b)
open(sys.argv[1], 'w').write(s)
