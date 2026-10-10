"""ir.py — RetDec .ll (raw / 正規化後) の軽量テキストモデル。

`, !insn.addr !N` (N→機械語 VA は末尾の `!N = !{i64 VA}`) を行に保持したまま扱う。
Module.dump(strip=True) で insn.addr を除去 (従来チェーン出力とのテキスト比較用)。
"""
import re

META_DEF = re.compile(r"^!(\d+) = !\{i64 (\d+)\}\s*$")
INSN_TOK = re.compile(r"(?:,\s*|\s+)!insn\.addr !(\d+)")
DEFINE = re.compile(r'^define\s+(.*?)@([\w$.\-]+)\((.*)\)(.*?)\{\s*$')
LABEL = re.compile(r"^([\w$.\-]+):(\s*;.*)?$")
DST = re.compile(r"^\s*(%[\w$.\-]+) = ")
CALL = re.compile(r"\bcall\b[^@]*@([\w$.\-]+)\(")


def strip_tokens(line):
    return INSN_TOK.sub("", line)


class Block:
    __slots__ = ("label", "header", "lines")

    def __init__(self, label, header, lines):
        self.label, self.header, self.lines = label, header, lines


class Func:
    def __init__(self, name, sig, blocks, trailer):
        self.name, self.sig, self.blocks, self.trailer = name, sig, blocks, trailer

    def render(self):
        out = [self.sig]
        for b in self.blocks:
            if b.header is not None:
                out.append(b.header)
            out.extend(b.lines)
        out.extend(self.trailer)
        return out

    def block(self, label):
        for b in self.blocks:
            if b.label == label:
                return b
        return None

    def block_index(self, label):
        for i, b in enumerate(self.blocks):
            if b.label == label:
                return i
        return -1

    def params(self):
        m = DEFINE.match(self.sig)
        args = m.group(3).strip()
        if not args:
            return []
        out = []
        depth = 0
        cur = ""
        for ch in args:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
            else:
                cur += ch
        out.append(cur.strip())
        return [tuple(p.rsplit(" ", 1)) for p in out]   # (type, %name)

    def ret_type(self):
        m = DEFINE.match(self.sig)
        return m.group(1).split()[0]

    def instr_lines(self):
        for bi, b in enumerate(self.blocks):
            for li, ln in enumerate(b.lines):
                yield bi, li, ln


class Module:
    def __init__(self):
        self.items = []        # str | Func
        self.meta = {}         # id -> va
        self._va_meta = {}
        self.next_meta = 0

    # ---- load -------------------------------------------------------------
    @classmethod
    def parse(cls, text):
        m = cls()
        lines = text.split("\n")
        body = []
        for ln in lines:
            md = META_DEF.match(ln)
            if md:
                i, va = int(md.group(1)), int(md.group(2))
                m.meta[i] = va
                m._va_meta.setdefault(va, i)
                continue
            if re.match(r"^!\w[\w.\-]* *= ", ln) or re.match(r"^!\d+ = ", ln):
                continue          # llvm.module.flags など (不要)
            body.append(ln)
        m.next_meta = (max(m.meta) + 1) if m.meta else 0
        i = 0
        n = len(body)
        while i < n:
            ln = body[i]
            if ln.startswith("define "):
                j = i + 1
                while j < n and body[j] != "}":
                    j += 1
                blk = body[i + 1:j]
                trailer = [body[j]] if j < n else []
                m.items.append(cls._parse_func(ln, blk, trailer))
                i = j + 1
            else:
                m.items.append(ln)
                i += 1
        return m

    @staticmethod
    def _parse_func(sig, blk, trailer):
        name = DEFINE.match(sig).group(2)
        blocks, cur = [], None
        for ln in blk:
            lm = LABEL.match(ln)
            if lm and not ln.startswith(" "):
                cur = Block(lm.group(1), ln, [])
                blocks.append(cur)
            else:
                if cur is None:
                    cur = Block(None, None, [])
                    blocks.append(cur)
                cur.lines.append(ln)
        return Func(name, sig, blocks, trailer)

    @classmethod
    def load(cls, path):
        with open(path) as fh:
            return cls.parse(fh.read())

    # ---- access -----------------------------------------------------------
    def funcs(self):
        return [it for it in self.items if isinstance(it, Func)]

    def func(self, name):
        for it in self.items:
            if isinstance(it, Func) and it.name == name:
                return it
        return None

    def addr_of(self, line):
        m = INSN_TOK.search(line)
        if not m:
            return None
        return self.meta.get(int(m.group(1)))

    def tag(self, va):
        """新規命令に付ける `, !insn.addr !N` トークン。"""
        i = self._va_meta.get(va)
        if i is None:
            i = self.next_meta
            self.next_meta += 1
            self.meta[i] = va
            self._va_meta[va] = i
        return ", !insn.addr !%d" % i

    def declares(self):
        out = {}
        for it in self.items:
            if isinstance(it, str):
                m = re.match(r"^declare\s+(\S+)\s+@([\w$.\-]+)\((.*?)\)", it)
                if m:
                    out[m.group(2)] = (m.group(1), m.group(3), it)
        return out

    def add_declare(self, line):
        # 先頭の最初の define の直前に挿入
        for i, it in enumerate(self.items):
            if isinstance(it, Func):
                self.items.insert(i, line)
                return
        self.items.append(line)

    def add_global(self, line):
        for i, it in enumerate(self.items):
            if isinstance(it, str) and it.startswith("declare "):
                self.items.insert(i, line)
                return
            if isinstance(it, Func):
                self.items.insert(i, line)
                return
        self.items.append(line)

    # ---- dump -------------------------------------------------------------
    def dump(self, strip=False):
        out = []
        for it in self.items:
            if isinstance(it, Func):
                out.extend(it.render())
            else:
                out.append(it)
        if strip:
            out = [strip_tokens(l) for l in out]
            while out and out[-1] == "":
                out.pop()
        else:
            used = set()
            for l in out:
                for mm in INSN_TOK.finditer(l):
                    used.add(int(mm.group(1)))
            while out and out[-1] == "":
                out.pop()
            out.append("")
            for i in sorted(used):
                out.append("!%d = !{i64 %d}" % (i, self.meta[i]))
        res = []
        for l in out:
            if l == "" and res and res[-1] == "":
                continue
            res.append(l)
        text = "\n".join(res)
        if not text.endswith("\n"):
            text += "\n"
        return text


def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def instr_dst(line):
    m = DST.match(line)
    return m.group(1) if m else None
