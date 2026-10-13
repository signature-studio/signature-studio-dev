"""flpianoroll — FL Studio ピアノロール scripting module (純 Python 実装)。

FL 実機の `flpianoroll` は FLEngine (Delphi) 内にある。本モジュールは .pyscript が使う面
(Note 17 / Marker 7 / score 22 / Utils 3 / ScriptDialog 15 メンバ、`analysis/flapi/flapi_table.json` の
`objects.flpianoroll`) を、ホスト側の in-memory score に対して提供する。
score の出入りは `load_score(dict)` / `dump_score()` (JSON 互換) で行い、ホストが現ピアノロールと同期する。

FL 実機で未確認の挙動 (推定) は `# ASSUMPTION:` で明示する。REPORT の「未解決」表が一覧。
"""
import json
import sys
import types

DEFAULT_PPQ = 96

# 整数でなければならないと推定する Note 属性 (同梱スクリプトは全て int() で丸めてから代入している)
_INT_FIELDS = ("number", "time", "length", "group", "color", "pitchofs", "repeats")
_FLOAT_FIELDS = ("pan", "velocity", "release", "fcut", "fres")
_BOOL_FIELDS = ("slide", "porta", "muted", "selected")

warnings = []  # 診断: 型/範囲の疑義。動作は変えない (回帰テストで同梱スクリプトは 0 件であることを確認)


def _warn(msg):
    warnings.append(msg)


class Note:
    __slots__ = _INT_FIELDS + _FLOAT_FIELDS + _BOOL_FIELDS

    def __init__(self):
        # docs の既定値: pan 0.5 / velocity 0.8 / fcut 0.5 / fres 0.5 / color 0
        # ASSUMPTION: number=60, length=PPQ (docs に既定値の記載なし)
        object.__setattr__(self, "number", 60)
        object.__setattr__(self, "time", 0)
        object.__setattr__(self, "length", globals().get("score", None) and score.PPQ or DEFAULT_PPQ)
        object.__setattr__(self, "group", 0)
        object.__setattr__(self, "color", 0)
        object.__setattr__(self, "pitchofs", 0)
        object.__setattr__(self, "repeats", 0)
        object.__setattr__(self, "pan", 0.5)
        object.__setattr__(self, "velocity", 0.8)
        object.__setattr__(self, "release", 0.0)
        object.__setattr__(self, "fcut", 0.5)
        object.__setattr__(self, "fres", 0.5)
        object.__setattr__(self, "slide", False)
        object.__setattr__(self, "porta", False)
        object.__setattr__(self, "muted", False)
        object.__setattr__(self, "selected", False)

    def __setattr__(self, k, v):
        if k in _INT_FIELDS and (isinstance(v, float) or not isinstance(v, int)):
            _warn(f"Note.{k} = {v!r} ({type(v).__name__}): int expected")
        elif k in _FLOAT_FIELDS and not isinstance(v, (int, float)):
            _warn(f"Note.{k} = {v!r} ({type(v).__name__}): number expected")
        object.__setattr__(self, k, v)

    def clone(self):
        n = Note()
        for k in Note.__slots__:
            object.__setattr__(n, k, getattr(self, k))
        return n

    def asdict(self):
        return {k: getattr(self, k) for k in Note.__slots__}

    @classmethod
    def fromdict(cls, d):
        n = cls()
        for k, v in d.items():
            if k in cls.__slots__:
                object.__setattr__(n, k, v)
        return n


class Marker:
    __slots__ = ("time", "name", "mode", "tsnum", "tsden", "scale_root", "scale_helper")

    def __init__(self):
        self.time = 0
        self.name = ""
        self.mode = 0
        self.tsnum = 0
        self.tsden = 0
        self.scale_root = 0
        self.scale_helper = None

    def asdict(self):
        return {k: getattr(self, k) for k in Marker.__slots__}

    @classmethod
    def fromdict(cls, d):
        m = cls()
        for k, v in d.items():
            if k in cls.__slots__:
                setattr(m, k, v)
        return m


