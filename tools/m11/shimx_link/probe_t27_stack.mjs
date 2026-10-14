// #1630 SHX-T27: stderr に出る特定の行 (既定 "[m11][VA] #1" と MessageBoxA) の時点の wasm 呼出 stack を採り、export 名で注釈する。
//   node probe_t27_stack.mjs <m11_sx_*.cjs> [--match <部分文字列>]...
// printErr は wasm から JS import 経由で呼ばれるため、Error().stack に wasm frame が入る。
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const matches = [];
for (let i = 3; i < process.argv.length; i++) if (process.argv[i] === '--match') matches.push(process.argv[++i]);
if (!matches.length) matches.push('[m11][VA] #', '[m11][MessageBox');

function exportNames(file) {   // wasm の Export section を直接読む (wasm-objdump 不要)
  const b = fs.readFileSync(file); let p = 8;
  const leb = () => { let r = 0, s = 0, x; do { x = b[p++]; r += (x & 0x7f) * 2 ** s; s += 7; } while (x & 0x80); return r; };
  const names = {};
  while (p < b.length) {
    const id = b[p++]; const len = leb(); const end = p + len;
    if (id === 7) {
      const n = leb();
      for (let i = 0; i < n; i++) {
        const l = leb(); const nm = b.toString('utf8', p, p + l); p += l;
        const kind = b[p++]; const idx = leb();
        if (kind === 0) names[idx] = nm;
      }
    }
    p = end;
  }
  return names;
}
const names = exportNames(cjs + '.wasm');
Error.stackTraceLimit = 80;
const hits = [];
const m2 = await import(cjs);
const mod = await (m2.default || m2)({
  printErr: (s) => {
    s = String(s);
    if (matches.some((m) => s.includes(m))) {
      const st = new Error().stack.split('\n').filter((l) => l.includes('wasm-function'))
        .map((l) => { const m = l.match(/wasm-function\[(\d+)\]:(0x[0-9a-f]+)/); return m ? `${names[m[1]] || '?'}@${m[2]}` : l.trim(); });
      hits.push({ line: s.slice(0, 160), stack: st });
    }
  },
});
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
let threw = null;
try { mod._m11_boot_enter(0n, 1n); } catch (e) { threw = (e && e.message) || String(e); }
console.log(JSON.stringify({ threw, hits }, null, 1));
