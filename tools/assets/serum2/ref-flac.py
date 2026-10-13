#!/usr/bin/env python3
"""独立参照: libsndfile (python-soundfile) で全 FLAC を復号し PCM の sha256 を出す。
wasm (libFLAC 1.5.0) 側の e2e と別実装 (libsndfile 内蔵の FLAC 経路) で突合するための検算。

  python3 ref-flac.py <extracted-root> <out.json> [--jobs N]
出力: { "<相対 path>": {"sha": <int32 left-justified little-endian PCM の sha256>, "ch","rate","frames","bps"} }
int32 left-justified = soundfile dtype='int32' (bps<32 は (32-bps) bit 左シフト)。e2e 側は wasm の int32 PCM を同形に変換して比較する。
"""
import sys, os, json, hashlib
from multiprocessing import Pool
import numpy as np
import soundfile as sf

BPS = {'PCM_16': 16, 'PCM_24': 24, 'PCM_32': 32, 'PCM_S8': 8}


def one(args):
    root, rel = args
    try:
        info = sf.info(os.path.join(root, rel))
        data, rate = sf.read(os.path.join(root, rel), dtype='int32', always_2d=True)
        return rel, {'sha': hashlib.sha256(np.ascontiguousarray(data).astype('<i4').tobytes()).hexdigest(),
                     'ch': int(data.shape[1]), 'rate': int(rate), 'frames': int(data.shape[0]), 'bps': BPS.get(info.subtype, 0)}
    except Exception as e:  # noqa: BLE001
        return rel, {'error': str(e)}


def main():
    root, out = sys.argv[1], sys.argv[2]
    jobs = int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else os.cpu_count()
    rels = []
    for top in sorted(os.listdir(root)):
        if top.startswith('$'):
            continue
        for d, _, fs in os.walk(os.path.join(root, top)):
            for f in fs:
                if f.lower().endswith('.flac'):
                    rels.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/'))
    rels.sort()
    with Pool(jobs) as p:
        res = dict(p.imap_unordered(one, [(root, r) for r in rels], chunksize=16))
    errs = [k for k, v in res.items() if 'error' in v]
    json.dump(res, open(out, 'w'))
    print(f'ref-flac: {len(rels)} flac, errors {len(errs)}, libsndfile {sf.__libsndfile_version__}')
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
