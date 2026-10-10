"""cov_nat.py out.json: 複数 scenario を native 単歩実行し, image 内で実行された命令 RVA 集合 + call target RVA 集合を出力。
   (lifter の対象関数 = call target ∪ root。scenario を増やすほど被覆が広がる)"""
import sys, os, json, math, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'native'))
import ottnat as N
N.load()
n_max = 256
buf = N.alloc(n_max * 16 + 0x100); inA = N.alloc(64); ouA = N.alloc(64)
def fill(n, sig=0.0, mono=False):
    N.wr(buf, b''.join(struct.pack('<f', math.sin(i*0.05)*0.7 + math.sin(i*0.011)*0.3 + sig) for i in range(n)) + b''.join(struct.pack('<f', math.cos(i*0.13)*0.5 + sig) for i in range(n)))
    N.wr(inA, struct.pack('<QQ', buf, buf + n*4)); N.wr(ouA, struct.pack('<QQ', buf + n*8, buf + n*12))
def scen(params, n=256, f248=None, p19=None, sig=0.0, nproc=1):
    OBJ = N.alloc(0x10000)
    N.call_cov(0x18011d400, (OBJ, 0))
    for i, v in enumerate(params):
        if v is not None: N.call_cov(0x180120af0, (OBJ, i), (0, 0, N.f32b(v)))
    if p19 is not None: N.call_cov(0x180120af0, (OBJ, 19), (0, 0, N.f32b(p19)))
    N.call_cov(0x180120800, (OBJ,))
    if f248 is not None: N.wr(OBJ + 0x248, bytes([f248]))
    fill(n, sig)
    for _ in range(nproc): N.call_cov(0x18011ec20, (OBJ, inA, ouA, n))
random.seed(1)
S = []
S.append(dict(params=[0.5]*19))
S.append(dict(params=[0.5]*19, f248=0))
for v in (0.0, 0.1, 0.25, 0.75, 1.0): S.append(dict(params=[v]*19)); S.append(dict(params=[v]*19, f248=0))
for i in range(19):
    for v in (0.0, 0.3, 0.8, 1.0):
        p = [0.5]*19; p[i] = v; S.append(dict(params=p)); S.append(dict(params=p, f248=0))
for n in (1, 3, 4, 5, 7, 16, 64, 255): S.append(dict(params=[0.5]*19, n=n)); S.append(dict(params=[0.5]*19, n=n, f248=0))
S.append(dict(params=[0.5]*19, p19=1.0)); S.append(dict(params=[0.5]*19, p19=0.0))
for k in range(12):
    S.append(dict(params=[random.random() for _ in range(19)], f248=random.choice([None, 0, 1]), sig=random.choice([0, 0.3, -0.5]), nproc=2))
insn = set(); cts = set(); failed = []
running = {}
def reap(block):
    global insn, cts
    while running:
        pid, st = os.waitpid(-1, 0 if block else os.WNOHANG)
        if pid == 0: return
        k, r, buf = running.pop(pid)
        while True:
            ch = os.read(r, 1 << 20)
            if not ch: break
            buf.append(ch)
        os.close(r)
        if st != 0:
            failed.append((k, st >> 8, {a: b for a, b in S[k].items() if a != 'params'}, S[k]['params'][:3])); 
        else:
            d = json.loads(b''.join(buf)); insn |= set(d['insn']); cts |= set(d['calltgt'])
        if block: return
import threading
for k, s in enumerate(S):
    while len(running) >= 12:
        reap(True)
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        try:
            scen(**s)
            b = N.cov_bytes(); c = N.cov_ct_bytes()
        except BaseException as e:
            os._exit(3)
        data = json.dumps({'insn': [i for i, v in enumerate(b) if v], 'calltgt': [i for i, v in enumerate(c) if v]}).encode()
        mv = memoryview(data)
        while len(mv):
            n_ = os.write(w, mv); mv = mv[n_:]
        os.close(w); os._exit(0)
    os.close(w)
    running[pid] = (k, r, [])
    # 子が pipe を満杯にしてブロックしないよう, 即 drain 用スレッドを使わず: 結果は小さい (<1MB) ので OK
while running: reap(True)
print('scenarios', len(S), 'failed', len(failed))
for f in failed: print('  FAILED', f)
print('covered instruction addrs', len(insn), 'call targets', len(cts))
json.dump({'insn': sorted(insn), 'calltgt': sorted(cts)}, open(sys.argv[1], 'w'))
