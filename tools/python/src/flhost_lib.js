// Emscripten JS library: flpy.c の `flhost_call` import 実装。
// Python(wasm) → ホスト境界。実処理は Module.flHostCall(fnId, argsArray) に委譲する (同期呼出し必須)。
//   - 戻り値: null/undefined→None, boolean→bool, number→int(整数) / {t:'D',v:x}→float, string→str,
//             Uint8Array→bytes, object/array→JSON ('J')
//   - 引数の Python callable は {__cb:id} になる (後で fl_rt:invoke_cb で呼び戻す)
//   - throw した Error の .flCode (1..8) が _flhost.HostError(code,msg) になる
addToLibrary({
  flhost_call__deps: ['$UTF8ToString', '$stringToUTF8', '$lengthBytesUTF8', 'malloc'],
  flhost_call: (fnId, argvPtr, argc, retPtr) => {
    const dv = new DataView(HEAPU8.buffer);
    const args = [];
    for (let i = 0; i < argc; i++) {
      const o = argvPtr + i * 16;
      switch (String.fromCharCode(HEAPU8[o])) {
        case 'N': args.push(null); break;
        case 'B': args.push(dv.getInt32(o + 8, true) !== 0); break;
        case 'I': args.push(Number(dv.getBigInt64(o + 8, true))); break;
        case 'D': args.push(dv.getFloat64(o + 8, true)); break;
        case 'S': args.push(UTF8ToString(dv.getUint32(o + 8, true), dv.getUint32(o + 12, true))); break;
        case 'F': args.push({ __cb: Number(dv.getBigInt64(o + 8, true)) }); break;
        case 'Y': { const p = dv.getUint32(o + 8, true), l = dv.getUint32(o + 12, true); args.push(HEAPU8.slice(p, p + l)); break; }
        default: return 2;
      }
    }
    const putStr = (tag, s, code) => {
      const len = lengthBytesUTF8(s);
      const p = _malloc(len + 1);
      stringToUTF8(s, p, len + 1);
      const d2 = new DataView(HEAPU8.buffer);
      HEAPU8[retPtr] = tag.charCodeAt(0);
      d2.setInt32(retPtr + 4, code | 0, true);
      d2.setUint32(retPtr + 8, p, true);
      d2.setUint32(retPtr + 12, len, true);
    };
    let r;
    try {
      r = Module.flHostCall(fnId, args);
    } catch (e) {
      putStr('E', String(e && e.message || e), (e && e.flCode) || 0);
      return 0;
    }
    const d = new DataView(HEAPU8.buffer);
    if (r === null || r === undefined) { HEAPU8[retPtr] = 78; }
    else if (typeof r === 'boolean') { HEAPU8[retPtr] = 66; d.setBigInt64(retPtr + 8, r ? 1n : 0n, true); }
    else if (typeof r === 'number') {
      if (Number.isInteger(r)) { HEAPU8[retPtr] = 73; d.setBigInt64(retPtr + 8, BigInt(r), true); }
      else { HEAPU8[retPtr] = 68; d.setFloat64(retPtr + 8, r, true); }
    }
    else if (typeof r === 'string') { putStr('S', r, 0); }
    else if (r instanceof Uint8Array) {
      const p = _malloc(r.length || 1);
      HEAPU8.set(r, p);
      const d2 = new DataView(HEAPU8.buffer);
      HEAPU8[retPtr] = 89; d2.setUint32(retPtr + 8, p, true); d2.setUint32(retPtr + 12, r.length, true);
    }
    else if (typeof r === 'object' && r.t === 'D') { HEAPU8[retPtr] = 68; d.setFloat64(retPtr + 8, +r.v, true); }
    else { putStr('J', JSON.stringify(r), 0); }
    return 0;
  },
});
