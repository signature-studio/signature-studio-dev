// SR-35 #2064: canvas platform (wasm) の IPlatformBitmap 実装。

#include "canvas_bitmap.h"

namespace VSTGUI {

//------------------------------------------------------------------------
CanvasBitmap::CanvasBitmap (uint32_t width, uint32_t height) noexcept
: size (width, height)
, pixels (static_cast<size_t> (width) * height * 4, 0)
{}

//------------------------------------------------------------------------
SharedPointer<IPlatformBitmapPixelAccess> CanvasBitmap::lockPixels (bool alphaPremultiplied)
{
	(void)alphaPremultiplied;
	auto bytesPerRow = static_cast<uint32_t> (size.x) * 4;
	return SharedPointer<IPlatformBitmapPixelAccess> (
	    new CanvasBitmapPixelAccess (pixels.data (), bytesPerRow,
	                                 IPlatformBitmapPixelAccess::kRGBA));
}

//------------------------------------------------------------------------
CanvasBitmapPixelAccess::CanvasBitmapPixelAccess (uint8_t* address, uint32_t bytesPerRow,
                                                  PixelFormat format) noexcept
: address (address)
, bytesPerRow (bytesPerRow)
, format (format)
{}

} // VSTGUI
