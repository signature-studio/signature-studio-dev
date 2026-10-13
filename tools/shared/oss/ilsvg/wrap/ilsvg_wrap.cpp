// ILSvg の 3 関数 wrapper (#927)。svgdom 0.4.7 + svgren 0.6.4 を wasm / native で共通に呼ぶ。
#include <cstdint>
#include <memory>
#include <svgdom/dom.hpp>
#include <svgren/render.hpp>
#include <utki/span.hpp>

namespace {
struct svg_handle {
	std::unique_ptr<svgdom::svg_element> dom;
	svgren::result last;
};
} // namespace

extern "C" {

void* svgCreate(const uint8_t* data, uint32_t size) {
	try {
		auto h = new svg_handle;
		h->dom = svgdom::load(utki::make_span(data, size));
		return h;
	} catch (...) {
		return nullptr;
	}
}

// 戻り値は ARGB32 ピクセル列 (handle が所有、次の svgRender / svgDestroy まで有効)。
const uint32_t* svgRender(void* handle, uint32_t w, uint32_t h, uint32_t* out_w, uint32_t* out_h) {
	auto hd = static_cast<svg_handle*>(handle);
	svgren::parameters p;
	p.dims_request = {w, h};
	hd->last = svgren::render(*hd->dom, p);
	if (out_w) {
		*out_w = hd->last.dims[0];
	}
	if (out_h) {
		*out_h = hd->last.dims[1];
	}
	return hd->last.pixels.data();
}

void svgDestroy(void* handle) {
	delete static_cast<svg_handle*>(handle);
}

} // extern "C"
