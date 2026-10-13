"""別算法の検算: lib.mjs とは独立に (Python 標準ライブラリのみ) FL 同梱 EULA.html / ToU(RTF) の正規化 SHA-256 を算出する。

  python3 tools/legal/terms-watch/crosscheck.py <FL_WIN64_DIR>

HTML は html.parser、RTF は正規表現トークナイザで実装し、lib.mjs の htmlToText/rtfToText とはコードを共有しない。
出力は `<id> <sha256> <chars>`。台帳 (docs/LEGAL_TERMS_LEDGER.json) の値と一致することを期待する。
"""
import hashlib
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub("[\u200b-\u200d\u2060\ufeff\u00ad]", "", s)
    s = re.sub("[\u2018\u2019\u201a\u201b\u02bc\u2032]", "'", s)
    s = re.sub("[\u201c-\u201f\u2033]", '"', s)
    s = re.sub("[\u2010-\u2015\u2212]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


class Html(HTMLParser):
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "section", "table", "thead", "tbody", "tfoot", "caption", "ul", "ol", "dl", "dt", "dd", "br", "hr", "blockquote", "pre", "article", "main", "title", "option", "select"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.depth_skip, self.in_head, self.in_title = [], 0, False, False

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.depth_skip += 1
        elif tag == "head":
            self.in_head = True
        elif tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.depth_skip -= 1
        elif tag == "head":
            self.in_head = False
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.depth_skip == 0 and (not self.in_head or self.in_title):
            self.out.append(data)


def html_text(b: bytes) -> str:
    p = Html()
    p.feed(b.decode("utf-8"))
    return "".join(p.out)


SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "listtable", "listoverridetable", "pict", "generator", "fldinst", "latentstyles", "themedata", "colorschememapping", "datastore", "rsidtbl", "xmlnstbl"}
SYM = {"bullet": "\u2022", "endash": "\u2013", "emdash": "\u2014", "lquote": "\u2018", "rquote": "\u2019", "ldblquote": "\u201c", "rdblquote": "\u201d", "tab": "\t", "emspace": " ", "enspace": " "}
TOK = re.compile(r"\\'([0-9a-fA-F]{2})|\\([a-zA-Z]+)(-?\d+)? ?|\\([^a-zA-Z'])|([{}])|([^\\{}]+)", re.S)


def rtf_text(raw: str) -> str:
    out, stack, skip, uc, pending = [], [], False, 1, 0
    for m in TOK.finditer(raw):
        hexb, word, num, sym, brace, text = m.groups()
        if brace == "{":
            stack.append((skip, uc))
            continue
        if brace == "}":
            skip, uc = stack.pop() if stack else (False, 1)
            pending = 0
            continue
        if hexb is not None:
            if pending:
                pending -= 1
            elif not skip:
                out.append(bytes([int(hexb, 16)]).decode("cp1252"))
            continue
        if text is not None:
            text = text.replace("\r", "").replace("\n", "")
            if pending:
                k = min(pending, len(text))
                text, pending = text[k:], pending - k
            if not skip:
                out.append(text)
            continue
        if sym is not None:
            if sym == "*":
                skip = True
            elif sym in "\\{}" and not skip:
                out.append(sym)
            elif sym == "~" and not skip:
                out.append(" ")
            elif sym == "_" and not skip:
                out.append("-")
            continue
        if word in SKIP:
            skip = True
        elif skip:
            continue
        elif word in ("par", "line", "sect", "page"):
            out.append("\n")
        elif word == "uc" and num is not None:
            uc = int(num)
        elif word == "u" and num is not None:
            n = int(num)
            out.append(chr(n + 65536 if n < 0 else n))
            pending = uc
        elif word in SYM:
            out.append(SYM[word])
    return "".join(out)


def find(root: Path, head: re.Pattern, body: list[re.Pattern]) -> bytes:
    hits = {}
    for f in sorted(root.glob("*_DATA.bin")):
        if f.stat().st_size > 4_000_000:
            continue
        d = f.read_bytes()
        if head.search(d[:8192].decode("latin1")) and all(r.search(d.decode("latin1")) for r in body):
            hits[f.name] = d
    assert len({hashlib.sha256(v).hexdigest() for v in hits.values()}) == 1, hits.keys()
    return next(iter(hits.values()))


if __name__ == "__main__":
    base = Path(sys.argv[1])
    root = base / "extracted" if (base / "extracted").exists() else base
    docs = {
        "fl-eula-html": html_text(find(root, re.compile(r"<title>[^<]*IMAGE LINE SOFTWARE EULA"), [])),
        "fl-tou-rtf": rtf_text(find(root, re.compile(r"^\{\\rtf1"), [re.compile("TERMS OF USE"), re.compile("Applicability"), re.compile("Cracked")]).decode("latin1")),
    }
    for k, v in docs.items():
        n = normalize(v)
        print(k, hashlib.sha256(n.encode()).hexdigest(), len(n))
