// worker.js — GuiRenderer を Worker で動かす検証用ハーネス (本番の gui_worker.ts 相当 + テスト用フック)
import { GuiRenderer } from "/js/gui_renderer.js";

let r = null, H = 0;
const mode = { checkUniform: false, syncGpu: false };
const acc = { uniformChecked: 0, torn: 0, tornEpisodes: 0, syncMs: 0, syncN: 0 };
let prevTorn = false;

onmessage = (ev) => {
  const m = ev.data;
  if (m.type === "init") {
    try {
      H = m.height;
      r = new GuiRenderer({
        canvas: m.canvas, memory: m.memory, base: m.base, width: m.width, height: m.height, present: m.present,
        post: (x) => { if (x.type === "frame") postMessage({ type: "frame", seq: x.seq }); },
        onFlush: (rr) => {
          if (mode.syncGpu) { const t = performance.now(); rr.syncGpu(); acc.syncMs += performance.now() - t; acc.syncN++; }
          if (mode.checkUniform) {
            const u = new Uint32Array(rr.readback(0, 0, 1, H).data  );
            let torn = false; const f = u[0];
            for (let i = 1; i < u.length; i++) if (u[i] !== f) { torn = true; break; }
            acc.uniformChecked++; if (torn) acc.torn++;
            if (torn && !prevTorn) acc.tornEpisodes++;
            prevTorn = torn;
          }
        },
      });
      r.start();
      postMessage({ type: "ready", info: r.info() });
    } catch (e) { postMessage({ type: "error", message: String(e && e.stack || e) }); }
  } else if (m.type === "mode") {
    Object.assign(mode, m.mode);
    postMessage({ type: "mode", id: m.id });
  } else if (m.type === "readback") {
    const rb = r.readback();
    postMessage({ type: "readback", id: m.id, data: rb.data }, [rb.data]);
  } else if (m.type === "stats") {
    postMessage({ type: "stats", id: m.id, stats: { ...r.stats }, gl: r.glStats(), acc: { ...acc }, frames: r.framesDone, info: r.info() });
  } else if (m.type === "reset") {
    for (const k of Object.keys(r.stats)) r.stats[k] = 0;
    for (const k of Object.keys(acc)) acc[k] = 0;
    postMessage({ type: "reset", id: m.id });
  }
};
