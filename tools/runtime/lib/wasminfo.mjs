// wasm バイナリの最小パーサ: memory 記述 (import/定義/export) と import/export 数を取り出す。
function leb(b, o) { let r = 0n, s = 0n, i = o; for (;;) { const x = b[i++]; r |= BigInt(x & 0x7f) << s; s += 7n; if (!(x & 0x80)) break; } return [r, i]; }
function str(b, o) { const [n, i] = leb(b, o); const len = Number(n); return [Buffer.from(b.subarray(i, i + len)).toString("utf8"), i + len]; }
function limits(b, o) {
  const flag = b[o++]; let initial, max = null;
  [initial, o] = leb(b, o);
  if (flag & 1) [max, o] = leb(b, o);
  return [{ initial: Number(initial), maximum: max === null ? null : Number(max), shared: !!(flag & 2), memory64: !!(flag & 4) }, o];
}
export function wasmInfo(buf) {
  const b = new Uint8Array(buf);
  if (b[0] !== 0 || b[1] !== 0x61 || b[2] !== 0x73 || b[3] !== 0x6d) throw new Error("not wasm");
  let o = 8; const info = { imported: false, exported: false, shared: false, memory64: false, initialPages: 0, maximumPages: null, importCount: 0, exportCount: 0 };
  while (o < b.length) {
    const id = b[o++]; let size; [size, o] = leb(b, o); const end = o + Number(size); let p = o;
    if (id === 2) { // import
      let n; [n, p] = leb(b, p); info.importCount = Number(n);
      for (let k = 0; k < Number(n); k++) {
        let _m, _f; [_m, p] = str(b, p); [_f, p] = str(b, p); const kind = b[p++];
        if (kind === 0) { [, p] = leb(b, p); }
        else if (kind === 1) { p++; [, p] = [0, limits(b, p)[1]]; }
        else if (kind === 2) { let L; [L, p] = limits(b, p); info.imported = true; Object.assign(info, { shared: L.shared, memory64: L.memory64, initialPages: L.initial, maximumPages: L.maximum }); }
        else if (kind === 3) { p += 2; }
        else if (kind === 4) { p++; [, p] = leb(b, p); }
      }
    } else if (id === 5) { // memory
      let n; [n, p] = leb(b, p); let L; [L, p] = limits(b, p);
      Object.assign(info, { shared: L.shared, memory64: L.memory64, initialPages: L.initial, maximumPages: L.maximum });
    } else if (id === 7) { // export
      let n; [n, p] = leb(b, p); info.exportCount = Number(n);
      for (let k = 0; k < Number(n); k++) { let nm; [nm, p] = str(b, p); const kind = b[p++]; [, p] = leb(b, p); if (kind === 2 && nm === "memory") info.exported = true; }
    }
    o = end;
  }
  return info;
}
