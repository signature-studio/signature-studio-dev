// SR-39 #2107: canvas platform (wasm) の IPlatformFont / IFontPainter 実装。
// SR-50 #3260: 文字は同梱の 5x7 ビットマップフォント (canvas_glyph5x7.h) で描き、幅は 1 字 6 px 固定。
// フォントサイズ・ascent・descent 等のメトリクスは未対応のため upstream の「未対応」値 (-1) を返す。

#pragma once

#include "vstgui/lib/cstring.h"
#include "vstgui/lib/platform/iplatformfont.h"
#include <string>

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasFontPainter : public IFontPainter
{
public:
	void drawString (const PlatformGraphicsDeviceContextPtr& context, IPlatformString* string,
	                 const CPoint& p, const CColor& color, bool antialias = true) const override;
	CCoord getStringWidth (const PlatformGraphicsDeviceContextPtr& context, IPlatformString* string,
	                       bool antialias = true) const override;
};

//------------------------------------------------------------------------
class CanvasFont : public IPlatformFont
{
public:
	CanvasFont (const UTF8String& name, CCoord size) noexcept;

	double getAscent () const override { return -1.; }
	double getDescent () const override { return -1.; }
	double getLeading () const override { return -1.; }
	double getCapHeight () const override { return -1.; }

	const IFontPainter* getPainter () const override { return &painter; }

private:
	std::string name;
	CCoord size;
	CanvasFontPainter painter;
};

} // VSTGUI
