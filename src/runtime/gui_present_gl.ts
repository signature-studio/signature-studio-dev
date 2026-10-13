/**
 * gui_present_gl.ts — WebGL2 present バックエンド (GUI-4 / #180)。Worker 非依存。
 *
 * - surface ごとに RGBA8 テクスチャを 1 枚持つ。共有メモリ上の BGRA32 (top-down) の dirty 矩形をそのまま
 *   `texSubImage2D(RGBA, UNSIGNED_BYTE)` へ渡す (CPU 側の画素ループ無し; R/B 入替は fragment の swizzle `.bgr` で行う, alpha は 1.0 固定)。
 * - 転送方式: "direct" = wasm の共有メモリ view を UNPACK_ROW_LENGTH/SKIP_* 付きで直接渡す (コピー無し)。
 *   ブラウザが共有 ArrayBufferView を拒否する場合 (TypeError) は "staged" (非共有バッファへ行コピー) へ自動降格する。
 *   seqlock 有効時 (gui_renderer.ts) は検証前にテクスチャへ書かないため direct を使わず、stage() → 検証 → uploadStaged() の順に転送する。
 * - 合成は quad 描画 (`texelFetch` の整数座標, 補間・フィルタ無し) = putImageData 経路と画素一致 (差 0)。
 *   canvas は preserveDrawingBuffer: dirty 領域だけ再描画しても他の領域が残る。
 */

export type GlUploadMode = "direct" | "staged";

const VS = `#version 300 es
uniform vec4 uDst;     // desktop 座標 (px): left, top, width, height
uniform vec4 uSrc;     // テクセル座標: left, top, width, height
uniform vec2 uScreen;
out vec2 vTexel;
void main() {
  vec2 c = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1));
  vec2 p = uDst.xy + c * uDst.zw;
  gl_Position = vec4(p.x / uScreen.x * 2.0 - 1.0, 1.0 - p.y / uScreen.y * 2.0, 0.0, 1.0);
  vTexel = uSrc.xy + c * uSrc.zw;
}`;

const FS = `#version 300 es
precision highp float;
precision highp int;
uniform highp sampler2D uTex;
in vec2 vTexel;
out vec4 outColor;
void main() {
  // テクスチャの RGBA = メモリ上の B,G,R,A バイト (BGRA32)。.bgr で RGB に戻し alpha は 1.0 固定
  outColor = vec4(texelFetch(uTex, ivec2(floor(vTexel)), 0).bgr, 1.0);
}`;

/** シェーダをコンパイル・リンクして program を返す (失敗したら throw)。init() と usable() の共通部 */
function buildProgram(gl: WebGL2RenderingContext): WebGLProgram {
  const sh = (type: number, src: string): WebGLShader => {
    const s = gl.createShader(type)!;
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("[gui] shader: " + gl.getShaderInfoLog(s));
    return s;
  };
  const p = gl.createProgram()!;
  gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error("[gui] link: " + gl.getProgramInfoLog(p));
  return p;
}

type Tex = { tex: WebGLTexture; w: number; h: number };

export type GlStats = { uploads: number; uploadPixels: number; draws: number; directFallbacks: number; contextRestores: number };

export class GlPresenter {
  readonly gl: WebGL2RenderingContext;
  uploadMode: GlUploadMode;
  lost = false;
  /** コンテキスト復帰時に呼ばれる (呼出側は全面再合成する) */
  onRestore: (() => void) | null = null;
  readonly stats: GlStats = { uploads: 0, uploadPixels: 0, draws: 0, directFallbacks: 0, contextRestores: 0 };
  private uDst!: WebGLUniformLocation;
  private uSrc!: WebGLUniformLocation;
  private uScreen!: WebGLUniformLocation;
  private vao!: WebGLVertexArrayObject;
  private texs: Array<Tex | null> = [];
  private staging: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private readonly auto: boolean;

  /**
   * この環境で WebGL2 とシェーダが使えるかを、描画先とは別の 1x1 OffscreenCanvas で確かめる (描画先 canvas には触れない)。
   * canvas は一度 WebGL コンテキストを持つと 2D へ降格できないため、backend "auto" は描画先 canvas で getContext する前にこれで判定する。
   */
  static usable(): boolean {
    try {
      const gl = new OffscreenCanvas(1, 1).getContext("webgl2") as WebGL2RenderingContext | null;
      if (!gl) return false;
      try { buildProgram(gl); return true; } finally { gl.getExtension("WEBGL_lose_context")?.loseContext(); }
    } catch {
      return false;
    }
  }

