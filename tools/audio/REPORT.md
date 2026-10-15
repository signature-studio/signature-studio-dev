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
- **未実装**: COM vtable アダプタ (win64 ABI/8 バイトポインタの ASIOCallbacks・ASIOBufferInfo・ASIOTime への変換; リフタ呼出規約待ち)、レジストリ `SOFTWARE\ASIO\FL Studio ASIO` と `CoCreateInstance` 配線 (別 shim 行)、~~DirectSound shim~~ (AU-4 で実装, §15)、~~WebMIDI shim~~ (AU-3 で実装, §13。FL 結線は未)、getUserMedia のデバイス選択の**製品 UI** (部品は §14 で実装、画面は AU-9 #184)、WASAPI capture/exclusive/loopback、安全/低遅延モード UI (§17)、macOS 固有 (AudioUnit 面) の薄いアダプタ。
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
6. ~~**[audio-latency-policy]**~~ T の縮小 (安定時に B 刻みで減衰) は実装済み (AU-6 #190, §17)。残るのは安全モード/低遅延モードの UI と、FL の selector 6 (0x17) 挙動確認後に `kAsioLatenciesChanged` を使うか決定すること。
7. **[audio-fl-profile]** (AU-7 #193) 静的に確定できた部分は §11。実 FLEngine 起動後の profile / `pbtrackingmode` 各モード (Driver/Hybrid/Mixer) でのカーソル追従確認は #34 待ち。
8. **[audio-worklet-wasm]** (任意) FL ミキサを Wasm Audio Worklet 内で直接走らせる案との遅延比較 (ブロッキング不可のため FL スレッド構造の再設計が前提)。
9. **[audio-ui-integration]** `src/index.ts` への組込 (ユーザジェスチャで `FlAudioShim.attach`, 既存 `audio.ts` ハーネスとの統合/置換)。
10. ~~**[audio-soak30]**~~ 30 分ソーク: 無負荷は実施済み (#191, §16)。負荷下 30 分は未実施。
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

要約: burst 4096 (96k/B=256) で旧 `depth>16` abort を解消 (depth 上限撤廃 + 容量超過は `ASE_NoMemory` で返す)。25 シナリオ実測 PASS・未解決 3 件は全文 `REPORT_AU11.md` (分割移動先)。

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
| `index.ts.diff` の `src/index.ts` への適用 (#25 管轄) | (§17 で適用済み。`e2e.sh` は適用済み HEAD を検証する) | 解消済み (§17) |
| 適用後に `audio.ts` / `dummy-worklet.js` を削除 (`deploy/probe/policy-check.mjs`・`tools/e2e/suite/checks.mjs` が dummy-worklet.js を参照) | 二重実装が残る | 適用 PR で併せて対応 (#185) |
| 本番配信での `/wasm/audio/*` (R2) と `/worklets/fl-audio-worklet.js` の COOP/COEP/CORP policy | `vite preview` では検証済み、Cloudflare/R2 配信は未検証 | #8 (H-2: R2 静的配信 + COOP/COEP) へ コメント |
| dev 経路の断続的 tone/underrun FAIL (レビュアー再現 6 回中 2 回、本 head では 9 回全 PASS で未再現) | 再現時の原因 (producer 遅延 / consumer 枯渇) 未切り分け | #863 (AU-15) |
| 旧ハーネス残骸 `public/worklets/dummy-worklet.js` の削除 (参照 2 箇所) | 未参照の残骸 | #839 (E2E-5) |
| `stage_wasm.mjs` / ルート `package.json` script への `stage_app.sh` 組込 | 現状は手動実行 | 適用 PR (#25 管轄) |
| `tools/e2e` スイートのパッチ適用後再実行 | 既存 `audioworklet` チェックとの互換は推定 (status 文言 `worklet 実行中`・samplePos 128f 単位は維持) | 適用 PR で実行 |

## 13. AU-3 (#188) Web MIDI shim (全文: `REPORT_MIDI.md`)

winmm `midiIn`/`midiOut` 20 関数の Web MIDI 実体を `src/flmidi*.c` / `src/runtime/midi-shim.ts` に実装。結論: **Chrome 154 の Worker には Web MIDI が無い (実測) ため main thread 中継が必須**。検証の数値・内訳は `REPORT_MIDI.md` §13-1、未解決は §13-3 を参照。モック `MIDIAccess` での検証のみで、実デバイス (AU-2 #187)・FL 結線/shimx 強定義置換 (#179, #37) は未達。

## 14. AU-5 (#192) 入力デバイス選択・controlPanel・入力喪失リセット (main thread 部品)

`FlAudioInput` (入力デバイス選択・権限・入力喪失)・`FlAudioShimOptions.input` / `controlPanel`・`FLA_CMD_CONTROL_PANEL` (=8)・`FLA_EV_INPUT_CHANGED` (=16) を実装。e2e 33/33 PASS (merged HEAD `a6212bc`、新規 5 シナリオ含む)。結論: 部品と UI 代替フックまで。FL 本体の kAsioResetRequest 再初期化確認 (#192)・入力遅延の実機実測 (#187)・製品 UI (#184) は未解決。詳細・検証回次・シナリオ表は `REPORT_AU5.md`。

## 15. AU-4 (#189) DirectSound shim (`src/flds.{h,c}`) と FL の DS バッファ形式

DirectSound shim を実装 (secondary = 循環バイト列, pump が T まで充填, Notify は offset 通過で bit)。FL の primary `SetFormat` は設定 bool `byte[0x15d3296]` で PCM16 / EXTENSIBLE-float32 に分岐するため、shim は両形式を受理 (16bit は `v/32768`)。**全文・静的確認の詳細・検証表・未解決は `REPORT_DS.md`**。

統合後 HEAD `b394287c` の e2e: **43/43 PASS** (DS 10 シナリオ含む, 実測 647 s)。未解決: 実 FL からの DS 呼出 (#98 AU-1)、実機の DS cursor (#187)、`byte[0x15d3296]` の DFM 解析 (#189 コメント)。

## 16. AU-10 (#191) 30 分ソーク (`--soak30`)

無負荷 30 分 (1800 s, B=256 48k ランプ) は PASS (underrun 0・ramp mismatch 0)、負荷下は 420 s で PASS。ただし head `fc93f45` (main 取り込み後) 上の 30 分ソークは未実施 (未計測)。head `fc93f45` の 10 秒ソークは PASS (ramp 0 / 481,024 f)。head `57519ca` の 10 秒ソークは 4 回中 1 回 FAIL (ramp mismatch 411,392/480,512、原因未特定) で、他 3 回は PASS。実機・Firefox/Safari は未計測。実測値・再現・未解決は `REPORT_AU10.md` (分割移動先) を参照。

## 17. AU-6 (#190) 遅延ポリシー: T の減衰 (全文: `REPORT_AU6.md`)

underrun が 3 秒続くと +B を 1 段ずつ戻す (下限は下げない)。`kAsioLatenciesChanged` は既定 OFF のまま。減衰テストと検証結果の正本は `REPORT_AU6.md` §2。**未解決**: 閾値 3 秒の実機調整 (#187)、安全/低遅延モード UI (#34 以降)、selector 6 の利用可否 (0x17 未確定)。

## 18. AU-9 (#185) 組込適用 (`src/index.ts` 反映・旧ハーネス削除)

§12 の提案パッチを `src/index.ts` に適用し、旧 `src/runtime/audio.ts` を削除した (#25 close 済みのため管轄の前提が解消)。`e2e.sh` は `index.ts` が未適用のときだけパッチを当てる (適用済み HEAD を検証可能にするため)。`e2e.sh` の `git archive` 範囲は HEAD 全体へ広げた (`vite.config.ts` が `tools/legal/notices`・`tools/ipp` の LICENSE を読むため部分展開では build が落ちた)。

検証: 素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (7.5 s) し `FL_WIN64_DIR` に指定。HEAD `321c94fa` (適用済み・audio.ts 削除後) で `bash tools/audio/integration/e2e.sh`: **13/13 PASS, exit 0, 67 s** (e2e.sh 全体)。同条件の直前 run (`3c52be7a`) は 13/13 PASS, 63 s / 60.7 s、その前の run は 13/13 PASS, 70 s。tsc --noEmit OK。

旧パッチ適用経路 (`e5f043c3`・index.ts 未コミット状態) の 3 回目 run では dev 側 `dev:tone` / `dev:underruns` が 1 回だけ FAIL (underruns=1, zero_runs=1)。以降の 3 run (`2d68a5bd`〜`321c94fa`) は dev/preview とも全 PASS。

**レビュー差し戻し対応 (fix, 2026-10-13)**: head `0e0e8634` のレビュー再実行で dev 失敗 2 回 (6 回中)・preview 後のハング (exit 124, 25 分) が報告された。対応:

- **ハング**: 原因候補は preview 終了時の `srv.httpServer.close(callback)` が Chrome の keep-alive 接続で完了を待ち続けること。`closeServer()` で `closeAllConnections()` を呼び、10 s の上限を付けた (dev は `srv.close()` のまま)。修正後の 1 run の実測では preview 後の後始末は即時完了。ハングの再現は本 head では未確認 (原因は未確定。対策は上限付きの防御)。
- **位置情報**: `verifyToneCapture` に `first_err_frame` / `first_zero_run_frame` / `underrun_cap` / `first_underrun_frame` / `last_underrun_frame` を追加 (worklet が capture ヘッダへ記録する値)。
- **dev 失敗の再現**: 本 head `755ecb23` で e2e.sh を無負荷 6 回 (`run1`〜`run5` + `c1`) + CPU 負荷 (`timeout` 付きの busy loop 6 本) 下 3 回の計 9 回実行 → **全 PASS (13/13, 7.6〜9.3 s)、underrun 0・zero_runs 0・first_err_frame=-1**。レビュアー再現条件 (素材・負荷) とは未一致のため未再現。追跡 **#863** (AU-15)。

検証 (commit 755ecb23・e2e.sh 1 run ずつの実測): 無負荷 `c1` 13/13 PASS, 7.6 s, exit 0 / 無負荷 5 run 全 PASS, 7.7〜7.8 s / 負荷下 3 run 全 PASS, 9.2〜9.3 s。
最終 HEAD `e983c1b6` (main 取り込み後・`pnpm install --frozen-lockfile` 後): `bash tools/audio/integration/e2e.sh` **13/13 PASS, exit 0, 7.8 s**。`tsc` OK・`vite build` OK。dev:tone `max_err=1.49e-8`・underrun 0・zero_runs 0・preview 同値。
最終 HEAD `948e6fb3` (REPORT §10 の件数修正のみ・コード差分なし、`FL_WIN64_DIR` 展開 `fl-win64`): `bash tools/audio/integration/e2e.sh` を 3 回実行 → **13/13 PASS・exit 0 が 3 回** (7.9 s / 7.8 s / 7.7 s、wall 12.0 s / 10.6 s / 10.4 s、load 0.48 / 0.47 / 0.81)。FAIL 0 件。

残り: `public/worklets/dummy-worklet.js` は `deploy/probe/policy-check.mjs`・`tools/e2e/suite/checks.mjs` が参照するため今回は削除せず、追跡 **#839** (E2E-5)。`tools/e2e` スイートの再実行は未実施 (#839 で実施)。

**状態注記 (#839 で更新)**: 上の「削除せず」は当時の記述。#839 で参照を `fl-audio-worklet.js` へ差し替え `dummy-worklet.js` を削除済み。`tools/e2e` の `audioworklet`・`console-clean` は `run.sh` が `stage_app.sh` でテスト音 wasm を配置するようになったため PASS (実測は `tools/e2e/REPORT.md` の「839 E2E-5」節)。

## 19. AU-15 (#863) dev 断続 FAIL の再現 (失敗 1 件を取得)

測定 HEAD は `906f6295` (main `c05efc3d` 取り込み後・PR 差分は本ファイルのみ)。素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`extracted/` と installer exe)・`FL_WIN64_DIR` 指定。`toolchain-emsdk` を `[EMSDK]` (emsdk 6.0.12) として展開し、`EMSDK_ENV` でそのエントリの `emsdk_env.sh` を指定。`bash tools/audio/integration/e2e.sh` を foreground で実行。

- 本 HEAD `906f6295` の連続 11 run (load 0.22〜2.09): **11/11 exit 0・13/13 PASS** (10〜11 s)。dev:tone `max_err=1.49e-8` zero_runs 0・underrun 0。
- 旧 HEAD `bb912951` (`d53f449c` からは REPORT のみの差分でコード同一。main 取り込み前): 初回 1 run exit 1・11/13 PASS (8.6 s)。FAIL は dev:tone (`max_err=6.85e-1` `zero_runs=1` `first_err_frame=56576` `first_zero_run_frame=56607`) と dev:underruns (`underruns=1` `first_underrun_frame=56576`)。直後の 10 回は 10/10 exit 0・13/13 PASS。
- 旧 HEAD `d53f449c` の記録 (失敗ログ未取得) は旧記録として残す。旧記述「21 run 全 PASS」は本実測と合わず撤回。
- 再現条件 (負荷・タイミング) は未特定。FAIL は旧 HEAD の 11 run 中 1 件のみで、切り分けは `first_underrun_frame=56576` (producer 遅延か consumer rebuffer か) を起点に行う。追跡 **#863** (AU-15)。

## 20. AU-15 (#863) 現 HEAD での再試行 (失敗 0 件)
結論: `origin/main` `2f235a0a` で 15 run 全 PASS (無負荷 9 + 負荷下 6)。`origin/main` `63ed695b` で追加 27 run 全 PASS (強負荷 12 本を含む)。全文は [REPORT_APPENDIX_863.md](REPORT_APPENDIX_863.md) §20・§21。

## 21. AU-15 (#4089) underrun 時刻と producer write 区間の突き合わせ

測定 commit `60b58c68a` (コード変更は本 commit のみ・base `47a76cf4b`)。`bash tools/audio/integration/e2e.sh` を foreground で実行 (`TMPDIR=$RUNNER_TEMP`)。

- 時間軸: worklet は underrun の最初の 1 回を `Date.now()` の epoch µs 下 32bit (`capture hdr[7]`) へ記録。producer の `pw_trace` は `emscripten_get_now()` の epoch 基準 µs 下 32bit。両者とも epoch 基準なので同じ軸で差を取る。精度は worklet 側の ms (±1000 µs)。
- 判定行: `uo_overlap` (重なり有無)・`uo_gap_us` (0 で区間内、>0 で区間後、<0 で区間前)・`uo_w`・`uo_wake_us`・`uo_done_us`。`underrun=0` の run は `uo_overlap=none`。
- 合成検証: `node tools/audio/integration/uo_negctl.mjs` で `matchUnderrunWrite` を抜き出して実行。正例 3 (内側・両端)・負例 3 (前・間・後)・u32 折り返し 2・空 1 の計 9 件 **ALL PASS** (終了コード 0)。
- 実 e2e: 無負荷 10 run・負荷 (Python 4 プロセスの CPU 占有) 10 run、計 20 run。**全 20 run exit 0・13/13 PASS**。無負荷 10.4〜10.9 s、負荷 14.9〜15.9 s。全 run で underrun 0 件のため、`uo_overlap` の実値 (true/false) は**未取得**。実 underrun での判定は #863 の再現待ち。
