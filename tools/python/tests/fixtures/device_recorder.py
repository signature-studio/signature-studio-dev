# name=PY-6 recorder (synthetic test fixture — FL 同梱スクリプトではない)
# 27 callback 全てを定義し、受けた (callback 名, 引数) を LOG に記録する。引数の flmidimsg は主要 field に畳む。
LOG = []
HANDLE_IN = False   # テストから書換え: OnMidiIn / OnMidiMsg で msg.handled を立てる
HANDLE_MSG = False


def _pack(a):
    if hasattr(a, "status"):
        return {"status": a.status, "data1": a.data1, "data2": a.data2, "port": a.port, "handled": a.handled,
                "sysex": None if a.sysex is None else list(a.sysex)}
    return a


def _rec(name):
    def f(*args):
        LOG.append([name, [_pack(a) for a in args]])
        if name == "OnMidiIn" and HANDLE_IN:
            args[0].handled = True
        if name == "OnMidiMsg" and HANDLE_MSG:
            args[0].handled = True
    f.__name__ = name
    return f


for _n in ("OnInit OnInitAll OnDeInit OnMidiIn OnMidiMsg OnSysEx OnNoteOn OnNoteOff OnControlChange OnProgramChange "
           "OnPitchBend OnKeyPressure OnChannelPressure OnMidiOutMsg OnIdle OnProjectLoad OnRefresh OnDoFullRefresh "
           "OnUpdateBeatIndicator OnDisplayZone OnUpdateLiveMode OnDirtyMixerTrack OnDirtyChannel OnFirstConnect "
           "OnUpdateMeters OnWaitingForInput OnSendTempMsg").split():
    globals()[_n] = _rec(_n)


def take():
    out = list(LOG)
    del LOG[:]
    return out


def set_flags(handle_in, handle_msg):
    global HANDLE_IN, HANDLE_MSG
    HANDLE_IN, HANDLE_MSG = handle_in, handle_msg