class Score:
    """現ピアノロールの Pattern。getNote は live 参照を返す (同梱 Humanize が `getNote(n).time = ...` で in-place 更新、
    Repeater が addNote 後に note を更新するため、コピーではなく同一オブジェクトを保持する)。"""

    def __init__(self, ppq=DEFAULT_PPQ):
        self.PPQ = ppq
        self.tsnum = 4
        self.tsden = 4
        self.length = 0
        self.snap_scale_helper = None
        self.snap_root_note = 0
        self._notes = []
        self._markers = []
        self._tl = (-1, -1)
        self._next_group = 1

    # -- properties
    @property
    def noteCount(self):
        return len(self._notes)

    @property
    def markerCount(self):
        return len(self._markers)

    # -- notes
    def addNote(self, note):
        if not isinstance(note, Note):
            raise TypeError("addNote() expects a Note")
        self._notes.append(note)

    def getNote(self, index):
        if not 0 <= index < len(self._notes):
            raise IndexError("Index out of range")
        return self._notes[index]

    def deleteNote(self, index):
        if not 0 <= index < len(self._notes):
            raise IndexError("Index out of range")
        del self._notes[index]

    def clearNotes(self, all=False):
        # "Specify True to clear all, instead of just selected." — selected 属性が True のものだけを消す。
        # ASSUMPTION: 選択ゼロのとき FL が全ノートを対象にするかは未確認 (ここでは厳密に selected のみ)
        self._notes = [] if all else [n for n in self._notes if not n.selected]

    # -- markers
    def addMarker(self, marker):
        if not isinstance(marker, Marker):
            raise TypeError("addMarker() expects a Marker")
        self._markers.append(marker)

    def getMarker(self, index):
        if not 0 <= index < len(self._markers):
            raise IndexError("Index out of range")
        return self._markers[index]

    def deleteMarker(self, index):
        if not 0 <= index < len(self._markers):
            raise IndexError("Index out of range")
        del self._markers[index]

    def clearMarkers(self, all=False):
        self._markers = [] if all else list(self._markers)  # ASSUMPTION: Marker に selected 属性が無いので all=False は no-op

    def clear(self, all=False):
        self.clearNotes(all)
        self.clearMarkers(all)

    # -- misc
    def getTimelineSelection(self):
        return self._tl

    def setTimelineSelection(self, x1, x2):
        self._tl = (x1, x2)

    def getDefaultNoteProperties(self):
        return Note()

    def getNextFreeGroupIndex(self):
        used = {n.group for n in self._notes}
        g = max(1, self._next_group)
        while g in used:
            g += 1
        self._next_group = g + 1
        return g

    def loadScoreFromFile(self, path):
        # ASSUMPTION: FL の .fst/.fsc (独自形式) は未解析。仮想 FS 上の JSON (dump() と同形式) を読む。
        # 存在しないパスは Python 標準の FileNotFoundError (実 FL の失敗種別は未確認)。
        with open(path, "rb") as f:
            d = json.loads(f.read().decode("utf-8"))
        if not isinstance(d, dict):
            raise ValueError(f"loadScoreFromFile: score object expected, got {type(d).__name__}")
        self.load(d)

    # -- host sync (JSON 互換)
    def load(self, d):
        self.PPQ = d.get("PPQ", DEFAULT_PPQ)
        self.tsnum = d.get("tsnum", 4)
        self.tsden = d.get("tsden", 4)
        self.length = d.get("length", 0)
        self._tl = tuple(d.get("timeline", (-1, -1)))
        self._notes = [Note.fromdict(x) for x in d.get("notes", [])]
        self._markers = [Marker.fromdict(x) for x in d.get("markers", [])]

    def dump(self):
        return {"PPQ": self.PPQ, "tsnum": self.tsnum, "tsden": self.tsden, "length": self.length,
                "timeline": list(self._tl),
                "notes": [n.asdict() for n in self._notes],
                "markers": [m.asdict() for m in self._markers]}


class TUtils:
    def __init__(self):
        self.messages = []  # (kind, payload) — ホストが HUD/ログへ流す

    def ProgressMsg(self, Msg, Pos, Total):
        self.messages.append(("progress", (Msg, Pos, Total)))

    def ShowMessage(self, Msg):
        self.messages.append(("message", Msg))

    def log(self, Msg):
        self.messages.append(("log", Msg))


