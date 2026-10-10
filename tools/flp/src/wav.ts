// Minimal WAV reader + comparison metrics for the render oracle (ORACLE.md section 4). Browser-safe (no Node APIs).
export interface Wav {
  sampleRate: number;
  channels: number;
  bits: number;
  float: boolean;
  frames: number;
  /** de-interleaved samples normalised to [-1, 1) (float32 values are kept exactly) */
  ch: Float64Array[];
  /** raw bytes of the data chunk (for determinism hashing) */
  raw: Uint8Array;
}

export function parseWav(b: Uint8Array): Wav {
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const tag = (o: number) => String.fromCharCode(b[o], b[o + 1], b[o + 2], b[o + 3]);
  if (b.length < 12 || tag(0) !== 'RIFF' || tag(8) !== 'WAVE') throw new Error('not a RIFF/WAVE file');
  let p = 12;
  let fmt: { tag: number; ch: number; rate: number; bits: number } | undefined;
  let data: Uint8Array | undefined;
  while (p + 8 <= b.length) {
    const id = tag(p);
    let size = dv.getUint32(p + 4, true);
    if (p + 8 + size > b.length) size = b.length - p - 8;
    if (id === 'fmt ') {
      let t = dv.getUint16(p + 8, true);
      if (t === 0xfffe && size >= 26) t = dv.getUint16(p + 8 + 24, true);
      fmt = { tag: t, ch: dv.getUint16(p + 10, true), rate: dv.getUint32(p + 12, true), bits: dv.getUint16(p + 22, true) };
    } else if (id === 'data') {
      data = b.subarray(p + 8, p + 8 + size);
    }
    p += 8 + size + (size & 1);
  }
  if (!fmt || !data) throw new Error('missing fmt/data chunk');
  const float = fmt.tag === 3;
  if (!(fmt.tag === 1 || float)) throw new Error(`unsupported WAV format tag ${fmt.tag}`);
  const bps = fmt.bits >> 3;
  const frames = Math.floor(data.length / (bps * fmt.ch));
  const ch = Array.from({ length: fmt.ch }, () => new Float64Array(frames));
  const d = new DataView(data.buffer, data.byteOffset, data.byteLength);
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < fmt.ch; c++) {
      const o = (i * fmt.ch + c) * bps;
      let v: number;
      if (float) v = fmt.bits === 32 ? d.getFloat32(o, true) : d.getFloat64(o, true);
      else if (fmt.bits === 16) v = d.getInt16(o, true) / 32768;
      else if (fmt.bits === 24) v = (((data[o + 2] << 24) | (data[o + 1] << 16) | (data[o] << 8)) >> 8) / 8388608;
      else if (fmt.bits === 32) v = d.getInt32(o, true) / 2147483648;
      else if (fmt.bits === 8) v = (data[o] - 128) / 128;
      else throw new Error(`unsupported bit depth ${fmt.bits}`);
      ch[c][i] = v;
    }
  }
  return { sampleRate: fmt.rate, channels: fmt.ch, bits: fmt.bits, float, frames, ch, raw: data };
}

/** serialise de-interleaved samples as IEEE-float32 or PCM16/24 WAV (used by tests and by synthetic stimulus tools) */
export function writeWav(ch: Float64Array[], sampleRate: number, bits: 16 | 24 | 32, float: boolean): Uint8Array {
  const n = ch[0].length;
  const bps = bits >> 3;
  const dataLen = n * ch.length * bps;
  const out = new Uint8Array(44 + dataLen);
  const dv = new DataView(out.buffer);
  const w = (o: number, s: string) => [...s].forEach((c, i) => (out[o + i] = c.charCodeAt(0)));
  w(0, 'RIFF');
  dv.setUint32(4, 36 + dataLen, true);
  w(8, 'WAVE');
  w(12, 'fmt ');
  dv.setUint32(16, 16, true);
  dv.setUint16(20, float ? 3 : 1, true);
  dv.setUint16(22, ch.length, true);
  dv.setUint32(24, sampleRate, true);
  dv.setUint32(28, sampleRate * ch.length * bps, true);
  dv.setUint16(32, ch.length * bps, true);
  dv.setUint16(34, bits, true);
  w(36, 'data');
  dv.setUint32(40, dataLen, true);
  for (let i = 0; i < n; i++)
    for (let c = 0; c < ch.length; c++) {
      const o = 44 + (i * ch.length + c) * bps;
      const v = ch[c][i];
      if (float) dv.setFloat32(o, v, true);
      else if (bits === 16) dv.setInt16(o, Math.max(-32768, Math.min(32767, Math.round(v * 32768))), true);
      else {
        const q = Math.max(-8388608, Math.min(8388607, Math.round(v * 8388608)));
        out[o] = q & 255;
        out[o + 1] = (q >> 8) & 255;
        out[o + 2] = (q >> 16) & 255;
      }
    }
  return out;
}

