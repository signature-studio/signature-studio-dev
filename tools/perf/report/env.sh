#!/usr/bin/env bash
# 測定環境を results/env.json に記録
cd "$(dirname "$0")/.."; export PATH=$HOME/.local/share/pnpm/bin:$PATH
python3 - <<PY > results/env.json
import json,subprocess,os
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True).stdout.strip()
print(json.dumps({
 'cpu': sh("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip(), 'cores': os.cpu_count(),
 'mem_total_gb': sh("free -g | awk '/Mem:/{print \$2}'"), 'kernel': sh('uname -r'),
 'node': sh('node --version'), 'node_v8': sh('node -p process.versions.v8'),
 'chrome': sh('/usr/bin/google-chrome --version'), 'emcc': sh('/opt/emsdk/upstream/emscripten/emcc --version | head -1'),
 'binaryen': sh('/opt/emsdk/upstream/bin/wasm-opt --version'), 'date': sh('date -Is'),
 'loadavg_at_record': open('/proc/loadavg').read().split()[:3],
 'note': '16 コアを他の subagent と共有 (loadavg 5〜25)。p50 は軽負荷時の最小値寄り、p99/max は負荷の影響を受ける。',
}, ensure_ascii=False, indent=1))
PY
cat results/env.json
