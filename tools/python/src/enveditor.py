"""enveditor — FL Studio Edison (波形エディタ) scripting module (純 Python 実装)。

FL 実機の `enveditor` は Edison (Delphi) 内にある。本モジュールは Audio scripts (.pyscript) が使う面を、
ホスト側の in-memory サンプルに対して提供する。仕様の正本は同梱ドキュメント
「Edison Script Reference」(FL_WIN64 DATA block24447) の 1〜5 節。

対象は Audio scripts が参照するメンバ (Sample / Region / Editor / Utils / ScriptDialog)。
実機の挙動が未確認のものは `# ASSUMPTION:` で明示する。戻り値の mock 値は REPORT に列挙する。
"""
import math
import sys

import flpianoroll
from flpianoroll import ScriptDialog  # noqa: F401  (Edison も同じ ScriptDialog を使う: 仕様 5 節)

# PasteFromTo modes (仕様 4 節)
PASTE_INSERT = 0
PASTE_REPLACE = 1
PASTE_MIX = 2

# NormalizeFormat flags (仕様 4 節)
NF_NumChannels = 1
NF_Format = 2
NF_Samplerate = 4
NF_All = 7
nfAll = NF_All

# ConvertToMono modes
CM_MergeLR = 0
CM_Left = 1
CM_Right = 2

DEFAULT_SAMPLE_RATE = 44100  # ASSUMPTION: 新規 Sample の既定値 (仕様に記載なし)
DEFAULT_NUM_CHANS = 2        # ASSUMPTION: 同上


class TUtils:
    def __init__(self):
        self.messages = []

    def ProgressMsg(self, Msg, Pos, Total):
        self.messages.append(("progress", (Msg, Pos, Total)))

    def ShowMessage(self, Msg):
        self.messages.append(("message", Msg))


class Region:
    """仕様 4 節 `def Region`。SampleEnd が Length を超えるものは region ではなく marker (仕様記載)。"""

    def __init__(self, SampleStart=0, SampleEnd=0, Name="", Info="", Time=0.0, KeyNum=0):
        self.SampleStart = SampleStart
        self.SampleEnd = SampleEnd
        self.Name = Name
        self.Info = Info
        self.Time = Time
        self.KeyNum = KeyNum

    def Copy(self, Source):
        self.SampleStart = Source.SampleStart
        self.SampleEnd = Source.SampleEnd
        self.Name = Source.Name
        self.Info = Source.Info
        self.Time = Source.Time
        self.KeyNum = Source.KeyNum


