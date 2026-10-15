// SR-50 #3260: canvas platform (wasm) の IPlatformString 実装。
// 文字列は UTF-8 のまま std::string に保持する。ワイド文字列の変換は要らない (IPlatformString は setUTF8String のみ)。

#pragma once

#include "vstgui/lib/platform/iplatformstring.h"
#include <string>
#include <vector>

namespace VSTGUI {

//------------------------------------------------------------------------
class CanvasString : public IPlatformString
{
public:
	explicit CanvasString (UTF8StringPtr utf8String = nullptr);

	void setUTF8String (UTF8StringPtr utf8String) override;

	const std::string& getUTF8String () const noexcept { return utf8; }

private:
	std::string utf8;
};

//------------------------------------------------------------------------
// UTF-8 をコードポイントの列へ分解する。不正なバイト並びは 0xFFFD にして 1 バイト進める。
std::vector<char32_t> canvasDecodeUTF8 (const std::string& utf8);

} // VSTGUI
