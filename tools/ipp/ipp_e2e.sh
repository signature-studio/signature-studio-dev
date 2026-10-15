#!/usr/bin/env bash
# tools/ipp 1 コマンド再現: 素材 → スライス分割 → ロード側/使用関数集合の静的解析 → 実 IPP(win DLL をネイティブ実行)との差分テスト → wasm 化 → node 突合
# usage: bash tools/ipp/ipp_e2e.sh      (所要 ~2 分。大物は tools/ipp/work/ に出力 = gitignore)
set -euo pipefail
cd "$(dirname "$0")"; HERE=$PWD; W=$HERE/work; mkdir -p "$W" data /tmp/opencode
source "$HERE/../shared/env.sh"
APP="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents"
DLL=$FL_WIN64_DIR/extracted/block24356_PE.bin
for f in "$APP/Resources/FL/Shared/dsp_ippv2_x64.dylib" "$APP/Libs/FLEngine_x64.dylib" "$DLL" "$FL_WIN64_DIR/extracted/block00031_PE.bin"; do [ -f "$f" ] || { echo "missing input: $f"; exit 2; }; done
step() { echo; echo "## $*"; }
step "1. universal Mach-O を分割 (lipo 代用)"
python3 fat_split.py "$APP/Resources/FL/Shared/dsp_ippv2_x64.dylib" "$W" dsp_ippv2 | sed 's/^/  /'
python3 fat_split.py "$APP/Libs/FLEngine_x64.dylib" "$W" FLEngine | sed 's/^/  /'
step "2. ローダ表 (FLEngine の UTF-16 リテラル列) と export 集合"
python3 ipp_names.py | sed 's/^/  /'; python3 exports.py | sed 's/^/  /'
step "3. ロード方式の静的証拠 (dlopen/dlsym, legacy90 fallback, 失敗時の挙動リテラル)"
python3 loader_evidence.py | cut -c1-230 | sed 's/^/  /'
step "4. 使用関数集合: mac x86_64/arm64 全 143 モジュール + win64 150 モジュール (capstone/命令語で call・関数ポインタ読出を分類)"
python3 discover.py | sed 's/^/  /'; python3 scan_all.py | sed 's/^/  /'; python3 scan_win.py | head -3 | cut -c1-200 | sed 's/^/  /'; python3 analyze_usage.py | head -3 | sed 's/^/  /'
step "5. arm64 スライス: 各 export が呼ぶ Accelerate/libc の対応表"
llvm-objdump --macho -d --no-show-raw-insn "$W/dsp_ippv2.arm64" > "$W/dsp_ippv2.arm64.dis" 2>/dev/null; python3 a64_map.py | sed 's/^/  /'
step "6. 実 Intel IPP (win64 dsp_ippv2_x64.dll を最小 PE ローダで Linux ネイティブ実行) との差分テスト基盤をビルド"
mkdir -p "$W/bin"; CF="-O2 -ffp-contract=off -fno-fast-math"
gcc $CF -o "$W/bin/ipp_ref" ref/ipp_ref.c ref/pe_load.c src/ipp_min.c -lm; gcc $CF -o "$W/bin/ipp_acc" ref/ipp_acc.c ref/pe_load.c src/ipp_min.c -lm
gcc $CF -o "$W/bin/ipp_bench" ref/ipp_bench.c ref/pe_load.c src/ipp_min.c -lm; gcc $CF -o "$W/bin/ipp_fft_ref" ref/ipp_fft_ref.c ref/pe_load.c shim/fft/ipp_fft_pffft.c shim/fft/pffft/pffft.c shim/fft/pffft/pffft_double.c shim/fft/pffft/pffft_common.c src/ipp_min.c -lm   # FFT 実装は shim/fft (CAB-139)
ALL=0xFFFFFFFFFFFFFFFF
"$W/bin/ipp_ref" err $DLL > "$W/err_grid.json"; tail -1 "$W/err_grid.json" | sed 's/^/  /'
"$W/bin/ipp_ref" cmp $DLL $ALL 2>/dev/null > "$W/cmp_avx512.json"; SPEC=1 "$W/bin/ipp_ref" cmp $DLL $ALL 2>/dev/null > "$W/cmp_avx512_spec.json"
python3 - <<'PY' | sed 's/^/  /'
import json
t=open('work/cmp_avx512.json').read(); r=json.loads(t[t.index('[\n'):])
print('cmp(AVX512 path): functions',len(r),' bit-exact functions',sum(1 for x in r if x['differ']==0 and x['status_mismatch']==0),' inexact:',[x['fn'] for x in r if x['differ'] or x['status_mismatch']])
PY
python3 - <<'PY'
import subprocess, json, os
D=os.path.join(os.environ['FL_WIN64_DIR'], 'extracted/block24356_PE.bin'); B='work/bin/ipp_ref'
pairs=[('0xFFFFFFFFFFFFFFFF','0x1FFFF','avx512_vs_avx2'),('0x1FFFF','0x1FF','avx2_vs_avx'),('0x1FF','0xFF','avx_vs_sse42'),('0xFF','0x1F','sse42_vs_ssse3'),('0x1F','0x7','ssse3_vs_sse2')]
out={}
for a,b,n in pairs:
    t=subprocess.run([B,'isa',D,a,b],capture_output=True,text=True).stdout; r=json.loads(t[t.index('[\n'):])
    out[n]={x['fn']:{'differ':x['differ'],'max_ulp':x['max_ulp'],'max_rel':x['max_rel']} for x in r if x['differ']}
