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

## 5. 検証結果 (`results/results.json` = 原実行 22/22 PASS。検収の独立再実行は §9)

| シナリオ | 結果 |
|---|---|
| ASIO ランプ B=128/256/512/1024 (各 20s) | underrun 0, 各 961,024〜961,536f 全 bit-exact。T = 768/1536/1536/2048 f (16.0/32.0/32.0/42.7 ms), `burst_obs` 512f (T は OPEN 較正値で決まり run ごとに変動: 再実行 B=1024 は 3072f) |
| ASIO 正弦 (B=256 48k / B=512 44.1k / B=256 96k) | underrun 0, 最大誤差 1.49e-8, 無音ラン 0。96k は 実行中 `burst_obs` 2048f、OPEN 較正 burst ≈3072f → depth=16 (上限ぎりぎり) → T=4096f (42.7ms) (原実行)。**検収再実行では 96k/B=256 は OPEN 較正 burst が 3072 / 4096 に揺れ、旧実装は 4096 で `fla_open` が depth>16 abort (8 回中 5 回)** → §10 で修正済み (AU-11, #211) |
| **ソーク 120s** (B=256 48k ランプ) | **underrun 0**, 5,764,608f bit-exact, コールバック 22,516 回, 最大 cb 504 µs, wake 遅延 <1ms 96.2% / 1–2ms 3.7% / 2–8ms 10 回 |
| `bufferSwitchTimeInfo` (ASIOTime 148B) | 1,883 回, 位置単調・sampleRate 一致 (bad 0), 正弦 PASS。※検収で起動時の samplePosition 巻き戻り (bad=1) が 2/8 回で再現 → `flasio.c` 修正済み (§9) |
| 過負荷 (busy 6 本 + main 30ms/100ms 停止 + cb 毎 1.5ms 演算) | underrun 0 (別実行では 1〜3 回/256〜1024f: 負荷依存で記録のみ), 復帰後ランプ一致 |
| 強制 60ms hiccup (200 cb 毎) | underrun 5 (4352f 無音) → T が 1536→2816f へ自動拡張, **復帰後 ramp[p−S] 17000/17000 一致** (データ非破壊) |
| `SetSampleRate` 48k→44.1k (CreateBuffers 後, Start 前) | `SET_SR` で AudioContext 再生成 → `ctx.sampleRate=44100`, `sampleRateDidChange` 1 回, 正弦誤差 1.49e-8, underrun 0 |
| `ctx.suspend()` 0.5s → resume | `kAsioResetRequest` 1 回受信, worklet 呼出間隔 max 508 ms を検知 |
| ループバック (入力→wasm→出力, 合成ノイズ入力) | B=128/256/512 で lag = 1408/1536/2048 f (29.3/32.0/42.7 ms), 相関 1.0000, in_overruns 0, in_underflows 0 (検収再実行: lag は run 変動、B=128 で in_underflows=4 の回あり) |
| getUserMedia fake device | `Fake Default Audio Input` 経由で RMS 0.141, 相関 1.000, lag 1536f (B=256) |
| WASAPI 風 (event, B=512 depth2 / B=256 depth3) | underrun 0, ランプ 720,384f bit-exact / 正弦誤差 1.49e-8 |
| fail-fast / API 検証 | init 前の ASIO 呼出, exclusive WASAPI → abort+関数名。`createBuffers(100/8192/不正ch)`=InvalidMode, `setSampleRate(12345)`=NoClock 等 16 戻り値一致 |

その他の実測: worklet スコープに `performance` が無い (`typeof performance === "undefined"`, `Date.now` のみ)・`Atomics.notify` は利用可だが **`Atomics.wait` は TypeError ("cannot be called in this context", Chrome 154 で検収が再確認)**。worklet は notify のみ使用し wait は使わない設計で整合。fake シンクの AudioContext は実時間進行 (2000 quanta = 5.32s)。一部の実行で起動直後に `currentFrame` が 512–1024f 飛ぶ現象を観測 (`clock_jumps`, shim の underrun ではない。最終 e2e では 0)。

## 6. 限界と未実装 (正直ベース)

- **fake シンクの数値**: 音声 HW が無いため `outputLatency` 35ms/`baseLatency` 10.7ms は fake 値。実デバイス (Windows WASAPI/mac CoreAudio, Firefox, Safari) での burst・遅延・underrun は**未計測**。往復の総遅延 (入力ブラウザバッファ含む) も未計測。
- **未実装**: COM vtable アダプタ (win64 ABI/8 バイトポインタの ASIOCallbacks・ASIOBufferInfo・ASIOTime への変換; リフタ呼出規約待ち)、レジストリ `SOFTWARE\ASIO\FL Studio ASIO` と `CoCreateInstance` 配線 (別 shim 行)、DirectSound shim、WebMIDI shim、getUserMedia のデバイス選択 UI、WASAPI capture/exclusive/loopback、T の縮小 (拡張のみ)、macOS 固有 (AudioUnit 面) の薄いアダプタ。
- B=128 は ILWASAPI2ASIO の min 256 より小さい (shim 既定プロファイル min=128/gran=128 の結果であり FL 実運用値ではない)。`-DFLASIO_PROFILE_ILWASAPI=1` での e2e は未実施。
- 未確認 (推定): `asioMessage` selector 6 → コマンド 0x17 が再起動かどうか、FL が granularity=128/min=128 を受理するか (ILWASAPI 値は `-DFLASIO_PROFILE_ILWASAPI=1` に用意)、DS バッファの 16/32bit、Web MIDI の Worker 内実装状況 (W3C 仕様上は `Exposed=(Window,Worker)`, 実装未確認)。
- `ctx.outputLatency` は起動直後 0 → 約 250ms 後に更新される。`getLatencies` は呼出時の値で、FL が起動直後に読むと小さく見える。

## 7. ユーザ依頼事項
- なし (必須の素材・認証は不要)。**任意**: 実機 (Windows/mac, 実オーディオ IF 接続) で `bash tools/audio/e2e.sh --quick` を実行した結果の共有 (fake シンクとの差分確認用)。

## 8. 下流チケット案 (Linear: AU-n → CAB 番号は末尾の対応表)
1. **[audio-com-adapter]** IASIO COM アダプタ生成 (win64 ABI ⇄ `flasio_*`)、`ASIOCallbacks` 4 関数 (0xc57420/0xc576b0/0xc576c0/0xc56ae0) の受け渡し、`DllGetClassObject`/`CoCreateInstance` と `SOFTWARE\ASIO` レジストリ配線 (registry shim 担当と連携)。依存: リフタの呼出規約 (M11)。
2. **[audio-realdevice]** 実機 Chrome/Firefox/Safari での burst・outputLatency・underrun 行列、ループバックケーブルによる総往復遅延、T 下限の再評価。
3. **[audio-midi]** WebMIDI shim (SAB MIDI ring, `midiIn/Out` 20 関数, CALLBACK_FUNCTION スレッド, SysEx バッファ, 再スキャン) と Worker 直受信の実機検証。
4. **[audio-directsound]** DirectSound shim (ring を循環バッファ化, Lock/Unlock/GetCurrentPosition/Notify)。FL の DS バッファ形式 (16/float) の確認を含む。
5. **[audio-input-ui]** getUserMedia デバイス選択 + `controlPanel` UI + `kAsioResetRequest` 連携、入力遅延実測。
6. **[audio-latency-policy]** T の縮小 (安定時に B 刻みで減衰)、安全モード/低遅延モードの UI、FL の selector 6 (0x17) 挙動確認後に `kAsioLatenciesChanged` を使うか決定。
7. **[audio-fl-profile]** FLEngine 起動後に granularity=128 / ILWASAPI プロファイルのどちらが必要か実機検証、`pbtrackingmode` 各モードでのカーソル追従確認。
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
