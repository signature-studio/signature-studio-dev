# tools/perf REPORT_P7 — ブラウザ別 wasm compile / 上限 / code cache / AudioWorklet 駆動 (PERF-P7 / #165) 【部分達成】

> **正本**: 本ファイル (`tools/perf/REPORT.md` §5 項目 3・5 の付録)。全表は `p7/results/TABLES.md` (自動生成)、生データ `p7/results/p7.jsonl`。
> **Issue #165 は Closes しない (Refs)**。GitHub runner (headless + 仮想ディスプレイ) で測れる範囲だけ測った。**実オーディオデバイス・Safari・Android/モバイル CPU・低負荷の専用機は未測** (§4)。

既知類型との関係: 該当なし (計測のみ。lift・既存 wasm・既存ハーネスは未変更)。
再現: `xvfb-run -a node tools/perf/p7/p7.mjs --full --rounds 3` → `node tools/perf/p7/tables.mjs > tools/perf/p7/results/TABLES.md`。判定ロジックのネガコン: `node tools/perf/p7/p7.mjs --negative`。

## 0. 結論

| 論点 | 結果 (この runner: AMD EPYC 7763 4 vCPU, loadavg 開始時 0.57〜1.29, Chrome 154.0.8037.97 / Firefox 157.0) |
|---|---|
| **headful Chrome (Xvfb) の自動 wasm code cache** | **観測できず**。immutable 配信の同一 URL を 3 回ロード後も `Default/Code Cache/wasm` は `index` / `the-real-index` のみ (headless=new と同一)。headful でも「エントリが作られる」という確証は得られなかった。**ただし Xvfb 上の headful であり、GPU/実ウィンドウ環境ではない** → 実機 headful は未確認のまま |
| **Firefox 157 の wasm 上限** | 関数数 1,000,000 まで OK・1,000,001 で `too many functions`。module サイズ 1 GiB OK・+1 で `module too big`。**Memory は 16 MiB でも 768 MiB でも 400 本 (本測定の上限) まで確保成功** (Chrome は 16 MiB でも 768 MiB でも 125 本確保した後の次で `could not allocate memory`)。Chrome と同じ 1,000,000 関数 / 1 GiB 上限 |
| **Firefox の同期 compile** | メインスレッドで 32 MiB の `new WebAssembly.Module` が **成功** (48 ms)。Chrome の「メイン 8 MB 超 RangeError」は Firefox に無い |
| **Firefox の compile 規模依存** | Worker で compile: 941 KB 43 ms / 32 MiB 57 ms (Chrome 4.6 / 16.2 ms の 3.5〜9×)。**定常実行は同じ wasm で Chrome の約 1.6〜2× 遅い** (mid 594 vs 297 µs/128f、large 969 vs 597 µs; §3 の分解能注意) |
| **AudioWorklet** | Chrome headless / headful (Xvfb): 48 kHz・2 s で `process()` 748 / 753 回 (期待 750)、出力は参照モデルと bit 一致。**headful は最大呼出間隔 14 ms・>10 ms が 3 回** (headless は 0 回) = ホスト揺らぎ込みの 1 回測定で、underrun 判定ではない。**Firefox は AudioContext が `suspended` のまま (`Closed before resume completed`)、process() は 1 回も回らず UNMEASURED** (出力デバイス無し) |
| **Module の transfer** | 全ブラウザで IndexedDB への `WebAssembly.Module` put は `DataCloneError`。`structuredClone(Module)` は 3 構成とも可。**AudioWorklet への `port.postMessage(Module)` は 3 構成とも JS 側で例外にならない。worklet 側では Chrome (headless/headful) が `messageerror` (受信不可・PERF.md §4 と一致)、Firefox 157 (headless) は受信 OK** (§7。runner 上の結果で、実機は未取得) |
| **bit-exact (判定)** | Worker 27 本 (3 構成 × 3 サイズ × 3 反復) と AudioWorklet 2 本 (Chrome) すべて参照モデル `makeRef` と hash 一致。ネガコン: 期待 hash を 1 bit 壊すと 9/9 が FAIL、結果欠落で FAIL (§2) |

## 1. 方法

