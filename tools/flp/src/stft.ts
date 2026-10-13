// Spectral / loudness metrics for the D-spectral oracle class (ORACLE.md section 4.4). Browser-safe (no Node APIs).

export const STFT_SIZE = 4096;
export const STFT_HOP = 1024;
/** bins are compared only when the reference magnitude is within this many dB of the reference's global STFT peak */
export const STFT_FLOOR_DB = -60;
export const STFT_TOL_DB = 0.1;
export const LUFS_TOL_LU = 0.1;
export const TRUE_PEAK_TOL_DB = 0.1;

const db20 = (x: number): number => (x > 0 ? 20 * Math.log10(x) : -Infinity);

// ---------------------------------------------------------------- FFT

const fftCache = new Map<number, { cos: Float64Array; sin: Float64Array; rev: Uint32Array }>();
function fftTables(n: number) {
  let t = fftCache.get(n);
  if (t) return t;
  if (n < 2 || (n & (n - 1)) !== 0) throw new Error(`FFT size must be a power of two (got ${n})`);
  const bits = Math.log2(n);
  const rev = new Uint32Array(n);
  for (let i = 0; i < n; i++) {
    let r = 0;
    for (let b = 0; b < bits; b++) if (i & (1 << b)) r |= 1 << (bits - 1 - b);
    rev[i] = r;
  }
  const cos = new Float64Array(n / 2);
  const sin = new Float64Array(n / 2);
  for (let i = 0; i < n / 2; i++) {
    cos[i] = Math.cos((2 * Math.PI * i) / n);
    sin[i] = -Math.sin((2 * Math.PI * i) / n);
  }
  t = { cos, sin, rev };
  fftCache.set(n, t);
  return t;
}

/** in-place radix-2 complex FFT (forward, unnormalised) */
export function fft(re: Float64Array, im: Float64Array): void {
  const n = re.length;
  const { cos, sin, rev } = fftTables(n);
  for (let i = 0; i < n; i++) {
    const j = rev[i];
    if (j > i) {
      const tr = re[i];
      re[i] = re[j];
      re[j] = tr;
      const ti = im[i];
      im[i] = im[j];
      im[j] = ti;
    }
  }
  for (let size = 2; size <= n; size <<= 1) {
    const half = size >> 1;
    const step = n / size;
    for (let s = 0; s < n; s += size) {
      for (let k = 0, w = 0; k < half; k++, w += step) {
        const a = s + k;
        const b = a + half;
        const xr = re[b] * cos[w] - im[b] * sin[w];
        const xi = re[b] * sin[w] + im[b] * cos[w];
        re[b] = re[a] - xr;
        im[b] = im[a] - xi;
        re[a] += xr;
        im[a] += xi;
      }
    }
  }
}

/** periodic Hann window */
export function hann(n: number): Float64Array {
  return Float64Array.from({ length: n }, (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / n));
}

/**
 * number of STFT frames covering `n` samples. Only full windows are used (a zero-padded tail would add phase-dependent
 * broadband leakage); the tail is covered by one extra window aligned to the end. Signals shorter than `size` get one padded frame.
 */
export function stftFrameCount(n: number, size = STFT_SIZE, hop = STFT_HOP): number {
  if (n <= 0) return 0;
  return n <= size ? 1 : Math.ceil((n - size) / hop) + 1;
}

/** first sample of frame `f`; the last frame is clamped so that it ends at `n` */
export function stftFrameStart(f: number, n: number, size = STFT_SIZE, hop = STFT_HOP): number {
  return Math.max(0, Math.min(f * hop, n - size));
}

// ---------------------------------------------------------------- STFT comparison

export interface StftBinPos {
  channel: number;
  frame: number;
  startSample: number;
  timeSec: number;
  bin: number;
  freqHz: number;
  refDb: number;
  testDb: number;
  /** |testDb - refDb| */
  diffDb: number;
}

export interface StftReport {
  size: number;
  hop: number;
  floorDb: number;
  tolDb: number;
  frames: number;
  /** global reference STFT peak magnitude (Hann-windowed, unnormalised) */
  refPeakDb: number;
  /** reference is digital silence: no bins qualify (caller must check the test signal separately) */
  refSilent: boolean;
  binsCompared: number;
  binsOverTol: number;
  maxDiffDb: number;
  /** first (time order, then channel, then bin) bin whose |diff| > tolDb */
  first: StftBinPos | null;
  worst: StftBinPos | null;
}

