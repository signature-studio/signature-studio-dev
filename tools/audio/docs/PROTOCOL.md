# PROTOCOL — FL オーディオ/MIDI shim (ASIO/WASAPI/DirectSound → AudioWorklet + SAB リング)

実測根拠は `../INVENTORY.md`、実装は `../src/*`・`public/worklets/fl-audio-worklet.js`・`src/runtime/audio-shim.ts`。数値は `../results/results.json` の実測。

## 1. 構成 (3 種のスレッド)

```
 FL (lift した wasm)                       main thread (JS)                  AudioWorklet (render thread)
 ┌───────────────────────┐   mailbox     ┌────────────────────────┐        ┌───────────────────────────┐
 │ FL 本体スレッド        │──cmd_seq────▶│ FlAudioShim (TS)        │        │ FlShimProcessor           │
 │ ASIO shim スレッド      │◀─ack_seq─────│  AudioContext 生成/較正  │        │  128f 毎に process()      │
 │  (bufferSwitch 駆動)   │              │  getOutputTimestamp 平滑 │        │  ring 読出し / 入力 write  │
 └──────────┬────────────┘              └────────────────────────┘        └───────────┬───────────────┘
            │  fla_out_write / fla_in_read (同一 SAB = wasm 線形メモリ上の fla_ctl_t + planar f32 ring)  │
            └────────────────────────────── Atomics (seq-cst) + futex wait/notify ─────────────────────────┘
```
- **ring と制御ブロックは wasm 線形メモリ内** (shared `WebAssembly.Memory`)。worklet は `memory.buffer` (SAB) を `processorOptions` で受け取り、同じアドレスを直接読み書きする。コピー無し。
- **AudioContext / getUserMedia / WebMIDI は main thread のみ** (worker に AudioContext は無い)。wasm → main は制御ブロック内の **mailbox 同期 RPC** (`cmd_seq`/`ack_seq`、wasm 側 `Atomics.wait`、main 側 `Atomics.waitAsync`)。
- 時間のマスター = **worklet のサンプルカウンタ** (`dev_frames`, `currentFrame`)。FL 側の位置・時刻はここから導出する (§6)。

## 2. 制御ブロック `fla_ctl_t` (384B, 64B ライン × 6) と ring

オフセットの単一の真実は `src/flaudio.h`。TS は `src/runtime/audio-layout.ts` に同表を持ち、起動時に wasm の `fla_layout_off(i)` と全 67 項目を照合 (不一致 → throw = fail-fast)。worklet は固定値を持たず `processorOptions.layout` を使う。

