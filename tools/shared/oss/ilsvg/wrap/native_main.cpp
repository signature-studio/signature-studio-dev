// native 側の基準出力 (#927): SVG を読み、寸法 64x64 で描画する。
//   usage: nat <in.svg> <out.bin>
// stdout: "dims W H nonzero_px N"、out.bin: ARGB32 生データ (wasm_smoke.cjs と同じ形式)。
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include <svgdom/dom.hpp>
#include <svgren/render.hpp>

int main(int argc, char** argv) {
	if (argc < 3) {
		return 2;
	}
	std::ifstream f(argv[1], std::ios::binary);
	std::vector<char> buf((std::istreambuf_iterator<char>(f)), {});
	auto dom = svgdom::load(utki::make_span(buf.data(), buf.size()));
	svgren::parameters p;
	p.dims_request = {64, 64};
	auto r = svgren::render(*dom, p);
	auto nonzero = std::count_if(r.pixels.begin(), r.pixels.end(), [](uint32_t v) {
		return v != 0;
	});
	std::printf("dims %u %u nonzero_px %zu\n", unsigned(r.dims[0]), unsigned(r.dims[1]), size_t(nonzero));
	FILE* out = std::fopen(argv[2], "wb");
	if (!out) {
		return 1;
	}
	std::fwrite(r.pixels.data(), 4, r.pixels.size(), out);
	std::fclose(out);
	return 0;
}
