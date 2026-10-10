# REPORT — CAB-102 user32 ポンプ shim (C) + tools/runtime RING ABI (worker_pump) 結線

日付: 2026-10-10 / 書込範囲: `tools/startup/pump/`(新規) のみ。`tools/startup/winstubs/` `tools/shimx/` `src/` `tools/gui/` `tools/runtime/` は改変 0 行 (読取のみ)。
再現: **`bash tools/startup/pump/pump.sh`** (exit 0 = 全 PASS。build → リンク置換 → C 単体 → ST(HOSTED) → MT(ATOMIC/SPIN/NONE/stress/ctrl) → headless Chrome を 1 コマンド直列実行)。

## 0. 結論 (数値は全て実測)

1. **winstubs (CAB-96) の weak ポンプ 10 本を強定義で置換し、`src/runtime/worker_pump.ts` の RING ABI に載せた**。リンクテスト: duplicate symbol **0**、weak 対照では `GetMessageW(空)=0`(=WM_QUIT 扱いでループ即終了) だったのが強定義では HOSTED の **-1** に変化 (置換の行動面証拠)。`GetProcAddress("user32.dll","GetMessageW")` も強定義へ解決 (単体 T48)。C 単体 **48 ケース ALL PASS** (node ランナ合計 54 checks)。
2. **実 FL 起動に必須のブロッキング GetMessage を実装**。MT ビルドでは C が `memory.atomic.wait32` で直接ブロックし、タイマ満期を futex タイムアウトに畳み込む (worker_pump.ts `MessagePump.waitForMessage` と同一方式)。
3. **レイテンシは D 検収 (JS MessagePump, p50 0.01ms) と同等**: headless Chrome (同一環境・同一拓扑: main が producer, Worker の C が consumer) で **p50 0.015ms / p90 0.040ms / p99 0.110ms / max 0.565ms** (n=301)。node (worker_threads) でも p50 ≈ 0.02ms (時計較正残差 jitter で ±0.02ms の負値を含む) / p99 0.032ms。
4. **2000 件ストレスで欠落 0**: 受信 2000/2000、ring dropped **0**、producer 通し番号の単調性で順序保存も検証。押し戻し (ring 満杯) は 0 (producer 側 1ms バックオフ再試行で吸収)。
5. **AudioWorklet 内では待たない** (D 検収の設計を C 側に実装): `PUMP_WAIT_NONE` モードで GetMessage/Peek は即帰り (e2e で 1 呼出 max **0.285ms** — 実質ブロック無し)。2000 件を poll 掬いで受信 2000/2000。
6. **「C がリングに要求を書き、ホスト (JS) が排水して戻す」経路** (ctrl 要求応答リング) を実装し、応答待ち戦略別の RTT を実測: ATOMIC p50 **1156µs** (ホスト排水の setTimeout 粒度支配) / SPIN p50 **0.73µs**。
7. ブロッキング wait の扱い (要件 2) は **5 戦略**で実装・計測: ATOMIC (futex 直接, 本命) / SLICE (futex 分割) / SPIN (ビジー) / HOSTED (C は待たず待ち時間ヒント `pump_wait_ms()` を返してホストに返す) / NONE (worklet)。
8. **時計較正の落し穴を検出・修正**: ctrl 経由較正は応答 RTT/2 (~1.6ms) の偏りを出し、Chrome e2e の見かけの p50 が 2ms に膨らんだ。page 駆動 ping-pong 較正 (誤差 ~0.1ms) / node 同スレッド直接差 (誤差 ~0) を追加し解消。**較正方式の選択は実測レイテンシを 130 倍変える** (§2.6)。

## 1. 成果物