- 1 ページ = 1 ブラウザ構成を**新規プロファイル**で起動し、結果を `POST /result` でサーバに送る (CDP 不要 = Firefox でも同一ハーネス)。
- wasm は `tools/perf/loader/gen_wasm.mjs` の合成 ws_v1 (ws_buffers / ws_process / ws_reset)。small 64 stages 4.8 KB、mid 500 stages + 30,000 filler 941 KB、large 1000 stages + 90,000 filler + 32 MiB pad (33,554,442 B)。**実 OTT / FLEngine ではない**。
- Worker 内で fetch → compile → instantiate → 初回呼出 → 定常 (small は 3000 block、mid/large は 400 block)。反復ごとに別 salt (末尾 custom section) でエンジン内キャッシュを避ける。
- 構成: `chrome-headless` (`--headless=new`)、`chrome-headful` (`xvfb-run -a`、実ウィンドウ・GPU 無し)、`firefox-headless`。
- code cache: `Cache-Control: public, max-age=31536000, immutable` の同一 URL を `location.href` 遷移で 3 回ロード (各 2.5 s 待機) し、終了後の `Code Cache/wasm` (Chrome) / `cache2` (Firefox) を列挙。
- 上限: 関数 1,000,000 / +1、Memory 本数 (16 MiB / 768 MiB を ≤400 本)、module 1 GiB / +1 (`--full`)。AudioWorklet 実験は Memory 上限実験より**前**に実施 (後だと残存 Memory で worklet 内 instantiate が OOM する。初回実装で踏んだ)。

## 2. 検証 (コミット済み HEAD での実測)

| 項目 | 結果 |
|---|---|
| ネガコン `node tools/perf/p7/p7.mjs --negative` | 正しい出力で FAIL 0・PASS 9 / 期待 hash を 1 bit 破壊で FAIL 9/9 / `done` 無しで FAIL 10 → exit 0 |
| 本測定 `xvfb-run -a node tools/perf/p7/p7.mjs --full --rounds 3` (採取コミット前の作業ツリー) | wall 105.9 s (chrome-headless 25.2 s / chrome-headful 22.2 s / firefox-headless 45.5 s)、`summary: PASS=29 FAIL=0 SKIP=0 UNMEASURED=1` (UNMEASURED = Firefox worklet)、exit 0 |
| コミット済み HEAD `0589b42` での再実行 (同コマンド) | wall 104.1 s (24.1 / 21.9 / 45.4 s)、`PASS=29 FAIL=0 SKIP=0 UNMEASURED=1`、exit 0。ネガコン再実行も exit 0。数値表 (`TABLES.md`) は初回の採取 (本測定行) のもの |

判定は **FAIL を 1 件でも出したら exit 1** (hash 不一致・done 未到達・ブラウザ異常終了・タイムアウト)。測れなかった項目は PASS に数えず `UNMEASURED` / `SKIP` として明示行を出す (`--require-worklet` で worklet 不通を FAIL に昇格できる)。

## 3. 数値の読み方・限界

- **非 cross-origin-isolated** (`crossOriginIsolated=false`): `performance.now` の分解能は Chrome 100 µs / **Firefox 1 ms (丸め)**。定常 µs は 32 block の区間平均 (Firefox の分解能誤差 ±31 µs)、Firefox の初回呼出 `1.00 ms` は丸めで、初回 stall の比較には使えない。Firefox の compile ms (43/57) も 1 ms 刻みで、mid/large の「3.5〜9×」は桁の目安。
- 初回の chrome-headless round0 compileStreaming が 202 ms で他 2 構成 (11 ms 前後) より遅い。原因未調査 (code cache は無いので、ブラウザ起動直後のコールドスタートと推定)。code cache の有無の結論はこの数値でなく**ディレクトリ列挙**による。
- runner は共有 VM (EPYC 7763 4 vCPU)。PERF.md の Zen5 16C と CPU が違うため**絶対値の直接比較は不可**。ブラウザ間の相対比は同一 run 内。

## 4. 未達・未解決 (起票依頼)

