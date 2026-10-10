// Event dump: human readable (default) or JSON.
// usage: node cli/dump.ts <file.flp|fst|fsc> [--json] [--limit N] [--ids 156,201] [--offsets] [--summary]
import { readFileSync } from 'node:fs';
import { parseFlp } from '../src/flp.ts';
import { dumpText, dumpJson } from '../src/format.ts';
import { summarize } from '../src/summary.ts';

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith('--') && !/^\d/.test(a) && !args[args.indexOf(a) - 1]?.startsWith('--'));
if (!file) {
  console.error('usage: node cli/dump.ts <file> [--json] [--limit N] [--ids a,b] [--offsets] [--summary]');
  process.exit(2);
}
const opt = (name: string): string | undefined => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const limit = opt('--limit') ? parseInt(opt('--limit')!, 10) : undefined;
const ids = opt('--ids') ? new Set(opt('--ids')!.split(',').map((x) => parseInt(x, x.startsWith('0x') ? 16 : 10))) : undefined;
const f = parseFlp(readFileSync(file));
if (args.includes('--summary')) console.log(JSON.stringify(summarize(f), null, 1));
else if (args.includes('--json')) console.log(JSON.stringify(dumpJson(f, { limit, ids }), null, 1));
else console.log(dumpText(f, { limit, ids, offsets: args.includes('--offsets') }));
