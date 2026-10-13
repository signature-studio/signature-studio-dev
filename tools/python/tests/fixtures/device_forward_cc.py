# name=PY-6 forward CCs (synthetic test fixture — FL 同梱の "Forward CCs to current plugin Port 10" ではない)
# 形だけ同梱スクリプトに合わせた合成物: OnInit / OnMidiIn / OnMidiMsg を持ち、CC を device.forwardMIDICC で現在のプラグインへ転送する。
import device

inited = 0


def OnInit():
    global inited
    inited += 1
    print("fixture forward-cc init, port", device.getPortNumber())


def OnMidiIn(event):
    pass


def OnMidiMsg(event):
    if event.status & 0xF0 == 0xB0:
        device.forwardMIDICC(event.status + (event.data1 << 8) + (event.data2 << 16) + (event.port << 24))
        event.handled = True
