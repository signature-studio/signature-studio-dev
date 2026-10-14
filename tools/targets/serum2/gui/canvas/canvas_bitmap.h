// SR-35 #2064: canvas platform (wasm) の IPlatformBitmap 実装。
// 画素は RGBA8 の連続メモリ (行長 = width * 4)。描画先は後続の canvas 層が担う。

#pragma once

#include "vstgui/lib/cpoint.h"
#include "vstgui/lib/platform/iplatformbitmap.h"
#include <cstdint>
#include <vector>

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasBitmap : public IPlatformBitmap
{
public:
	CanvasBitmap (uint32_t width, uint32_t height) noexcept;

	const CPoint& getSize () const override { return size; }

	SharedPointer<IPlatformBitmapPixelAccess> lockPixels (bool alphaPremultiplied) override;

	void setScaleFactor (double factor) override { scaleFactor = factor; }
	double getScaleFactor () const override { return scaleFactor; }

	uint8_t* data () { return pixels.data (); }

private:
	CPoint size;
	double scaleFactor {1.};
	std::vector<uint8_t> pixels;
};

//------------------------------------------------------------------------
class CanvasBitmapPixelAccess : public IPlatformBitmapPixelAccess
{
public:
	CanvasBitmapPixelAccess (uint8_t* address, uint32_t bytesPerRow, PixelFormat format) noexcept;

	uint8_t* getAddress () const override { return address; }
	uint32_t getBytesPerRow () const override { return bytesPerRow; }
	PixelFormat getPixelFormat () const override { return format; }

private:
	uint8_t* address;
	uint32_t bytesPerRow;
	PixelFormat format;
};

} // VSTGUI
