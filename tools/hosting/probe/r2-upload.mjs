// r2-upload.mjs <bucket> — work/r2/upload.json の全キーを `cf r2 objects put` (OAuth のみ・1件300MB上限・Content-Typeのみ設定可) で並列アップロード
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const ex = promisify(execFile);
const here = path.dirname(fileURLToPath(import.meta.url));
const R = path.resolve(here, '../work/r2');
const bucket = process.argv[2];
if (!bucket?.startsWith('signature-studio-')) throw new Error('bucket must start with signature-studio-');
const list = JSON.parse(fs.readFileSync(path.join(R, 'upload.json'), 'utf8'));
const t0 = Date.now();
let done = 0, bytes = 0, failed = [];
async function worker() {
  for (let e = list.shift(); e; e = list.shift()) {
    const f = path.join(R, e.key);
    try {
      await ex('cf', ['r2', 'objects', 'put', e.key, '--bucket-name', bucket, '--file', f, '--content-type', e.contentType], { maxBuffer: 1 << 24 });
      bytes += fs.statSync(f).size;
    } catch (err) { failed.push({ key: e.key, err: String(err.stderr ?? err.message).slice(0, 300) }); }
    done++;
  }
}
await Promise.all(Array.from({ length: Number(process.env.CONC ?? 8) }, worker));
const sec = (Date.now() - t0) / 1000;
console.log(JSON.stringify({ done, failed: failed.length, MB: +(bytes / 1048576).toFixed(1), sec: +sec.toFixed(1), MBps: +(bytes / 1048576 / sec).toFixed(1), firstFail: failed[0] }));
