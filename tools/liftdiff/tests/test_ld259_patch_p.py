"""LD-259 (#5202): liftdiff run --patch が C ランナーの p= として受理されることの実測テスト。
691dd0 (vmo: rcx=VMT 付きオブジェクト) の wasm ret が、patch の値で変わることを確かめる。
patch を外すと (p= が無視されると) wasm ret が変わらず、この test が落ちる。
素材 (work/m11/boot_state.json・ld_wasm.cjs) が必要。無ければ exit 2 で止める。失敗で非 0 終了。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LD = os.path.join(HERE, '..')
sys.path.insert(0, LD)
STATE = os.path.join(LD, 'work', 'm11', 'boot_state.json')
ARGS = 'i:a:0x1000,i:0x3,i:0x0'


def run(patch):
    out = tempfile.NamedTemporaryFile(suffix='.json', delete=False).name
    cmd = [sys.executable, 'liftdiff.py', 'run', 'targets/m11.json', '--fn', '0x691dd0',
           '--state', STATE, '--nobuild', '--args', ARGS, '--blob', 'vmt', '--json', out]
    if patch:
        cmd += ['--patch', patch]
    subprocess.run(cmd, cwd=LD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    c = json.load(open(out))['cases'][0]
    os.unlink(out)
    return c['outcome'], c.get('diffs', {}).get('ret')


def main():
    if not os.path.exists(STATE):
        print('missing input: %s (oc_artifacts: work-m11 work-liftdiff)' % STATE)
        sys.exit(2)
    base_o, base_r = run(None)
    p_o, p_r = run('a:0x1078:q=0x7')
    assert base_o == 'diff' and p_o == 'diff', (base_o, p_o)
    assert base_r and p_r and p_r['wasm_rax'] != base_r['wasm_rax'], ('p= が効いていない', base_r, p_r)
    print('PASS test_ld259_patch_p wasm_rax %s -> %s' % (base_r['wasm_rax'], p_r['wasm_rax']))


if __name__ == '__main__':
    main()
