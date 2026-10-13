# REPORT_MIDI — AU-3 (#188) Web MIDI shim: SAB MIDI ring + winmm midiIn/midiOut 20 関数 + CALLBACK_FUNCTION スレッド + SysEx

既知類型との関係: 該当なし (lift 欠陥ではなくランタイム shim)。検証起点 commit `d88c57c` (ブランチ `188-audio-midi-shim`, base `8f55002`)。再現 `bash tools/audio/e2e_midi.sh` (tsc → emcc → headless Chrome 154, exit 0 = 全 PASS)。

**実装**: `src/flmidi{.h,.c}` (ctl 320B・入出力 ring 各 64KiB・デバイス表・mailbox RPC)、`src/flmidi_winmm{.h,.c}` (winmm 20 関数の実体 `flm_midi*`・専用 MIDI スレッド)、`src/runtime/midi-{layout,shim}.ts` (JS コントローラ: SCAN/OPEN/CLOSE RPC、`onmidimessage`→入力 ring、出力 ring→`MIDIOutput.send`、`onstatechange`→再スキャン)、テスト `test/flmidi_test.c` + `test/page_midi.mjs` (モック `MIDIAccess`)、`harness/midi_run.mjs`。ring 形式は `flmidi.h` 冒頭、設計は PROTOCOL §9。

**方針**: 入力 ring は JS→wasm の SPSC (16B レコード + payload、満杯は**新しい方を捨てて計数**)。FL スレッドは API を呼ぶだけで、`CALLBACK_FUNCTION` は専用 MIDI スレッドから呼ぶ (winmm と同じくドライバスレッド上)。`midiInStart` 前・Stop 後・Start より古い timestamp・閉じた slot/世代違いのデータは捨てて計数。SysEx は `AddBuffer` 済みバッファへ `dwBufferLength` 単位に分割し `MIM_LONGDATA`、空きが無ければ `sx_nobuf` 計数。出力は `ShortMsg`/`LongMsg`→出力 ring→main が `send`、`LongMsg` は JS が消費した後に `MOM_DONE`。ring 満杯は `MIDIERR_NOTREADY`。デバイス ID = 表の添字、ハンドル = 方向 bit + 16bit 世代 + slot。

### 13-1. 検証 (コミット済み HEAD `d88c57c` を `git worktree add --detach` で展開, headless Chrome 154 / emcc 6.0.12, GitHub runner 4 コア, 並列 1)

| 回 | 結果 | 所要 (e2e_midi.sh 全体) | 開始時 load average (1 分) |
|---|---|---|---|
| 1 | 4/4 PASS, exit 0 | 69.69 s | 0.14 |
| 2 | 4/4 PASS, exit 0 | 69.65 s | 0.42 |
| 3 | 4/4 PASS, exit 0 | 122.24 s | 0.96 |

4 本 = `midi_all` (wasm 内 check **54/54** + JS 側の出力内容検算) / ネガコン 2 / Worker 内 Web MIDI 実測。3 回の所要の差は ネガコン `drop500` が wasm 側 `wait_until` のタイムアウト待ち (8 s) を含むためで、3 回目は他より 52 s 長かった (原因は未調査)。

| 検査 (`midi_all` 内, 数え方 = check 1 件 = wasm が自己判定した 1 条件) | 実測 |
|---|---|
| 列挙・caps | 入力 2/出力 2 台。名前 31 文字切詰め (`szPname[31]=0`)、範囲外 id → BADDEVICEID、`MIDI_MAPPER` → 出力 0、ErrorText 既知/未知 |
| CALLBACK_FUNCTION | `MIM_OPEN`/`MIM_CLOSE`/`MOM_*` が `dwInstance` 付きで 1 回ずつ。`CALLBACK_WINDOW` は NOTSUPPORTED、cb=NULL は INVALPARAM、二重 open は ALLOCATED |
| 短メッセージ入力 | 1000 件を**欠落 0・順序一致・timestamp 単調**で `MIM_DATA` 配送。コールバックは `midiInOpen` 呼出スレッドと**別の単一スレッド** (他スレッド 0) |
| Start/Stop/Close | Start 前 10 件・Stop 中 5 件は捨てて計数 (callbacks +0)。閉じた slot 宛 3 件は `in_stale=3`、close 後のコールバック +0、JS 側ハンドラは close で外れる |
| SysEx 入力 | 300B + 1000B (512B バッファで 1+2 = LONGDATA 3 回) を内容一致で復元。空きバッファ無しの 3 件目は `sx_nobuf=1`。`midiInReset` で未使用バッファ 1 本を `dwBytesRecorded=0` で返却。キュー残りの `Close` は STILLPLAYING。コールバック内 `AddBuffer` 可 |
| 入力 ring 溢れ | MIDI スレッド停止中に 5000 件 → accepted 4096 + dropped 904 = 5000 (ring 65536B / 16B)。再開後、受理分 4096 件は順序どおり全配送 |
| 出力 | ShortMsg 100 件が JS 側で内容・順序一致 (`synShortOk`)。LongMsg 3000B/40000B が内容一致 (`synSysex`)、`MOM_DONE` 後に `DONE`・非 `INQUEUE`。消費停止中に 40000B を 2 本 → 1 本目 OK/2 本目 `MIDIERR_NOTREADY (67)`。送信中の Close は STILLPLAYING。別デバイス (drum) への送信 0 |
| 再スキャン | `onstatechange` で 2→3 台 (`scan_gen` 1→2, 新名称反映)、`midiInGetNumDevs` は表の seqlock スナップショット。通知が来ない除去は `flmidi_rescan()` (SCAN RPC) で 3→2 |

