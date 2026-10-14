// SR-40 #2109 (親 #2064): canvas platform (wasm) の IPlatformFrame 実装。

#include "canvas_frame.h"

namespace VSTGUI {

//------------------------------------------------------------------------
CanvasFrame::CanvasFrame (IPlatformFrameCallback* frame, const CRect& size) noexcept
: IPlatformFrame (frame)
, size (size)
{}

//------------------------------------------------------------------------
bool CanvasFrame::getGlobalPosition (CPoint& pos) const
{
	pos = size.getTopLeft ();
	return true;
}

//------------------------------------------------------------------------
bool CanvasFrame::setSize (const CRect& newSize)
{
	size = newSize;
	return true;
}

//------------------------------------------------------------------------
bool CanvasFrame::getSize (CRect& s) const
{
	s = size;
	return true;
}

//------------------------------------------------------------------------
bool CanvasFrame::getCurrentMousePosition (CPoint& mousePosition) const
{
	(void)mousePosition;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::getCurrentMouseButtons (CButtonState& buttons) const
{
	(void)buttons;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::getCurrentModifiers (Modifiers& modifiers) const
{
	(void)modifiers;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::setMouseCursor (CCursorType type)
{
	(void)type;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::invalidRect (const CRect& rect)
{
	(void)rect;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::scrollRect (const CRect& src, const CPoint& distance)
{
	(void)src;
	(void)distance;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::showTooltip (const CRect& rect, const char* utf8Text)
{
	(void)rect;
	(void)utf8Text;
	return false;
}

//------------------------------------------------------------------------
bool CanvasFrame::hideTooltip ()
{
	return false;
}

//------------------------------------------------------------------------
void* CanvasFrame::getPlatformRepresentation () const
{
	return nullptr;
}

//------------------------------------------------------------------------
SharedPointer<IPlatformTextEdit>
CanvasFrame::createPlatformTextEdit (IPlatformTextEditCallback* textEdit)
{
	(void)textEdit;
	return nullptr;
}

//------------------------------------------------------------------------
SharedPointer<IPlatformOptionMenu> CanvasFrame::createPlatformOptionMenu ()
{
	return nullptr;
}

//------------------------------------------------------------------------
SharedPointer<IPlatformViewLayer>
CanvasFrame::createPlatformViewLayer (IPlatformViewLayerDelegate* drawDelegate,
                                      IPlatformViewLayer* parentLayer)
{
	(void)drawDelegate;
	(void)parentLayer;
	return nullptr;
}

#if VSTGUI_ENABLE_DEPRECATED_METHODS
//------------------------------------------------------------------------
DragResult CanvasFrame::doDrag (IDataPackage* source, const CPoint& offset, CBitmap* dragBitmap)
{
	(void)source;
	(void)offset;
	(void)dragBitmap;
	return kDragRefused;
}
#endif

//------------------------------------------------------------------------
bool CanvasFrame::doDrag (const DragDescription& dragDescription,
                          const SharedPointer<IDragCallback>& callback)
{
	(void)dragDescription;
	(void)callback;
	return false;
}

//------------------------------------------------------------------------
PlatformType CanvasFrame::getPlatformType () const
{
	return PlatformType::kDefaultNative;
}

//------------------------------------------------------------------------
void CanvasFrame::onFrameClosed () {}

//------------------------------------------------------------------------
Optional<UTF8String> CanvasFrame::convertCurrentKeyEventToText ()
{
	return {};
}

//------------------------------------------------------------------------
bool CanvasFrame::setupGenericOptionMenu (bool use, GenericOptionMenuTheme* theme)
{
	(void)use;
	(void)theme;
	return false;
}

} // VSTGUI
