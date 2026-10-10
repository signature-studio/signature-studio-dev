// 有効な wasm (空モジュール + 乱数 custom section) を MB 単位で作る。node deploy/probe/make-wasm.mjs <MB> <out>
import { randomBytes } from "node:crypto";
import { writeFileSync } from "node:fs";
const mb = Number(process.argv[2]);
const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return Buffer.from(o); };
const name = Buffer.from("pad");
const payload = Buffer.concat([Buffer.from([name.length]), name, randomBytes(mb * 1024 * 1024)]);
writeFileSync(process.argv[3], Buffer.concat([Buffer.from([0, 0x61, 0x73, 0x6d, 1, 0, 0, 0, 0]), leb(payload.length), payload]));