/**
 * Hann-4096 / hop-1024 STFT magnitude comparison. A bin is compared when the reference magnitude is within
 * `floorDb` of the reference's global peak bin (all channels, all frames); it fails when |20log10(test/ref)| > tolDb.
 * Inputs must have equal frame counts; channels are compared pairwise over min(channels).
 */
export function compareStft(
  ref: Float64Array[],
  test: Float64Array[],
  sampleRate: number,
  opts: { size?: number; hop?: number; floorDb?: number; tolDb?: number } = {},
): StftReport {
  const size = opts.size ?? STFT_SIZE;
  const hop = opts.hop ?? STFT_HOP;
  const floorDb = opts.floorDb ?? STFT_FLOOR_DB;
  const tolDb = opts.tolDb ?? STFT_TOL_DB;
  const channels = Math.min(ref.length, test.length);
  const n = Math.min(ref[0]?.length ?? 0, test[0]?.length ?? 0);
  const frames = stftFrameCount(n, size, hop);
  const win = hann(size);
  const nb = size / 2 + 1;
  const re = new Float64Array(size);
  const im = new Float64Array(size);
  const load = (x: Float64Array, start: number, dst: Float64Array, useWin = true) => {
    for (let i = 0; i < size; i++) {
      const j = start + i;
      dst[i] = j < n ? x[j] * (useWin ? win[i] : 1) : 0;
    }
  };

  let peak = 0;
  for (let c = 0; c < channels; c++)
    for (let f = 0; f < frames; f++) {
      load(ref[c], stftFrameStart(f, n, size, hop), re);
      im.fill(0);
      fft(re, im);
      for (let k = 0; k < nb; k++) {
        const m = Math.hypot(re[k], im[k]);
        if (m > peak) peak = m;
      }
    }

  const rep: StftReport = {
    size,
    hop,
    floorDb,
    tolDb,
    frames,
    refPeakDb: db20(peak),
    refSilent: peak === 0,
    binsCompared: 0,
    binsOverTol: 0,
    maxDiffDb: 0,
    first: null,
    worst: null,
  };
  if (peak === 0) return rep;

  const thr = peak * Math.pow(10, floorDb / 20);
  // test frame goes in the imaginary part of one FFT; split by conjugate symmetry
  const pos = (c: number, f: number, k: number, ma: number, mb: number, d: number): StftBinPos => ({
    channel: c,
    frame: f,
    startSample: stftFrameStart(f, n, size, hop),
    timeSec: stftFrameStart(f, n, size, hop) / sampleRate,
    bin: k,
    freqHz: (k * sampleRate) / size,
    refDb: db20(ma),
    testDb: db20(mb),
    diffDb: d,
  });
  for (let f = 0; f < frames; f++)
    for (let c = 0; c < channels; c++) {
      const st = stftFrameStart(f, n, size, hop);
      load(ref[c], st, re);
      load(test[c], st, im);
      fft(re, im);
      for (let k = 0; k < nb; k++) {
        const k2 = (size - k) & (size - 1);
        const ar = 0.5 * (re[k] + re[k2]);
        const ai = 0.5 * (im[k] - im[k2]);
        const br = 0.5 * (im[k] + im[k2]);
        const bi = -0.5 * (re[k] - re[k2]);
        const ma = Math.hypot(ar, ai);
        if (ma < thr) continue;
        const mb = Math.hypot(br, bi);
        const d = mb > 0 ? Math.abs(20 * Math.log10(mb / ma)) : Infinity;
        rep.binsCompared++;
        if (!(d <= tolDb)) {
          rep.binsOverTol++;
          if (!rep.first) rep.first = pos(c, f, k, ma, mb, d);
        }
        if (d > rep.maxDiffDb || (rep.worst === null && d >= 0)) {
          rep.maxDiffDb = d;
          rep.worst = pos(c, f, k, ma, mb, d);
        }
      }
    }
  return rep;
}

// ---------------------------------------------------------------- BS.1770-4 loudness

