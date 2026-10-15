# REPORT — AU-8 (#194) FL ミキサを Wasm Audio Worklet 内で直接走らせる案 vs 現行 ring 方式のレイテンシ比較

既知類型との関係: 該当なし (lift 欠陥ではなくランタイム構成の比較実験)。測定 commit (コードを変えた最後の commit): `40aa2f8a6` (§4-2 の静的計測と e2e。§5)。§2・§3 の動的値は前回測定 `f3680404` の run (`results/results.json`)。
再現 (1 コマンド): `FL_WIN64_DIR=<fl-win64 展開先> PY=<pefile 入り python3> bash tools/audio/wl/e2e.sh` (exit 0 = 全 gate + 全ネガコン成立)。

## 1. 結論

1. **実 FL ミキサでの比較は未達 (#34 待ち)**。本実験の「ミキサ」は FL ではなく、`tools/audio/test/fla_test.c` と同じ**テスト音ミキサ代役** (ramp / 正弦 / 入力素通し)。よって下記は **「ring + producer スレッド」構成と「worklet 内で直接 render」構成の構造的な遅延差** であり、FL 実機の遅延ではない。→ #194 は **Refs** (Closes しない)。
2. **構造的な差**: 入力→出力の往復遅延 (相互相関, 同一 worklet クロック上) は worklet 直走行が **B フレームちょうど** (128/256/512 → 2.67/5.33/10.67 ms)、ring 方式は **T フレーム** (1408/1536/2048 f = 29.33/32.00/42.67 ms)。差は 26.67/26.67/32.00 ms (各 n=3 全 run 同値)。T は `T ≥ burst×1.25 + B` (`tools/audio/docs/PROTOCOL.md` §4) で決まり、worklet 直走行にはこの項が無い。
3. **過負荷時の挙動 (実測・持続過負荷)**: render が worklet のオーディオスレッド上で走る。B=256@48k (予算 5333 µs) で模擬負荷 4000 µs は両方式とも健全 (underrun 0 / ramp 不一致 0)。**8000 µs (予算の 1.5 倍) では worklet 直走行の実時間比が 0.7421 (測定 commit `f3680404` で 1 回, n=1)**。音声が実時間の 74.2% しか進まない。ring は underrun 443 (>0)。過去の 3 run の min–max 0.6049〜0.6357 は §3 項目 2 に残す。持続過負荷では両方式とも破綻するため、**直走行固有の代償はこの測定では示せていない**。一過性の単発超過を ring の T が吸収する側との比較は未測定 (§3 項目 4)。直走行は `Atomics.wait` 系のブロッキングが使えない (§3 項目 1)。
4. **FL スレッド構造の再設計見積り (静的・FLEngine 全体の数であってミキサ専用ではない)**: §4。結論は「FL 本体は 1 DLL 内で CreateThread 3 箇所 / 待機系 760 箇所 (うち CS Enter 699) / 非ブロッキング同期 971 箇所 (CS Leave・Init・Delete と Event 系) を使い、worklet 直走行にはミキサ呼出グラフの切り出しが前提」。切り出し範囲 (どの関数がミキサ render から到達するか) は、直接 call だけの下限と、間接 call を閉世界の候補で置いた上限の区間で測った (§4-2)。ミキサ本体は未切り出し。

## 2. 比較実験 (`run.mjs`, 実測)

構成: ring 版 = `fla_test` (`-pthread -sPROXY_TO_PTHREAD=1`, ASIO 風 producer スレッド, `tools/audio/docs/PROTOCOL.md`)、worklet 直走行版 = `wl/fla_wl.c` (`-sAUDIO_WORKLET=1 -sWASM_WORKERS=1`, `process()` が 128f quantum を B/128 個集めて 1 ブロック render、出力は 1 ブロック遅れ = ASIO 風 double buffer と同型)。どちらも headless Chrome (fake 出力シンク)・48 kHz・入力はノイズ (`AudioBufferSourceNode`)。
遅延 = 入力→出力の相互相関ピーク (`tools/audio/test/page.mjs` と同じ 1 s 窓・lag 0〜8192 f)。

| B | worklet 直走行 lag (n=3) | ring lag (n=3) | ring の T (n=3) | 差の中央値 |
|---|---|---|---|---|
| 128 | 128, 128, 128 f (2.67 ms) | 1408, 1408, 1408 f (29.33 ms) | 1408 f | 26.67 ms |
| 256 | 256, 256, 256 f (5.33 ms) | 1536, 1536, 1536 f (32.00 ms) | 1536 f | 26.67 ms |
| 512 | 512, 512, 512 f (10.67 ms) | 2048, 2048, 2048 f (42.67 ms) | 2048 f | 32.00 ms |

- ring の T は OPEN 較正 burst (この runner では 512 f) で決まる。**実機 burst は未計測** (REPORT.md §6 / #187)。実機で burst が 2048〜4096 f なら ring 側の T は 5376 f (56 ms) まで伸びる (AU-11 §10)。直走行側が実機 burst からどう影響を受けるかは**未測定**。
- 直走行の ramp 出力は B=128/256/512 で全フレーム bit-exact (frames_checked 290,176 / 290,048 / 289,792 f, 不一致 0, clock_jumps 0, head_nonzero 0 = `results/results.json`、測定 commit `f3680404` の run)。先頭 B フレームは無音。

## 3. 直走行の制約 (実測)

1. **worklet 内 `Atomics.wait` / `memory.atomic.wait32` は戻らず `process()` が停止する** (`probe=2`): 到達マーカ 100 のまま quanta=10 で止まり、3 s 後も増えない (gate `wl_probe_atomic_wait32_traps`)。ring 方式の「FL スレッドが ring へブロッキング write」はそのままでは持ち込めない。
2. **予算超過は無音ではなく「実時間が進まない」形で現れる**: 8000 µs/ブロックで `rt_ratio` は測定 commit `f3680404` の run で 0.7421 (n=1, `results/results.json` の `overload_1.5_wl_detects`)。過去の 3 本 (0.6049 = 916fa7a クリーン HEAD, 0.6351 = fea636d 作業ツリー, 0.6357 = PR #599 レビュー側の独立再実行) の min–max は 0.6049〜0.6357 で、0.7421 はその外側 (高い側)。n=1 のため単発の分散が大きく、この値の再現幅は未測定。`clock_jumps` 0 (shim の `clock_jumps` では検知できない)。検知には wall 時間との比が要る。
3. **バースト内の連続 render (推定・未測定)**: ブラウザは quantum を OS バッファ単位で連続呼出する (本 runner の gap ヒストグラムは 0 ms 間隔が多数 + 約 10.7 ms 周期: `results/results.json` の `gap_hist`)。B=256 の render は 2 quantum ごとなので、バースト内で連続して走り得る。4000 µs (予算の 0.75 倍) では健全だった (`load_0.75_wl`, rt_ratio 1.0013)。予算 0.75〜1.0 倍の間でどこから崩れるかは**測っていない**。
4. **一過性の単発超過 (未測定)**: ring 側は `tools/audio/REPORT.md` §5 の hiccup 試験 (60 ms 停止を 200 cb 毎) で underrun 5 → T 自動拡張 (1536→2816 f)・復帰後データ非破壊を実測済み。直走行に同条件の単発超過を入れた比較は**未実施**のため、一過性の超過に対する直走行の耐性は不明。

## 4. FL ミキサの worklet 内実行に必要なスレッド再設計の見積り (静的)

`python3 tools/audio/wl/fl_thread_surface.py` (FLEngine_x64.dll = `block00031_PE.bin`, ImageBase 0x400000, .pdata 関数 57,816 / import 795 / DLL 33)。数え方: IAT スロットへの `call [rip+disp]` + `jmp [rip+IAT]` thunk 経由の `call/jmp rel32` の参照元を数え、.pdata で関数に解決。**FLEngine 全体の数でミキサ render から到達する範囲ではない**。

| クラス | API 数 | call 箇所 | distinct 関数 | 主な内訳 (箇所) |
|---|---|---|---|---|
| thread_create | 3 | 17 | 17 | SetTimer 13, CreateThread 3, CreateTimerQueueTimer 1 |
| blocking_wait | 9 | 760 | 594 | EnterCriticalSection 699, Sleep 33, WaitForSingleObject 16, MsgWaitFor* 4, WaitForMultipleObjects(Ex) 4, SwitchToThread 3, SignalObjectAndWait 1 |
| nonblocking_sync | 6 | 971 | 759 | LeaveCriticalSection 799, Initialize/DeleteCriticalSection 各 65, CreateEventW 17, SetEvent 17, ResetEvent 8 |
| thread_attr | 11 | 75 | 65 | GetCurrentThreadId 51, SetProcessAffinityMask 9, Tls* 8, SetThreadPriority 1 |
| atomic (Interlocked*) | 0 | 0 | 0 | import 無し (IAT 経由の Interlocked* は 0。インライン `lock` 命令の個数は**未集計**) |

数え方の限界: 生バイト列走査 (`ff15`/`ff25`/`e8`/`e9`) のため、偶然一致や取りこぼしが混じり得る。別算法 (逆アセンブル) による検算 (PR #599 の review 記録) では 18 API 中 17 が一致し、LeaveCriticalSection のみ 798 (本表 799)。1 件差は下記の見積りの結論に影響しない。

見積り (**推定**。根拠は上表と §3):
- 排他は待機系 760 箇所のうち 92% (699/760) が **CriticalSection**。worklet では `Atomics.wait` が使えないので、ミキサ render 経路に入る CS は「競合しない保証 (単一スレッドに寄せる)」か「try-lock + スキップ」への書換えが必要。ミキサ経路の CS 数は未解析。
- **FL の実スレッドは CreateThread 3 箇所 + CreateTimerQueueTimer 1 + SetTimer 13 (UI タイマ)**。どれが ASIO bufferSwitch / ミキサ / ファイル I/O かは未特定。ミキサ本体を worklet 上で走らせると、ASIO 風コールバックのスレッド (現行 producer) が無くなり、`WaitForSingleObject` 16 箇所 + `Sleep` 33 箇所のうちミキサ到達分は全て「ポーリング or メッセージ待ち」へ変更になる。
- プラグインのロード/GUI/ディスク読込は worklet から直接は呼べない (DOM・fetch が無いことは仕様上の事実。メモリ増加の可否は未確認) ため、**ミキサ経路から非同期要求 (ring/メール箱) を main/worker へ出す境界**が別途必要。これは本 PoC で未検証。
- したがって工数見積りは「ミキサ到達関数集合の抽出 (lift 後の call graph) → その集合内の同期プリミティブ個数の再集計」が前提。間接 call を閉世界の候補で置いた区間の再集計は §4-2 (個別の目標の特定は §6)。

### 4-2 bufferSwitchTimeInfo (0xc56ae0) からの到達集合 (下限・上限の区間)

再現 (1 コマンド): `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/audio/wl/mixer_reach.py --json tools/audio/wl/results/mixer_reach.json --check-objdump` (測定 commit `40aa2f8a6`・出力 `results/mixer_reach.txt`・32.3 s)。入口は FL の bufferSwitchTimeInfo 本体 (ASIO 表の 0xc56ae0)。API は `thread_api.py` の分類で数える。

| 項目 | 下限 (直接 call + tail jmp のみ) | 上限 (間接 call/jmp の目標を閉世界の候補で置く) |
|---|---|---|
| 到達関数 (.pdata 57,816 中) | 4,433 (7.7%) | 14,523 (25.1%) |
| 到達命令 / 範囲外の目標 | 295,499 / 10 | 959,573 / 30 |
| 到達集合内の call/jmp 箇所 (分母) | 27,475 (関数宛て直接 22,568 + API 1,106 + 間接 3,801) | 96,514 (関数宛て直接 78,766 + API 2,872 + 間接 14,876) |
| 間接 call/jmp | 3,801 = 13.8% (未追跡) | 14,876 = 15.4% (全件を候補で近似。個別の目標は未特定) |
| thread_create (CreateThread・SetTimer 等) | 4 箇所 / 4 関数 | 5 箇所 / 5 関数 |
| blocking_wait (うち EnterCriticalSection) | 188 箇所 / 121 関数 (CS Enter 170) | 405 箇所 / 295 関数 (CS Enter 368) |
| nonblocking_sync (うち LeaveCriticalSection) | 201 箇所 / 131 関数 (CS Leave 178) | 422 箇所 / 304 関数 (CS Leave 382) |
| thread_attr | 18 箇所 / 15 関数 | 51 箇所 / 42 関数 |
| atomic (Interlocked* の import) | 0 | 0 |
| 既知の辺 winmm!timeGetTime (gate の got) | 12 箇所 | 38 箇所 |

解決方法 (上限):
- 候補集合 AT = アドレスを取られた関数 3,495 件。(a) 非コード領域 (.data 等) に現れる関数アドレス (vtable・関数ポインタ表を含む) と、(b) コード中の rip 相対 lea・即値 mov で作られる関数アドレス (コード参照 2,633 件)。生バイト走査で求める。
- 間接 call/jmp の目標は AT の全件とする (閉世界仮定: 関数アドレスは (a)(b) の経路でしか作られない)。候補が空で未解決の箇所は 0。
- 参考 (slot): 基底がメモリ読込の `[R+d]` は、非コード領域の関数ポインタ表 695 表 / 7,295 スロットの d 番目に候補を限る (R が表を指すことは仮定)。到達集合は上限と同一 (14,523)。1,209 箇所は AT にフォールバックし、そこから閉包が AT 全体に広がるため、slot 限定は到達集合を縮めない。

読み方:
- 上限は閉世界仮定に依存する。仮定が成り立てば真の到達集合は下限以上・上限以下。崩れる場合 (AT 外の関数アドレス、関数ポインタ経由の API 呼出し) は上限が真の値を下回り得る。
- 区間の幅は下限の 3.3 倍。ミキサ render の到達集合はこの区間の中にある。個別の目標の特定は実行時値の採取が要り、未実施。
- 同期箇所 (blocking_wait + nonblocking_sync) は下限 389 → 上限 827 箇所。CS の Enter/Leave は 348 (89.5%) → 750 (90.7%)。上限の CS Enter 368・Leave 382 は FLEngine 全体 (§4 表: Enter 699・Leave 799) の約 53%・48%。
- 下限で CreateThread が 1 箇所到達する (初回呼出しか毎回の経路かは未確認)。
- 到達集合は UI (PostMessageW・SendMessageW・ShowWindow 等) や設定読込 (RegQueryValueExW 等) を含む。入口の 1 関数が広く呼ぶため、ミキサ本体だけは切り出せていない。
- gate が検査するのは「入口が .pdata の関数先頭であること」と「既知辺が上限の到達集合にあること」だけ。到達集合の正しさ (取りこぼし・過剰) は検査していない。gate PASS (入口 pdata 先頭・timeGetTime got=38)。入口を関数内部に差し替えた `--negctl` は gate FAIL (期待どおり)。

検算 (別算法 = objdump の全 .text 線形走査で、上限の同じ BFS を別実装): objdump は関数 14,522 / 関数宛て直接 78,760 / API 2,872 / 間接 14,876。capstone は 14,523 / 78,766 / 2,872 / 14,876。API と間接は一致。関数 1 と直接 6 箇所の差は未特定 (推定: 線形走査の命令境界のずれ)。下限は検算していない。

## 5. 検証

検証 commit: `40aa2f8a6` (コード差分の最終 commit。前回の動的測定は `f3680404`)。`git worktree add ../ws-2993 -b 2993-indirect-reach origin/main` で作業し、同 worktree で実行。`toolchain-emsdk` は `$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` を `$RUNNER_TEMP/tc` へ展開 (3.8 s) し `EMSDK_ENV` で指定 (本測定の run)。素材: fl-win64 = `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` へ展開 (5.5 s)。以下の『前回』の run (`f3680404`) では emsdk を上流から pin 版 `6.0.12` (`tools/m1/flags.sh`) で `emsdk install` (27 s) して取得し、`$ARTIFACTS_DIR` の `toolchain-emsdk` は使っていない。

| 項目 | 結果 |
|---|---|
| 到達集合 (`python3 tools/audio/wl/mixer_reach.py --check-objdump`, 静的のみ) | gate 2/2 PASS (入口が pdata 先頭・既知辺 timeGetTime 上限 38 箇所)。`--negctl` (入口を関数内部に差替え) は gate FAIL = 期待どおり。実行 32.3 s (n=1, 検算込み)。検算 (objdump) との差は関数 1・直接 6 箇所 (§4-2)。結果は §4-2 |
| 比較 e2e (`bash tools/audio/wl/e2e.sh`, 測定 commit `40aa2f8a6`) | **32/32 合格 (negctl 5 件を含む), exit 0**。run.mjs 230.4 s, load average 開始 0.70 / 終了 0.17, 並列 1。e2e 全体 300.8 s (real 5m0.8s、ビルド・静的 gate を含む)。同 commit の前段 run (`20a74b4ef`, 検算なし) は 32/32・231.4 s・load 1.39 → 0.08。前回 (`f3680404`) は 32/32・230.6 s・load 0.62 → 0.14。 |
| 静的スレッド面 (`fl_thread_surface.py`) | gate 4/4 PASS (CreateThread≥1, WaitForSingleObject≥1, SetEvent≥1, Sleep≥1) |
| 静的 negctl (`--negctl`: gate の API 名を実在しない名に差替え) | gate 4/4 FAIL → exit 0 (検出能力あり) |
| 動的 negctl 5 件 (全て「壊した入力で検査器が FAIL を出す」を確認) | ①負荷 1.5 倍で直走行の健全性 gate が FAIL (rt_ratio 0.7421 < 0.99, n=1) ②ring の underrun 443 (>0) ③入力を接続しない loop は corr 0 で lag gate が FAIL ④ring の lag 1536 f を直走行用 gate (lag==B) に通すと FAIL ⑤ramp を 1 件壊した結果を gate が FAIL |

「PASS」の意味は限定する: e2e の gate は、直走行の bit-exact・lag・健全性と ring の lag・underrun を検査する。これは測定の成立の確認であり、FL の実ミキサの正しさや遅延の検査ではない。

**鮮度の基準 (WORKFLOW §6)**: 旧測定は `916fa7a`。`916fa7a` → 測定 commit の間に ring の実行コードが main の別 PR で変わっている (`tools/audio/src/flasio.c` の AU-6 T 縮小・`tools/audio/src/flds.c`・`tools/audio/src/flmidi*.c`・`tools/audio/test/*`・`tools/audio/build.sh` の MIDI ビルド追加)。その差分 (`git diff --stat 916fa7a f3680404 -- tools/audio/src tools/audio/test tools/audio/build.sh`):

```
 tools/audio/build.sh                  |  14 +-
 tools/audio/src/flasio.c              |  32 ++-
 tools/audio/src/flasio.h              |   1 +
 tools/audio/src/flaudio.c             |   4 +-
 tools/audio/src/flaudio.h             |  18 +-
 tools/audio/src/flds.c                | 362 +++++++++++++++++++++++++++
 tools/audio/src/flds.h                |  98 ++++++++
 tools/audio/src/flmidi.c              | 142 +++++++++++
 tools/audio/src/flmidi.h              | 110 ++++++++
 tools/audio/src/flmidi_shimx.c        |  40 +++
 tools/audio/src/flmidi_winmm.c        | 456 ++++++++++++++++++++++++++++++++++
 tools/audio/src/flmidi_winmm.h        |  57 +++++
 tools/audio/test/fla_test.c           | 279 ++++++++++++++++++++-
 tools/audio/test/flmidi_test.c        | 269 ++++++++++++++++++++
 tools/audio/test/index_midi.html      |   5 +
 tools/audio/test/index_midiprobe.html |  24 ++
 tools/audio/test/page.mjs             |  60 ++++-
 tools/audio/test/page_midi.mjs        |  82 ++++++
 18 files changed, 2025 insertions(+), 28 deletions(-)
```

`wl/run.mjs`・`wl/fla_wl.c`・`wl/build.sh` は `916fa7a` 以降で変わっていない (`git diff 916fa7a f3680404 -- tools/audio/wl/run.mjs tools/audio/wl/fla_wl.c tools/audio/wl/build.sh` は空)。したがって ring の実行コードが変わったため、旧測定の lag・underrun の値は使わず、上の e2e (`f3680404`) の値に置き換えた。

測定後の差分 (本 REPORT の commit を除く): `git diff 40aa2f8a6 HEAD -- tools/audio ':!tools/audio/wl/REPORT.md' ':!tools/audio/wl/results'` の出力は 0 行 (差分 0。PR コメントに出力を添付)。

旧測定 (参考。本 HEAD の値ではない): `916fa7a` (`bash tools/audio/wl/e2e.sh`, `TMPDIR=$RUNNER_TEMP`) で 32/32 合格・255 s・load 0.23 → 0.23。`fea636d` で 32/32 合格・246 s。これらの lag は現在の値と同じ (wl = B f, ring = 1408/1536/2048 f)。

検証範囲 / 範囲外: 範囲 = fake シンクの headless Chrome・48 kHz・テスト音ミキサ代役・FLEngine PE の静的 import 解析・上流 pin 版 emsdk 6.0.12 での build。**範囲外 = 実 FL ミキサ / 実機 (Windows/mac の実デバイス) の遅延 / Firefox・Safari / 96 kHz / burst が大きい環境での直走行の挙動 / ミキサ到達関数の特定 / 間接 call を解決した到達集合**。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL ミキサでの ring vs 直走行の比較 (本 PoC はテスト音代役) | #194 の「FL ミキサ」比較は未達 → #194 は Refs のまま | #34 (AU-13) にコメント。#34 完了後に本 `wl/run.mjs` の producer を FL に差替えて再実行 |
| 間接 call/jmp の個別の真の目標 (上限の 14,876 箇所は AT 候補で近似)。上限 14,523 関数は閉世界仮定に依存 | 到達集合の区間 (下限 4,433 〜 上限 14,523 関数) が幅広く、ミキサ本体の切り出しに使えない | #194 (親) にコメント。実行時値の採取 (未実施) が前提 |
| 実機の burst (2048〜4096 f) での直走行の挙動と ring の T 伸長との比較 | 実機での差が未測定 (headless の burst 512 f のみ) | #187 (AU-2) にコメント |
| 直走行の予算超過検知 (`rt_ratio` は本ハーネス独自。shim の `clock_jumps` に出ない) | 本番化する場合の監視設計が無い | #190 (AU-6) にコメント |
| 一過性の単発超過 (ring の hiccup 試験と同条件) を直走行に入れた比較 | 直走行の一過性超過耐性が不明 (§3 項目 4)。持続過負荷しか測っていない | #190 (AU-6) にコメント (ring と同条件で実施) |
