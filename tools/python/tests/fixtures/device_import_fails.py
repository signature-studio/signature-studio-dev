# name=PY-14 import fails (synthetic test fixture — top-level で例外を出す device script)
# OnMidiIn を定義した後に存在しない module を import して失敗する。読込失敗後も配送対象に残らないことの回帰用 (#601)。


def OnMidiIn(event):
    print("bad OnMidiIn delivered")


import no_such_module  # noqa: E402,F401
