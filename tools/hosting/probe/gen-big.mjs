// gen-big.mjs [N=2400] — Static Assets の規模検証 (既定 2400 x 1MiB = 2.34GiB) 用ダミー chunk を /dev/urandom から生成し work/dist-big に配置
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, '../work/dist-big');
const N = Number(process.argv[2] ?? 2400), MiB = 1 << 20;
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const fd = fs.openSync('/dev/urandom', 'r');
const list = [];
const buf = Buffer.alloc(MiB);
for (let i = 0; i < N; i++) {
  let o = 0;
  while (o < MiB) o += fs.readSync(fd, buf, o, MiB - o, null);
  const id = crypto.createHash('sha256').update(buf).digest('hex').slice(0, 32);
  const rel = `d/c/${id.slice(0, 2)}/${id}.raw`;
  fs.mkdirSync(path.join(OUT, path.dirname(rel)), { recursive: true });
  fs.writeFileSync(path.join(OUT, rel), buf);
  list.push(id);
}
fs.writeFileSync(path.join(OUT, 'd/ids.json'), JSON.stringify(list));
fs.writeFileSync(path.join(OUT, 'index.html'), 'big probe\n');
fs.writeFileSync(path.join(OUT, '_headers'), '/*\n  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Embedder-Policy: require-corp\n  Cross-Origin-Resource-Policy: same-origin\n/d/c/*\n  Cache-Control: public, max-age=31536000, immutable\n');
console.log(JSON.stringify({ out: OUT, n: N, bytes: N * MiB }));