class Sample:
    """仕様 4 節 `def Sample`。サンプル値は float。ch ごとのリストで保持する。"""

    def __init__(self):
        self.SampleRate = DEFAULT_SAMPLE_RATE
        self._chans = [[] for _ in range(DEFAULT_NUM_CHANS)]
        self._regions = []

    # -- properties
    @property
    def Length(self):
        return len(self._chans[0]) if self._chans else 0

    @Length.setter
    def Length(self, value):
        n = int(value)
        if n < 0:
            raise ValueError("Length must be >= 0")
        # ASSUMPTION: Length の設定は末尾を 0 埋め / 切り詰め (同梱 genPulse/genSine が 0 から書く用途のみ確認)
        for ch in self._chans:
            if n <= len(ch):
                del ch[n:]
            else:
                ch.extend([0.0] * (n - len(ch)))

    @property
    def NumChans(self):
        return len(self._chans)

    @NumChans.setter
    def NumChans(self, value):
        n = int(value)
        if n < 1:
            raise ValueError("NumChans must be >= 1")
        # ASSUMPTION: チャンネル数の増加は先頭 ch の複製 (モノ→ステレオ)、減少は末尾を捨てる
        while len(self._chans) < n:
            self._chans.append(list(self._chans[0]) if self._chans else [0.0] * self.Length)
        del self._chans[n:]

    @property
    def RegionCount(self):
        return len(self._regions)

    # -- sample access
    def _check(self, pos, ch):
        if not 0 <= ch < len(self._chans):
            raise IndexError(f"channel {ch} out of range")
        if not 0 <= pos < self.Length:
            raise IndexError(f"position {pos} out of range")  # ASSUMPTION: 範囲外は IndexError

    def GetSampleAt(self, Position, Channel):
        self._check(int(Position), int(Channel))
        return self._chans[int(Channel)][int(Position)]

    def SetSampleAt(self, Position, Channel, Value):
        self._check(int(Position), int(Channel))
        self._chans[int(Channel)][int(Position)] = float(Value)

    def _span(self, x1, x2):
        x1, x2 = int(x1), int(x2)
        # ASSUMPTION: 範囲は [0, Length-1] にクリップする (仕様は inclusive としか書かない)
        return max(0, x1), min(self.Length - 1, x2)

    def _each(self, x1, x2, fn):
        a, b = self._span(x1, x2)
        for ch in self._chans:
            for n in range(a, b + 1):
                ch[n] = fn(ch[n], n)

    def AmpFromTo(self, x1, x2, Vol):
        self._each(x1, x2, lambda v, n: v * Vol)

    def SilenceFromTo(self, x1, x2):
        self._each(x1, x2, lambda v, n: 0.0)

    def SineFromTo(self, x1, x2, Freq, Phase, Vol=1.0):
        # ASSUMPTION: Phase はラジアン・x1 を位相 0 の基準とする (仕様に記載なし)
        rate = float(self.SampleRate)
        base = int(x1)
        self._each(x1, x2, lambda v, n: Vol * math.sin(2 * math.pi * Freq * (n - base) / rate + Phase))

    def NormalizeFromTo(self, x1, x2, Vol, OnlyIfAbove=False):
        a, b = self._span(x1, x2)
        peak = max((abs(ch[n]) for ch in self._chans for n in range(a, b + 1)), default=0.0)
        if peak == 0.0 or (OnlyIfAbove and peak <= Vol):
            return
        k = Vol / peak
        self._each(x1, x2, lambda v, n: v * k)

    def PasteFromTo(self, aSample, x1, x2, Mode):
        # 仕様: x1 と x2 がブロックサイズを決め、x2 = 0 で aSample の全長を使う。
        # ASSUMPTION: 貼付け先は [x1, x1+len-1]。チャンネル数が違えば aSample の ch は先頭から循環して使う。
        x1 = int(x1)
        length = aSample.Length if int(x2) == 0 else min(aSample.Length, int(x2) - x1 + 1)
        if length <= 0:
            return
        src = [[aSample._chans[c % aSample.NumChans][i] for i in range(length)] for c in range(self.NumChans)]
        if Mode == PASTE_INSERT:
            for c, ch in enumerate(self._chans):
                ch[x1:x1] = src[c]
        elif Mode == PASTE_REPLACE or Mode == PASTE_MIX:
            need = x1 + length
            for c, ch in enumerate(self._chans):
                if need > len(ch):
                    ch.extend([0.0] * (need - len(ch)))
                for i in range(length):
                    ch[x1 + i] = src[c][i] if Mode == PASTE_REPLACE else ch[x1 + i] + src[c][i]
        else:
            raise ValueError(f"PasteFromTo: unknown mode {Mode}")

    def NormalizeFormat(self, Source, Mode=NF_All):
        # ASSUMPTION: サンプル形式 (ビット深度) は保持しない mock のため NF_Format は no-op
        if Mode & NF_NumChannels:
            self.NumChans = Source.NumChans
        if Mode & NF_Samplerate:
            self.SampleRate = Source.SampleRate

    def ConvertToMono(self, mode):
        if self.NumChans < 2:
            return
        if mode == CM_Left:
            mono = list(self._chans[0])
        elif mode == CM_Right:
            mono = list(self._chans[1])
        else:
            mono = [(a + b) * 0.5 for a, b in zip(self._chans[0], self._chans[1])]
        self._chans = [mono]

    def CenterFromTo(self, x1, x2):
        a, b = self._span(x1, x2)
        for ch in self._chans:
            mean = sum(ch[a:b + 1]) / (b - a + 1) if b >= a else 0.0
            for n in range(a, b + 1):
                ch[n] -= mean

    def ReverseFromTo(self, x1, x2):
        a, b = self._span(x1, x2)
        for ch in self._chans:
            ch[a:b + 1] = ch[a:b + 1][::-1]

    def ReversePolarityFromTo(self, x1, x2):
        self._each(x1, x2, lambda v, n: -v)

    def SwapChannelsFromTo(self, x1, x2):
        if self.NumChans < 2:
            return
        a, b = self._span(x1, x2)
        for n in range(a, b + 1):
            self._chans[0][n], self._chans[1][n] = self._chans[1][n], self._chans[0][n]

    def InsertSilence(self, x1, x2):
        # 仕様: x1 位置に (x2-x1+1) 個の 0 を挿入する
        k = int(x2) - int(x1) + 1
        for ch in self._chans:
            ch[int(x1):int(x1)] = [0.0] * k

    def NoiseFromTo(self, x1, x2, Mode=1, Vol=1):
        import random
        # ASSUMPTION: 乱数源は Python 標準 random (実機の乱数系列とは一致しない)
        def gen(v, n):
            return (random.gauss(0.0, 1.0) if Mode == 1 else random.uniform(-1.0, 1.0)) * Vol
        self._each(x1, x2, gen)

    def DeleteFromTo(self, x1, x2, Copy=False):
        a, b = self._span(x1, x2)
        for ch in self._chans:
            del ch[a:b + 1]

    def TrimFromTo(self, x1, x2):
        a, b = self._span(x1, x2)
        for ch in self._chans:
            ch[:] = ch[a:b + 1]

    def MSToSamples(self, Time):
        return Time * self.SampleRate / 1000.0

    def SamplesToMS(self, Time):
        return Time * 1000.0 / self.SampleRate

    def LoadFromClipboard(self):
        # MOCK: 実 FL のクリップボードは無い。ホストが set_clipboard で注入する。未注入なら空 (Length 0)。
        self._chans = [[] for _ in range(DEFAULT_NUM_CHANS)]
        self._regions = []

    def LoadFromFile(self, Filename):
        # ASSUMPTION: 仮想 FS 上の 16bit PCM WAV は未対応。mock では読み込まず例外にする (実 FL の失敗種別は未確認)
        raise NotImplementedError("LoadFromFile: mock 未対応 (WAV デコード未実装)")

    def LoadFromFile_Ask(self):
        raise NotImplementedError("LoadFromFile_Ask: headless では対話ダイアログを出せない (mock 未対応)")

    # -- regions
    def AddRegion(self, Name, SampleStart, SampleEnd):
        r = Region(SampleStart=int(SampleStart), SampleEnd=int(SampleEnd), Name=Name)
        self._regions.append(r)
        # ASSUMPTION: region は SampleStart 昇順に並べる。返り値はその index
        self._regions.sort(key=lambda x: x.SampleStart)
        return self._regions.index(r)

    def DeleteRegion(self, Index):
        if not 0 <= Index < len(self._regions):
            raise IndexError("region index out of range")
        del self._regions[Index]

    def GetRegion(self, Index):
        if not 0 <= Index < len(self._regions):
            raise IndexError("region index out of range")
        return self._regions[Index]  # live 参照 (同梱 Markers→Regions 変換は in-place 更新する)


