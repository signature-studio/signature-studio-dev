// wasm 側のスモーク描画 (#927)。createILSvg 経由で svgCreate → svgRender(W,H) し、ARGB32 生データを書き出す。
//   usage: node wasm_smoke.cjs <ilsvg.js> <smoke.svg> <out.bin> <W> <H>
// stdout: "dims W H nonzero_px N" (native_main と同じ形式)
const fs = require("fs");
const path = require("path");

const [, , jsPath, svgPath, outPath, wStr, hStr] = process.argv;
const W = Number(wStr), H = Number(hStr);

(async () => {
	const createILSvg = require(path.resolve(jsPath));
	const M = await createILSvg();
	const svg = fs.readFileSync(svgPath);
	const p = M._malloc(svg.length);
	M.HEAPU8.set(svg, p);
	const h = M._svgCreate(p, svg.length);
	M._free(p);
	if (!h) {
		throw new Error("svgCreate returned null");
	}
	const outW = M._malloc(4), outH = M._malloc(4);
	const px = M._svgRender(h, W, H, outW, outH);
	const dw = M.HEAPU32[outW >> 2], dh = M.HEAPU32[outH >> 2];
	const n = dw * dh;
	const bytes = Buffer.from(M.HEAPU8.buffer, px, n * 4).slice();
	M._svgDestroy(h);
	M._free(outW); M._free(outH);
	fs.writeFileSync(outPath, bytes);
	let nonzero = 0;
	for (let i = 0; i < n; i++) {
		if (bytes.readUInt32LE(i * 4) !== 0) nonzero++;
	}
	console.log(`dims ${dw} ${dh} nonzero_px ${nonzero}`);
})().catch((e) => {
	console.error(e);
	process.exit(1);
});