interface Biquad {
  b: [number, number, number];
  a: [number, number];
}

/** K-weighting stage 1 (high shelf) + stage 2 (RLB high-pass) for any sample rate (BS.1770-4 analog prototype, bilinear) */
export function kWeighting(fs: number): [Biquad, Biquad] {
  const shelf = (() => {
    const f0 = 1681.974450955533;
    const G = 3.999843853973347;
    const Q = 0.7071752369554196;
    const K = Math.tan((Math.PI * f0) / fs);
    const Vh = Math.pow(10, G / 20);
    const Vb = Math.pow(Vh, 0.4996667741545416);
    const a0 = 1 + K / Q + K * K;
    return {
      b: [(Vh + (Vb * K) / Q + K * K) / a0, (2 * (K * K - Vh)) / a0, (Vh - (Vb * K) / Q + K * K) / a0],
      a: [(2 * (K * K - 1)) / a0, (1 - K / Q + K * K) / a0],
    } as Biquad;
  })();
  const rlb = (() => {
    const f0 = 38.13547087602444;
    const Q = 0.5003270373238773;
    const K = Math.tan((Math.PI * f0) / fs);
    const a0 = 1 + K / Q + K * K;
    return { b: [1, -2, 1], a: [(2 * (K * K - 1)) / a0, (1 - K / Q + K * K) / a0] } as Biquad;
  })();
  return [shelf, rlb];
}

function biquad(x: Float64Array, q: Biquad): Float64Array {
  const y = new Float64Array(x.length);
  let x1 = 0;
  let x2 = 0;
  let y1 = 0;
  let y2 = 0;
  for (let i = 0; i < x.length; i++) {
    const v = q.b[0] * x[i] + q.b[1] * x1 + q.b[2] * x2 - q.a[0] * y1 - q.a[1] * y2;
    x2 = x1;
    x1 = x[i];
    y2 = y1;
    y1 = v;
    y[i] = v;
  }
  return y;
}

/** channel weights G_i: 1.0 for L/R/C, 1.41 for the surround pair (indices 4,5 of L R C LFE Ls Rs), LFE excluded */
function channelWeight(i: number, n: number): number {
  if (n < 5) return 1;
  if (i === 3) return 0;
  return i >= 4 ? 1.41 : 1;
}

const LUFS_OFFSET = -0.691;
const lufsOf = (z: number): number => (z > 0 ? LUFS_OFFSET + 10 * Math.log10(z) : -Infinity);

/**
 * Integrated loudness (LUFS-I) per BS.1770-4 / EBU R128: K-weighting, 400 ms blocks with 75 % overlap,
 * -70 LUFS absolute gate, -10 LU relative gate. Signals shorter than one block are measured as a single block.
 * Returns -Infinity when nothing passes the absolute gate.
 */
export function integratedLoudness(ch: Float64Array[], fs: number): number {
  const n = ch[0]?.length ?? 0;
  if (n === 0) return -Infinity;
  const [s1, s2] = kWeighting(fs);
  const w = ch.map((x) => biquad(biquad(x, s1), s2));
  // prefix sums of squares per channel
  const cum = w.map((x) => {
    const c = new Float64Array(x.length + 1);
    for (let i = 0; i < x.length; i++) c[i + 1] = c[i] + x[i] * x[i];
    return c;
  });
  const blockLen = Math.round(0.4 * fs);
  const step = Math.round(0.1 * fs);
  const zs: number[] = [];
  const zAt = (s: number, len: number): number => {
    let z = 0;
    for (let c = 0; c < cum.length; c++) z += (channelWeight(c, cum.length) * (cum[c][s + len] - cum[c][s])) / len;
    return z;
  };
  if (n < blockLen) zs.push(zAt(0, n));
  else for (let s = 0; s + blockLen <= n; s += step) zs.push(zAt(s, blockLen));
  const abs = zs.filter((z) => lufsOf(z) > -70);
  if (abs.length === 0) return -Infinity;
  const relThr = lufsOf(abs.reduce((a, b) => a + b, 0) / abs.length) - 10;
  const gated = abs.filter((z) => lufsOf(z) > relThr);
  if (gated.length === 0) return -Infinity;
  return lufsOf(gated.reduce((a, b) => a + b, 0) / gated.length);
}

