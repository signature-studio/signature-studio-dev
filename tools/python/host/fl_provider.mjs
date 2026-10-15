// flprov.wasm (provider/ の C 実装 `fl_api_call`) を engine.call(name, args) インタフェースで包む。
//   host/fl_mock.mjs の createMockEngine() と差し替え可能: FlPython.create({ engine, ids, ... })
// JS → 16B スロット変換 (flhost_lib.js の逆)。戻り型は C 側が決める (D=float / I=int)。
const SLOT = 16;
const te = new TextEncoder();

export async function createWasmEngine({ flprovUrl, ids }) {
  const M = await (await import(String(flprovUrl))).default({
    locateFile: (p) => new URL(p, flprovUrl).pathname,
  });
  M._fl_engine_reset();
  const idOf = new Map(ids.map((n, i) => [n, i]));
  const MAXARG = 32;
  const argv = M._malloc(MAXARG * SLOT);
  const ret = M._malloc(SLOT);
  const record = [];
  const td = new TextDecoder();

  const call = (name, args) => {
    record.push([name, args]);
    const fn = idOf.get(name);
    if (fn === undefined) throw Object.assign(new Error(`unknown flapi ${name}`), { flCode: 2 });
    if (args.length > MAXARG) throw Object.assign(new Error("too many arguments"), { flCode: 5 });
    const owned = [];
    let dv = new DataView(M.HEAPU8.buffer);
    M.HEAPU8.fill(0, argv, argv + args.length * SLOT);
    const putBytes = (bytes) => {
      const p = M._malloc(bytes.length + 1);
      M.HEAPU8.set(bytes, p);
      M.HEAPU8[p + bytes.length] = 0;
      owned.push(p);
      dv = new DataView(M.HEAPU8.buffer); // malloc で memory grow しうる
      return p;
    };
    for (let i = 0; i < args.length; i++) {
      const a = args[i];
      const o = argv + i * SLOT;
      if (a === null || a === undefined) M.HEAPU8[o] = 78;
      else if (typeof a === "boolean") { M.HEAPU8[o] = 66; dv.setBigInt64(o + 8, a ? 1n : 0n, true); }
      else if (typeof a === "number") {
        if (Number.isInteger(a)) { M.HEAPU8[o] = 73; dv.setBigInt64(o + 8, BigInt(a), true); }
        else { M.HEAPU8[o] = 68; dv.setFloat64(o + 8, a, true); }
      } else if (typeof a === "string") {
        const b = te.encode(a);
        const p = putBytes(b);
        M.HEAPU8[o] = 83; dv.setUint32(o + 8, p, true); dv.setUint32(o + 12, b.length, true);
      } else if (a instanceof Uint8Array) {
        const p = putBytes(a);
        M.HEAPU8[o] = 89; dv.setUint32(o + 8, p, true); dv.setUint32(o + 12, a.length, true);
      } else if (typeof a === "object" && "__cb" in a) { M.HEAPU8[o] = 70; dv.setBigInt64(o + 8, BigInt(a.__cb), true); }
      else throw Object.assign(new Error("unsupported argument"), { flCode: 5 });
    }
    try {
      const rc = M._fl_api_call(fn, argv, args.length, ret);
      if (rc !== 0) throw Object.assign(new Error(`fl_api_call transport error rc=${rc}`), { flCode: 2 });
      dv = new DataView(M.HEAPU8.buffer);
      const tag = String.fromCharCode(M.HEAPU8[ret]);
      const text = () => {
        const p = dv.getUint32(ret + 8, true), l = dv.getUint32(ret + 12, true);
        const s = td.decode(M.HEAPU8.subarray(p, p + l));
        M._free(p);
        return s;
      };
      switch (tag) {
        case "N": return null;
        case "B": return dv.getBigInt64(ret + 8, true) !== 0n;
        case "I": return Number(dv.getBigInt64(ret + 8, true));
        case "D": return { t: "D", v: dv.getFloat64(ret + 8, true) };
        case "S": return text();
        case "J": return JSON.parse(text());
        case "E": { const code = dv.getInt32(ret + 4, true); throw Object.assign(new Error(text()), { flCode: code }); }
        default: throw Object.assign(new Error(`bad ret tag ${tag}`), { flCode: 2 });
      }
    } finally {
      owned.forEach((p) => M._free(p));
    }
  };
  return {
    record,
    call,
    highlightCb: () => Number(M._fl_engine_highlight_cb()),
    channelCount: () => M._fl_engine_channel_count(),
    midiOutCount: () => M._fl_engine_midi_out_count(),
    gridBit: (c, p) => M._fl_engine_grid_bit(c, p),
    displayTime: () => Number(M._fl_engine_display_time()),
    stepItemProbe: (prm, v, s0, s1) => M._fl_engine_step_item_probe(prm, v, s0, s1),
    noteEnumProbe: (seed, n, chan, step, V) => {
      const k = M._fl_engine_note_enum_probe(seed, n, chan, step, V);
      return Array.from(new Int32Array(M.HEAPU8.buffer, M._fl_engine_note_enum_out(), k));
    },
  };
}
