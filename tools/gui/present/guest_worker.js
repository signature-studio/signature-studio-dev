// guest_worker.js — tearing 試験用の模擬 guest: 全面を「1 フレーム 1 色」で行ごとに描画する (seqlock 書込み側プロトコルに従う)。
// フレーム f の画素は全て同一色 => 描画器の画面に 2 色以上が混ざれば tear (フレーム境界をまたいだ読出し)。
import { MockGuest, hash32 } from "/present/mock_guest.js";
import { W as WORD } from "/js/gui_proto.js";

onmessage = (ev) => {
  const { memory, base, width, height, frames, periodMs, rowWorkUs } = ev.data;
  const g = new MockGuest(memory, base, width, height);
  g.create(0, 0, 0, width, height, 1);
  const px = g.px(0);
  const spin = (us) => { const t = performance.now() + us / 1000; while (performance.now() < t); };
  const wait = new Int32Array(new SharedArrayBuffer(4));
  const t0 = performance.now();
  let maxInflight = 0;
  for (let f = 1; f <= frames; f++) {
    while (f - (Atomics.load(g.i32, WORD.presentDoneSeq) >>> 0) > 3) Atomics.wait(g.i32, WORD.presentDoneSeq, Atomics.load(g.i32, WORD.presentDoneSeq), 50);
    const color = hash32(f, 7, 9) | 0xff000000;
    g.wseqBegin(0);
    for (let y = 0; y < height; y++) { px.fill(color, y * width, (y + 1) * width); if (rowWorkUs) spin(rowWorkUs); }
    g.wseqEnd(0);
    g.present(0, 0, 0, width, height);
    g.frameEnd();
    maxInflight = Math.max(maxInflight, f - (Atomics.load(g.i32, WORD.presentDoneSeq) >>> 0));
    const next = t0 + f * periodMs, d = next - performance.now();
    if (d > 0) Atomics.wait(wait, 0, 0, d);
  }
  postMessage({ type: "done", frames, seq: g.seq, lastColor: hash32(frames, 7, 9) | 0xff000000, maxInflight, elapsedMs: performance.now() - t0 });
};
