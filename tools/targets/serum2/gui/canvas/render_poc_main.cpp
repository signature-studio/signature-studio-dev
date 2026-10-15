// SR-36 #2065: CTextLabel のみの canvas 描画 harness (wasm)。検証専用で製品には入らない。
// 描画経路: CanvasPlatformFactory → CTextLabel → CDrawContext (canvas の graphics device context) → CViewContainer::draw。
// 注意: CanvasGraphicsDevice::createBitmapContext は引数の bitmap を使わず、描画命令は false を返すため、
// 描画経路は bitmap に書き込まない。after の画素数は構造上 0 になる (成功扱いにしない)。
// control は計数ロジックの陽性対照 (bitmap へ 1 画素を直接書いたときに 1 と数えること) で、描画の証拠ではない。

#include "canvas_bitmap.h"
#include "canvas_graphicsdevice.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/controls/ctextlabel.h"
#include "vstgui/lib/cviewcontainer.h"
#include "vstgui/lib/vstguiinit.h"
#include <cstdio>
#include <memory>

namespace {

constexpr uint32_t kWidth = 200;
constexpr uint32_t kHeight = 60;

size_t countNonZeroPixels (const uint8_t* rgba, size_t byteCount)
{
	size_t n = 0;
	for (size_t i = 0; i < byteCount; i += 4)
	{
		if (rgba[i] || rgba[i + 1] || rgba[i + 2] || rgba[i + 3])
			++n;
	}
	return n;
}

} // namespace

int main ()
{
	using namespace VSTGUI;
	// 初期化は upstream の init() (initPlatform → CFontDesc::init) を使う。wasm の factory は platformfactory.cpp の WASM 分岐が定義する。
	init (nullptr);
	const size_t byteCount = static_cast<size_t> (kWidth) * kHeight * 4;

	CanvasBitmap bitmap (kWidth, kHeight);
	const size_t before = countNonZeroPixels (bitmap.data (), byteCount);

	bitmap.data () [0] = 255;
	const size_t control = countNonZeroPixels (bitmap.data (), byteCount);
	bitmap.data () [0] = 0;

	auto device = std::make_shared<CanvasGraphicsDevice> ();
	auto deviceContext = std::make_shared<CanvasGraphicsDeviceContext> (device);
	CDrawContext drawContext (deviceContext, CRect (0, 0, kWidth, kHeight), 1.);

	auto* container = new CViewContainer (CRect (0, 0, kWidth, kHeight));
	auto* label = new CTextLabel (CRect (0, 0, kWidth, kHeight), "Signature");
	container->addView (label);

	drawContext.beginDraw ();
	container->draw (&drawContext);
	drawContext.endDraw ();

	const size_t after = countNonZeroPixels (bitmap.data (), byteCount);
	drawContext.setFont (label->getFont ());
	const CCoord textWidth = drawContext.getStringWidth (label->getText ().data ());
	std::printf ("render_poc size=%ux%u bytes=%zu nonzero_before=%zu control=%zu nonzero_after=%zu text=%s text_width=%g\n",
	             kWidth, kHeight, byteCount, before, control, after, label->getText ().data (), textWidth);
	return 0;
}
