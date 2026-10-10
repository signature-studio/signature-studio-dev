// 検証用ダミーデータ生成 (/dev/urandom のみ。実資産は一切使わない)。
//   out: work/data/{big-100m.bin, part-24m.bin, over-26m.bin(デプロイ対象外), c/xx/<id>.raw x100, x.br, x.zst, x.raw, probe.wasm, pixel.png, probe-manifest.json}
// manifest は E (tools/assets) の chunk 配信 (c/<id[0:2]>/<id>.<ext>, id = sha256 先頭 128bit hex, 1MiB) と同じ命名にしてある。
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, '../work/data');
const MiB = 1 << 20;
const N_CHUNKS = Number(process.env.N_CHUNKS ?? 100);
const BIG_MIB = Number(process.env.BIG_MIB ?? 100);

fs.mkdirSync(OUT, { recursive: true });
const fd = fs.openSync('/dev/urandom', 'r');
function rnd(n) {
  const b = Buffer.alloc(n);
  let o = 0;
  while (o < n) o += fs.readSync(fd, b, o, n - o, null);
  return b;
}
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
const w = (rel, buf) => {
  const p = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, buf);
};

const manifest = { created: new Date().toISOString(), miB: MiB, files: {}, chunks: [] };

// big / part (分割 piece hash = 1MiB 毎の sha256 hex。ブラウザ側で Range 取得の中身を検証する)
const big = rnd(BIG_MIB * MiB);
w('big-100m.bin', big);
const part = big.subarray(0, 24 * MiB);
w('part-24m.bin', part);
w('../over-26m.bin', rnd(26 * MiB));
const pieces = (b) => Array.from({ length: Math.ceil(b.length / MiB) }, (_, i) => sha(b.subarray(i * MiB, (i + 1) * MiB)));
manifest.files['big-100m.bin'] = { size: big.length, pieces: pieces(big), sha256: sha(big) };
manifest.files['part-24m.bin'] = { size: part.length, pieces: pieces(part), sha256: sha(part) };

for (let i = 0; i < N_CHUNKS; i++) {
  const b = rnd(MiB);
  const id = sha(b).slice(0, 32);
  const rel = `c/${id.slice(0, 2)}/${id}.raw`;
  w(rel, b);
  manifest.chunks.push({ path: rel, id, size: b.length });
}

// 拡張子別 Content-Type / Content-Encoding の挙動確認用 (小)
const txt = Buffer.from('signature-studio hosting probe '.repeat(200));
w('x.raw', txt);
w('x.br', zlib.brotliCompressSync(txt));
w('x.zst', zlib.zstdCompressSync ? zlib.zstdCompressSync(txt) : txt);
manifest.files['x.raw'] = { size: txt.length, sha256: sha(txt) };
manifest.files['x.br'] = { size: fs.statSync(path.join(OUT, 'x.br')).size };
manifest.files['x.zst'] = { size: fs.statSync(path.join(OUT, 'x.zst')).size };

// 25MiB 超の単一 wasm を想定した分割配信テスト: 30MiB の custom section を持つ有効な wasm を 3 分割 (各 10MiB) し、クライアントで連結して compileStreaming する
{
  const payload = rnd(30 * MiB);
  const sec = Buffer.concat([Buffer.from([3, 0x70, 0x61, 0x64]), payload]); // name="pad" + payload
  const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return Buffer.from(o); };
  const wasm = Buffer.concat([Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00, 0x00]), leb(sec.length), sec]);
  const parts = [];
  for (let i = 0; i * 10 * MiB < wasm.length; i++) {
    const b = wasm.subarray(i * 10 * MiB, (i + 1) * 10 * MiB);
    w(`wasm-parts/big.wasm.p${i}`, b);
    parts.push({ path: `wasm-parts/big.wasm.p${i}`, size: b.length });
  }
  manifest.wasmParts = { parts, total: wasm.length, payload: payload.length, sha256: sha(wasm) };
}

// 最小の有効 wasm (空モジュール) と 1x1 PNG
w('probe.wasm', Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]));
w('pixel.png', Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64'));
manifest.files['probe.wasm'] = { size: 8 };

w('probe-manifest.json', JSON.stringify(manifest));
fs.closeSync(fd);
console.log(JSON.stringify({ out: OUT, big: big.length, chunks: manifest.chunks.length, bytes: big.length + part.length + N_CHUNKS * MiB }));