| 区分 | パス |
|---|---|
| ABI ヘッダ | `src/pump_abi.h` (RING レイアウト / Win64 MSG 48B / 待機モード / 統計 / pop ログ) |
| C 実装 | `src/pump_ring.c` (Vyukov MPSC), `src/pump_win.c` (強定義 15+Ex / 取り出し中核), `src/pump_timer.c`, `src/pump_wait.c`, `src/pump_ctrl.c`, `src/pump_stats.c`, `src/pump_host.c` (ホスト結線 export) |
| 内部/API ヘッダ | `src/pump_internal.h`, `src/pump_api.h` (テスト用プロトタイプ) |
| テスト | `test/pump_unit.c` (48 ケース), `test/pump_e2e.c` (e2e ドライバ export), `test/weakprobe.c` (置換前対照) |
| ホスト側 | `host/run_e2e.mjs` (node e2e), `host/run_chrome.mjs` (headless Chrome e2e), `host/producer_worker.mjs` (**worker_pump.ts の PumpRing 実物**で push), `host/responder_worker.mjs` / `responder_browser.mjs` (ctrl 排水) |
| ビルド | `scripts/build.sh` (**本 dir 専用 `work/`** に shimx/winstubs を別 prefix ビルド — winstubs.sh の work/ は共有しない), `pump.sh` (1 コマンド検収) |

## 2. 設計

### 2.1 RING ABI — `worker_pump.ts` `RING` との同一レイアウト
- ヘッダ 16×i32 (64B): `enq, deq, wake(futex), **magic**, capacity, dropped`。`[3]` は TS 未使用 → マジック `0x50554D50`("PUMP") を置き、ホストが構築前に C 側初期化を検査できる。スロット 16×i32 (64B) × capacity 1024: `seq, message, hwnd(lo,hi), wParam(lo,hi), lParam(lo,hi), time, pt.x, pt.y, tPost(f64@+48B)`。
- 配置は **C 側静的領域 (共有 wasm メモリ内, 64B アライン)**。`pump_ring_addr()` をホストに渡し、`new PumpRing(memory.buffer, addr)` (init=false, capacity はヘッダから) で JS producer が push する。初期化 (seq/capacity/magic) は C の constructor (`__wasm_call_ctors`) が行い、二重初期化は magic でガード。
- producer は複数可 (JS 任意スレッド + C の PostMessage)。consumer は単一 (wasm UI スレッド)。
- **producer 実装は runtime の正本を使って検証**: e2e の producer は `src/runtime/worker_pump.ts` をリポジトリの tsc (7.0.2) でトランスパイルした `PumpRing.push` そのもの (node は型削除がパラメータプロパティ非対応のためトランスパイルが必要 — 実行時に条件分岐する凝った実装は避け tsc 直を使う)。

### 2.2 Win64 MSG (48B) と取り出し優先順
- `WMSG`: `hwnd(+0, 8B), message(+8), wParam(+16), lParam(+24), time(+32), pt(+36..44)` の **Win64 レイアウトを wasm32 でも維持** (RT-1 の「Win64 MSG 48B レイアウトに変換」)。wasm32 の `void*` は 4B ため、`hwnd` は明示 `uint64_t` (実装初期に 4B ポインタで書いてレイアウトが 1 語ずれた経験 → 修正済・単体 T01/T07 で担保)。
- 取り出し優先順は `worker_pump.ts MessagePump.take` と同一: **held(Peek NOREMOVE) → フィルタ stash → ring(投稿) → WM_QUIT → WM_PAINT → WM_TIMER**。
- フィルタ (hwnd / msg 範囲) は **stash 方式**: 範囲外の先頭メッセージを退避し (最大 64)、後続の無フィルタ取得で先出しする (Win32 のフィルタ意味論の ring 上での実現。単体 T16〜T19)。
- `PostQuitMessage` は **1 回だけ** WM_QUIT を返しフラグを消す (Win32 準拠。TS `MessagePump` は quitCode を保持して繰り返す — 意図的な差分、REPORT 既記載の gui 実装と同じ挙動)。
- `DispatchMessageW`: WM_TIMER + lParam(TIMERPROC) は直接呼出、それ以外は `pump_set_wndproc(hwnd,proc)` 登録済 wndproc を呼ぶ (boot 経路用の結線入口。未登録は fail-soft 0 + 統計 `wndproc_miss`)。