  /** WebGL2 が使えなければ throw */
  constructor(canvas: OffscreenCanvas, readonly width: number, readonly height: number, upload: GlUploadMode | "auto" = "auto") {
    const gl = canvas.getContext("webgl2", {
      alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: false,
      preserveDrawingBuffer: true, powerPreference: "high-performance",
    }) as WebGL2RenderingContext | null;
    if (!gl) throw new Error("[gui] WebGL2 context unavailable");
    this.gl = gl;
    this.auto = upload === "auto";
    this.uploadMode = upload === "staged" ? "staged" : "direct";
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.lost = true; });
    canvas.addEventListener("webglcontextrestored", () => {
      this.texs = [];
      this.init();
      this.lost = false;
      this.stats.contextRestores++;
      this.onRestore?.();
    });
    this.init();
  }

  private init(): void {
    const gl = this.gl;
    const p = buildProgram(gl);
    this.uDst = gl.getUniformLocation(p, "uDst")!;
    this.uSrc = gl.getUniformLocation(p, "uSrc")!;
    this.uScreen = gl.getUniformLocation(p, "uScreen")!;
    this.vao = gl.createVertexArray()!;
    gl.bindVertexArray(this.vao);
    gl.useProgram(p);
    gl.uniform1i(gl.getUniformLocation(p, "uTex"), 0);
    gl.uniform2f(this.uScreen, this.width, this.height);
    gl.viewport(0, 0, this.width, this.height);
    gl.disable(gl.BLEND); gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); gl.disable(gl.DITHER);
    gl.activeTexture(gl.TEXTURE0);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  clear(): void {
    this.gl.clear(this.gl.COLOR_BUFFER_BIT);
  }

  /** surface id のテクスチャを w×h で確保 (サイズ変更時は作り直す)。作り直した/新規なら true (呼出側は全面転送する) */
  ensure(id: number, w: number, h: number): boolean {
    const gl = this.gl;
    const cur = this.texs[id];
    if (cur && cur.w === w && cur.h === h) return false;
    if (cur) gl.deleteTexture(cur.tex);
    const tex = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, w, h);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.texs[id] = { tex, w, h };
    return true;
  }

  release(id: number): void {
    const t = this.texs[id];
    if (t) { this.gl.deleteTexture(t.tex); this.texs[id] = null; }
  }

  has(id: number, w: number, h: number): boolean {
    const t = this.texs[id];
    return !!t && t.w === w && t.h === h;
  }

  /**
   * 共有メモリ上の BGRA32 surface の矩形 [l,l+w)×[t,t+h) を転送する。
   * mem は surface 画素領域の先頭から stride*surfH バイトの view (共有バッファ上でよい)。
   */
  upload(id: number, mem: Uint8Array, strideBytes: number, l: number, t: number, w: number, h: number): void {
    const gl = this.gl;
    const tx = this.texs[id];
    if (!tx) throw new Error(`[gui] upload: no texture for surf ${id}`);
    gl.bindTexture(gl.TEXTURE_2D, tx.tex);
    if (this.uploadMode === "direct") {
      try {
        gl.pixelStorei(gl.UNPACK_ROW_LENGTH, strideBytes >> 2);
        gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, l);
        gl.pixelStorei(gl.UNPACK_SKIP_ROWS, t);
        gl.texSubImage2D(gl.TEXTURE_2D, 0, l, t, w, h, gl.RGBA, gl.UNSIGNED_BYTE, mem);
        gl.pixelStorei(gl.UNPACK_ROW_LENGTH, 0); gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, 0); gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0);
      } catch (e) {
        gl.pixelStorei(gl.UNPACK_ROW_LENGTH, 0); gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, 0); gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0);
        if (!this.auto || !(e instanceof TypeError)) throw e;
        this.uploadMode = "staged";
        this.stats.directFallbacks++;
        this.upload(id, mem, strideBytes, l, t, w, h);
        return;
      }
    } else {
      this.stage(mem, strideBytes, l, t, w, h);
      this.uploadStaged(id, l, t, w, h);
      return;
    }
    this.stats.uploads++;
    this.stats.uploadPixels += w * h;
  }

  /** 共有メモリ上の矩形を非共有の staging へ行コピーする (テクスチャには触れない)。seqlock 検証をコピーの後ろに置くための分離 */
  stage(mem: Uint8Array, strideBytes: number, l: number, t: number, w: number, h: number): void {
    const need = w * h * 4;
    if (this.staging.length < need) this.staging = new Uint8Array(need);
    const rowB = w * 4;
    if (strideBytes === rowB && l === 0) {
      this.staging.set(mem.subarray(t * strideBytes, t * strideBytes + need), 0);
    } else {
      for (let y = 0; y < h; y++) {
        const s = (t + y) * strideBytes + l * 4;
        this.staging.set(mem.subarray(s, s + rowB), y * rowB);
      }
    }
  }

  /** stage() 済みの w×h をテクスチャの (l,t) へ転送する */
  uploadStaged(id: number, l: number, t: number, w: number, h: number): void {
    const gl = this.gl;
    const tx = this.texs[id];
    if (!tx) throw new Error(`[gui] upload: no texture for surf ${id}`);
    gl.bindTexture(gl.TEXTURE_2D, tx.tex);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, l, t, w, h, gl.RGBA, gl.UNSIGNED_BYTE, this.staging);
    this.stats.uploads++;
    this.stats.uploadPixels += w * h;
  }

  /** surface id のテクセル矩形 (sl,st,w,h) を desktop の (dx,dy) へ描く */
  draw(id: number, sl: number, st: number, w: number, h: number, dx: number, dy: number): void {
    const tx = this.texs[id];
    if (!tx) return;
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, tx.tex);
    gl.uniform4f(this.uDst, dx, dy, w, h);
    gl.uniform4f(this.uSrc, sl, st, w, h);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    this.stats.draws++;
  }

  /** GPU 完了まで待つ (計測用; 1 px の readPixels で同期) */
  sync(): void {
    const gl = this.gl;
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.px1);
  }
  private readonly px1 = new Uint8Array(4);

  /** desktop (または矩形 x,y,w,h) を top-down RGBA で読み戻す (getImageData と同じ並び) */
  readback(x = 0, y = 0, w = this.width, h = this.height): { width: number; height: number; data: ArrayBuffer } {
    const gl = this.gl;
    const flipped = new Uint8Array(w * h * 4);
    gl.readPixels(x, this.height - y - h, w, h, gl.RGBA, gl.UNSIGNED_BYTE, flipped);
    const out = new Uint8Array(w * h * 4);
    const rowB = w * 4;
    for (let r = 0; r < h; r++) out.set(flipped.subarray((h - 1 - r) * rowB, (h - r) * rowB), r * rowB);
    return { width: w, height: h, data: out.buffer };
  }
}
