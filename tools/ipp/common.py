import glob, os, re, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
def implemented_names():
    """src/ipp_*.c を gcc -c → nm で実装済み ipp* シンボルを得る (マクロ生成も拾う)。"""
    os.makedirs('/tmp/opencode', exist_ok=True); names = set()
    for f in sorted(glob.glob(f'{HERE}/src/ipp_*.c')):
        subprocess.run(['gcc', '-c', '-O0', '-o', '/tmp/opencode/_ipp_nm.o', f], check=True, capture_output=True)
        out = subprocess.run(['nm', '-g', '--defined-only', '/tmp/opencode/_ipp_nm.o'], capture_output=True, text=True).stdout
        names |= set(re.findall(r'\sT\s(ipp\w+)', out))
    return names