| 項目 | 理由 | 次 |
|---|---|---|
| **実オーディオデバイスでの underrun 評価** | runner は null sink。Firefox は出力デバイス無しで AudioContext が suspended | ユーザ実機が必要 (`xvfb-run` 無しの headful で `p7.mjs` をそのまま実行し `--require-worklet` を付ける)。**起票依頼: `[PERF-P7b]` 実機 (Windows/macOS) 採取** |
| **Safari (WebKit)** | Linux runner に無い | 起票依頼: `[PERF-P7c]` macOS 実機。`p7.mjs` は Chrome/Firefox 以外の起動を未実装 (URL を開くだけで動くので `?cfg=safari` 手動オープンで可) |
| **Android / モバイル CPU (3〜10× 低速想定)** | 実機無し | `[PERF-P7d]` Android Chrome 実機 (`chrome://inspect` かページ手動オープン)。手順は §6 |
| headful (実ウィンドウ・GPU 有) の wasm code cache | Xvfb 上では観測できず (§0)。実機の headful で違うかは不明 | 上の実機採取に含める |
| worklet 内 `postMessage(Module)` の受信・`messageerror` の実機採取 (#948 受入条件 3 の残り) | ハーネス拡張は済み (§7)。runner (Linux) では Chrome = messageerror・Firefox 157 = 受信 OK | 実機 (Windows/macOS) で `p7.mjs` を実行し worklet の `modRecv` / `msgerr` を採取 |
| Firefox 上限: Memory 400 本超 | CAP を 400 にしたため上限未到達 | 実機でも必要なら CAP を上げる (RSS 0 の仮想予約のみ) |
| compilationHints の機序・低負荷専用機での再測 | 本 run は共有 VM | 既存 REPORT §5.3 に残置 |

## 5. Safari (macOS 実機) の手動採取手順 ([PERF-P7c] #949)

runner (Linux) では Safari を起動できないため、macOS 実機で以下を行う。`p7.mjs` の自動起動は使わない。

1. macOS の端末で repo を checkout し、リポジトリ直下で次を実行する (Node 必要。サーバは 127.0.0.1 のみで待つ)。
   ```sh
   mkdir -p work && node --input-type=module -e "import fs from 'node:fs'; import {startServer} from './tools/perf/p7/server.mjs'; const s = await startServer(); console.log(s.url + '/p7.html?cfg=safari&rounds=3'); setInterval(() => fs.writeFileSync('work/p7_safari.json', JSON.stringify(s.results, null, 1)), 3000);"
   ```
   `work/` は `.gitignore` 対象 (`**/work/`) で checkout に含まれないため、`mkdir -p work` を先に実行する。
   表示された URL (`http://127.0.0.1:<port>/p7.html?cfg=safari&rounds=3`) を **Safari で開く**。
2. ページは round 0 の全実験を行った後、同一 URL を 2 回再ロードする (wasm code cache の観測)。`work/p7_safari.json` の `done` キーが出るまで待つ (目安は端末依存。`done` が出なければ失敗)。
   書き出しは 3 秒おきの interval なので、`done` が出ても直後のファイルには含まれないことがある。**`done` が出てから 3 秒以上待ってから** `work/p7_safari.json` を確認し、`done` キーが含まれることを確かめる。
3. `work/p7_safari.json` を `tools/perf/p7/results/` に移し、上限・lazy compile・Memory 本数の数値を §0 と同じ表形式で本ファイルに追記する。
4. 検証: Safari 上で `done` が届かない場合は、Safari の開発メニュー → コンソールのエラーを記録する。

確認済み (runner, 26ce4469): `work/` を削除した状態から `mkdir -p work` → one-liner 起動 → `POST /result?cfg=safari&key=done` 200 → 3.5 秒待機後に `work/p7_safari.json` を読み、`{"safari":{"done":{"ok":true}}}` が含まれることを確認 (rc=0)。`p7.html` 200・`/wasm?c=mid` 200 (941,572 B) も確認済み。Safari 本体の挙動は未確認 (runner では Safari を起動できない)。

## 6. Android Chrome 実機の手動採取手順 ([PERF-P7d] #950)

runner では Android 実機を使えないため、実機担当者が以下を行う。結果は未取得 (本ファイルに実測値は無い)。`p7.mjs` の自動起動は使わない (Safari 節 §5 と同じ方式)。

1. PC (Linux / macOS。adb が使えること) で repo を checkout し、リポジトリ直下で次を実行する (Node 必要。サーバは 127.0.0.1 のみで待つ)。
   ```sh
   mkdir -p work && node --input-type=module -e "import fs from 'node:fs'; import {startServer} from './tools/perf/p7/server.mjs'; const s = await startServer(); console.log(s.url + '/p7.html?cfg=android&rounds=3'); setInterval(() => fs.writeFileSync('work/p7_android.json', JSON.stringify(s.results, null, 1)), 3000);"
   ```
   表示された URL のポート番号 (`<port>`) を控える。
2. USB 接続の Android 端末に対して `adb reverse tcp:<port> tcp:<port>` を実行し、端末の 127.0.0.1 から PC のサーバへ届くようにする。端末の Chrome で `http://127.0.0.1:<port>/p7.html?cfg=android&rounds=3` を開く。ページは round 0 の全実験を行い、同一 URL を 2 回再ロードする (wasm code cache の観測)。
3. PC 側で `work/p7_android.json` の `done` キーが出るまで待つ。`done` が出てから 3 秒以上待ってから同ファイルを確認する (書き出しは 3 秒おきの interval)。
4. `work/p7_android.json` を `tools/perf/p7/results/` に移し、compile 時間・定常実行・AudioWorklet の `process()` 間隔 (underrun 判定) を §0 と同じ表形式で本ファイルに追記する。端末名・Chrome バージョン・CPU・メモリを併記する。
5. 検証: `done` が届かない場合は、Android Chrome の `chrome://inspect` からコンソールのエラーを記録する。

## 7. worklet 内 `postMessage(Module)` の受信・`messageerror` の記録 (#948 受入条件 3)

- ハーネス: `web/worklet.js` は `mod` 受信時に `modRecv {isModule}` を返し、`port.onmessageerror` で `msgerr` を返す。`web/p7.html` は `worklet.modRecv` / `worklet.msgerr` に記録する。判定 (`p7.mjs`): 受信 = PASS (Module でなければ FAIL)、`messageerror` = INFO (判定外の記録で exit は変えない)、どちらも無い = UNMEASURED (`--require-worklet` で FAIL)。
- 測定 commit: `6edc5ada` (コードを変えた最後の commit)。再現: `xvfb-run -a node tools/perf/p7/p7.mjs --rounds 3 --out <tmp>`。判定区分を INFO に変える前の同コードの実行は、`messageerror` を FAIL として数えたため rc=1 だった (観測値は同じ)。区分変更後に再測定し rc=0。

| 構成 | ブラウザ | wall | loadavg (開始時) | worklet `process()` | worklet 内の `postMessage(Module)` |
|---|---|---|---|---|---|
| chrome-headless | Chrome 154.0.8037.97 | 18.7 s | 0.44 | 748 回 (期待 750)・最大間隔 10 ms・>10 ms 0 回。出力は参照と bit 一致 | 受信なし・`messageerror` 発火 |
| chrome-headful (Xvfb) | 同 | 15.9 s | 0.82 | 748 回・最大間隔 14 ms・>10 ms 9 回。bit 一致 | 受信なし・`messageerror` 発火 |
| firefox-headless | Firefox 157.0 | 34.7 s | 1.21 | UNMEASURED (AudioContext `suspended`・結果なし) | **受信 OK (`isModule=true`)**。worklet 内の bytes compile は 10 ms で成功 |

- `summary: PASS=30 FAIL=0 SKIP=0 UNMEASURED=1 INFO=2` → exit 0。UNMEASURED は Firefox の worklet `process()` (§0 と同じ)。INFO は Chrome 2 構成の `messageerror`。
- ネガコン `--negative` は exit 0 (正しい出力 PASS 9 / 1 bit 破壊 FAIL 9/9 / 結果欠落 FAIL 10)。
- Firefox では AudioContext が `suspended` のままでも Module の受信は成立した (受信と `process()` 実行は別)。実機で同じかは未確認。
- **未了 (実機)**: Windows/macOS の実機で `xvfb-run` 無しの headful Chrome/Firefox を `p7.mjs --require-worklet` で実行し、受信・`messageerror`・underrun・code cache を採取する。runner で確認したのは受信・`messageerror` の経路と記録まで。
