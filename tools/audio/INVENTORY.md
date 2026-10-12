# 自動生成: `tools/audio` の import/API 呼出面抽出 driver

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

# INVENTORY — FL(win/mac) のオーディオ/MIDI import・API 呼出面 (実測)
再生成: `bash tools/audio/inventory.sh` → `results/inventory_raw.txt` (生出力)・`results/xref.json`。
対象: win64 `FLEngine_x64.dll` (block00031, image base 0x400000, Delphi) / `ILWASAPI2ASIO_x64.dll` (block00001) / mac `FLEngine_x64.dylib` x86_64 スライス。アドレスは win64 VA。

## 1. 結論 (優先度)

| P | 面 | 根拠 (実測) | shim 先 |
|---|---|---|---|
| **P0** | **ASIO (IASIO COM, 既定ドライバ "FL Studio ASIO" = ILWASAPI2ASIO)** | FLEngine に ASIO ラッパ 19 メソッド + コールバック 4 種。UI 文字列/エラー文字列多数 | `flasio_*` (実装済 PoC) |
| P0 | `timeBeginPeriod/timeGetTime` 等 4 関数 | `timeGetTime` 参照元 68 関数 | 別 shim 行 (time)。本ディレクトリ対象外 |
| P1 | DirectSound (`DirectSoundCreate/EnumerateA`) | UI の "DirectSound" 選択肢、`IDirectSoundNotify` GUID あり | 設計のみ (PROTOCOL §8) |
| P1 | WinMM MIDI in/out (20 関数) | 呼出関数群 0xba24a0–0xba4af0 | WebMIDI 設計 (PROTOCOL §9) |
| P2 | WASAPI (`IAudioClient`) | **FLEngine は直接使わない** (GUID 0 件)。ILWASAPI2ASIO 内部のみ | `flwasapi_*` (実装済 PoC) |
| P2 | msacm32 (ACM コーデック 14 関数) | 参照元 0xa5dad0–0xa5ee30, 0x6726b0–0x673f40 = ファイル変換用 (リアルタイムでない) | コーデック行 (別担当) |
| 非該当 | `waveOut*/waveIn*` | **import 0 件** | 不要 |
| mac | CoreAudio HAL + AudioUnit render callback、CoreMIDI | §4 | ASIO 風 API に集約 |

## 2. win64 FLEngine_x64.dll (738 import 名)

