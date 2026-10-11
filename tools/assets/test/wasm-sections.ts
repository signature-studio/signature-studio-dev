// wasm の section 走査だけで export/import 数を数える最小パーサ (WebAssembly API を使わない独立経路)。
// 検算対象: Chrome の WebAssembly.Module.exports()/imports() の戻り値。
//   使い方: node test/wasm-sections.ts <file.wasm>
export interface WasmSections {
  exports: number;
  imports: number;
  importModules: string[];
  exportKinds: Record<string, number>;
  importKinds: Record<string, number>;
  sectionSizes: Record<string, number>;
}

function readU8(b: Uint8Array, o: number): number {
  return b[o];
}

/** unsigned LEB128 */
export function readU(b: Uint8Array, o: number): { val: number; next: number } {
  let r = 0;
  let s = 0;
  let p = o;
  for (;;) {
    const x = b[p++];
    r += (x & 0x7f) * 2 ** s;
    if ((x & 0x80) === 0) break;
    s += 7;
    if (s > 35) throw new Error('leb128 too long');
  }
  return { val: r, next: p };
}

/** name (vec 要素 1 個: len + bytes) */
export function readName(b: Uint8Array, o: number): { val: string; next: number } {
  const n = readU(b, o);
  const s = Buffer.from(b.subarray(n.next, n.next + n.val)).toString('utf8');
  return { val: s, next: n.next + n.val };
}

const SEC_NAMES: Record<number, string> = {
  0: 'custom', 1: 'type', 2: 'import', 3: 'function', 4: 'table', 5: 'memory', 6: 'global', 7: 'export',
  8: 'start', 9: 'element', 10: 'code', 11: 'data', 12: 'datacount', 13: 'tag',
};

export function parseWasmSections(b: Uint8Array): WasmSections {
  if (b.length < 8 || b[0] !== 0x00 || b[1] !== 0x61 || b[2] !== 0x73 || b[3] !== 0x6d) throw new Error('not wasm');
  const ver = (b[4] | (b[5] << 8) | (b[6] << 16) | (b[7] << 24)) >>> 0;
  if (ver !== 1) throw new Error('wasm version ' + ver);
  let p = 8;
  const out: WasmSections = { exports: 0, imports: 0, importModules: [], exportKinds: {}, importKinds: {}, sectionSizes: {} };
  while (p < b.length) {
    const id = readU8(b, p++);
    const sz = readU(b, p);
    p = sz.next;
    const end = p + sz.val;
    out.sectionSizes[SEC_NAMES[id] ?? String(id)] = sz.val;
    if (id === 2) {
      // import section: vec(import) = module, name, desc
      const cnt = readU(b, p);
      let q = cnt.next;
      for (let i = 0; i < cnt.val; i++) {
        const m = readName(b, q);
        const n = readName(b, m.next);
        const kind = readU8(b, n.next);
        const kn = ['func', 'table', 'memory', 'global', 'tag'][kind] ?? String(kind);
        out.imports++;
        out.importKinds[kn] = (out.importKinds[kn] ?? 0) + 1;
        if (!out.importModules.includes(m.val)) out.importModules.push(m.val);
        // desc を読み飛ばす (kind 別)
        let q2 = n.next + 1;
        if (kind === 0) {
          const t = readU(b, q2);
          q2 = t.next;
        } else if (kind === 1) {
          const et = readU8(b, q2);
          const fl = readU(b, q2 + 1);
          let mn = readU(b, fl.next);
          let mx = mn.next;
          if (fl.val & 0x01) {
            const m2 = readU(b, mn.next);
            mx = m2.next;
          }
          q2 = mx;
        } else if (kind === 2) {
          // メモリ limits: flags, min, [max if flags & 1]
          const fl = readU(b, q2);
          const mn = readU(b, fl.next);
          q2 = fl.val & 0x01 ? readU(b, mn.next).next : mn.next;
        } else if (kind === 3) {
          const vt = readU8(b, q2);
          const mut = readU8(b, q2 + 1);
          q2 = q2 + 2;
        } else if (kind === 4) {
          const attr = readU8(b, q2);
          q2 = q2 + 1;
        } else throw new Error('unknown import kind ' + kind);
        q = q2;
      }
    } else if (id === 7) {
      const cnt = readU(b, p);
      let q = cnt.next;
      for (let i = 0; i < cnt.val; i++) {
        const n = readName(b, q);
        const kind = readU8(b, n.next);
        const kn = ['func', 'table', 'memory', 'global', 'tag'][kind] ?? String(kind);
        if (kind > 4) throw new Error('unknown export kind ' + kind + ' at ' + q);
        out.exports++;
        out.exportKinds[kn] = (out.exportKinds[kn] ?? 0) + 1;
        // export の desc は kind に関わらず index 1 個 (LEB)。import は kind 別の型記述なので別扱び
        q = readU(b, n.next + 1).next;
      }
    }
    p = end;
  }
  return out;
}

import fs from 'node:fs';

if (import.meta.url === `file://${process.argv[1]}`) {
  const b = new Uint8Array(fs.readFileSync(process.argv[2]));
  const s = parseWasmSections(b);
  console.log(JSON.stringify({ ...s, importModules: s.importModules.join(',') }, null, 1));
}