### 2.3 待機モード (5 種, `pump_set_wait_mode`)
| モード | 振る舞い | 用途 / 実測 |
|---|---|---|
| `ATOMIC` (0) | `memory.atomic.wait32(wake語, 期待値, min(次タイマ満期, wait_cap))` | 本命 (MT)。タイマ満期を futex タイムアウトに畳み込み。e2e: waits_atomic 326 回 / Chrome p50 0.015ms |
| `SLICE` (1) | 同 futex を `slice_ms` (既定 5ms) 刻み | 長時間待ちの分割・保守フォールバック |
| `SPIN` (2) | wake 語ビジー比較 | 極短待ち。CPU 消費と引き換え (e2e: waits_spin 241, p99 0.19ms) |
| `HOSTED` (3) | **ブロックしない**。空なら -1 を返し、`pump_wait_ms()` (次タイマ満期ヒント) をホストが使って寝て再入場 (`pump_step` プロトコル) | ST ビルド。e2e: 500/500 受信, hosted_empty 555 (C は 1 度もブロックせず), p50 0.151ms |
| `NONE` (4) | 決して待たない (空は即 -1 / FALSE) | **AudioWorklet** (Atomics.wait 不可)。e2e: poll 1 呼出 max 0.285ms, 2000/2000 受信 |

- 既定モード: MT ビルド=ATOMIC / ST=HOSTED (`pump_default_wait_mode`)。未設定 (-1) の場合も実効モードへ解決する (`pump_eff_wait_mode`)。
- GetMessage 内部待機には安全弁 `wait_cap_ms` (既定 1000ms) — チャンク刻みで再チェックし、無限待ちの暴走をテスト可能にする。本番は cap を十分大きく取れば Win32 同等の INFINITE 挙動。

### 2.4 タイマ (C 側テーブル, 128 件)
- `SetTimer`: id=0 は自動採番、同一 (hwnd,id) は満期リセット、ms<1 は 1 にクランプ。`KillTimer`: 見つからなければ FALSE。
- WM_TIMER はキューに溜めずポンプ時に合成 (Win32 同様・低優先・合流)。遅延時は 1 周期に丸める (`due = max(due+interval, now)` — TS と同一)。TIMERPROC 付きは `DispatchMessageW` が直接呼ぶ。
- e2e 実測: 10ms 間隔タイマが MT で 32 回発火、**タイマ遅延 (t_pop − due) p50 = 0.033ms** (pop ログの t_post に期待時刻を記録して計測)。

### 2.5 ctrl 要求応答リング (C→host の「要求を書き、ホストが排水して戻す」)
- 要求リング 16 スロット (32B: `seq, op, a0, a1, req_id, t_req(f64)`) はヘッダ+スロット**連続配置** (ホスト JS が `reqAddr+16語` をスロット先頭として排水)。Vyukov 型で C が push、ホストが排水。応答は 1 深度メールボックス (32B: `seq, req_id, ret(f64), t_resp(f64)`) + req_id 照合、in-flight は 1 件のみ。
- ops: `EPOCH_NOW=2` (ホスト実時刻 — 較正用), `ECHO=3`。将来のホストサービス (VFS sync-RPC 等, runtime DESIGN §2.5) の入口。
- 応答待ち戦略は pump_wait_mode に従う。HOSTED/NONE ではブロックせず -1 (pending) を返し、**後続の `pump_step` / take 時に `pctrl_service_done()` が非同期完了させる** (ST e2e で ECHO 0xBEEF の非同期完了を実証)。
- タイムアウト既定 1000ms (`pump_set_ctrl_timeout_ms`)。RTT ログ 512 件 (`pump_ctrl_rtt`)。
- 実測 RTT (node MT, ホスト排水 0.5ms 周期): ATOMIC p50 **1156µs** (排水粒度支配 — 待ち戦略ではなくホスト側の周期) / SPIN p50 **0.73µs** (応答が既に棚にあった場合の下限)。

