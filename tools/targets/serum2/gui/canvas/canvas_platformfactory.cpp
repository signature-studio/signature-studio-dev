// SR-42 #2139 (親 #2064): canvas platform (wasm) の IPlatformFactory 実装。

#include "canvas_platformfactory.h"
#include "canvas_bitmap.h"
#include "canvas_font.h"
#include "canvas_frame.h"
#include "canvas_string.h"
#include "vstgui/lib/platform/iplatformtimer.h"
#include <chrono>

namespace VSTGUI {

//------------------------------------------------------------------------
uint64_t CanvasPlatformFactory::getTicks () const noexcept
{
	using namespace std::chrono;
	return static_cast<uint64_t> (
	    duration_cast<milliseconds> (steady_clock::now ().time_since_epoch ()).count ());
}

//------------------------------------------------------------------------
PlatformFramePtr CanvasPlatformFactory::createFrame (IPlatformFrameCallback* frame,
                                                     const CRect& size, void* parent,
                                                     PlatformType parentType,
                                                     IPlatformFrameConfig* config) const noexcept
{
	(void)parent;
	(void)parentType;
	(void)config;
	return PlatformFramePtr (new CanvasFrame (frame, size));
}

//------------------------------------------------------------------------
PlatformFontPtr CanvasPlatformFactory::createFont (const UTF8String& name, const CCoord& size,
                                                   const int32_t& style) const noexcept
{
	(void)style;
	return PlatformFontPtr (new CanvasFont (name, size));
}

//------------------------------------------------------------------------
bool CanvasPlatformFactory::getAllFontFamilies (const FontFamilyCallback& callback) const noexcept
{
	(void)callback;
	return false;
}

//------------------------------------------------------------------------
PlatformBitmapPtr CanvasPlatformFactory::createBitmap (const CPoint& size) const noexcept
{
	if (size.x <= 0. || size.y <= 0.)
		return nullptr;
	return PlatformBitmapPtr (
	    new CanvasBitmap (static_cast<uint32_t> (size.x), static_cast<uint32_t> (size.y)));
}

//------------------------------------------------------------------------
PlatformBitmapPtr CanvasPlatformFactory::createBitmap (const CResourceDescription& desc) const
    noexcept
{
	(void)desc;
	return nullptr;
}

//------------------------------------------------------------------------
PlatformBitmapPtr CanvasPlatformFactory::createBitmapFromPath (UTF8StringPtr absolutePath) const
    noexcept
{
	(void)absolutePath;
	return nullptr;
}

//------------------------------------------------------------------------
PlatformBitmapPtr CanvasPlatformFactory::createBitmapFromMemory (const void* ptr,
                                                                 uint32_t memSize) const noexcept
{
	(void)ptr;
	(void)memSize;
	return nullptr;
}

//------------------------------------------------------------------------
PNGBitmapBuffer CanvasPlatformFactory::createBitmapMemoryPNGRepresentation (
    const PlatformBitmapPtr& bitmap) const noexcept
{
	(void)bitmap;
	return {};
}

//------------------------------------------------------------------------
PlatformResourceInputStreamPtr
CanvasPlatformFactory::createResourceInputStream (const CResourceDescription& desc) const noexcept
{
	(void)desc;
	return nullptr;
}

//------------------------------------------------------------------------
PlatformStringPtr CanvasPlatformFactory::createString (UTF8StringPtr utf8String) const noexcept
{
	return PlatformStringPtr (new CanvasString (utf8String));
}

//------------------------------------------------------------------------
PlatformTimerPtr CanvasPlatformFactory::createTimer (IPlatformTimerCallback* callback) const
    noexcept
{
	(void)callback;
	return nullptr;
}

//------------------------------------------------------------------------
bool CanvasPlatformFactory::setClipboard (const DataPackagePtr& data) const noexcept
{
	(void)data;
	return false;
}

//------------------------------------------------------------------------
CanvasPlatformFactory::DataPackagePtr CanvasPlatformFactory::getClipboard () const noexcept
{
	return nullptr;
}

//------------------------------------------------------------------------
PlatformGradientPtr CanvasPlatformFactory::createGradient () const noexcept
{
	return nullptr;
}

//------------------------------------------------------------------------
PlatformFileSelectorPtr CanvasPlatformFactory::createFileSelector (PlatformFileSelectorStyle style,
                                                                   IPlatformFrame* frame) const
    noexcept
{
	(void)style;
	(void)frame;
	return nullptr;
}

//------------------------------------------------------------------------
const IPlatformGraphicsDeviceFactory& CanvasPlatformFactory::getGraphicsDeviceFactory () const
    noexcept
{
	return graphicsDeviceFactory;
}

//------------------------------------------------------------------------
const LinuxFactory* CanvasPlatformFactory::asLinuxFactory () const noexcept
{
	return nullptr;
}

//------------------------------------------------------------------------
const MacFactory* CanvasPlatformFactory::asMacFactory () const noexcept
{
	return nullptr;
}

//------------------------------------------------------------------------
const Win32Factory* CanvasPlatformFactory::asWin32Factory () const noexcept
{
	return nullptr;
}

} // VSTGUI