| ライン | 書き手 | 主なフィールド |
|---|---|---|
| 0 (@0) 構成 | wasm (open 時) | magic, state, sample_rate, out_ch, in_ch, ring_frames, ring_mask, buffer_frames, depth, rebuffer_frames, out/in_ring_ptr, flags, dev_events |
| 1 (@64) | worklet | dev_frames(u64), dev_ctx_time_bits(f64), out_read, in_write, underruns, silence_frames, quanta, in_overruns, wl_state, clock_seq(seqlock), play_start_frame, clock_jumps/_frames, clock_skip_frames/clock_dup_frames/clock_jump_max/clock_jump_max_q (@164-179, burst_obs の後の pad2 から割当) |
| 2 (@128) | producer | out_write, in_read, wake_target, gen, go, tick_target, notify_ms, burst_obs(worklet 書) |
| 3 (@192) | main | ref_ctx_time_bits, ref_epoch_ms_bits (seqlock), out/base_latency_us |
| 6 (@384) | worklet | burst_hist[32] (連続 process() の 1 run 終了ごとに bin=floor(len/512) を +1。末尾 bin は以上。AU-30 #3151) |
| 4 (@256) | wasm↔main | cmd_seq/op/arg[4], ack_seq/status/res[4], ctrl_ready |
| 5 (@320) | producer | cb_count/late/max_us, wake_count, wait_timeouts, in_underflows, min_fill, wake_hist[6] |

- ring は **planar float32、ch ごとに `ring_frames` (2 の冪, 16384 以上)**。index は 32bit 単調増加 (modular, 差 < 2^31)。fill = `write - read`。SPSC: 出力 ring は producer=wasm / consumer=worklet、入力 ring は逆。**データ書込 → index の seq-cst store** の順で公開 (JS の `Atomics.store` / C の `__atomic_store_n` は同一メモリモデル)。
- 64bit 値 (dev_frames 等) は 2×32bit を `clock_seq` seqlock で一貫読み。

## 3. ASIO 風コールバック駆動 (`flasio_*`, 本命 P0)

FL は ASIO を COM (IASIO) 経由で使い、`bufferSwitch` コールバックで音声を生成する (INVENTORY §2)。shim は ILWASAPI2ASIO と同じ面を再現する:

1. `Init` → `GetChannels/GetBufferSize/CanSampleRate/GetSampleRate/GetChannelInfo` は定数応答 (**ILWASAPI 実測値**: 2in/2out, `ASIOSTFloat32LSB(19)`, clock "Internal", レート {22050,44100,48000,96000,192000}, `outputReady`=ASE_NotPresent)。
2. `CreateBuffers(infos, n, B, callbacks)`: `fla_open` = **(a) OPEN: AudioContext 生成 + worklet module ロード + バースト較正 (§4) → (b) ring 確保 (malloc) → (c) ATTACH: ring 確保後の最新 SAB で AudioWorkletNode 生成・接続・resume**。2 相にする理由: ring ポインタと `memory.grow` 後の SAB を node 生成時点で確定させるため。ホストへ `asioMessage(kAsioSelectorSupported/EngineVersion/SupportsTimeInfo)` を問い合わせ、`SupportsTimeInfo=1` なら `bufferSwitchTimeInfo(ASIOTime*)` 経路を使う (FL は 1 を返す: 実測)。バッファは `ASIOBufferInfo.buffers[0/1]` に float32 planar を返す。
3. `Start`: producer スレッド生成 → **prefill** (T フレーム分 `bufferSwitch` を連続で呼ぶ。ASIO の起動時二重呼出に相当) → `go=1`。worklet は `gen` 変化を見て run を開始し `play_start_frame` を記録。
4. 定常: `while(!stop){ fla_out_wait_fill_le(T-B); [入力 B フレームを buffers[idx] へ]; bufferSwitch(idx); idx^=1; ring へ B フレーム write }`。**ブロッキング write** = ring 充填が `T-B` 以下になるまで `memory.atomic.wait32(&out_read)` で眠る。
5. 起床: worklet は quantum 毎に `out_read` を store し、`out_read ≥ wake_target` なら **一回限り** `Atomics.notify` (CAS で `wake_target` を到達不能値へ退避。producer の再武装は上書きしない)。producer は `wake_target` を先に武装してから `wait32(&out_read, 観測値)` → 武装前に進んだ場合は not-equal で即復帰 (取りこぼし無し)。50ms 毎のタイムアウトで `stop`/`dev_events` を確認。
6. `Stop`: `stop=1` → join → `go=0` → worklet が `wl_state=IDLE` を書いて notify するまで待機 (≤300ms)。次の Start は `fla_reset_indexes` (ring 0 クリア, 統計リセット) 後に `gen++`。
7. 停止中は ASIO 仕様どおり `GetSamplePosition` が `ASE_SPNotAdvancing`。`DisposeBuffers` = Stop + `fla_close` (CLOSE コマンドで ctx close)。

fail-fast: 未初期化/`bufferSwitch==NULL`/チャネル外/`buffer_frames` が 128 の倍数でない/ring 溢れ/main thread での blocking 呼出は **abort + 関数名を stderr** (`fla_failfast`)。

## 4. バッファ・レイテンシ選択と「バースト」

- worklet は **128 フレーム固定**。ASIO バッファは **128 の倍数** を createBuffers が受理 (profile に依らず [128,4096])。getBufferSize の既定報告は **ILWASAPI 値 min=256/max=4096/pref=512/granularity=0** (AU-7 #193 で確定; FL は min/max/granularity を読まない: REPORT §11)。shim 単体用の min=128/granularity=128 は `-DFLASIO_PROFILE_ILWASAPI=0`。
- **重要な実測**: ブラウザは quantum を 1 つずつでなく **バースト** (OS 出力バッファ単位) で連続呼出する。headless Chrome では 48k で 512f (10.7ms) 周期、96k では 2048–3072f。`ctx.baseLatency` は 96k で実態 (3072f) より小さい (1024f) ため当てにならない。
- よって目標充填 `T = depth*B` は **T ≥ burst×1.25 + B** が必要 (1 バースト通過で ring が枯渇しないこと)。決定手順:
  1. OPEN 時に 96 quanta の較正プローブ (`fl-burst-probe`, 約 0.25s) で実バーストを測定、`max(baseLatency, probe)` を ACK で返す → `fla_open` が `depth` を引き上げ。
  2. 実行中は worklet が `burst_obs` を更新、producer が `T` を拡張 (underrun 毎に +B も加算)。underrun が `FLASIO_SHRINK_STABLE_MS` (3000ms) 続くと +B を 1 段ずつ戻す (下限 `max(burst 由来 need, T0)` は下げない。REPORT §17)。`kAsioLatenciesChanged` 通知は既定 OFF (FL の `asioMessage` は selector 6 を内部コマンド 0x17 に配線 = 再起動の疑い: INVENTORY §2) 。
- 報告レイテンシ: `output = T + 128 + (baseLatency + outputLatency)·sr`, `input = B + 128 + baseLatency·sr` (推定。実測 shim in→out = T フレーム)。
- `outputLatency` は起動直後 0 で約 250ms 後に更新される。FL は createBuffers 直後の getLatencies を一度だけ読むため、ATTACH は outputLatency>0 になるまで最大 600ms 待ってから CreateBuffers を返す (`FlAudioShimOptions.outputLatencyWaitMs`, 0 で無効)。上限まで 0 のブラウザは 0 のまま進む。
- サンプルレート: `AudioContext({sampleRate})` を要求 (ブラウザが必要ならリサンプル)。`SetSampleRate` は停止中のみ → `SET_SR` コマンドで ctx 再生成 → ring はそのまま再接続、`sampleRateDidChange` をホストへ。

## 5. Underrun 処理 (クロック連続・データ非破壊)

worklet は quantum 毎に `avail = write-read` を見る:
- `avail ≥ 128`: 128 フレーム消費。
- `avail < 128`: `avail` 分を消費し残りは無音。**declick**: 最後の値から 32 フレームで線形減衰 (無音部分のみ書換え、有効サンプルは不変)。`underruns++`, `silence_frames += 128-avail`、`BUFFERING` 状態へ。
- `BUFFERING`: 無音出力・非消費・`dev_frames` は進行。`avail ≥ rebuffer_frames(=B)` で復帰、復帰先頭 32 フレームをフェードイン。起動直後の初回バッファリングは underrun に数えない。
- データは**捨てない**: 欠落の代わりに無音が挿入され以降は遅れて再生 (ネイティブ ASIO が前バッファを再生して遅延する挙動と同型)。FL の転送位置は FL 自身の生成フレームで決まるため整合は保たれる。
- ブラウザ側スキップ (`currentFrame` が process() 間で連続しない) は `clock_jumps/clock_jump_frames` に別計上 (shim の underrun と区別)。`clock_jump_frames` は符号付き合計で正負が相殺しうるため、正の成分 `clock_skip_frames` (描画されなかったフレーム) と負の成分の絶対値 `clock_dup_frames` を別に持つ。`clock_jump_max` / `clock_jump_max_q` は 1 回の最大 jump と発生 quantum 番号。
- `AudioContext` の suspended/interrupted/closed は main が `dev_events` に立て、producer が `asioMessage(kAsioResetRequest)` を送る。

## 6. クロック同期 (worklet = master)

- worklet は毎 quantum 先頭で `(currentFrame, currentTime)` を seqlock 付きで公開。`performance` は AudioWorkletGlobalScope に無い (実測 `typeof performance === "undefined"`) ため、system 時刻は main thread が `ctx.getOutputTimestamp()` を 250ms 毎に取得し、直近 16 点の最小二乗直線で平滑化した `(ref_ctx_time, ref_epoch_ms=performance.timeOrigin+performanceTime)` を公開 (±数ms のジッタを低減)。
- wasm 側 `fla_clock_read`: `audible_ns = ref_epoch + (ctx_time(quantum) - ref_ctx)·1000`。= **その quantum 先頭が「聴こえる」時刻** (outputLatency を含む)。`fla_clock_read` の `audible_ns` は shim 内部の時刻写像 (e2e の `clock.*` はこれを直接測る)。ASIO `GetSamplePosition` / `ASIOTime.timeInfo` は `(dev_frames - play_start_frame, systemTime)` を返し (`kSystemTimeValid|kSamplePositionValid|kSampleRateValid`)、**`systemTime` は既定で基準ドライバ ILWASAPI2ASIO と同じ「コールバック時刻」= `(uint32)timeGetTime() ms × 1e6` ns** (AU-7 #193; FL は systemTime だけを読み timeGetTime と同じ時間軸で扱う: REPORT §11)。従来の可聴時刻は `-DFLASIO_SYSTIME_AUDIBLE=1`。
- 位置の意味: デバイスクロック基準 (underrun 中の無音も進む)。FL の再生カーソル `pbtrackingmode` はこの位置で補間される想定。

## 7. WASAPI 風 (`flwasapi_*`, P2)

FLEngine は WASAPI を直接呼ばない (GUID/IAT 走査で 0 件)。ILWASAPI2ASIO 内の `IMMDeviceEnumerator → IAudioClient (shared, float, ポーリング) → IAudioRenderClient` に相当する最小面を同じ ring 上に実装:

| WASAPI | shim |
|---|---|
| `GetMixFormat` | 48000Hz/2ch/float32 固定 |
| `Initialize(shared, EVENTCALLBACK, bufdur, period)` | `fla_open(period→B, bufdur/period→depth)` (burst 較正で depth 自動引上げ) |
| `GetBufferSize` / `GetCurrentPadding` | `depth·B` / `write-read` |
| `GetBuffer`/`ReleaseBuffer(SILENT)` | interleaved staging → planar へ de-interleave → `fla_out_write` |
| `SetEventHandle` + `WaitForSingleObject` | デバイスクロック (`dev_frames`) が period 境界を跨ぐ度に 1 回起床 (`quanta` を futex、auto-reset 相当・取りこぼしは合体) |
| `Start/Stop/Reset` | `go=1` / `go=0`(index 保持) / index リセット |
| exclusive / loopback / capture | 未実装 (exclusive は fail-fast、capture は fail-fast スタブ + §9 設計) |

## 8. DirectSound 風 (`flds_*`, 実装済み: AU-4 #189)

FL が実際に呼ぶ面 (受け手別, `results/ds_static.txt`): `IDirectSound` {SetCooperativeLevel(PRIORITY), CreateSoundBuffer×2 = primary + secondary}、primary {GetFormat, SetFormat}、secondary {Lock, Unlock, GetCurrentPosition (play のみ / write のみの 2 呼出), SetCurrentPosition, Play(LOOPING), Stop, QueryInterface→IDirectSoundNotify}、`IDirectSoundNotify::SetNotificationPositions` (2 点)。`SetVolume`/`SetFrequency` は DS オブジェクトには呼ばれない (INVENTORY §2 の集計は Delphi オブジェクトへの同 disp 呼出を含んでいた)。

secondary は shim 内の循環バイト列 (PCM16 または float32, interleaved)。Play で pump スレッドが起動し、`fla_out_wait_fill_le` で ring が T-P 以下になる度に P フレーム (既定 256) を secondary から planar f32 へ変換して `fla_out_write` する (flasio と同じ動的 T 拡張則)。

| DS | shim |
|---|---|
| `CreateSoundBuffer(secondary)` | `fla_open` (rate/ch は WAVEFORMATEX から)。`LOCHARDWARE`→`DSERR_ALLOCATED`、バッファ < T+2P フレームは `INVALIDPARAM` |
| `Lock/Unlock` | secondary 上のポインタ (wrap 時 2 区間)。Unlock は Lock 区間との一致のみ検査 (変換は pump が「その時点の内容」を読む) |
| play cursor | `(base + out_read 拡張 64bit) mod size` (underrun 中は worklet 無音で止まる) |
| write cursor | `(base + 変換済み総フレーム + P) mod size` (それ以前は凍結扱い)。play との差は [P, T+2P] |
| `Play(LOOPING)` / `Stop` | pump 起動 + `go=1` / pump 停止 + `go=0`、停止時 play cursor を保持。非 LOOPING・EXCLUSIVE/WRITEPRIMARY は fail-fast |
| `SetCurrentPosition` | 停止中のみ (再生中は `INVALIDCALL`) |
| Notify | play cursor が各 offset を通過 (開始位置自身は数えない) する度に bit。`flds_wait_notify` が futex 短周期 (≤4ms) で判定。取りこぼしは合体 |
| 形式 | PCM16 / IEEE float32 (PCM・FLOAT・EXTENSIBLE) を受理。16bit は `v/32768` で float 化 (厳密)。再サンプル/ch 変換なし |

FL のバッファ形式 (`ds_32bitbufbox` 経路, 静的確認): primary SetFormat の組立は設定 bool (0x15d3296) で分岐 — 0 → `WAVE_FORMAT_PCM` 16bit ステレオ (0x674e10)、非 0 → `WAVE_FORMAT_EXTENSIBLE` + `KSDATAFORMAT_SUBTYPE_IEEE_FLOAT` 32bit (0x674e50)。secondary も同じ wfx。両形式とも本 shim が受理する。`pollbox` (ポーリング) は GetCurrentPosition ループ、非ポーリング時は `DSBCAPS_CTRLPOSITIONNOTIFY` + Notify。COM vtable アダプタ (win64 ABI) は AU-1 側で生成 (未実装)。

## 9. WebMIDI / オーディオ入力 (設計)

**MIDI (WinMM `midiIn*/midiOut*` 20 関数、macOS CoreMIDI 16 関数)**: FL は `midiInOpen(CALLBACK_FUNCTION=0x30000)` でコールバックを受け取り (実測 dwFlags)、SysEx は `midiInPrepareHeader/AddBuffer` の MIDIHDR バッファ。
- 制御: main thread で `navigator.requestMIDIAccess({sysex:true})` (secure context + 権限、ユーザ操作後)。`midiInGetNumDevs/GetDevCapsW` は OPEN 時スナップショット (`MIDIInputMap` 反復順 = デバイス ID、`szPname` は 31 文字に切詰め)、`onstatechange` はホットプラグ → 再スキャン通知。
- 入力: `MIDIInput.onmidimessage` (main) → **SPSC MIDI ring (SAB, 1 本。レコード = 16B ヘッダ + payload。short は packed msg を `w1` に、SysEx は `w1` にバイト長を置いて直後にバイト列を続ける。16B 境界へ切上げ。形式の正は `flmidi.h` 冒頭)** → wasm の専用 MIDI スレッドが `Atomics.wait` で受け、FL のコールバックを呼ぶ (`MIM_DATA 0x3C3`, `MIM_LONGDATA 0x3C4`; `dwParam2` = `midiInStart` からの ms)。W3C WD 2025 では `MIDIAccess` は `Exposed=(Window,Worker), Transferable` だが、**Chrome 154 の DedicatedWorker には `navigator.requestMIDIAccess`・`MIDIAccess` が無い (実測, REPORT_MIDI §13-2)** → main 中継が必須。実装: `src/flmidi*.c` (wasm) + `src/runtime/midi-shim.ts` (JS)、ring/レイアウトは `src/flmidi.h` が単一の真実 (TS `midi-layout.ts` が起動時に照合)、数値・検証は REPORT_MIDI.md。
- 出力: `midiOutShortMsg/LongMsg` → out ring → main が `MIDIOutput.send(data)` を呼ぶ (実装は timestamp 未指定 = 即時送信。`send(data, timestamp)` による時刻指定は未実装, REPORT_MIDI §13-3(d))。Safari は Web MIDI 非対応 (caniuse)。Firefox は権限アドオン要。
**オーディオ入力 (getUserMedia)**: `{echoCancellation:false, noiseSuppression:false, autoGainControl:false, channelCount}` → `MediaStreamAudioSourceNode` を worklet node の入力へ接続 (PoC で fake device 経由 `input_rms≈0.14` / 相関 1.0 を確認、`asio_loop_gum_fake`)。入力 ring へ worklet が write、`bufferSwitch` 直前に producer が `buffers[idx]` へ read。デバイス選択は `enumerateDevices` (ラベルは権限後) + ASIO `controlPanel` UI、変更は `kAsioResetRequest`。入力側ブラウザ内部バッファで +20–40ms (survey 4.2、未実測)。
