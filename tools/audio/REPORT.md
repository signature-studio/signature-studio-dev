# REPORT — C audio-shim: FL の ASIO/WASAPI/DirectSound/MME 経路 → AudioWorklet + SAB リング (設計 + PoC)

実行環境: headless `google-chrome 154.0.8037.97` (Linux VM, **音声ハードウェア無し = fake 出力シンク**, 共有ホスト load avg 9–12/16 コア下で実測)。再現: `bash tools/audio/e2e.sh` (約 10 分 / `--quick` 約 3 分, exit 0 = 全 PASS)。生結果 `results/results.json`。

## 1. 結論

1. **FL のオーディオ入口は事実上 ASIO 1 本で足りる**。FLEngine は `waveOut*`/WASAPI を一切 import せず (実測 0 件)、既定は同梱ドライバ `ILWASAPI2ASIO` (COM/IASIO) 経由。DirectSound (`DirectSoundCreate/EnumerateA`) と WinMM MIDI 20 関数は代替経路。mac は CoreAudio/AudioUnit render callback (ASIO bufferSwitch と同型) + CoreMIDI 16 関数。→ **P0 = ASIO 風コールバック駆動**、P1 = DirectSound/MIDI、P2 = WASAPI 風。
2. **FL が呼ぶ IASIO は 19 メソッド**で、FL が渡すコールバックと `asioMessage` の応答まで静的に特定した (INVENTORY §2)。特に **FL は `kAsioSupportsTimeInfo` に 1 を返す → ドライバは `bufferSwitchTimeInfo` を呼ぶ**、`kAsioLatenciesChanged(6)` は内部コマンド 0x17 発行に配線されている (動的レイテンシ変更を既定で通知しない根拠)。
3. **PoC 実装は動作**: C shim (ASIO 風 19 API / WASAPI 風 render) + AudioWorkletProcessor + main thread コントローラ。emcc `-pthread -sPROXY_TO_PTHREAD=1` の wasm から SAB リング経由で worklet に出力し、headless Chrome で **22 シナリオ全 PASS (AU-11 で 25 シナリオ化, §10)** (原コミット時の 1 回の実行。検収の独立再実行では 2 件の不安定さを検出・1 件修正、§9)。
4. **実測 (fake シンク)**: 120 秒ソーク (B=256, 48kHz) で **underrun 0・5,764,608 フレーム bit-exact** (ランプ照合; フレーム数は停止タイミングで run ごとに変動、検収再実行は 5,765,632)。128/256/512/1024 × 20 秒の ASIO で underrun 0・各 約 96.1 万フレーム bit-exact (原実行 961,024〜961,536、再実行 961,024〜962,560)。正弦 440/660Hz は最大誤差 1.49e-8、RMS 0.3536 (理論 0.3536)。44.1k は PASS。96k は **B=256 だと burst 次第で不安定** (§5, §9)。
5. **最大の発見 = バースト**: ブラウザは 128f quantum を 1 つずつでなく OS バッファ単位でまとめて呼ぶ (48k で 512f/10.7ms、96k で 2048–4096f: 原実行 2048、検収再実行 3072/4096)。`baseLatency` は 96k で実態の 1/3。→ ring 目標充填 `T ≥ burst×1.25 + B` が必須で、OPEN 時の較正プローブ + 実行中の動的拡張で自動化した。**T が FL から見える出力レイテンシの下限**を決める。
6. **shim の入出力往復 (in→out) = T フレームちょうど** (相互相関 1.0000, 同一 worklet クロック上): B=128 → 1408f (29.3ms)、B=256 → 1536f (32.0ms)、B=512 → 2048f (42.7ms) (原実行。T は OPEN 時の burst 較正値 512/1024 で決まり run ごとに変動: 検収フル再実行は 768/1024/1536f = 16.0/21.3/32.0ms、クイック再実行は原実行と同値)。これに Chrome の `baseLatency` 10.7ms + `outputLatency` ≈35ms (いずれも fake シンクの報告値) が加わる。**実機の遅延は未計測** (§6)。
7. クロック: worklet の `(currentFrame, currentTime)` を master にし、`getOutputTimestamp` を最小二乗平滑化して epoch ns に写像。フィット傾き 48,013 Hz (公称 48,000 Hz, +0.03%) / 96,061 Hz (公称 96,000) / 44,122 Hz (公称 44,100) は ramp 系の代表値で、シナリオ全体では 48k が 47,925〜48,015 Hz (−0.16〜+0.03%、ループバック/負荷時に低め)。`audible − now` ≈ +32.5 ms (48k ramp 系; 全体 30.6〜38.6ms、96k は 56.9ms。Chrome の outputLatency 35ms 近傍)。

## 2. 実測した呼出面 (詳細 `INVENTORY.md`, 生データ `results/inventory_raw.txt`)