**ネガティブコントロール** (入力を壊して該当 check が FAIL することを確認。FAIL しなければ runner が exit 1): (N1) 500 番を 1 件欠落 → FAIL = `short_seq_ok` + `ring_overflow_oldest_kept` の 2 件 (他 52 件は PASS)。(N2) 1000B SysEx の 1 バイトを 1 ビット反転 → FAIL = `sysex_content` の 1 件。check 総数が 54 でなければ FAIL (空振り防止)。

### 13-2. Worker 直受信の実測 (Chrome 154.0.8037.97, headless, 3 回とも同一)

| 場所 | `navigator.requestMIDIAccess` | `MIDIAccess` / `MIDIInput` コンストラクタ |
|---|---|---|
| main thread | あり (権限未付与のため `NotAllowedError: Permission to use Web MIDI API was not granted.`) | — |
| DedicatedWorker (`isSecureContext=true`) | **無し** (`typeof === 'undefined'`) | **無し** |

→ **Chrome 154 は W3C 仕様の `Exposed=(Window,Worker)` を実装していない**。Worker 直受信は不可で、**main thread 中継 (本実装) が必須**。`FlMidiShim` は `MIDIAccess` 互換オブジェクトだけを受け取るので、将来 Worker で露出すれば差替え可能。Firefox/Safari 未検証。

### 13-3. 検証範囲 / 範囲外

範囲: wasm 側 winmm 互換実体 + SAB ring + JS コントローラの結合を、**モック `MIDIAccess`** で決定的に検証。範囲外 (正直ベース): (a) **実 Web MIDI・実デバイス**での遅延・取りこぼし・SysEx 実機 (AU-2 #187 に集約)。headless では権限が取れず実 `MIDIAccess` は未使用。(b) `performance.now` 基準の入力 timestamp は実機 `MIDIMessageEvent.timeStamp` の意味に依存 (モックは `performance.now()`)。(c) **shimx の weak スタブ置換・win64 ABI 変換** (`MIDIHDR`/`MIDIINCAPSW` が win64 では 8B ポインタ, コールバック呼出を `shimx_cb_translator` 経由にする) は本 PR に含めない (#179 SHX-T6)。本実装は `flm_*` 名・wasm ネイティブ幅で、`flmidi_set_invoke()` が lift 側 invoke の接続点。(d) `midiOutShortMsg` 時刻指定なし (即時 send)。出力 `MIDIOutput.send` の timestamp 指定・ランニングステータス・`midiInOpen` の `CALLBACK_THREAD/EVENT`・`MIM_ERROR/MOREDATA`・FL 実機が使う `midiInGetDevCapsW` の `MIDIINCAPS2W` 差は未実装/未確認。(e) mac CoreMIDI 16 関数は未着手。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shimx weak `midi*` の強定義置換 + win64 ABI (8B ポインタ構造体・MS ABI コールバック) 変換 | FL からは未接続 (**#188 受入のうち FL 結線側は未達**) | #179 (SHX-T6) にコメント |
| 実 Web MIDI (Windows/mac Chrome, 実 IF) での遅延・SysEx・hotplug | モック検証のみ | #187 (AU-2) にコメント |
| FL 結線 (`midiInOpen` 0xba3010 呼出元から本 shim へ) と UI の権限取得 (ユーザ操作 → `requestMIDIAccess`) | 権限前は 0 台列挙 | #37 にコメント |
| 3 回目の e2e が 52 s 長い (122.24 s vs 69.7 s) 原因未調査 | 所要の再現性 | 本 PR で明記 (n=3, 要再計測) |
| macOS CoreMIDI 16 関数 | 未着手 | 新規子チケット案: `[AU-12] CoreMIDI thin adapter` (PM 判断) |