### 2.6 時計較正 (実測レイテンシを 130 倍変えた要点)
- C 内部クロックは `emscripten_get_now()` (shimx と同一)。node ではプロセス相対、ブラウザ Worker では文脈相対 → producer の `tPost` (epoch 基準) との差 = オフセットを較正して pop ログに適用する。
- **ctrl 経由較正** (`pump_calibrate`, EPOCH_NOW の往復中点): 応答経路の排水粒度分 (~RTT/2) の偏りを持つ。実測: Chrome で offset 誤差 **1.64ms** → e2e の p50 が見かけ上 **1.96ms** に膨らんだ (実体は時計誤差)。
- **修正**: (a) node — C モジュールが main スレッドなので `performance.timeOrigin+now − pump_now_raw()` の直接差で誤差 ~0; (b) Chrome — page 駆動 ping-pong (page epoch の往復中点と C 生クロックの中点を突合, 誤差 ~0.1ms) で `pump_set_clock_offset` を設定。結果: Chrome p50 **0.015ms**。
- 教訓: **クロススレッド遅延計測では較正方式自体を e2e で検証すること** (本 REPORT の e2e は `offsetVsRawReady` を常時出力する)。Chrome の Worker `performance.timeOrigin` は page と ~52ms+ ずれるが、`timeOrigin+now` の epoch 値は文脈間で ~0.4ms 以内に揃う (実測 §clock_skew)。

## 3. e2e 実測サマリ (`bash tools/startup/pump/pump.sh`, 全 PASS)