| 面 | 実測 |
|---|---|
| win FLEngine import | `dsound` 2, `winmm` 24 (time 4 + midiIn 11 + midiOut 9), `msacm32` 14 (ファイル変換用), `ole32` COM 系、`waveOut*` **0**, WASAPI GUID **0**, `avrt` なし |
| ASIO (FL 側) | IASIO ラッパ 19 個 (0xc53da0–0xc53ff0)、コールバック 4 つ (bufferSwitch 0xc57420 / sampleRateDidChange 0xc576b0 / asioMessage 0xc576c0 / **bufferSwitchTimeInfo 0xc56ae0 = 本体**) |
| ILWASAPI2ASIO (FL が期待するドライバ面) | 2in/2out, `ASIOSTFloat32LSB`, buffer min256/max4096/pref512/**granularity 0**, レート {22050,44100,48000,96000,192000}, clock "Internal", `outputReady`=NotPresent。内部は WASAPI **shared/float/ポーリング** + MMCSS "Pro Audio"。CLSID `{188135E1-7171-3434-854F-01A3C71F3DF9}` |
| DirectSound (FL 側) | `CreateSoundBuffer, SetCooperativeLevel, GetCurrentPosition, GetFormat, Lock, Unlock, Play, Stop, SetCurrentPosition, SetFormat, SetFrequency, SetVolume` + `IDirectSoundNotify` |
| MIDI | `midiInOpen(CALLBACK_FUNCTION)` + SysEx バッファ (`PrepareHeader/AddBuffer`)、`midiOutShortMsg/LongMsg` |
| mac | CoreAudio 5 + AudioToolbox 10 (`AudioComponent*`, `AudioOutputUnit*`, `AudioUnit{Get,Set}Property/Render`) + CoreMIDI 16 + pthread 優先度 API |

## 3. 設計 (詳細 `docs/PROTOCOL.md`)

- ring・制御ブロック (`fla_ctl_t` 384B) は **wasm 線形メモリ内**。worklet は同じ SAB を直接読む (コピー無し)。planar f32 SPSC、32bit 単調 index、seq-cst Atomics。レイアウトは C ヘッダが単一の真実で、TS が起動時に 59 項目を照合 (不一致 → throw)。
- 制御面 (AudioContext/getUserMedia/WebMIDI) は main thread のみ → wasm からは **mailbox 同期 RPC** (`Atomics.wait` ↔ `Atomics.waitAsync`)。`CreateBuffers` = OPEN (ctx 生成+較正) → ring 確保 → ATTACH (node 生成) の 2 相。
- producer (ASIO shim スレッド) は **ブロッキング write**: 充填 ≤ T−B まで `memory.atomic.wait32`、worklet が目標到達時に一回限り `Atomics.notify` (CAS で再武装を保護)。prefill → `go` → 定常。
- underrun: 無音 + 32f declick + `BUFFERING` で `rebuffer`(=B) まで待機、データは捨てずクロックは進む。ブラウザ側スキップは `clock_jumps` に別計上。fail-fast: 不正状態は abort + 関数名 (§5 で検証)。
- WASAPI 風は `GetBuffer/ReleaseBuffer` + デバイスクロック駆動の event 相当、DirectSound 風は ring を循環バッファとみなす設計 (未実装)。MIDI/getUserMedia は SAB MIDI ring と `MediaStreamSource` 接続の設計 (PROTOCOL §9)。

## 4. 実装物

| ファイル | 内容 |
|---|---|
| `tools/audio/src/flaudio.{h,c}` | 制御ブロック, ring, mailbox RPC, クロック読出し, fail-fast |
| `tools/audio/src/flasio.{h,c}` | ASIO 風 19 API + `bufferSwitch`/`bufferSwitchTimeInfo` 駆動スレッド, 動的 T 拡張 |
| `tools/audio/src/flwasapi.{h,c}` | WASAPI 風 render (shared/float/event+polling), capture は fail-fast スタブ |
| `public/worklets/fl-audio-worklet.js` | `fl-audio-shim` (ring 読出し/入力 write/クロック/underrun) + `fl-burst-probe` |
| `src/runtime/audio-shim.ts`, `audio-layout.ts` | main thread コントローラ (mailbox, AudioContext, 時刻写像平滑化, dev_events), レイアウト表 |
| `tools/audio/test/*`, `harness/*` | テスト wasm (正弦/ランプ/ループバック), CDP 駆動 headless Chrome ランナー (COOP/COEP 付き静的サーバ込み) |
| `tools/audio/{inventory.sh,e2e.sh,build.sh,flags.sh}`, `*.py` | 実測スクリプト群 (capstone/pefile/llvm-nm), emcc フラグは `tools/m1,shim/flags.sh` 流儀 |

## 5. 検証結果 (下表は原実行 (検収時) の値。`results/results.json` は merged HEAD `a6212bc` の 33/33 run。差分は §14 / `REPORT_AU5.md`。検収の独立再実行は §9)

| シナリオ | 結果 |
|---|---|
| ASIO ランプ B=128/256/512/1024 (各 20s) | underrun 0, 各 961,024〜961,536f 全 bit-exact。T = 768/1536/1536/2048 f (16.0/32.0/32.0/42.7 ms), `burst_obs` 512f (T は OPEN 較正値で決まり run ごとに変動: 再実行 B=1024 は 3072f) |
| ASIO 正弦 (B=256 48k / B=512 44.1k / B=256 96k) | underrun 0, 最大誤差 1.49e-8, 無音ラン 0。96k は 実行中 `burst_obs` 2048f、OPEN 較正 burst ≈3072f → depth=16 (上限ぎりぎり) → T=4096f (42.7ms) (原実行)。**検収再実行では 96k/B=256 は OPEN 較正 burst が 3072 / 4096 に揺れ、旧実装は 4096 で `fla_open` が depth>16 abort (8 回中 5 回)** → §10 で修正済み (AU-11, #211) |
| **ソーク 120s** (B=256 48k ランプ) | **underrun 0**, 5,764,608f bit-exact, コールバック 22,516 回, 最大 cb 504 µs, wake 遅延 <1ms 96.2% / 1–2ms 3.7% / 2–8ms 10 回 |
| `bufferSwitchTimeInfo` (ASIOTime 148B) | 1,883 回, 位置単調・sampleRate 一致 (bad 0), 正弦 PASS。※検収で起動時の samplePosition 巻き戻り (bad=1) が 2/8 回で再現 → `flasio.c` 修正済み (§9) |
| 過負荷 (busy 6 本 + main 30ms/100ms 停止 + cb 毎 1.5ms 演算) | underrun 0 (別実行では 1〜3 回/256〜1024f: 負荷依存で記録のみ), 復帰後ランプ一致 |
| 強制 60ms hiccup (200 cb 毎) | underrun 5 (4352f 無音) → T が 1536→2816f へ自動拡張, **復帰後 ramp[p−S] 17000/17000 一致** (データ非破壊)。※原実行値 (検収時)。merged HEAD の再生成 run では underrun 6 / 4736f / T=3072 (`results/results.json`、`REPORT_AU5.md` 参照) |
| `SetSampleRate` 48k→44.1k (CreateBuffers 後, Start 前) | `SET_SR` で AudioContext 再生成 → `ctx.sampleRate=44100`, `sampleRateDidChange` 1 回, 正弦誤差 1.49e-8, underrun 0 |
| `ctx.suspend()` 0.5s → resume | `kAsioResetRequest` 1 回受信, worklet 呼出間隔 max 508 ms を検知 |
| ループバック (入力→wasm→出力, 合成ノイズ入力) | B=128/256/512 で lag = 1408/1536/2048 f (29.3/32.0/42.7 ms), 相関 1.0000, in_overruns 0, in_underflows 0 (検収再実行: lag は run 変動、B=128 で in_underflows=4 の回あり) |
| getUserMedia fake device | `Fake Default Audio Input` 経由で RMS 0.141, 相関 1.000, lag 1536f (B=256) |
| WASAPI 風 (event, B=512 depth2 / B=256 depth3) | underrun 0, ランプ 720,384f bit-exact / 正弦誤差 1.49e-8 |
| fail-fast / API 検証 | init 前の ASIO 呼出, exclusive WASAPI → abort+関数名。`createBuffers(100/8192/不正ch)`=InvalidMode, `setSampleRate(12345)`=NoClock 等 16 戻り値一致 |

その他の実測: worklet スコープに `performance` が無い (`typeof performance === "undefined"`, `Date.now` のみ)・`Atomics.notify` は利用可だが **`Atomics.wait` は TypeError ("cannot be called in this context", Chrome 154 で検収が再確認)**。worklet は notify のみ使用し wait は使わない設計で整合。fake シンクの AudioContext は実時間進行 (2000 quanta = 5.32s)。一部の実行で起動直後に `currentFrame` が 512–1024f 飛ぶ現象を観測 (`clock_jumps`, shim の underrun ではない。最終 e2e では 0)。

## 6. 限界と未実装 (正直ベース)

- **fake シンクの数値**: 音声 HW が無いため `outputLatency` 35ms/`baseLatency` 10.7ms は fake 値。実デバイス (Windows WASAPI/mac CoreAudio, Firefox, Safari) での burst・遅延・underrun は**未計測**。往復の総遅延 (入力ブラウザバッファ含む) も未計測。
- **未実装**: COM vtable アダプタ (win64 ABI/8 バイトポインタの ASIOCallbacks・ASIOBufferInfo・ASIOTime への変換; リフタ呼出規約待ち)、レジストリ `SOFTWARE\ASIO\FL Studio ASIO` と `CoCreateInstance` 配線 (別 shim 行)、~~DirectSound shim~~ (AU-4 で実装, §15)、~~WebMIDI shim~~ (AU-3 で実装, §13。FL 結線は未)、getUserMedia のデバイス選択の**製品 UI** (部品は §14 で実装、画面は AU-9 #184)、WASAPI capture/exclusive/loopback、T の縮小 (拡張のみ)、macOS 固有 (AudioUnit 面) の薄いアダプタ。
- B=128 は ILWASAPI2ASIO の min 256 より小さい (shim 単体の性能であり FL 実運用値ではない)。→ AU-7 で既定 profile を ILWASAPI 値に確定し、FL が min/max/granularity を読まないことを静的に確認 (§11)。
- 未確認 (推定): `asioMessage` selector 6 → コマンド 0x17 が再起動かどうか、~~FL が granularity=128/min=128 を受理するか~~ (解決: FL は読まない, §11)、~~DS バッファの 16/32bit~~ (§15 で静的確定)、Web MIDI の Firefox/Safari の挙動 (Chrome 154 の DedicatedWorker に Web MIDI が無いことは実測済み, `tools/audio/REPORT_MIDI.md` §13-2)。
- `ctx.outputLatency` は起動直後 0 → 約 250ms 後に更新される。`getLatencies` は呼出時の値で、FL が起動直後に読むと小さく見える。→ AU-7 で ATTACH 側の待ちを実装 (§11-3)。

## 7. ユーザ依頼事項
- なし (必須の素材・認証は不要)。**任意**: 実機 (Windows/mac, 実オーディオ IF 接続) で `bash tools/audio/e2e.sh --quick` を実行した結果の共有 (fake シンクとの差分確認用)。

## 8. 下流チケット案 (Linear: AU-n → CAB 番号は末尾の対応表)
1. **[audio-com-adapter]** IASIO COM アダプタ生成 (win64 ABI ⇄ `flasio_*`)、`ASIOCallbacks` 4 関数 (0xc57420/0xc576b0/0xc576c0/0xc56ae0) の受け渡し、`DllGetClassObject`/`CoCreateInstance` と `SOFTWARE\ASIO` レジストリ配線 (registry shim 担当と連携)。依存: リフタの呼出規約 (M11)。
2. **[audio-realdevice]** 実機 Chrome/Firefox/Safari での burst・outputLatency・underrun 行列、ループバックケーブルによる総往復遅延、T 下限の再評価。
3. **[audio-midi]** WebMIDI shim (SAB MIDI ring, `midiIn/Out` 20 関数, CALLBACK_FUNCTION スレッド, SysEx バッファ, 再スキャン) と Worker 直受信の実機検証。
4. ~~**[audio-directsound]**~~ 実装済み (AU-4 #189, §15)。
5. **[audio-input-ui]** (#192, 部品は §14 で実装済み。FL 本体側の再初期化確認と入力遅延実測は未達) getUserMedia デバイス選択 + `controlPanel` UI + `kAsioResetRequest` 連携、入力遅延実測。
6. **[audio-latency-policy]** T の縮小 (安定時に B 刻みで減衰)、安全モード/低遅延モードの UI、FL の selector 6 (0x17) 挙動確認後に `kAsioLatenciesChanged` を使うか決定。
7. **[audio-fl-profile]** (AU-7 #193) 静的に確定できた部分は §11。実 FLEngine 起動後の profile / `pbtrackingmode` 各モード (Driver/Hybrid/Mixer) でのカーソル追従確認は #34 待ち。
8. **[audio-worklet-wasm]** (任意) FL ミキサを Wasm Audio Worklet 内で直接走らせる案との遅延比較 (ブロッキング不可のため FL スレッド構造の再設計が前提)。
9. **[audio-ui-integration]** `src/index.ts` への組込 (ユーザジェスチャで `FlAudioShim.attach`, 既存 `audio.ts` ハーネスとの統合/置換)。
10. **[audio-soak30]** 30 分ソーク (CAB-9 検証条件。既存は 120 秒のみ)。検収で追加。
11. ~~**[audio-96k-depth]**~~ 解決 (#211, §10)。

対応表: AU-1 audio-com-adapter=CAB-97 / AU-2 realdevice=CAB-186 / AU-3 midi=CAB-187 / AU-4 directsound=CAB-188 / AU-5 input-ui=CAB-191 / AU-6 latency-policy=CAB-189 / AU-7 fl-profile=CAB-192 / AU-8 worklet-wasm=CAB-193 / AU-9 ui-integration=CAB-184 / AU-10 soak30=CAB-190 / AU-11 96k-depth=CAB-210 (親は全て CAB-9)。

## 9. 検収記録 (独立再実行, 2026-10-10, headless Chrome 154, 共有ホスト load avg 4〜22)
| 項目 | 結果 |
|---|---|
| フル e2e 1 回 | 21/22 PASS。`asio_sine_b256_timeinfo` が bad=1 (samplePosition 巻き戻り)。さらに runner が終了処理 (`rmSync` ENOTEMPTY) で例外終了し `results.json` を書かず exit 1 |
| クイック e2e 2 回 | 1 回目: `asio_sine_b256_96k` の abort を `expect` が例外化して runner 異常終了。2 回目 (runner 修正後): 20/21 PASS (96k のみ FAIL = AU-11) |
| 再計算で一致 | ランプ underrun 0・bit-exact (B=128〜1024)、ソーク 120s underrun 0・0 mismatch (5,765,632f = 120.1 s)、hiccup underrun 5/4352f (=17×256)、`SetSampleRate` 48k→44.1k、ループバック lag 1408/1536/2048f = 29.33/32.00/42.67 ms (クイック再実行で原実行と一致)、apicheck 16 項目、fail-fast 2 件。T = ceil((1.25·burst+B)/B)·B を原実行 17 件・クイック再実行 15 件の depth×B から逆算し、128 の倍数の OPEN 較正 burst (48k: 512〜1024、96k: 約 3072) と全件整合 (不整合 0) |
| 修正 (本コミット) | (1) `flasio.c`: worklet が新 gen を認識する前 (wl_state=IDLE) は ASIOTime.samplePosition を 0 固定。修正前 2/8 回で bad=1 → 修正後 22/22 回で bad=0 (他 2 回は無関係な Chrome 起動失敗)。(2) `harness/chrome.mjs`: 終了時 `rmSync` を retry+握り潰し。(3) `harness/run.mjs`: `expect` 例外・想定外 abort を FAIL として記録 (runner を落とさない) |
| 未修正 (チケット化) | 96k/B=256 の abort (AU-11)、30 分ソーク未実施 (AU-10)、`Atomics.wait` 記述の誤り (本 REPORT で訂正済み) |


## 10. AU-11 (#211) 96kHz/B=256 の burst 4096 abort の解消

既知類型との関係: 該当なし (lift 欠陥ではなくランタイム shim の容量判定)。方針は両案の併用: **(b) depth 固定上限 16 を撤廃** (制約は ring 容量 `(depth+2)×B ≤ FLA_MAX_RING=32768` のみ。+2B は動的 T 拡張 `Tmax=ring−2B` の余地) し、**(a) それでも収まらない burst は abort でなく `fla_open` が `FLA_E_BURST_TOO_LARGE` を返し `flasio_create_buffers` が `ASE_NoMemory(-994)` を返す** (AudioContext は CLOSE して CLOSED に戻すので再 CreateBuffers 可)。FL 側は CreateBuffers エラー ("Couldn't create the streaming ASIO buffer." が出る経路) になる。`fla_open` の fail-fast は引数不正・二重 open など呼び側バグに限定。

| 条件 (96kHz) | 挙動 |
|---|---|
| B=256, burst 3072 | depth=16, T=4096f (従来どおり) |
| B=256, burst 4096 | depth=21, T=5376f (56.0ms) で成功 (旧: abort)。ring=32768 に収まる |
| B=512, burst 4096 | depth=11 (計算値) で成功 |
| `(depth+2)×B > 32768` | `ASE_NoMemory`、abort なし。計算上の限界 burst は B=128/256/512 で 25856/25600/24960f (`need=(b+b/4+2B-1)/B` を b=128 刻みで走査) |

e2e 追加 3 本 (`harness/run.mjs`, 計 25 シナリオ): `asio_sine_b512_96k` / `asio_sine_b256_96k_burst4096` / `asio_createbuffers_burst_overflow` (B=256, burst 40000 → depth 197, (197+2)×256=50944 > 32768)。後 2 本は burst をテスト専用フック `fla_test_set_burst_floor()` (`burst_floor=` クエリ) で強制し、環境依存の揺れを決定的に再現する。

実測 (コミット `14fa86a` でビルド (main へリベース後は同内容の `57c9143`。実装 5 ファイルの diff が 0 行であることを確認済み), headless Chrome / emcc 6.0.12, GitHub runner, 並列 1):

| 検証 | 結果 |
|---|---|
| フル e2e 1 回 (`node harness/run.mjs`) | **25/25 PASS**, exit 0, 所要 440.51 s (開始時 load average 0.22 / 終了時 0.03)。soak120: underrun 0・5,763,328f 一致 |
| 96k 3 シナリオ × 6 周 (`--quick`, load average 0.00 開始) | **18/18 PASS** (b256_96k / b512_96k / b256_96k_burst4096 各 6/6)。burst4096 は毎回 T=5376, underrun 0, 正弦最大誤差 1.49e-8 (7 周目以降は打切りのため集計外) |
| burst 溢れ | `first=-994, retry=0, dispose=0, aborted=false` |

検証範囲 / 範囲外: 本 runner の fake シンクでは自然な OPEN 較正 burst は 1024 で、**検収環境で見えた burst 4096 は自然には再現していない**。burst 4096 の経路は強制フックでの検証。実機 burst 分布は未計測。**ネガティブコントロール (旧コードで burst4096 が abort することの再実行) は未実施**。旧挙動の根拠は検収記録 §9 と旧コードの `depth > 16` 判定 (`git show 14fa86a^:tools/audio/src/flaudio.c`) のみ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T 縮小が未実装 (burst 4096 で T=56ms 固定) | 96k/B=256 の遅延が burst 最大値に引きずられる | #190 (AU-6) にコメント |
| 実機 burst 分布が未計測 | 自然な burst 4096 の発生頻度・遅延影響が不明 | #187 (AU-2) にコメント |
| 旧コードでの abort 再現 (ネガティブコントロール) 未実施 | 修正前後の差を本 runner で実測していない | 本 PR 本文に明記 |

## 11. AU-7 (#193) ASIO プロファイル確定・systemTime 規約・outputLatency 吸収

既知類型との関係: 該当なし (lift 欠陥ではなく、FLEngine の ASIO 呼出面の静的解析とランタイム shim の規約合わせ)。検証起点 commit `712bcdd` (コード)。再現: 静的 `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/audio/fl_asio_profile.py [--negctl]` (要 capstone/pefile)、動的 `bash tools/audio/build.sh && node tools/audio/harness/run.mjs`。`tools/audio/e2e.sh` は 1 コマンドで通る (inventory.sh の MAC 段は dylib 無しで skip)。

**結論**: (1) FL は getBufferSize の **min/max/granularity を読まない** → 既定 profile を ILWASAPI 値 (256/4096/512/0) に確定 (報告値は FL の挙動を変えない)。(2) FL の `bufferSwitchTimeInfo` は **samplePosition を読まず systemTime だけ**を使うので、systemTime を基準ドライバ ILWASAPI と同じ「コールバック時刻」に揃えた。(3) 起動直後 outputLatency=0 は ATTACH の待ちで吸収。**実 FLEngine 上の確認 (profile・pbtrackingmode 各モードのカーソル追従) は #34/#98 待ちで未達**。

### 11-1. 静的解析 (`fl_asio_profile.py`, 12/12 PASS, 実測 5.486 s)
| 項目 | 実測 |
|---|---|
| A getBufferSize | ラッパ 0xc53e30 の呼出元は 0xc589a0 (関数 0xc58970, 58 B) の 1 箇所のみ。min/max/gran の出力先は自スタック `[rsp+0x3c]/[rsp+0x38]/[rsp+0x34]`、call 直後は `add rsp; ret` = **読まれない**。pref だけ `r9` の大域 0x16b880c へ |
| B pref の行き先 | 0xc57a00 内で 0x16b880c → 大域 0x1504bcc にコピーされ、createBuffers ラッパ 0xc53de0 呼出の `r9d` (bufferSize) = 0x1504bcc。→ FL は **ドライバの pref をそのまま bufferSize にする** (shim は pref=512 を返すので createBuffers(512)) |
| C getLatencies | 呼出は 0xc577a4 (関数 0xc57760) と 0xc58348 (0xc57a00 内, **createBuffers 成功直後の一度**)。結果は大域に保存され、あるフラグが真なら outLat += bufferSize (asiotriplebufbox と**推定**) |
| D bufferSwitchTimeInfo (0xc56ae0) | 最初の call までに params を使うのは `flags(+0x30)` の kSystemTimeValid と `&systemTime(+0x18)` だけ。params は保存されず **samplePosition(+0x20)/sampleRate は未使用**。systemTime(ns) は ÷1e6 (imul 0x431bde82d7b634db; sar 0x12) で int32 ms。大域モード値 (0x15d89d0) が 1 または kSystemTimeValid 無しなら `winmm!timeGetTime` (0x663480 の thunk) を使う |
| E 基準ドライバ ILWASAPI | 0x1800032e0: `timeGetTime()×1e6` (0x1800039b0) → vtable+0x88 getSamplePosition → callbacks+0x18 bufferSwitchTimeInfo(params, 0, 0)。**systemTime = コールバック時刻**、位置はバッファ長の積算 |
| UI | `PBTrackingModeBox` の Items = **Driver / Hybrid / Mixer** (Hints: 位置はドライバから取得 / 推定 / 粗いミキサ位置) |

ネガティブコントロール: `--negctl` (D を bufferSwitch ラッパ 0xc57420 に向ける) で **9/12 PASS、D1/D3/D4 が FAIL** (検出能力あり)。時間軸: shimx の `timeGetTime` = `emscripten_get_now()` で、emsdk 6.0.12 の `libcore.js` は PTHREADS ビルドで `performance.timeOrigin + performance.now()` (epoch ms) → shim の systemTime と同一基準 (ソース読解)。

### 11-2. 変更と動的検証 (`flasio.{h,c}`, `audio-shim.ts`, `fla_test.c`, `harness/run.mjs`)
- `FLASIO_PROFILE_ILWASAPI` 既定 0→1 (createBuffers は profile に依らず 128 の倍数 [128,4096] を受理するので B=128 の e2e は継続)。COM アダプタ (`asio/build.sh`) は元々 ILWASAPI でビルドされており、FL が通る経路の値は不変。
- systemTime = `(uint32)timeGetTime() ms ×1e6` (従来の可聴時刻は `-DFLASIO_SYSTIME_AUDIBLE=1`)。時刻写像 `clock.*` は `fla_clock_read` を直接測るよう変更 (意味不変)。
- e2e 追加 3 シナリオ + timeinfo 判定強化 (計 28): FL と同じ変換で `d = systemTime_ms − timeGetTime()` を全コールバックで測る。

| 検証 (commit `712bcdd`, headless Chrome, emcc 6.0.12, 並列 1) | 結果 |
|---|---|
| フル e2e `node harness/run.mjs` | **28/28 PASS**, exit 0, **458.9 s** (load average 開始 0.52 / 終了 0.04)。soak120: underrun 0・5,762,816f 一致 |
| `asio_sine_b256_timeinfo` | calls=1882 bad=0, systemTime valid=1882 invalid=0 nonmono=0, **d=[0,0] ms** |
| `asio_profile_ilwasapi_b512` | 報告 min/max/pref/gran = 256/4096/512/0, ch 2/2, type 19 (0x13), ramp 0/288,512 不一致 |
| COM 経路 `bash tools/audio/asio/e2e.sh` | node check **126/126**, Chrome **4/4 PASS** (soak120 含む), 194.55 s |
| ネガティブ: `FLA_DEFS="-DFLASIO_SYSTIME_AUDIBLE=1 -DFLASIO_PROFILE_ILWASAPI=0"` ビルド | timeinfo **FAIL (d=[-247,+40] ms: 起動直後に陳腐化した時刻、定常は +40 ms 先行)**、profile **FAIL (128/4096/512/128)** |

### 11-3. outputLatency=0 の吸収
`ATTACH` は outputLatency>0 になるまで最大 600 ms 待つ (`outputLatencyWaitMs`、0 で旧挙動)。headless Chrome では OPEN の較正プローブ後で既に 30 ms (`ATTACH outLat=0.03`) だったため、「最初の呼出から 300 ms 0」を返すテスト用フック (`readOutputLatency`, クエリ `olat_zero_ms`) で再現した。

| 条件 (B=256, 48k, 実測) | createBuffers 直後 `out_latency_us` | `lat_out` (FL が読む値) |
|---|---|---|
| 待ちあり (`asio_outlat_zero_at_start_absorbed`) | 30000 | 3585f (終了時と同値) |
| 待ち無効 (`..._unabsorbed_control`) | **0** | **2145f** (終了時 3585f より 1440f = 30 ms 小さい) |

### 11-4. 検証範囲 / 範囲外
範囲: FLEngine/ILWASAPI2ASIO のバイナリ静的解析、fake シンクの headless Chrome での shim 単体と COM 経路。範囲外: 実 FLEngine 起動 (#34)、FL の再生カーソル消費側 (0xc56b46 以降: 保存した (位置, ms) からの補間と outLat の使い方) の解読、実機の outputLatency 更新遅延。systemTime 規約の変更は「基準ドライバと同じ」という根拠によるもので、**FL 上でカーソルが改善することは未確認**。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FLEngine での profile / pbtrackingmode (Driver/Hybrid/Mixer) カーソル追従の確認 | AU-7 の受入未達 (#193 は Refs のまま) | #34 (AU-13) にコメント |
| モード大域 0x15d89d0 と UI の Driver/Hybrid/Mixer の対応 (setter 0x12539b0 は設定構造体の別フィールドと組合せ) 未解読 | どのモードが systemTime を使うか確定していない | #34 にコメント |
| FL が ts + outLat で可聴時刻を作るか (消費側 0xc56b46〜) 未解析 | systemTime 規約変更の効果を静的に確認できていない | #34 にコメント |
| 実機で outputLatency が上限 600 ms まで 0 のまま (Firefox/Safari 等) の場合、0 のまま進む | 遅延を過小報告 | #187 (AU-2) にコメント |
| ~~`tools/audio/e2e.sh` 先頭の `inventory.sh` が `/home/ubuntu` 固定パス~~ | 解消 (`5f7ceb6`: MAC 段を存在確認して skip。WIN は `FL_WIN64_DIR`)。runner で 1 コマンド e2e が通ることを §15 に記録 | — |

## 12. AU-9 (#185) src/index.ts 組込パッチ設計 (`tools/audio/integration/`)

既知類型との関係: 該当なし (lift 欠陥ではなくアプリ組込)。検証起点 commit: `d9cdc00` (ブランチ `185-audio-ui-integration`, base `86df5e6`)。

**方針 (決定案 — D(runtime-arch, #25) の合意待ち)**: `audio.ts` + `dummy-worklet.js` の独自 SAB レイアウト (RUN_FLAG/SAMPLE_POS) は廃止し、`FlAudioShim` に置換する。ring レイアウトは `flaudio.h` が単一の真実で、`attach()` が起動時に 59 項目を照合する (不一致は throw)。

| ファイル | 内容 | 管轄 |
|---|---|---|
| `src/runtime/audio_app.ts` (新規・適用済み) | `startFlAudio()`: テスト音 wasm ロード → `FlAudioShim.attach`。`verifyToneCapture()`: ダンプを 440/660Hz 理論値と照合 | audio (新規ファイルのみ) |
| `tools/audio/integration/index.ts.diff` | `src/index.ts` 差分: `createAudioHarness` → `startFlAudio` (クリック内で実行)。`?audio_capture=1` で `window.__audio` 公開 | **#25 管轄のため未適用 (提案)** |
| `tools/audio/integration/stage_app.sh` | `fla_test` を build し `${RUNTIME_WASM_DIR}/audio/` へハッシュ名 + `manifest.json` で stage | audio |
| `tools/audio/integration/e2e.{sh,mjs}` | HEAD を一時ディレクトリへ `git archive` → パッチ適用 → typecheck → `vite build` → headless Chrome (dev / preview) | audio |

- **worklet 配置**: `public/worklets/fl-audio-worklet.js` は vite がそのまま `dist/worklets/` へ出力 (build 後の `ls dist/worklets` で確認)。URL は `document.baseURI` 基準。`vite.config.ts` の変更は不要 (`/wasm/audio/*` は既存 `wasmAssets` プラグインが配信し COOP/COEP/CORP を付与)。
- **glue (.mjs)**: emcc glue は pthread Worker スクリプトも兼ねるので、wasm 名のみハッシュ名へ置換 (`stage_wasm.mjs` と同流儀。glue 内の `fla_test.` 参照が残れば stage 失敗)。
- **producer**: 現状は `fla_test` (ASIO 風, 正弦)。FL 本体接続時は `loadToneWasm` を差し替える (接点は `FlAudioWasmApi` の 5 関数)。

### 検証 (`bash tools/audio/integration/e2e.sh`, headless Chrome / emcc 6.0.12, GitHub runner, fake 出力シンク)

| 回 | 結果 | 所要 (e2e.sh 全体 / e2e.mjs) | 開始時 load average |
|---|---|---|---|
| 1 | 13/13 PASS, exit 0 | 65.4 s / 63.2 s | 0.11 |
| 2 | 13/13 PASS, exit 0 | 63.2 s / 61.1 s | 0.29 |
| 3 | 13/13 PASS, exit 0 | 62.7 s / 60.5 s | 0.16 |

13 項目 = dev・preview(本番ビルド) 各 6 (isolated / samplePos / tone / underruns / neg1 / console-clean) + neg2。代表値 (回 3): samplePos 1920→11008 (44,549 frames/s, 128f 単位)、ダンプ 149,504 f で最大誤差 1.49e-8・RMS 0.3536 (理論 0.3536)・無音ラン 0・underrun 0。パッチ適用後の `tsc --noEmit`・`vite build` も成功。素のブランチの `pnpm typecheck` も成功 (`audio_app.ts` 追加後)。

**ネガティブコントロール**: (N1) 照合の sampleRate を ×1.01 にずらすと max_err=1.00 で FAIL 判定 (dev/preview とも)。(N2) テスト音 wasm 未配置だと状態表示が「オーディオ開始に失敗: … manifest 取得失敗」になりボタンが再有効化。実際に初回実行で `audio_app.ts` の SAB 型キャスト誤り (TS2352) を typecheck が検出し修正済み。

検証範囲 / 範囲外: fake シンクでの正弦ビット近似のみ。**実機の可聴再生・実デバイス遅延は未計測**。`tools/e2e` (`audioworklet` チェック等) をパッチ適用後に流してはいない。Firefox/Safari 未検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `index.ts.diff` の `src/index.ts` への適用 (#25 管轄) | 適用までアプリ本体は旧ハーネスのまま = #185 完了条件は未達 | #185 コメントで PM/#25 担当に合意依頼 |
| 適用後に `audio.ts` / `dummy-worklet.js` を削除 (`deploy/probe/policy-check.mjs`・`tools/e2e/suite/checks.mjs` が dummy-worklet.js を参照) | 二重実装が残る | 適用 PR で併せて対応 (#185) |
| 本番配信での `/wasm/audio/*` (R2) と `/worklets/fl-audio-worklet.js` の COOP/COEP/CORP policy | `vite preview` では検証済み、Cloudflare/R2 配信は未検証 | #62 系 (H) へ コメント |
| `stage_wasm.mjs` / ルート `package.json` script への `stage_app.sh` 組込 | 現状は手動実行 | 適用 PR (#25 管轄) |
| `tools/e2e` スイートのパッチ適用後再実行 | 既存 `audioworklet` チェックとの互換は推定 (status 文言 `worklet 実行中`・samplePos 128f 単位は維持) | 適用 PR で実行 |

## 13. AU-3 (#188) Web MIDI shim (全文: `REPORT_MIDI.md`)

winmm `midiIn`/`midiOut` 20 関数の Web MIDI 実体を `src/flmidi*.c` / `src/runtime/midi-shim.ts` に実装。結論: **Chrome 154 の Worker には Web MIDI が無い (実測) ため main thread 中継が必須**。検証の数値・内訳は `REPORT_MIDI.md` §13-1、未解決は §13-3 を参照。モック `MIDIAccess` での検証のみで、実デバイス (AU-2 #187)・FL 結線/shimx 強定義置換 (#179, #37) は未達。

## 14. AU-5 (#192) 入力デバイス選択・controlPanel・入力喪失リセット (main thread 部品)

`FlAudioInput` (入力デバイス選択・権限・入力喪失)・`FlAudioShimOptions.input` / `controlPanel`・`FLA_CMD_CONTROL_PANEL` (=8)・`FLA_EV_INPUT_CHANGED` (=16) を実装。e2e 33/33 PASS (merged HEAD `a6212bc`、新規 5 シナリオ含む)。結論: 部品と UI 代替フックまで。FL 本体の kAsioResetRequest 再初期化確認 (#192)・入力遅延の実機実測 (#187)・製品 UI (#184) は未解決。詳細・検証回次・シナリオ表は `REPORT_AU5.md`。

## 15. AU-4 (#189) DirectSound shim (`src/flds.{h,c}`) と FL の DS バッファ形式の静的確認

既知類型との関係: 該当なし (ランタイム shim 新規実装。lift 欠陥ではない)。検証起点 commit `5f7ceb6` (HEAD, §15 末尾の表)。設計は `docs/PROTOCOL.md` §8。

**FL の DS バッファ形式 (静的, `bash tools/audio/ds_static.sh` → `results/ds_static.txt`)**: primary `SetFormat` の WAVEFORMATEX 組立は設定 bool `byte[0x15d3296]` で分岐 (0x12afcd0)。0 → `WAVE_FORMAT_PCM` 16bit ステレオ (組立 0x674e10)、非 0 → `WAVE_FORMAT_EXTENSIBLE` + `IEEE_FLOAT` 32bit・mask=3 (組立 0x674e50)。secondary は同じ wfx (0x16bd4b0) を渡す。secondary への書込みも `wBitsPerSample==0x20` で float 直コピー / 16bit 変換に分岐 (0x12af12b)。**結論: FL はユーザ設定で 16bit PCM と float32 の両方を使う** → shim は両形式を受理し、16bit は `v/32768` で float 化 (厳密)。静的イメージの初期値は 0 (=16bit) だが実値は保存設定由来で静的には不定。**推定**: この bool が UI の `ds_32bitbufbox` に対応する (設定 3 bool のうち用途が消去法で残る 1 つ。DFM フィールド表は未解析)。

**呼出面の訂正**: `fl_asio_surface.py` / INVENTORY §2 の DS 集計 (SetVolume×3, SetFrequency, GetFormat×3 等) は disp のみの集計で Delphi オブジェクトへの同 disp 呼出を含んでいた。受け手 (rcx のロード元グローバル) で分類した結果 (`fl_ds_surface.py`): IDirectSound {CreateSoundBuffer×2, SetCooperativeLevel×1}、primary {GetFormat×1, SetFormat×1}、secondary {GetCurrentPosition×2 (play のみ / write のみ), Lock×2, Unlock×2, Play, Stop, SetCurrentPosition, QueryInterface×1}、IDirectSoundNotify {SetNotificationPositions×1}。**SetVolume/SetFrequency は DS オブジェクトに呼ばれない** (走査範囲 `0x12ae000..0x12b2000` 内の結論。受け手未解決の `[+0]` 呼出が 6 件あり、範囲外・未解決分は含めて否定できない)。(INVENTORY.md は生成物扱いのため本 PR では未更新 — 下表)

**実装**: secondary = shim 内循環バイト列、pump スレッドが ring を T まで充填 (flasio と同じ T 拡張則)。play cursor = `out_read` 由来、write cursor = 変換済み + P。Notify は offset 通過で bit (合体)。`SetCurrentPosition` は停止中のみ。非 LOOPING / EXCLUSIVE / WRITEPRIMARY は fail-fast。

**e2e (追加 10 シナリオ, `harness/run.mjs`)**: poll/notify × pcm16/f32 のランプ bit-exact・正弦・44.1k・極小バッファ (4096f)・過負荷・Stop/再開・API 境界 37 項目・EXCLUSIVE fail-fast。

| 検証 (HEAD `5f7ceb6`, headless Chrome / emcc 6.0.12, GitHub runner 4 コア, 並列 1) | 結果 |
|---|---|
| `bash tools/audio/e2e.sh` 1 回目 (11:40:20 開始, FL_WIN64_DIR=展開先, TMPDIR=RUNNER_TEMP) | **37/38**, exit 1, 実測 586 s。FAIL は `asio_ramp_b128_d2` のみ (underrun 1, silence 768, ramp 不一致 922,752/961,024)。他 37 件 PASS |
| 上記 FAIL の再実行 `--only asio_ramp_b128_d2` (同 HEAD) | **1/1 PASS**, exit 0, 実測 73.4 s (load 0.22 → 0.54)。underrun 0・不一致 0/961,024。1 回目の FAIL は一過性の負荷揺れとして扱うが、原因未特定 (再発の監視が必要) |
| フル e2e 2 回目 (`node harness/run.mjs --out results/results.json`, 11:51:39 開始) | **38/38 PASS**, exit 0, 実測 557.6 s (load 0.91 at end)。`results/results.json` はこの run の出力そのもの (手で合成していない) |
| (旧 HEAD `4483b84`) フル e2e 1 回 (`node harness/run.mjs`, 既存 25 + DS 10) | **35/35 PASS**, exit 0, 実測 539 s (開始 load average 0.27 / 終了 1.28)。DS: underrun 0・ramp16 / ramp 不一致 0 (最大 721,408f)・write cursor − play cursor = 1152..2560f (許容 [P, T+2P]) |
| (旧 HEAD `4483b84`) ネガティブコントロール: `flds.c` の 16bit 係数 1/32768 → 1/32767 に壊して `ds_pcm16_poll_ramp_b256 --quick` | **FAIL** (ramp16 mismatches 192384/192384)。戻し後は diff 0 行 |

検証範囲 / 範囲外: fake シンク + 合成クライアント (FL の呼出手順の再現) のみ。**実 FL (FLEngine) からの呼出は未実施** (COM vtable アダプタ = AU-1 待ち)。DS の `Lock`→`Unlock` を介さない書込みや、FL の play cursor 利用方式 (`pbtrackingmode` 連動) は未検証。16bit 変換の FL 側係数・ディザは未解析 (shim は厳密 /32768)。独立検収の別算法検算は検収側に委ねる。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `byte[0x15d3296]` = `ds_32bitbufbox` の対応は推定 (DFM 未解析) | 形式の既定が 16/32 のどちらかは不明 (両対応なので shim 影響なし) | #189 コメント (PM 判断で DFM 解析を別チケット化) |
| INVENTORY.md §2 の DS 集計の訂正反映 (生成物扱いのため未編集) | 旧集計 (SetVolume 等) が残る | #11 にコメント (PM が生成元整備) |
| 実 FL からの DS 呼出 e2e | COM アダプタ未実装 | #98 (AU-1) |
| 実機での DS cursor 精度・write-ahead | fake シンクのみ | #187 (AU-2) |
