// Event-level diff of two FLP/FST files (volatile ids masked). usage: node cli/flpdiff.ts a.flp b.flp [--no-mask]
import { readFileSync } from 'node:fs';
import { parseFlp } from '../src/flp.ts';
import { diffFlp } from '../src/flpdiff.ts';

const [fa, fb] = process.argv.slice(2).filter((x) => !x.startsWith('--'));
if (!fa || !fb) {
  console.error('usage: node cli/flpdiff.ts a.flp b.flp [--no-mask]');
  process.exit(2);
}
const d = diffFlp(parseFlp(readFileSync(fa)), parseFlp(readFileSync(fb)), process.argv.includes('--no-mask') ? new Set() : undefined);
console.log(JSON.stringify(d, null, 1));
process.exit(d.identical ? 0 : 1);