| 項目 | 実測 |
|---|---|
| (a) リンク置換 | duplicate symbol **0** (winstubs weak × pump 強定義, ST/MT)。weak 対照 `GetMessageW(空)=0` → 強定義 `-1`。GetProcAddress=強定義 (T48)。C 単体 48 ケース (node 計 54 checks) |
| (b) ポンプ疎通 (MT ATOMIC) | 301 件受信 / ring dropped **0** / WM_TIMER **32** 回発火 (10ms 間隔, 遅延 p50 0.033ms) / 実ブロッキング wait **326** 回 |
| (c) レイテンシ (tPost→pop) | **node MT: p50 ≈0.02ms / p99 0.032ms** (較正残差で ±0.02ms) ・ **headless Chrome: p50 0.015ms / p90 0.040ms / p99 0.110ms / max 0.565ms** — D 検収 p50 0.01ms と同等 (同一環境・同一拓扑) |
| (c') 待機戦略比較 | SPIN p50 ≈0.01ms (p99 0.19) / HOSTED (ST) p50 0.151ms / NONE poll 1 呼出 max 0.285ms。SPIN は CPU 連れ回し (waits_spin 241 チャンク) と引き換え |
| (d) 2000 件ストレス | 受信 **2000/2000**、順序 (producer 通し番号) 単調 **OK**、ring dropped **0** (producer 押し戻し再試行 0 回発露) |
| NONE (worklet 相当) | 2000/2000 受信、poll 呼出 max 0.285ms (ブロック無しの証拠)、ring 満杯 134 回は producer 押し戻しで吸収 (実欠落 0) |
| ctrl 要求応答 | 50/50 成功 (ATOMIC)。RTT: ATOMIC p50 1156µs / SPIN p50 0.73µs |
| ST (HOSTED) 疎通 | 500/500 受信、WM_TIMER 105 回、dropped 0、hosted_empty 555 (C は待たずホストに返す)、p50 0.151ms / p99 2.21ms |

## 4. 構成 (composition) — winstubs / gui との関係
- 本 TU は **winstubs (CAB-96) の weak ポンプ 10 本を同一シグネチャの強定義で置換する別 TU**。wasm リンクは署名一致を要求するため、シグネチャは ws_ui.c の weak 定義と 1 ビットも変えていない (`MsgWaitForMultipleObjects(Ex)` は shimx wait.c の weak も置換 — shimx の kernel-object 待機は `WaitForMultipleObjects`(shimx 強定義) にスライス委譲して横取りする)。
- **tools/gui (CAB-8/159) は別構成**: gui は `gui_adapt_w32.c` が公開名の強定義を持つため、pump TU と gui_adapt を同時リンクすると duplicate strong symbol になる。**gui をリンクする構成では本 TU を外す** (gui 独立のメッセージキューを持つ)。RING ABI への gui 側結線は次タスク (§7-3)。
- 呼出カウントは winstubs REPORT §4 の指示どおり **`g_ws.pump_calls` を踏襲** (weak extern 参照 — winstubs が無いリンクでは NULL スキップで単独リンク可)。winstubs の `ws_register_procs` が `(void*)GetMessageW` 等を GetProcAddress に登録するため、動的束縛 (Delphi) も自動で強定義へ解決される (T48 で実証)。

## 5. 制限
1. **WM_CHAR 合成は未実装** (`TranslateMessage` は KEYDOWN..SYSKEYUP の範囲判定のみ — TS/gui と同一挙動)。キーレイアウト合成は入力経路 (RT-3) と一体で次タスク。
2. `SendMessageW` / `DispatchMessageW` は wndproc 登録 (`pump_set_wndproc`) が無いと fail-soft で 0 を返す。FL の RegisterClass 経路 (m11 boot glue) での登録が次タスク。
3. `PostThreadMessageW` は tid を無視し UI スレッド (wasm UI スレッド) 1 本のキューへ投稿 (gui 実装と同一近似)。
4. フィルタ stash は 64 件。溢れた場合はフィルタ無視で先頭を返す (fail-soft, 統計 `stash_overflow`)。FL 実機のフィルタ使用パターンでの校正は未実施。
5. 較正: ctrl 経由 (`pump_calibrate`) は単体で使うと ~RTT/2 の誤差。**組込み時はホスト主導の直接差 (同スレッド) か ping-pong を使うこと** (§2.6)。e2e は両方を実装済み。
6. `e2e_wait_bench` 等 `test/pump_e2e.c` の export は検証ドライバ用 (製品リンクには不要 — リンク対象から外せば残らない)。
7. 実 FL lift コード (m11 boot closure) からの呼出は未結線 (winstubs 罌の置換と結線検証まで)。実機ブラウザでの FL 起動観察は未実施。
8. レイテンシ計測は共有 VM (load 9〜12) 実測。node と Chrome で数値の意味が異なる (node=同一プロセス時計, Chrome=page 較正) — 比較は Chrome vs D 検収で行うこと。

## 6. shimx への要求 / ユーザ依頼事項
- **shimx への要求: なし** (既存 API の範囲で足りた。`WaitForMultipleObjects` 強定義への委譲のみ使用)。
- ユーザ依頼事項: なし (ブロッカーなし)。

## 7. 次タスク提案 (下流)
1. **m11 boot closure への結線** (最重要): `m11_genstubs.py` の「別 TU 定義済み除外リスト」に pump 由来 15+Ex API を追加し、boot glue で `winstubs_init(0)` + `pump_ring_addr()` → `PumpRing` 結線 + 時計較正 (§2.6 の直接差/ping-pong) を行う。実 FL の `GetMessageW` ループが RING ABI で回る状態を作る。
2. **入力プロデューサ実装 (RT-3 と合流)**: GUI worker / main の DOM イベント → `PumpRing.push` (mouse move coalesce は producer 側責務) + `WM_CHAR` 合成 (`TranslateMessage` 実装)。
3. **gui 経路との統合方針決定**: tools/gui のメッセージキューを RING ABI に載せる (gui_impl_GetMessageW を ring 消費に差し替え) か、gui/pump の別構成をリンク構成で切り替えるか。CAB-159 担当と要調整。
4. **AudioWorklet 側の生産者結線 (RT-4 と合流)**: worklet から `PostMessageW` (NONE モードの C producer として ring へ push) — 音声スレッド → UI スレッド通知の本体経路。
5. **WM_TIMER 系の拡張確認**: `timeSetEvent`/`timeKillEvent` (winmm) との整合、高頻度タイマ (FL の UI 描画タイマ) での合成コスト実測。
6. **実 FL 起動観察でのフィルタ校正**: PeekMessage フィルタ (WM_KEYFIRST..WM_KEYLAST 等) の使用頻度と stash 必要サイズを確定 (現状 64)。
