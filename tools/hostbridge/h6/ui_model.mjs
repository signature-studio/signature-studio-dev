// ui_model.mjs — HB-H6 (G1): 宣言的 UI のモデル. manifest (ott.ui.json) + 資産 → 表示リスト, 入力 → パラメータ変更.
//   描画先 (Canvas / soft renderer) と plugin 呼出は持たない. 純関数に近い構造にして headless で検証する.
//   パラメータは manifest の param 名 (effGetParamName の文字列) で束縛し, effEditOpen 時に index へ解決する
//   (index を manifest に焼かない: surrogate 名表の index ずれ = HOSTBRIDGE h2 REPORT §0 の再発防止).
const f32 = Math.fround;
const norm = (s) => String(s).trim().toLowerCase();

export class UiModel {
  constructor(manifest, assets, { onChange } = {}) {
    this.m = manifest; this.assets = assets; this.onChange = onChange || (() => {});
    this.controls = manifest.controls.map((c) => ({ ...c, index: -1, value: 0 }));
    this.drag = null; this.unbound = [];
  }

  // names[i] = plugin の effGetParamName(i). 戻り: {missing: manifest にあって plugin に無い param 名}
  resolve(names) {
    const by = new Map(); names.forEach((n, i) => { if (!by.has(norm(n))) by.set(norm(n), i); });
    const missing = [];
    for (const c of this.controls) {
      const i = by.get(norm(c.param));
      if (i === undefined) { c.index = -1; missing.push(c.param); } else c.index = i;
    }
    const bound = new Set(this.controls.filter((c) => c.index >= 0).map((c) => c.index));
    this.unbound = names.map((n, i) => ({ index: i, name: n })).filter((x) => !bound.has(x.index));
    return { missing };
  }

  // values: index -> 0..1. 戻り: 変化した control id の配列 (idle の再描画判定)
  setValues(get) {
    const changed = [];
    for (const c of this.controls) {
      if (c.index < 0) continue;
      const v = f32(get(c.index));
      if (v !== c.value) { c.value = v; changed.push(c.id); }
    }
    return changed;
  }

  frameOf(c, asset) { return Math.max(0, Math.min(asset.frames - 1, Math.round(c.value * (asset.frames - 1)))); }

  displayList(display = () => '') {
    const A = this.m.assets, L = [];
    for (const l of this.m.layers) L.push({ op: 'image', asset: l.asset, sx: 0, sy: 0, sw: A[l.asset].w, sh: A[l.asset].h, dx: l.x, dy: l.y });
    for (const c of this.controls) {
      if (c.kind === 'knob') {
        const body = A.knobBody, tick = A.knobTick, fr = this.frameOf(c, tick);
        L.push({ op: 'image', asset: 'knobBody', sx: 0, sy: 0, sw: body.w, sh: body.h, dx: c.cx - 40, dy: c.cy - 40, id: c.id });
        L.push({ op: 'image', asset: 'knobTick', sx: 0, sy: fr * tick.frameH, sw: tick.w, sh: tick.frameH, dx: c.cx - 40, dy: c.cy - 40, id: c.id, frame: fr });
        if (this.drag && this.drag.id === c.id) L.push({ op: 'image', asset: 'knobRing', sx: 0, sy: 0, sw: 80, sh: 80, dx: c.cx - 40, dy: c.cy - 40, id: c.id });
        if (c.readout) L.push({ op: 'text', text: display(c), cx: c.readout.cx, cy: c.readout.cy, id: c.id });
      } else if (c.kind === 'hslider') {
        const x = c.x0 + c.value * (c.x1 - c.x0);
        L.push({ op: 'rect', x: Math.round(x) - 4, y: c.y - 10, w: 8, h: 20, id: c.id, value: c.value });
      }
    }
    return L;
  }

  hit(x, y) {
    for (const c of this.controls) {
      if (c.index < 0) continue;
      if (c.kind === 'knob' && Math.abs(x - c.cx) <= 40 && Math.abs(y - c.cy) <= 40) return c;
      if (c.kind === 'hslider' && x >= c.x0 - 8 && x <= c.x1 + 8 && Math.abs(y - c.y) <= 14) return c;
    }
    return null;
  }

  set(c, v) {
    v = f32(Math.max(0, Math.min(1, v)));
    if (v === c.value) return false;
    c.value = v; this.onChange(c.index, v, c); return true;
  }

  pointerDown(x, y) {
    const c = this.hit(x, y);
    if (!c) return false;
    this.drag = { id: c.id, y0: y, v0: c.value };
    if (c.kind === 'hslider') this.set(c, (x - c.x0) / (c.x1 - c.x0));
    return true;
  }
  pointerMove(x, y, { fine = false } = {}) {
    if (!this.drag) return false;
    const c = this.controls.find((k) => k.id === this.drag.id);
    if (c.kind === 'hslider') return this.set(c, (x - c.x0) / (c.x1 - c.x0));
    const it = this.m.interaction, k = (fine ? it.knobFineFactor : 1) / it.knobPixelsPerRange;
    return this.set(c, this.drag.v0 + (this.drag.y0 - y) * k);
  }
  pointerUp() { const d = this.drag; this.drag = null; return !!d; }
}
