// native 側の基準出力: SVG を読み、先頭行に "dims W H nonzero_px N"、続けて ARGB32 生データを stdout に出す。
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include <svgdom/dom.hpp>
#include <svgren/render.hpp>

int main(int argc, char** argv) {
	if (argc < 2) {
		return 2;
	}
	std::ifstream f(argv[1], std::ios::binary);
	std::vector<char> buf((std::istreambuf_iterator<char>(f)), {});
	auto dom = svgdom::load(utki::make_span(buf.data(), buf.size()));
	auto r = svgren::render(*dom, svgren::parameters());
	auto nonzero = std::count_if(r.pixels.begin(), r.pixels.end(), [](uint32_t v) {
		return v != 0;
	});
	std::printf("dims %u %u nonzero_px %zu\n", unsigned(r.dims[0]), unsigned(r.dims[1]), size_t(nonzero));
	std::fwrite(r.pixels.data(), 4, r.pixels.size(), stdout);
	return 0;
}
