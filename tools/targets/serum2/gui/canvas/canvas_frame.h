// SR-40 #2109 (親 #2064): canvas platform (wasm) の IPlatformFrame 実装。
// ネイティブのウィンドウを持たない。描画・入力は後続の canvas 層が担い、ここではサイズと状態だけを保持する。

#pragma once

#include "vstgui/lib/platform/iplatformframe.h"
#include "vstgui/lib/platform/iplatformoptionmenu.h"
#include "vstgui/lib/platform/iplatformtextedit.h"
#include "vstgui/lib/platform/iplatformviewlayer.h"

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasFrame : public IPlatformFrame
{
public:
	CanvasFrame (IPlatformFrameCallback* frame, const CRect& size) noexcept;

	bool getGlobalPosition (CPoint& pos) const override;
	bool setSize (const CRect& newSize) override;
	bool getSize (CRect& size) const override;
	bool getCurrentMousePosition (CPoint& mousePosition) const override;
	bool getCurrentMouseButtons (CButtonState& buttons) const override;
	bool getCurrentModifiers (Modifiers& modifiers) const override;
	bool setMouseCursor (CCursorType type) override;
	bool invalidRect (const CRect& rect) override;
	bool scrollRect (const CRect& src, const CPoint& distance) override;
	bool showTooltip (const CRect& rect, const char* utf8Text) override;
	bool hideTooltip () override;
	void* getPlatformRepresentation () const override;
	SharedPointer<IPlatformTextEdit>
	createPlatformTextEdit (IPlatformTextEditCallback* textEdit) override;
	SharedPointer<IPlatformOptionMenu> createPlatformOptionMenu () override;
	SharedPointer<IPlatformViewLayer>
	createPlatformViewLayer (IPlatformViewLayerDelegate* drawDelegate,
	                         IPlatformViewLayer* parentLayer = nullptr) override;
#if VSTGUI_ENABLE_DEPRECATED_METHODS
	DragResult doDrag (IDataPackage* source, const CPoint& offset, CBitmap* dragBitmap) override;
#endif
	bool doDrag (const DragDescription& dragDescription,
	             const SharedPointer<IDragCallback>& callback) override;
	PlatformType getPlatformType () const override;
	void onFrameClosed () override;
	Optional<UTF8String> convertCurrentKeyEventToText () override;
	bool setupGenericOptionMenu (bool use, GenericOptionMenuTheme* theme = nullptr) override;

private:
	CRect size;
};

} // VSTGUI
