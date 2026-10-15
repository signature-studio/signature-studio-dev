// SR-42 #2139 (親 #2064): canvas platform (wasm) の IPlatformFactory 実装。
// 既存の canvas 実装 (bitmap / font / frame / graphicsdevice / graphicspath) を組み合わせる。
// 資源の読込み・文字列・タイマー・クリップボードなどの実体を持たない関数は nullptr・false・空値を返す。

#pragma once

#include "canvas_graphicsdevice.h"
#include "vstgui/lib/platform/platformfactory.h"

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasPlatformFactory : public IPlatformFactory
{
public:
	explicit CanvasPlatformFactory (PlatformInstanceHandle) noexcept {}

	uint64_t getTicks () const noexcept override;

	PlatformFramePtr createFrame (IPlatformFrameCallback* frame, const CRect& size, void* parent,
	                              PlatformType parentType,
	                              IPlatformFrameConfig* config = nullptr) const noexcept override;

	PlatformFontPtr createFont (const UTF8String& name, const CCoord& size,
	                            const int32_t& style) const noexcept override;
	bool getAllFontFamilies (const FontFamilyCallback& callback) const noexcept override;

	PlatformBitmapPtr createBitmap (const CPoint& size) const noexcept override;
	PlatformBitmapPtr createBitmap (const CResourceDescription& desc) const noexcept override;
	PlatformBitmapPtr createBitmapFromPath (UTF8StringPtr absolutePath) const noexcept override;
	PlatformBitmapPtr createBitmapFromMemory (const void* ptr,
	                                          uint32_t memSize) const noexcept override;
	PNGBitmapBuffer
	createBitmapMemoryPNGRepresentation (const PlatformBitmapPtr& bitmap) const noexcept override;

	PlatformResourceInputStreamPtr
	createResourceInputStream (const CResourceDescription& desc) const noexcept override;

	PlatformStringPtr createString (UTF8StringPtr utf8String = nullptr) const noexcept override;
	PlatformTimerPtr createTimer (IPlatformTimerCallback* callback) const noexcept override;

	bool setClipboard (const DataPackagePtr& data) const noexcept override;
	DataPackagePtr getClipboard () const noexcept override;

	PlatformGradientPtr createGradient () const noexcept override;
	PlatformFileSelectorPtr createFileSelector (PlatformFileSelectorStyle style,
	                                            IPlatformFrame* frame) const noexcept override;

	const IPlatformGraphicsDeviceFactory& getGraphicsDeviceFactory () const noexcept override;

	const LinuxFactory* asLinuxFactory () const noexcept override;
	const MacFactory* asMacFactory () const noexcept override;
	const Win32Factory* asWin32Factory () const noexcept override;

private:
	CanvasGraphicsDeviceFactory graphicsDeviceFactory;
};

} // VSTGUI
