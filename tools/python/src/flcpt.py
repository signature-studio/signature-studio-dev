"""flcpt (Chord progression tool が import する組込モジュール)。PY-30 (#1327)。

CPT の 4 メンバの引数書式・int 戻り値・要素返却・内部配列の操作は FLEngine PE の実装から確定した (根拠と逆アセンブル表: tools/python/REPORT_PY30.md §2)。
- addChordMarker(obj): 書式 'O' (PyArg_ParseTuple)。末尾へ追加 (list append 0x50a830)。戻り値は None と推定 (§2.3・#3034)。
- getChordMarker(index): 書式 'i'。0 <= index < count なら要素、それ以外は None と推定 (§2.3・#3034)。
- clearChordMarkers(): 要素を全て取り除く (0x50a8c0 を count 回)。戻り値は None と推定 (§2.3・#3034)。
- chordMarkerCount: 読取専用の int。要素数 (PyLong_FromLong)。
上記以外の CPT 属性は根拠が無いので定義しない (AttributeError)。
ChordMarker: alternativeCount (getset・定数 7 を返す。PE の `alternativeCount` ハンドラ 0xd2eb30 が `PyLong_FromLong(7)`) と getAlternative(index) (書式 'i'・0〜7 の範囲で要素、範囲外は None と推定。PE 0xd2eb50。REPORT_PY30 §7)。
ChordMarker の time・length・name は PE 内に候補が複数あり所属を確定できないため未実装 (AttributeError)。ChordAlternative / ChordPool は import 時に名前を参照されるだけの空の型 (mock (根拠なし))。
"""


class CPT:
    def __init__(self):
        self._markers = []

    def addChordMarker(self, obj):
        self._markers.append(obj)

    def getChordMarker(self, index):
        if 0 <= index < len(self._markers):
            return self._markers[index]
        return None

    def clearChordMarkers(self):
        self._markers.clear()

    @property
    def chordMarkerCount(self):
        return len(self._markers)


class ChordMarker:
    def __init__(self):
        self._alternatives = []

    @property
    def alternativeCount(self):
        return 7

    def getAlternative(self, index):
        if 0 <= index <= 7 and index < len(self._alternatives):
            return self._alternatives[index]
        return None


class ChordAlternative:
    pass


class ChordPool:
    pass


cpt = CPT()
