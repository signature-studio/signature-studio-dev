#!/usr/bin/env python3
"""PE バイナリ中の既知 GUID (WASAPI/MMDevice/DirectSound/DMO 等) を走査し、参照位置を列挙する。"""
import sys, uuid, struct
import pefile
GUIDS = {
 "CLSID_MMDeviceEnumerator": "BCDE0395-E52F-467C-8E3D-C4579291692E",
 "IID_IMMDeviceEnumerator": "A95664D2-9614-4F35-A746-DE8DB63617E6",
 "IID_IMMDevice": "D666063F-1587-4E43-81F1-B948E807363F",
 "IID_IMMNotificationClient": "7991EEC9-7E89-4D85-8390-6C703CEC60C0",
 "IID_IAudioClient": "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2",
 "IID_IAudioClient2": "726778CD-F60A-4EDA-82DE-E47610CD78AA",
 "IID_IAudioClient3": "7ED4EE07-8E67-4CD4-8C1A-2B7A5987AD42",
 "IID_IAudioRenderClient": "F294ACFC-3146-4483-A7BF-ADDCA7C260E2",
 "IID_IAudioCaptureClient": "C8ADBD64-E71E-48A0-A4DE-185C395CD317",
 "IID_IAudioSessionManager": "BFA971F1-4D5E-40BB-935E-967039BFBEE4",
 "IID_IAudioEndpointVolume": "5CDF2C82-841E-4546-9722-0CF74078229A",
 "IID_IPropertyStore": "886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99",
 "IID_IUnknown": "00000000-0000-0000-C000-000000000046",
 "IID_IClassFactory": "00000001-0000-0000-C000-000000000046",
 "CLSID_DirectSound": "47D4D946-62E8-11CF-93BC-444553540000",
 "CLSID_DirectSound8": "3901CC3F-84B5-4FA4-BA35-AA8172B8A09B",
 "IID_IDirectSound": "279AFA83-4981-11CE-A521-0020AF0BE560",
 "IID_IDirectSound8": "C50A7E93-F395-4834-9EF6-7FA99DE50966",
 "IID_IDirectSoundBuffer": "279AFA85-4981-11CE-A521-0020AF0BE560",
 "IID_IDirectSoundBuffer8": "6825A449-7524-4D82-920F-50E36AB3AB1E",
 "IID_IDirectSoundNotify": "B0210783-89CD-11D0-AF08-00A0C925CD16",
 "KSDATAFORMAT_SUBTYPE_PCM": "00000001-0000-0010-8000-00AA00389B71",
 "KSDATAFORMAT_SUBTYPE_IEEE_FLOAT": "00000003-0000-0010-8000-00AA00389B71",
 "IID_IMFTransform(unused)": "BF94C121-5B05-4E6F-8000-BA598961414D",
}
def scan(path):
    pe = pefile.PE(path)
    data = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    out = {}
    for name, g in GUIDS.items():
        b = uuid.UUID(g).bytes_le
        hits = []
        i = 0
        while True:
            i = data.find(b, i)
            if i < 0: break
            hits.append(base + i); i += 1
        if hits: out[name] = hits
    return out
if __name__ == "__main__":
    for p in sys.argv[1:]:
        print("##", p)
        for k, v in scan(p).items():
            print(f"  {k}: {[hex(x) for x in v][:6]}")
