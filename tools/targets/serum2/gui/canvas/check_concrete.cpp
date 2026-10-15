// SR-39 #2107: canvas platform の新規クラスが具象 (純粋仮想の実装漏れなし) であることを確認する。
// 検査のみ。実行は REPORT_EFFORT.md §13 のコマンドで em++ -fsyntax-only する (リンクはしない)。

#include "canvas_font.h"
#include "canvas_graphicsdevice.h"
#include "canvas_platformfactory.h"
#include "canvas_string.h"
#include <memory>
#include <type_traits>

static_assert(!std::is_abstract_v<VSTGUI::CanvasString>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasFontPainter>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasFont>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasGraphicsDeviceFactory>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasGraphicsDevice>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasGraphicsDeviceContext>);
static_assert(!std::is_abstract_v<VSTGUI::CanvasPlatformFactory>);

int main ()
{
	VSTGUI::CanvasFont font {"sans", 12.};
	auto device = std::make_shared<VSTGUI::CanvasGraphicsDevice> ();
	VSTGUI::CanvasGraphicsDeviceContext context {device, VSTGUI::PlatformBitmapPtr {}};
	return font.getPainter () ? 0 : 1;
}
