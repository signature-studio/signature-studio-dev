#!/usr/bin/env python3
"""check.py — loadpaths.json の各 group をインストーラ由来の実ファイル一覧に当て、件数・サイズ・VFS 写像・既存推定 tier との差を実測する (ST-T14 / #39)。

入力: <installer.exe> <extracted_dir> (fl-win64 素材。$FL_WIN64_DIR の直下)
手順: mk_manifest.py (block idx ↔ payload_off 再構成) → tools/assets/win_paths/recover_paths.py (NSIS script から元パス復元)
      → 実ファイルサイズ = extracted/blockNNNNN_* のバイト数 → group の glob 照合 → pathreg の JS ミラーで Win→VFS 写像を検査
glob 規則は tools/assets/bootset/classify_bootset.py と同じ (`*` は `/` を跨がない / 末尾 `/*` は部分木全体 / `**` は任意)。
group は配列順で first-match (先に当たった group が取る)。大小無視。

usage: check.py <installer.exe> <extracted_dir> [--spec loadpaths.json] [--out result.json] [--work dir]
exit 0 = 全 group が 1 件以上 かつ Win→VFS 写像が全件 /fl/<rel> と一致 (first-match で後続 group に落ちた件数は shadowed に出す)
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
INSTALL_DIR = 'C:\\Program Files\\Image-Line\\FL Studio 2026'


def rx(g):
    gg = g[:-2] + '/**' if g.endswith('/*') else g
    r, i = '', 0
    while i < len(gg):
        if gg.startswith('**', i):
            r += '.*'; i += 2
        elif gg[i] == '*':
            r += '[^/]*'; i += 1
        else:
            r += re.escape(gg[i]); i += 1
    return re.compile('^' + r + '$', re.I)


def main(argv):
    a = [x for x in argv[1:]]
    opt = {}
    for k in ('--spec', '--out', '--work'):
        if k in a:
            i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    exe, ext = a[0], a[1]
    spec = json.load(open(opt.get('--spec', os.path.join(HERE, 'loadpaths.json'))))
    work = opt.get('--work', os.path.join(HERE, 'work'))
    os.makedirs(work, exist_ok=True)
    man, wp = os.path.join(work, 'block_manifest.json'), os.path.join(work, 'win_paths.json')
    subprocess.run([sys.executable, os.path.join(HERE, 'mk_manifest.py'), exe, man, ext], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools/assets/win_paths/recover_paths.py'), exe, man, wp], check=True, stdout=subprocess.DEVNULL)

    files = {fn[5:10]: fn for fn in os.listdir(ext) if re.match(r'block\d{5}_', fn)}
    inv = {}                                               # rel('/' 区切り) -> size
    for idx, paths in json.load(open(wp)).items():
        if not idx.isdigit():
            continue
        sz = os.path.getsize(os.path.join(ext, files[idx]))
        for p in paths:
            if p.startswith('$INSTDIR\\'):
                inv[p[9:].replace('\\', '/')] = sz
    # 既存の静的推定 tier (bootset.json の rules を同じ順・同じ glob 規則で適用。一致なしは T2)
    rules = [(r['tier'], rx(r['glob'])) for r in json.load(open(os.path.join(ROOT, 'tools/assets/bootset/bootset.json')))['rules']]
    est = lambda p: next((t for t, r in rules if r.match(p)), 'T2')

    taken, res, shadow = {}, [], 0
    for g in spec['groups']:
        rs = [rx(x) for x in g['globs']]
        hit = [p for p in sorted(inv) if any(r.match(p) for r in rs)]
        mine = [p for p in hit if p not in taken]
        shadow += len(hit) - len(mine)
        for p in mine:
            taken[p] = g['id']
        dist = {}
        for p in mine:
            t = est(p); d = dist.setdefault(t, [0, 0]); d[0] += 1; d[1] += inv[p]
        res.append({'id': g['id'], 'phase': g['phase'], 'tier': g['tier'], 'files': len(mine), 'bytes': sum(inv[p] for p in mine),
                    'est_tier_dist': {t: {'files': v[0], 'bytes': v[1]} for t, v in sorted(dist.items())}, 'paths': mine})

    # Win→VFS 写像 (pathreg JS ミラー)。全 group の全ファイルが /fl/<rel> になること
    allp = [p for r in res for p in r['paths']]
    wins = [INSTALL_DIR + '\\' + p.replace('/', '\\') for p in allp]
    out = subprocess.run(['node', os.path.join(HERE, 'mapcheck.mjs')], input=json.dumps(wins), capture_output=True, text=True, check=True).stdout
    mapped = json.loads(out)
    map_bad = [p for p, m in zip(allp, mapped) if m != '/fl/' + p]

    fail = []
    for r in res:
        if r['files'] == 0:
            fail.append(f"group {r['id']}: 実ファイル 0 件")
    if map_bad:
        fail.append(f'写像不一致 {len(map_bad)} 件 (先頭 {map_bad[:3]})')
    summary = {'inventory_files': len(inv), 'groups': [{k: v for k, v in r.items() if k != 'paths'} for r in res],
               'grouped_files': len(allp), 'shadowed': shadow, 'map_checked': len(allp), 'map_mismatch': len(map_bad), 'fail': fail}
    if '--out' in opt:
        json.dump(dict(summary, files={r['id']: r['paths'] for r in res}), open(opt['--out'], 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if fail else 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv))
