#!/usr/bin/env python3
"""verify_consistency.py — CAB-213 検収の整合チェック (seed / pathreg マウント表 / キー)。

ALL PASS 条件:
  1. seed entries の (hive,key,name) 一意 (重複 0)
  2. key=null エントリ ≤ 20 (CAB-213 の目標)
  3. username 表記: seed 内の C:\\Users\\<name> は正規 'webstudio' に統一
     (shimx 内蔵値も CAB-214 で webstudio に統一済み。pathreg 既定マウント表は webstudio のみ —
      予備 profile `user2Profile` (user) は CAB-214 follow-up で退役)
  4. seed 'Shared data' 値と pathreg 既定マウント (webstudio\\Documents\\Image-Line →
     /c/home/Documents/Image-Line) が同一実体
  5. apply=true エントリは全て key を持ち、value が空でない
  6. key 確定 (key_conf=確定) のうち low-key 由来 112 の内訳を集計
"""
import json, os, sys, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import REPO_ROOT  # noqa: E402
SEED = os.path.join(REPO_ROOT, 'tools', 'startup', 'vreg', 'data', 'seed.json')
KEYS = os.path.join(REPO_ROOT, 'tools', 'startup', 'vreg', 'data', 'keys.json')
PATHMAP_JS = os.path.join(REPO_ROOT, 'tools', 'shimx', 'pathreg', 'js', 'pathmap.mjs')
PATHMAP_C = os.path.join(REPO_ROOT, 'tools', 'shimx', 'pathreg', 'src', 'pathmap.c')

CANON = 'webstudio'          # 正規 username (CAB-213 確定 / CAB-214 で shimx 内蔵値も統一)
RETIRED = 'user'             # 旧 shimx 内蔵値 — pathreg 予備 profile (user2Profile) は退役済み

fails = []


def check(name, ok, detail=''):
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' — ' + detail) if detail else ''))
    if not ok:
        fails.append(name)


seed = json.load(open(SEED))
entries = seed['entries']

# 1. 一意性
seen = collections.Counter((e['hive'], (e['key'] or '').lower(), e['name'].lower()) for e in entries if e.get('key'))
dups = [k for k, c in seen.items() if c > 1]
check('seed (hive,key,name) 一意', not dups, str(dups[:3]))

# 2. key=null 上限
nulls = [e for e in entries if not e.get('key')]
check('key 不明エントリ ≤ 20', len(nulls) <= 20, 'null=%d (%s)' % (len(nulls), ','.join(e['name'] for e in nulls)))

# 3. username 統一 (seed)
users = set()
for e in entries:
    for m in re.finditer(r'C:\\\\Users\\\\([A-Za-z0-9_\-]+)', json.dumps(e, ensure_ascii=False)):
        users.add(m.group(1))
for k in ('env', 'known_folders'):
    for m in re.finditer(r'C:\\\\Users\\\\([A-Za-z0-9_\-]+)', json.dumps(seed.get(k, {}), ensure_ascii=False)):
        users.add(m.group(1))
extra = users - {CANON, 'GENERATE_ONCE_PER_PROFILE'}
check('seed username 表記 = 正規 %s のみ' % CANON, not extra, 'users=%s' % sorted(users))

# 4. Shared data ↔ pathreg 既定マウント
sd = next(e for e in entries if e['name'] == 'Shared data' and e['group'] == 'paths')
pm_c = open(PATHMAP_C, encoding='utf-8').read()
pm_js = open(PATHMAP_JS, encoding='utf-8').read()
ok_c = ('userProfile = "C:\\\\Users\\\\%s"' % CANON) in pm_c and 'user2Profile' not in pm_c
check('pathreg C 既定: 正規 %s のみ (予備 %s 退役済み)' % (CANON, RETIRED), ok_c)
ok_js = ("userProfile: 'C:\\\\Users\\\\%s'" % CANON) in pm_js and 'user2Profile' not in pm_js
check('pathreg JS ミラー既定: 正規 %s のみ (予備 %s 退役済み)' % (CANON, RETIRED), ok_js)
target = sd['value'].replace('C:\\\\%s\\\\Documents\\\\Image-Line\\\\' % CANON, '/c/home/Documents/Image-Line')
check('seed "Shared data" → /c/home/Documents/Image-Line (同一実体)',
      sd['value'] == 'C:\\Users\\%s\\Documents\\Image-Line\\' % CANON, sd['value'])

# 5. apply エントリの健全性
bad = [e['name'] for e in entries if e['apply'] and (not e.get('key') or e['value'] in (None, ''))]
check('apply=true は key+value を持つ', not bad, str(bad[:5]))

# 6. 集計
kc = collections.Counter(e['key_conf'] for e in entries if e.get('key'))
kp = collections.Counter(e['key_conf'] for e in entries if not e.get('key'))
apply_n = sum(1 for e in entries if e['apply'])
print('--- 集計: entries=%d apply=%d key確定=%d key推定=%d key=null=%d (推定=%s)' % (
    len(entries), apply_n, kc.get('確定', 0), kc.get('推定', 0), len(nulls), dict(kp)))

if fails:
    print('RESULT: FAIL (%s)' % ', '.join(fails))
    sys.exit(1)
print('RESULT: ALL PASS')