audio/MIDI 関連 import (DLL 別):
- `dsound.dll` 2: `DirectSoundCreate`(呼出元 0x12afb50, 640B), `DirectSoundEnumerateA`(0x12af3e0, 196B)。
- `winmm.dll` 24: time 4 (`timeBeginPeriod/EndPeriod/GetDevCaps/GetTime`) + `midiIn*` 11 (GetNumDevs/GetDevCapsW/GetErrorTextW/Open/Close/Start/Stop/Reset/PrepareHeader/UnprepareHeader/AddBuffer) + `midiOut*` 9 (GetNumDevs/GetDevCapsW/GetErrorTextW/Open/Close/ShortMsg/LongMsg/PrepareHeader/UnprepareHeader)。`midiInOpen` は `dwFlags=0x30000 (CALLBACK_FUNCTION)` で呼ばれる (0xba3010)。
- `ole32.dll` 29: `CoCreateInstance`, `CoGetClassObject`, `CLSIDFromString`, `StringFromCLSID`, `ProgIDFromCLSID` ほか — ASIO ドライバの COM 生成に使用 (レジストリ列挙は registry shim 側。FLEngine 内の実文字列は小文字 UTF-16 の `software\asio` / `software\asio\` + 値名 `clsid` で、レジストリは大小無視。`SOFTWARE\ASIO\FL Studio ASIO` というキー全体は ILWASAPI2ASIO 側の断片 `SOFTWARE`/`ASIO`/`FL Studio ASIO`/`CLSID`/`InprocServer32` からの組立てと推定 — DllRegisterServer は未デコンパイル。CLSID `{188135E1-…}` は FLEngine には無く ILWASAPI2ASIO の DllGetClassObject 表のみ)。
- `msacm32.dll` 14、`avrt.dll` **なし** (MMCSS は ILWASAPI 側のみ)、`waveOut*` **なし**、WASAPI GUID (`IID_IAudioClient` 等) **なし**。

### ASIO (P0)
FL は IASIO を直接 vtable 呼出する小ラッパ 19 個 (0xc53da0–0xc53ff0, 各 22–35B) を持つ。呼ぶメソッド: `init, getDriverName, getDriverVersion, getChannels, getLatencies, getBufferSize, canSampleRate, getSampleRate, setSampleRate, getClockSources, setClockSource, getSamplePosition, getChannelInfo, createBuffers, disposeBuffers, controlPanel, outputReady, start, stop`。**呼ばないメソッド**: `getErrorMessage`, `future` (QueryInterface/AddRef/Release は COM 生成/解放で別途)。

FL がドライバへ渡す `ASIOCallbacks` (構造体 VA 0x16b87e9, Delphi packed, 初期化コード 0xc5e360):
| # | 関数 | VA | 実測挙動 |
|---|---|---|---|
| 0 | bufferSwitch | 0xc57420 (161B) | `ASIOGetSamplePosition` で 0x94B の ASIOTime を組み立て #3 へ委譲 |
| 1 | sampleRateDidChange | 0xc576b0 (14B) | `ASIOGetSampleRate` 再取得 (0xc57550) |
| 2 | asioMessage | 0xc576c0 (152B) | 下表 |
| 3 | bufferSwitchTimeInfo | 0xc56ae0 (2353B) | **本体** (ミキサ → 出力バッファ変換) |

`asioMessage` (FL 側の応答): selector 1 (Supported) → value ∈ [2..8] なら 1; 2 (EngineVersion) → 2; 3,4,5 (Reset/BufferSizeChange/Resync) → エラー/通知ダイアログ処理 (0x425210, id 0x55f) して 1; **6 (LatenciesChanged) → 内部コマンド 0x17 (0xbd68e0) を発行して 1** (再起動系と推定); **7 (SupportsTimeInfo) → 1** ⇒ ドライバは `bufferSwitchTimeInfo` を呼ぶべき; 8 (TimeCode) → 0; その他 0。
エラー文字列 (CreateBuffers/GetLatencies/GetSamplePosition/GetSampleRate failed, "ASIO driver is not open.", "Couldn't init/open the ASIO driver.", "Couldn't create the streaming ASIO buffer.") の参照元は 0xc57a00/0xc589b0 等。設定 UI: `asiopanel.{asioclockbox, asiomixinbsbox, asiopanelbtn, asiotriplebufbox}`, `audiooutpanel.{smpratebox, prioritybox, safeoverloadbox, underrunslabel, pbtrackingmodebox}`。

### DirectSound (P1)
0x12ae000–0x12b2000 の `call [reg+disp]` 集計 (IDirectSound/IDirectSoundBuffer のスロットは disp が重複 — 0x18–0x30 は両インターフェース):
`CreateSoundBuffer(+0x18)×4, GetCurrentPosition(+0x20)×2, GetFormat(+0x28)×3, SetCooperativeLevel(+0x30)×1, Lock(+0x58)×2, Play(+0x60), SetCurrentPosition(+0x68), SetFormat(+0x70), SetVolume(+0x78)×3, SetFrequency(+0x88), Stop(+0x90), Unlock(+0x98)×2` + `IDirectSoundNotify` GUID (0x12afa0e)。文字列: "Couldn't create the primary DirectSound buffer." (0x12afb50)、オプション `dspanel.{hardbufbox, pollbox, ds_32bitbufbox, buflslider, buflofsslider}`。

## 3. ILWASAPI2ASIO_x64.dll — FL が期待するドライバ面 (ILWasapiToAsioDriver vtable, RTTI 復元)

- vtable 0x1800657e0 (24 スロット = IASIO 順)。CLSID (DllGetClassObject の表) `{188135E1-7171-3434-854F-01A3C71F3DF9}`、`Software\Image-Line\ASIO` に設定保存、"FL Studio ASIO V1.05"。
- `getChannels` = **2 in / 2 out**。`getChannelInfo`: type=`0x13 (ASIOSTFloat32LSB)`, group 0, 名前 `"In %i"`/`"Out %i"` (1 始まり)。
- `getBufferSize`: **min 256 / max 4096 / preferred = 設定値 (既定 0x200=512) / granularity 0**。バッファは float32×4096frame×2ch の 2 面 (stride 0x4000B)。
- `canSampleRate`: 22050, 44100, 48000, 96000, 192000。`getClockSources`: 1 件 "Internal"。`outputReady` = `0xfffffc18 (ASE_NotPresent)`。`future` 既定 `-998`。`controlPanel` = ダイアログ表示。
- WASAPI 側 (`.?AVWASAPIWrapper@@`): `IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia)` → `IAudioClient` **shared mode / `KSDATAFORMAT_SUBTYPE_IEEE_FLOAT`** → `IAudioRenderClient` (+ `IAudioCaptureClient` で入力)。**イベント API 無し** (`CreateEvent` import 0) = ポーリング (`Sleep` + `GetCurrentPadding`)、`CreateThread` + `SetThreadPriority` + `AvSetMmThreadCharacteristicsA("Pro Audio")`。`IMMNotificationClient` でデバイス変更。

## 4. macOS FLEngine_x64.dylib (x86_64 スライス, undefined 337 シンボル)

- CoreAudio 5: `AudioObject{Add,Remove}PropertyListener`, `AudioObject{Get,Set}PropertyData`, `AudioObjectGetPropertyDataSize` (デバイス列挙・レート・バッファ長・変更通知)。
- AudioToolbox 10: `AudioComponentFindNext/InstanceNew/InstanceDispose`, `AudioOutputUnitStart/Stop`, `AudioUnit{Initialize,Uninitialize,GetProperty,SetProperty,Render}` (HAL Output Unit + render callback = ASIO bufferSwitch と同型のコールバック駆動。`AudioUnitRender` は入力取得)。
- CoreMIDI 16: `MIDIClient{Create,Dispose}`, `MIDIInputPortCreate/OutputPortCreate/PortDispose/PortConnectSource/PortDisconnectSource`, `MIDIGetNumberOfDevices/Sources/Destinations`, `MIDIGetSource/Destination`, `MIDIObjectGetStringProperty`, `MIDIPacketListInit/Add`, `MIDISend`。
- スレッド優先度: `pthread_setschedparam/getschedparam/attr_setinheritsched`、`dispatch_semaphore_*` 3、`sched_yield`。UI 文字列 "CoreAudio devices", "CoreAudio input devices", "--- CoreAudio init", "Could not enable the CoreAudio device."。
- 写像: AudioUnit render callback(frames, bufferList) ≡ `bufferSwitch`。`AudioObjectSetPropertyData(kAudioDevicePropertyBufferFrameSize)` ≡ `createBuffers(B)`、デバイス変更 listener ≡ `kAsioResetRequest`。

## 5. 未確認 (推定を含む)
- FL が DS バッファを 16bit/float32 どちらで使うか (`ds_32bitbufbox` は存在)。
- `asioMessage` selector 6 の内部コマンド 0x17 の正体 (再起動と推定; 動的 T 拡張時は既定で通知しない根拠)。
- ILWASAPI の `getLatencies` 計算式 (WASAPI GetStreamLatency + buffer; 内部関数 0x180006380 未解析)。
