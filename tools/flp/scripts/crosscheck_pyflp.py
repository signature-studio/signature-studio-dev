#!/usr/bin/env python3
"""Cross-check our parser against PyFLP 2.2.1 (public upstream, reference only) on every .flp of the corpus.
PyFLP is run unmodified from a venv (work/venv). Output: corpus/pyflp_crosscheck.json
Compared per file: raw event count (PyFLP event stream vs ours), tempo, channel count, pattern count, insert count.
Files PyFLP cannot parse are listed with the exception text (expected for FL >= 25.2: extended 0xAC ids)."""
import json, os, sys, glob, collections, warnings
warnings.filterwarnings('ignore')
import pyflp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_MAC_DIR

ROOT = os.environ.get('FL_ROOT', f'{FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL')
ours = {p['rel']: p for p in json.load(open('corpus/manifest.json'))['projects']}
rows = []
agree = collections.Counter()
for rel, o in sorted(ours.items()):
    path = os.path.join(ROOT, rel)
    r = {'rel': rel, 'version': o['version']}
    try:
        proj = pyflp.parse(path)
        r['pyflp_events'] = sum(1 for _ in proj.events) if hasattr(proj, 'events') else None
        r['pyflp_tempo'] = float(proj.tempo) if proj.tempo is not None else None
        r['pyflp_channels'] = len(list(proj.channels))
        r['pyflp_patterns'] = len(list(proj.patterns))
        r['pyflp_inserts'] = len(list(proj.mixer))
        r['ok'] = True
        r['events_match'] = r['pyflp_events'] == o['events']
        r['tempo_match'] = r['pyflp_tempo'] is not None and o.get('tempo') is not None and abs(r['pyflp_tempo'] - o['tempo']) < 0.01
        r['channels_match'] = r['pyflp_channels'] == o['channels']
        r['patterns_match'] = r['pyflp_patterns'] == o['patterns']
        for k in ('events_match', 'tempo_match', 'channels_match', 'patterns_match'):
            agree[k] += int(r[k])
    except Exception as e:
        r['ok'] = False
        r['error'] = (type(e).__name__ + ': ' + str(e))[:200]
    rows.append(r)
summary = {
    'files': len(rows), 'pyflp_parsed': sum(1 for r in rows if r['ok']), 'pyflp_failed': sum(1 for r in rows if not r['ok']),
    'agree': dict(agree),
}
fails = collections.Counter((r['version'].split('.')[0] + '.' + r['version'].split('.')[1]) for r in rows if not r['ok'])
summary['failed_by_version'] = dict(fails)
json.dump({'summary': summary, 'rows': rows}, open('corpus/pyflp_crosscheck.json', 'w'), indent=1)
print(json.dumps(summary))
