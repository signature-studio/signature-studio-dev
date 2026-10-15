// SR-50 #3260: canvas platform (wasm) の IPlatformString 実装。

#include "canvas_string.h"

namespace VSTGUI {

//------------------------------------------------------------------------
CanvasString::CanvasString (UTF8StringPtr utf8String)
{
	setUTF8String (utf8String);
}

//------------------------------------------------------------------------
void CanvasString::setUTF8String (UTF8StringPtr utf8String)
{
	utf8 = utf8String ? utf8String : "";
}

//------------------------------------------------------------------------
std::vector<char32_t> canvasDecodeUTF8 (const std::string& utf8)
{
	std::vector<char32_t> result;
	size_t i = 0;
	while (i < utf8.size ())
	{
		auto lead = static_cast<unsigned char> (utf8[i]);
		size_t length = 1;
		char32_t codePoint = lead;
		if (lead >= 0xF0 && lead < 0xF8)
		{
			length = 4;
			codePoint = lead & 0x07;
		}
		else if (lead >= 0xE0)
		{
			length = lead < 0xF0 ? 3 : 1;
			codePoint = lead & 0x0F;
		}
		else if (lead >= 0xC0)
		{
			length = 2;
			codePoint = lead & 0x1F;
		}
		bool valid = length == 1 ? lead < 0x80 : i + length <= utf8.size ();
		for (size_t k = 1; valid && k < length; ++k)
		{
			auto continuation = static_cast<unsigned char> (utf8[i + k]);
			valid = (continuation & 0xC0) == 0x80;
			codePoint = (codePoint << 6) | (continuation & 0x3F);
		}
		if (!valid)
		{
			length = 1;
			codePoint = 0xFFFD;
		}
		result.push_back (codePoint);
		i += length;
	}
	return result;
}

} // VSTGUI