const f32 = new Float32Array(1);
const u32 = new Uint32Array(f32.buffer);
/** distance in float32 ULPs between two values (monotonic integer mapping; 0 for +0/-0) */
export function ulpDistF32(a: number, b: number): number {
  f32[0] = a;
  let x = u32[0];
  f32[0] = b;
  let y = u32[0];
  if (x & 0x80000000) x = 0x80000000 - (x & 0x7fffffff);
  else x += 0x80000000;
  if (y & 0x80000000) y = 0x80000000 - (y & 0x7fffffff);
  else y += 0x80000000;
  return Math.abs(x - y);
}

export interface Metrics {
  sameShape: boolean;
  framesA: number;
  framesB: number;
  channels: number;
  nanOrInf: number;
  bitExact: boolean;
  maxAbs: number;
  maxAbsDb: number;
  maxUlp: number;
  rmsDiffDb: number;
  snrDb: number;
  peakDiffDb: number;
  rmsDiffRefDb: number;
}

const db = (x: number): number => (x > 0 ? 20 * Math.log10(x) : -Infinity);

export function compareWav(a: Wav, b: Wav): Metrics {
  const frames = Math.min(a.frames, b.frames);
  const channels = Math.min(a.channels, b.channels);
  let nan = 0;
  let maxAbs = 0;
  let maxUlp = 0;
  let sumD = 0;
  let sumA = 0;
  let pa = 0;
  let pb = 0;
  let exact = a.frames === b.frames && a.channels === b.channels;
  for (let c = 0; c < channels; c++)
    for (let i = 0; i < frames; i++) {
      const x = a.ch[c][i];
      const y = b.ch[c][i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        nan++;
        exact = false;
        continue;
      }
      const d = Math.abs(x - y);
      if (d !== 0) exact = false;
      if (d > maxAbs) maxAbs = d;
      sumD += d * d;
      sumA += x * x;
      pa = Math.max(pa, Math.abs(x));
      pb = Math.max(pb, Math.abs(y));
      const u = ulpDistF32(x, y);
      if (u > maxUlp) maxUlp = u;
    }
  const n = Math.max(frames * channels, 1);
  const rmsD = Math.sqrt(sumD / n);
  const rmsA = Math.sqrt(sumA / n);
  return {
    sameShape: a.frames === b.frames && a.channels === b.channels && a.sampleRate === b.sampleRate,
    framesA: a.frames,
    framesB: b.frames,
    channels,
    nanOrInf: nan,
    bitExact: exact,
    maxAbs,
    maxAbsDb: db(maxAbs),
    maxUlp,
    rmsDiffDb: db(rmsD),
    snrDb: rmsD === 0 ? Infinity : db(rmsA) - db(rmsD),
    peakDiffDb: db(pb) - db(pa),
    rmsDiffRefDb: rmsA > 0 ? db(rmsD / rmsA) : -Infinity,
  };
}

/** Tolerance classes of ORACLE.md section 4. */
export type ToleranceClass = 'A-exact' | 'B-ulp' | 'C-statistical' | 'D-spectral';
export interface Verdict {
  cls: ToleranceClass;
  pass: boolean;
  why: string;
}

export function judge(m: Metrics, cls: ToleranceClass): Verdict {
  if (m.nanOrInf > 0) return { cls, pass: false, why: `${m.nanOrInf} NaN/Inf samples` };
  if (!m.sameShape) return { cls, pass: false, why: `shape differs (${m.framesA} vs ${m.framesB} frames)` };
  switch (cls) {
    case 'A-exact':
      return { cls, pass: m.bitExact, why: m.bitExact ? 'bit-exact' : `maxUlp=${m.maxUlp} maxAbs=${m.maxAbs.toExponential(2)}` };
    case 'B-ulp': {
      const pass = m.maxUlp <= 4 && m.maxAbs <= 1e-6;
      return { cls, pass, why: `maxUlp=${m.maxUlp} (<=4) maxAbs=${m.maxAbs.toExponential(2)} (<=1e-6)` };
    }
    case 'C-statistical': {
      const pass = m.rmsDiffRefDb <= -80 && Math.abs(m.peakDiffDb) <= 0.01 && m.maxAbs <= 1e-4;
      return { cls, pass, why: `rmsDiff/ref=${m.rmsDiffRefDb.toFixed(1)}dB (<=-80) peakDiff=${m.peakDiffDb.toFixed(4)}dB (<=0.01) maxAbs=${m.maxAbs.toExponential(2)} (<=1e-4)` };
    }
    case 'D-spectral': {
      const pass = m.rmsDiffRefDb <= -60 && Math.abs(m.peakDiffDb) <= 0.1;
      return { cls, pass, why: `rmsDiff/ref=${m.rmsDiffRefDb.toFixed(1)}dB (<=-60) peakDiff=${m.peakDiffDb.toFixed(3)}dB (<=0.1); spectral STFT stage must also pass (ORACLE.md 4.4)` };
    }
  }
}