// ---------------------------------------------------------------- true peak

function besselI0(x: number): number {
  let sum = 1;
  let term = 1;
  for (let k = 1; k < 50; k++) {
    term *= (x / (2 * k)) * (x / (2 * k));
    sum += term;
    if (term < 1e-16 * sum) break;
  }
  return sum;
}

// Kaiser-windowed sinc, each phase normalised to unity DC gain; <= 0.001 dB error on sines up to 0.4 fs (measured)
const TP_TAPS = 16;
const TP_BETA = 8;

/** polyphase kernels for L-times oversampling: h[p][j] weights x[i + j - TP_TAPS/2 + 1] for output phase p/L */
function tpKernels(L: number): Float64Array[] {
  const half = TP_TAPS / 2;
  const i0b = besselI0(TP_BETA);
  const ker: Float64Array[] = [];
  for (let p = 0; p < L; p++) {
    const h = new Float64Array(TP_TAPS);
    for (let j = 0; j < TP_TAPS; j++) {
      const t = j - half + 1 - p / L;
      const r = t / half;
      const wv = Math.abs(r) < 1 ? besselI0(TP_BETA * Math.sqrt(1 - r * r)) / i0b : 0;
      h[j] = (t === 0 ? 1 : Math.sin(Math.PI * t) / (Math.PI * t)) * wv;
    }
    const sum = h.reduce((s, v) => s + v, 0);
    for (let j = 0; j < TP_TAPS; j++) h[j] /= sum;
    ker.push(h);
  }
  return ker;
}

/** oversampling factor per BS.1770-4: 4x below 96 kHz, 2x below 192 kHz, else none */
export const truePeakFactor = (fs: number): number => (fs < 96000 ? 4 : fs < 192000 ? 2 : 1);

/** inter-sample (true) peak in dBTP over all channels (linear amplitude 1.0 = 0 dBTP) */
export function truePeakDb(ch: Float64Array[], fs: number): number {
  const L = truePeakFactor(fs);
  const ker = tpKernels(L);
  const half = TP_TAPS / 2;
  let peak = 0;
  for (const x of ch) {
    const n = x.length;
    for (let i = 0; i < n; i++) {
      const a = Math.abs(x[i]);
      if (a > peak) peak = a;
      for (let p = 1; p < L; p++) {
        const h = ker[p];
        let y = 0;
        for (let j = 0; j < TP_TAPS; j++) {
          const idx = i + j - half + 1;
          if (idx >= 0 && idx < n) y += h[j] * x[idx];
        }
        if (Math.abs(y) > peak) peak = Math.abs(y);
      }
    }
  }
  return db20(peak);
}

// ---------------------------------------------------------------- combined D-class metrics

export interface SpectralMetrics {
  stft: StftReport;
  lufsA: number;
  lufsB: number;
  /** lufsB - lufsA (0 when both are -Infinity; +/-Infinity when only one is) */
  lufsDiff: number;
  truePeakA: number;
  truePeakB: number;
  truePeakDiff: number;
}

const diffOrZero = (a: number, b: number): number => (a === b ? 0 : b - a);

export function spectralMetrics(a: { ch: Float64Array[]; sampleRate: number }, b: { ch: Float64Array[]; sampleRate: number }): SpectralMetrics {
  const channels = Math.min(a.ch.length, b.ch.length);
  const n = Math.min(a.ch[0]?.length ?? 0, b.ch[0]?.length ?? 0);
  const cut = (w: { ch: Float64Array[] }) => w.ch.slice(0, channels).map((x) => x.subarray(0, n));
  const ca = cut(a);
  const cb = cut(b);
  const lufsA = integratedLoudness(ca, a.sampleRate);
  const lufsB = integratedLoudness(cb, b.sampleRate);
  const truePeakA = truePeakDb(ca, a.sampleRate);
  const truePeakB = truePeakDb(cb, b.sampleRate);
  return {
    stft: compareStft(ca, cb, a.sampleRate),
    lufsA,
    lufsB,
    lufsDiff: diffOrZero(lufsA, lufsB),
    truePeakA,
    truePeakB,
    truePeakDiff: diffOrZero(truePeakA, truePeakB),
  };
}
