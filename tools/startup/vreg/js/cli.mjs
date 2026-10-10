#!/usr/bin/env node
// vreg CLI (node): FileStore 上のプロファイルに対する .reg の import / export。
//   node js/cli.mjs export <out.reg> [--profile P] [--dir D] [--hives HKCU,HKLM] [--utf8]
//   node js/cli.mjs import <in.reg>  [--profile P] [--dir D]
//   node js/cli.mjs show   [--profile P] [--dir D]           (ライセンス観察・統計)
// 前提: bash build.sh module 済み。 --dir 既定は vreg/work/profiles。
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Vreg } from './vreg.mjs';
import { FileStore } from './store.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const cmd = args.shift();
const opt = (n, d) => { const i = args.indexOf(n); return i < 0 ? d : args.splice(i, 2)[1]; };
const flag = (n) => { const i = args.indexOf(n); if (i < 0) return false; args.splice(i, 1); return true; };
const profile = opt('--profile', 'default');
const dir = opt('--dir', path.join(ROOT, 'work/profiles'));
const hives = opt('--hives', 'HKCU,HKLM').split(',');
const utf8 = flag('--utf8');
const file = args[0];
if (!['export', 'import', 'show'].includes(cmd) || (cmd !== 'show' && !file)) { console.error(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 6).join('\n')); process.exit(2); }

const createModule = (await import(path.join(ROOT, 'build/vreg_wasm.mjs'))).default;
const seed = JSON.parse(readFileSync(path.join(ROOT, 'data/seed.json'), 'utf8'));
const v = await Vreg.create({ createModule, seed, store: new FileStore(dir), profile, flushDelayMs: 0 });
if (cmd === 'export') {
  const out = v.exportReg({ hives, utf16le: !utf8 });
  writeFileSync(file, out);
  console.log(`exported ${file} (${out.length} bytes, ${utf8 ? 'UTF-8' : 'UTF-16LE'}, ${hives.join('+')})`);
} else if (cmd === 'import') {
  const n = v.importReg(readFileSync(file));
  await v.flush(true);
  console.log(`imported ${n} items from ${file} → profile "${profile}" (HKCU は永続化、HKLM は次回起動で seed に戻る)`);
} else console.log(JSON.stringify({ profile, boot: v.bootInfo, stats: v.stats(), registration: v.observeRegistration(), license: v.expectedLicense() }, null, 1));
await v.close();
