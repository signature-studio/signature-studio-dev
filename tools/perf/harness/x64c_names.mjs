// emcc glue (.cjs) から wasm export 名の対応 (minify 後の名前) を引く。 node x64c_names.mjs <dir> で <v>.names.json を生成。
// minify は -O2 以上 (assertion 無し) の glue のみ: `Module["_ott_run"]=wasmExports["l"]` 形式。 それ以外 (o0/o1 の assertion 付き glue) は恒等。
import fs from 'node:fs';
import path from 'node:path';
const IDENT = { memory: 'memory', ctors: '__wasm_call_ctors', ott_data_install: 'ott_data_install', ott_run: 'ott_run' };
export function namesFromGlue(cjs) {
  const t = fs.readFileSync(cjs, 'utf8');
  const g = (re, what) => { const m = t.match(re); if (!m) throw new Error(`${cjs}: ${what} が glue に無い`); return m[1]; };
  const run = t.match(/Module\["_ott_run"\]=wasmExports\["([\w$]+)"\]/);
  if (!run || run[1] === 'ott_run') return { ...IDENT };
  return {
    memory: g(/memory=wasmMemory=wasmExports\["([\w$]+)"\]/, 'memory'),
    ctors: g(/initRuntime\(\)\{runtimeInitialized=true;wasmExports\["([\w$]+)"\]\(\)/, '__wasm_call_ctors'),
    ott_data_install: g(/Module\["_ott_data_install"\]=wasmExports\["([\w$]+)"\]/, 'ott_data_install'),
    ott_run: run[1],
  };
}
if (process.argv[1] === new URL(import.meta.url).pathname && process.argv[2]) {
  for (const f of fs.readdirSync(process.argv[2]).filter((x) => x.endsWith('.cjs'))) {
    const n = namesFromGlue(path.join(process.argv[2], f));
    fs.writeFileSync(path.join(process.argv[2], f.replace(/\.cjs$/, '.names.json')), JSON.stringify(n));
    console.log(f, JSON.stringify(n));
  }
}
