// SR-39 #2107: canvas platform (wasm) の IPlatformFont / IFontPainter 実装。
// SR-50 #3260: drawString は canvas_graphicsdevice の context へ字形の点灯画素を書く。

#include "canvas_font.h"
#include "canvas_glyph5x7.h"
#include "canvas_graphicsdevice.h"
#include "canvas_string.h"
#include "vstgui/lib/cstring.h"
#include <cmath>

namespace VSTGUI {

namespace {

//------------------------------------------------------------------------
// p を左上基準の字形枠の基準点とし、字形の上端は p.y - 字形の高さ とする (文字の下端が p.y - 1 行目まで)。
void paintGlyphs (const CanvasGraphicsDeviceContext& target, const std::string& utf8, const CPoint& p,
                  const CColor& color)
{
	auto x = static_cast<int32_t> (std::floor (p.x));
	auto top = static_cast<int32_t> (std::floor (p.y)) - kCanvasGlyphHeight;
	for (auto codePoint : canvasDecodeUTF8 (utf8))
	{
		const auto* glyph = canvasGlyph5x7 (codePoint);
		for (int32_t row = 0; row < kCanvasGlyphHeight; ++row)
		{
			for (int32_t col = 0; col < kCanvasGlyphWidth; ++col)
			{
				if (glyph[row] & (0x10 >> col))
					target.blendPixel (x + col, top + row, color);
			}
		}
		x += kCanvasGlyphAdvance;
	}
}

} // namespace

//------------------------------------------------------------------------
void CanvasFontPainter::drawString (const PlatformGraphicsDeviceContextPtr& context,
                                    IPlatformString* string, const CPoint& p, const CColor& color,
                                    bool antialias) const
{
	(void)antialias;
	auto* canvasContext = dynamic_cast<const CanvasGraphicsDeviceContext*> (context.get ());
	auto* canvasString = dynamic_cast<CanvasString*> (string);
	if (canvasContext && canvasString)
		paintGlyphs (*canvasContext, canvasString->getUTF8String (), p, color);
}

//------------------------------------------------------------------------
CCoord CanvasFontPainter::getStringWidth (const PlatformGraphicsDeviceContextPtr& context,
                                          IPlatformString* string, bool antialias) const
{
	(void)context;
	(void)antialias;
	auto* canvasString = dynamic_cast<CanvasString*> (string);
	if (!canvasString)
		return 0.;
	return static_cast<CCoord> (kCanvasGlyphAdvance)
	     * static_cast<CCoord> (canvasDecodeUTF8 (canvasString->getUTF8String ()).size ());
}

//------------------------------------------------------------------------
CanvasFont::CanvasFont (const UTF8String& name, CCoord size) noexcept
: name (name.getString ())
, size (size)
{}

} // VSTGUI