class TEditor:
    """仕様 4 節 `def Editor`。選択範囲はホストが set_selection で注入する。"""

    def __init__(self):
        self._sel = (0, 0)

    @property
    def SelectionStartS(self):
        return self._sel[0]

    @property
    def SelectionEndS(self):
        return self._sel[1]

    def set_selection(self, start, end):
        self._sel = (int(start), int(end))


EditorSample = Sample()
Editor = TEditor()
Utils = TUtils()

__all__ = ["Sample", "Region", "Editor", "EditorSample", "Utils", "ScriptDialog",
           "PASTE_INSERT", "PASTE_REPLACE", "PASTE_MIX", "NF_NumChannels", "NF_Format", "NF_Samplerate", "NF_All",
           "nfAll", "CM_MergeLR", "CM_Left", "CM_Right", "reset", "install"]


def reset(sample=None, selection=None):
    """新しい run 用に EditorSample / Editor / Utils をリセットする (同一オブジェクトを in-place 更新)。
    sample は {"ch": [[...], ...], "rate": int, "regions": [...]} (ホストの JSON 形式)。"""
    s = Sample()
    if sample:
        s._chans = [list(map(float, ch)) for ch in sample.get("ch", [[]])]
        s.SampleRate = int(sample.get("rate", DEFAULT_SAMPLE_RATE))
        for r in sample.get("regions", []):
            s.AddRegion(r.get("name", ""), r["start"], r["end"])
    EditorSample.__dict__.clear()
    EditorSample.__dict__.update(s.__dict__)
    Editor.set_selection(*(selection or (0, 0)))
    del Utils.messages[:]
    return EditorSample


def dump():
    """ホスト同期用の JSON 互換スナップショット。"""
    return {"ch": [list(ch) for ch in EditorSample._chans], "rate": EditorSample.SampleRate,
            "regions": [{"name": r.Name, "start": r.SampleStart, "end": r.SampleEnd} for r in EditorSample._regions],
            "messages": list(Utils.messages)}


def install():
    """sys.modules['enveditor'] にこの module 自身を登録する (FL では組込 module)。"""
    sys.modules["enveditor"] = sys.modules[__name__]
    return sys.modules[__name__]