json.dump(out,open('work/isa_diff.json','w'),indent=1)
print('  実IPPのISA経路間で出力が異なる関数:', {k:sorted(v) for k,v in out.items()})
PY
"$W/bin/ipp_acc" $DLL > "$W/acc.json"; python3 -c "
import json;d=json.load(open('work/acc.json'))['acc']
for r in d: print('  acc',r['impl'].ljust(16),'exp_bits',r['exp_bits'],'sqrt_bits',r['sqrt_bits'],'slope_err(eps24)',r['slope_in_eps24'])"
mkdir -p "$W/golden"; "$W/bin/ipp_ref" gen $DLL $ALL "$W/golden" > "$W/golden/native_summary.json" 2>/dev/null; "$W/bin/ipp_fft_ref" $DLL "$W/golden" | sed 's/^/  fft native: /'
step "7. wasm 化 (emcc: scalar と simd128) と node 突合"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 gen_table.py | sed 's/^/  /'; ./build_wasm.sh | sed 's/^/  /'; EXTRA=-msimd128 OUT="$W/ipp_min_simd.wasm" ./build_wasm.sh | sed 's/^/  /'
node ipp_wasm_cmp.mjs "$W/ipp_min.wasm" "$W/golden" "$W/wasm_cmp.json" | tail -2 | sed 's/^/  scalar: /' || true
node ipp_wasm_cmp.mjs "$W/ipp_min_simd.wasm" "$W/golden" "$W/wasm_cmp_simd.json" | tail -2 | sed 's/^/  simd128: /' || true
node ipp_wasm_fft.mjs "$W/ipp_min.wasm" "$W/golden" "$W/wasm_fft.json" | sed 's/^/  /' || true
"$W/bin/ipp_bench" $DLL $ALL > "$W/bench_native.json"; node ipp_wasm_bench.mjs "$W/ipp_min.wasm" "$W/ipp_min_simd.wasm" > "$W/bench_wasm.json"
python3 -c "
import json;n=json.load(open('work/bench_native.json'))['ns_per_call'];w=json.load(open('work/bench_wasm.json'))
for k,v in n.items():
    if k=='_': continue
    print('  bench',k.ljust(26),'IPP(avx512)',v['ipp'],'ns | wasm scalar',w['ipp_min.wasm'].get(k),'| wasm simd128',w['ipp_min_simd.wasm'].get(k))"
step "8. 集約・判定"
python3 e2e_check.py
