// SR-39 #2107: canvas platform (wasm) の IPlatformFont / IFontPainter 実装。

#include "canvas_font.h"
#include "vstgui/lib/cstring.h"

namespace VSTGUI {

//------------------------------------------------------------------------
void CanvasFontPainter::drawString (const PlatformGraphicsDeviceContextPtr& context,
                                    IPlatformString* string, const CPoint& p, const CColor& color,
                                    bool antialias) const
{
	(void)context;
	(void)string;
	(void)p;
	(void)color;
	(void)antialias;
}

//------------------------------------------------------------------------
CCoord CanvasFontPainter::getStringWidth (const PlatformGraphicsDeviceContextPtr& context,
                                          IPlatformString* string, bool antialias) const
{
	(void)context;
	(void)string;
	(void)antialias;
	return 0.;
}

//------------------------------------------------------------------------
CanvasFont::CanvasFont (const UTF8String& name, CCoord size) noexcept
: name (name.getString ())
, size (size)
{}

} // VSTGUI
