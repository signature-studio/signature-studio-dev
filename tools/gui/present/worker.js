// worker.js — GuiRenderer を Worker で動かす検証用ハーネス (本番の gui_worker.ts 相当 + テスト用フック)
import { GuiRenderer } from "/js/gui_renderer.js";
import { GlPresenter } from "/js/gui_present_gl.js";
import { OFF, S, SURF_WORDS } from "/js/gui_proto.js";

let r = null, H = 0;
const mode = { checkUniform: false, syncGpu: false };
const acc = { uniformChecked: 0, torn: 0, tornEpisodes: 0, syncMs: 0, syncN: 0 };
let prevTorn = false;
const inject = { armed: false, surf: 0, fired: 0, i32: null };

// テスト用フック (init の test で有効化)。本番の gui_worker.ts には無い。
// injectWrite: 次の surface 読出し (GL=stage, 2D=convert) の直後 = seqlock の検証の前に、guest の書込み開始 (wseq 偶数→奇数) を模擬する
function installInjectWrite(memory) {
  inject.i32 = new Int32Array(memory.buffer);
  for (const [proto, name] of [[GlPresenter.prototype, "stage"], [GuiRenderer.prototype, "convert"]]) {
    const orig = proto[name];
    proto[name] = function (...a) {
      const ret = orig.apply(this, a);
      if (inject.armed) { inject.armed = false; inject.fired++; Atomics.add(inject.i32, (OFF.surf >> 2) + inject.surf * SURF_WORDS + S.wseq, 1); }
      return ret;
    };
  }
}
// breakShader: "all" = どのコンテキストでもシェーダのコンパイルを失敗させる / "afterProbe" = 最初に使われたコンテキスト (= auto の 1x1 プローブ) 以外を失敗させる
function breakShaders(kind) {
  const proto = WebGL2RenderingContext.prototype, orig = proto.getShaderParameter;
  let first = null;
  proto.getShaderParameter = function (sh, pname) {
    if (pname === this.COMPILE_STATUS) { first ??= this; if (kind === "all" || this !== first) return false; }
    return orig.call(this, sh, pname);
  };
}

onmessage = (ev) => {
  const m = ev.data;
  if (m.type === "init") {
    try {
      H = m.height;
      if (m.test?.injectWrite) installInjectWrite(m.memory);
      if (m.test?.breakShader) breakShaders(m.test.breakShader);
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
  } else if (m.type === "inject") {
    inject.surf = m.surf; inject.armed = true;
    postMessage({ type: "inject", id: m.id });
  } else if (m.type === "readback") {
    const rb = r.readback();
    postMessage({ type: "readback", id: m.id, data: rb.data }, [rb.data]);
  } else if (m.type === "stats") {
    postMessage({ type: "stats", id: m.id, stats: { ...r.stats }, gl: r.glStats(), acc: { ...acc }, injected: inject.fired, frames: r.framesDone, info: r.info() });
  } else if (m.type === "reset") {
    for (const k of Object.keys(r.stats)) r.stats[k] = 0;
    for (const k of Object.keys(acc)) acc[k] = 0;
    postMessage({ type: "reset", id: m.id });
  }
};
