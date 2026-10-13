// SlotCache 回帰: 末尾 slot の chunk が chunkSize 未満 (ファイル長が slotBytes の整数倍でない) でも再起動で復元される (#70)。
//   node test/slotcache-tail-test.ts          既定: 修正版 SlotCache を検査 (期待: 復元 5/5)
//   node test/slotcache-tail-test.ts --neg    旧 scan (floor(size / slotBytes)) を模した検査 (期待: 末尾 slot が落ちて exit 1)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { SlotCache } from '../vfs/cache.ts';
import { openNodeSyncFile } from '../vfs/node-file.ts';

const NEG = process.argv.includes('--neg');
const CS = 1 << 16;
const dir = fs.mkdtempSync(path.join(process.env.TMPDIR ?? os.tmpdir(), 'slot-tail-'));
const f = path.join(dir, 'c.bin');
const id = (i: number) => i.toString(16).padStart(32, '0');
const data = (i: number, n: number) => Uint8Array.from({ length: n }, (_, k) => (k * 7 + i) & 255);

const a = new SlotCache(openNodeSyncFile(f), CS, 16);
const lens = [CS, CS, CS, CS, 1234]; // 末尾だけ短い
lens.forEach((n, i) => a.put(id(i), data(i, n)));
a.close();
let size = fs.statSync(f).size;
if (NEG) {
  // 旧実装の復元条件を再現: 末尾 slot が完全長に満たなければファイルを slotBytes の整数倍へ切り詰めて開き直す
  const slotBytes = (a as any).slotBytes as number;
  size = Math.floor(size / slotBytes) * slotBytes;
  fs.truncateSync(f, size);
}
const b = new SlotCache(openNodeSyncFile(f), CS, 16);
let ok = 0;
lens.forEach((n, i) => {
  const dst = new Uint8Array(n);
  if (b.has(id(i)) && b.readRange(id(i), 0, dst, 0, n) && dst.every((v, k) => v === ((k * 7 + i) & 255))) ok++;
});
b.close();
fs.rmSync(dir, { recursive: true, force: true });
console.log(`slot-tail restore ${ok}/${lens.length} (file ${size} B, mode ${NEG ? 'neg' : 'pass'})`);
process.exit(ok === lens.length ? 0 : 1);