class ScriptDialog:
    """スクリプトのフォーム。実機は GUI を出すが、ここではコントロール記述 (describe) を持ち、値はホストが
    set_values で注入する (HUD フォーム連携 #10 の境界)。Execute() は headless では True (OK) を返す。"""

    restoreFormValues = True

    def __init__(self, Title="", Description=""):
        self.title = Title
        self.description = Description
        self._controls = []   # dict(name,type,value,min,max,items,hint,group)
        self._byname = {}
        self._group = None
        self.accepted = True

    def _add(self, name, typ, value, **kw):
        full = f"{self._group}: {name}" if self._group else name  # docs: 群内は "[groupname]: [controlname]"
        c = {"name": full, "type": typ, "value": value, "hint": kw.pop("hint", ""), "group": self._group}
        c.update(kw)
        if full in self._byname:
            _warn(f"duplicate control name {full!r}")
        self._controls.append(c)
        self._byname[full] = c

    def SetText(self, description):
        self.description = description

    def AddInput(self, name, value, hint=""):
        self._add(name, "generic", value, hint=hint)

    def AddInputKnob(self, name, value, min, max, hint=""):
        self._add(name, "knob", float(value), min=min, max=max, hint=hint)

    def AddInputKnobInt(self, name, value, min, max, hint=""):
        self._add(name, "knobint", int(value), min=min, max=max, hint=hint)

    def AddInputCombo(self, name, valueList, value=0, hint=""):
        items = valueList.split(",") if isinstance(valueList, str) else [str(x) for x in valueList]
        self._add(name, "combo", int(value), items=items, hint=hint)

    def AddInputCheckbox(self, name, value, hint=""):
        self._add(name, "checkbox", 1 if value else 0, hint=hint)

    def AddInputText(self, name, value, hint=""):
        self._add(name, "text", str(value), hint=hint)

    def AddInputSurface(self, presetName):
        self._add(presetName, "surface", None)

    def GetInputValue(self, aName):
        try:
            return self._byname[aName]["value"]
        except KeyError:
            raise KeyError(f"no such input: {aName!r}") from None

    def SetNormalizedValue(self, name, value):
        c = self._byname[name]
        if c["type"] in ("knob", "knobint"):
            v = c["min"] + (c["max"] - c["min"]) * value
            c["value"] = int(round(v)) if c["type"] == "knobint" else float(v)
        elif c["type"] == "combo":
            c["value"] = int(round(value * (len(c["items"]) - 1)))
        elif c["type"] == "checkbox":
            c["value"] = 1 if value >= 0.5 else 0
        else:
            c["value"] = value

    def addGroup(self, name):
        self._group = name

    def endGroup(self):
        self._group = None

    def Execute(self):
        return self.accepted

    # -- host 側 API
    def set_values(self, values):
        """HUD 入力などで控制値を注入。未知名は KeyError (typo を黙って無視しない)。範囲 clamp はしない
        (ASSUMPTION: 実機の clamp 挙動は未確認。範囲外は diagnostics に残す)。"""
        for k, v in values.items():
            c = self._byname[k]
            if c["type"] in ("knob", "knobint") and not (c["min"] <= v <= c["max"]):
                _warn(f"{k!r} = {v!r} outside [{c['min']}, {c['max']}]")
            c["value"] = v

    def DialogParams(self):
        # MOCK: 実 FL の戻り値の形 (dict / オブジェクト / キー名) は未確認。現在の控制値を {name: value} で返す。
        # 実 FL との照合は #81 (PY-9) の範囲。
        return {c["name"]: c["value"] for c in self._controls}

    def describe(self):
        return {"title": self.title, "description": self.description,
                "restoreFormValues": self.restoreFormValues, "controls": [dict(c) for c in self._controls]}

    # docs は lowerCamel 表記 (addInputKnob 等)、同梱スクリプトは UpperCamel (AddInputKnob) — 両方を受ける
    execute = Execute
    setText = SetText
    addInput = AddInput
    addInputKnob = AddInputKnob
    addInputKnobInt = AddInputKnobInt
    addInputCombo = AddInputCombo
    addInputCheckbox = AddInputCheckbox
    addInputText = AddInputText
    addInputSurface = AddInputSurface
    getInputValue = GetInputValue
    setNormalizedValue = SetNormalizedValue


score = Score()
Utils = TUtils()

__all__ = ["Note", "Marker", "Score", "ScriptDialog", "TUtils", "score", "Utils"]


def reset(score_dict=None):
    """新しい run 用に score / Utils / 診断をリセットして loaded module に反映する。"""
    # `from flpianoroll import *` 済みのスクリプトが古い参照を持たないよう、同一オブジェクトを in-place で更新する
    score.load(score_dict or {})
    del Utils.messages[:]
    del warnings[:]
    return score


def install():
    """sys.modules['flpianoroll'] にこの module 自身を登録する (FL では組込 module)。"""
    sys.modules["flpianoroll"] = sys.modules[__name__]
    return sys.modules[__name__]
