# tools/runtime/rt10/REPORT.md — RT-10 (#128): 実 FLEngine lift の起動時間・tier-up・soak 計測

既知類型との関係 (docs/DEFECTS.md): **該当なし** (lift ロジックは無改変。既存 x64c `tools/flelift/boot/` の成果物を再生成して計測しただけ)。
検証起点: main `bfccd23` (本 PR の commit は計測ハーネス `tools/runtime/rt10/` の追加と REPORT のみ)。環境: GitHub Actions runner
(AMD EPYC 7763, 4 vCPU, RAM 16GB + swap 3GB + 追加 24GB), Chrome 154.0.8037.97 headless (GPU なし), node v22.23.3, emcc 6.0.12。
素材: `oc_artifacts: fl-win64 toolchain-emsdk`。数値はすべて実測。範囲指定は n≥3 の min–max (med = 中央値)、load は各回開始時の 1 分 load average。

## 0. 結論 (先出し)

1. **実 FLEngine lift (x64c boot 連鎖, closure 2) は wasm 126,995,440 B** (code section 106,525,508 B / data 20,432,171 B / 定義関数 31,684 /
   import 32 / export 58)。合成 (M11×K, ≤52 MiB) ではなく**実物の 100MiB 級**が初めて得られた。brotli q11 (lgwin 24) で **16,196,755 B = 7.84×**
   (従来の M11 実測 3.31× は RetDec 経路 6.0 MB の値。x64c -O0 は冗長なため圧縮が効く)。gzip -9 は 34,595,917 B (3.67×)、zstd -19 は 17,186,585 B (7.39×)。
2. **Chrome Worker での download→compile→instantiate→boot (unit 209 まで) は cold で合計 1,022–1,096 ms** (localhost・br 配信・既定 flags・n=3):
   fetch+compileStreaming 489–541 ms / instantiate 11.9–13.6 ms / boot 呼出 484–545 ms。boot は node 参照と**同一結果** (units_run 209/942, GetMem 1,890 / FreeMem 776, 停止 `unlifted:0x6a7b70`)。
3. **ダウンロードが支配的になるのは 123.5 Mbps 以下** (算術: br 後 16,196,755 B×8 を §5 の 1 Gbps 総時間中央値 1.049 s で割った値)。サーバ側で br 圧縮後 16.2 MB を帯域制限した実測の総時間:
   10 Mbps 13.8–13.9 s / 50 Mbps 3.38–3.39 s / 100 Mbps 1.84–1.86 s / 1 Gbps 1.03–1.09 s (§5)。1 Gbps では compile+boot が総時間の大半。
4. **compile は線形外挿どおり**: bytes→`WebAssembly.compile` 212–220 ms (= 1.75–1.82 ms/MiB wasm, 2.09–2.17 ms/MiB code)。M11 合成の 1.5 ms/MiB を 121.1 MiB に外挿した値 (推定) 181.7 ms に対し +17–21%。
   一方 **eager (`--no-wasm-lazy-compilation`) は 4,118–4,140 ms** で、PERF-P6 の事前見積り (1.2 s, 推定) の 3.4 倍。code が見積り 38.7 MB の 2.75 倍 (106.5 MB) だったため (§7)。
5. **tier-up**: 同一 Module から 6 instance を連続 boot すると boot 呼出は 515–558 → 106–108 → 105–123 → 57–86 → 61–66 → 64–67 ms。初回 (中央値 520 ms) の 79% (→ 108 ms) は lazy compile (初回呼出時の関数コンパイル)、残りが Liftoff→TurboFan (§6)。
6. **soak (boot ループ代替)**: instance 作成→boot→破棄を 540 s 回して **8,726 cycle**、boot 中央値は全 90 s 区間で 54 ms 不変、renderer RSS 462–684 MB で**単調増加なし**、unit 209 の結果は全 cycle 同一 (180 s 版 2,913 cycle も同傾向)。実 FL の soak ではない (§8)。
7. **測れなかったもの**: 「初回フレーム総時間」と「実 FL の長時間 soak」。boot が InitUnits の unit 209/942 で止まり (上流 `f_653f40` の早期 return, #253)、GUI 初期化・初回描画に届かないため。理由と起票先は §9。

## 1. 依頼と到達状況 (測れた範囲 / 測れない範囲)

| 項目 | 状態 | 備考 |
|---|---|---|
| 実 FLEngine lift の wasm サイズ・圧縮率 | **測定済** | §2 |
| download→compile→instantiate | **測定済** (localhost + 帯域制限) | §3–§5。実 R2/CDN は未測 (§9) |
| boot 実行 (unit 209 まで) の所要 | **測定済** | 「初回フレーム」の代替には**ならない** (下記) |
| tier-up 影響 | **測定済** (boot コードに限る) | §6 |
| 長時間 soak (メモリ増加/GC/tier-up) | **代替指標のみ** | boot ループ。実 FL の main ループ soak は不可 (§8, §9) |
| 初回フレームまでの総時間 | **測れない** | unit 209 停止、GUI 未到達 (§9-1) |
| m11 経路 (RetDec) の `reached_stage 4/6` | 参照のみ | 本計測は x64c boot 経路。両者は別指標 (下記) |

- 現状確認: `tools/m11/trap_triage/REPORT.md` = m11 (RetDec) 経路は `reached_stage 4/6`, units_run 17 (unit#18 OOB 解消後も不変)。`tools/flelift/boot/REPORT.md` = x64c 経路は InitUnits の **unit 209/942 まで進行**、停止は `unlifted 0x6a7b70`
  (真因は `f_653f40` が VCL リソース読出し失敗で早期 return し fill callback `0x15F34A0` 未登録, #253)。今回の Chrome 実行も同じ `units_run 209 / threw unlifted:0x6a7b70` で、再現性を確認した。
- 本書の `stage` (= `fle_boot_stage()` の値 1) は x64c boot ドライバ内の内部カウンタで、m11 の `reached_stage N/6` とは別指標。比較しない。

## 2. 実 FLEngine lift の build とサイズ

再現: `bash tools/runtime/rt10/build_fle_boot.sh` (= `boot_e2e.sh` の phase 1–3 と同一手順 + `build.sh plain` + Chrome 用 web/ESM 再 link)。

| 工程 | 実測 |
|---|---|
| x64c lift (closure 2) | **412.8 s** (swap 逼迫時。boot REPORT §9 の 227 s より遅い)。関数 29,907 / 命令 1,557,882 / unlifted callees 1,681 (boot REPORT と一致) / import 680 / x87・rcpps の fail-fast 未対応 site 766 (`lift_meta.json` `unsup_sites`) |
| data gen + imp bridge + shimx obj | 7.3 s + 13.4 s + 4.2 s |
| `build.sh plain` (clang -O0 + node 用 link) | **535.7 s** (RSS 観測値: x64c python 14,668,064 KiB, clang 13.15 GiB。swap 24GB を追加しないと RAM 16GB では危険) |
| web/ESM 再 link (`-sENVIRONMENT=web,worker -sEXPORT_ES6`) | 1.25 s。node 版と **wasm の sha256 が同一** (`225f6320…cd782`) |
| 全体 | 981.4 s (16.4 分) |

注: wasm は 126,995,440 B で、boot REPORT §9 の記録 126,995,230 B と **210 B 差** (原因未特定。capstone/Python の環境差が候補, 推定)。boot の実行結果 (209 / 1,890 / 776) は一致。

| 計測 | 値 (単位・分母) |
|---|---|
| wasm 全体 | 126,995,440 B (121.1 MiB) |
| code section (10) | 106,525,508 B (101.6 MiB)。定義関数 31,684 → 平均 3,362 B/関数 |
| data section (11) | 20,432,171 B (.text 窓 #embed 16.4 MB を含む) |
| brotli q11 / lgwin 24 | 16,196,755 B (**7.84×**)。圧縮 286.2 s (単一スレッド)、node 復号 0.33 s |
| gzip -9 / zstd -19 (`--long=27`) | 34,595,917 B (3.67×) / 17,186,585 B (7.39×) |

集計: `node tools/runtime/rt10/measure.mjs sizes` (節サイズは自前 LEB パーサ)。検算 (別実装 python パーサ) は §10。

## 3. cold 起動 (新規 profile, HTTP cache 空)

配信: localhost、`fleweb.wasm.br` を `Content-Encoding: br` で無制限配信、Worker 内 `fetch → compileStreaming → glue(instantiateWasm 注入) → _fle_boot_enter(0)`。
各行 n=3 (fresh Chrome 3 回)。時間は Worker 内 `performance.now()`、「合計」= glue import 開始〜boot 呼出完了。

| flags (V8) | fetch+compile ms | instantiate ms | boot 呼出 ms | 合計 ms | renderer HWM MB |
|---|---|---|---|---|---|
| 既定 (lazy + 動的 tiering) | 489–541 (med 524) | 11.9–13.6 | 484–545 (med 510) | **1,022–1,096** (med 1,048) | 763–769 |
| `--no-wasm-lazy-compilation` (eager) | 4,118–4,140 | 15.0–16.1 | 138–153 | 4,285–4,317 | 650–719 |
| `--liftoff-only` | 510–516 | 10.1–15.1 | 447–464 | 984–997 | 673–677 |
| `--no-wasm-dynamic-tiering` | 499–530 | 10.0–12.8 | 732–760 | 1,253–1,315 | 794–831 |
| 既定, bytes 経路 (`arrayBuffer`→`compile`) | 630–649 (body 410–437 + compile **212–220**) | 16.4–18.8 | 482–540 | 1,163–1,208 | 632–654 |

- 全 15 回で `units_run 209 / units_total 942 / GetMem 1,890 / FreeMem 776 / threw unlifted:0x6a7b70`。node 参照 (`fle_boot.mjs --boot-only` on `fleboot_plain.cjs`) と一致。
- wasm メモリは instance あたり 864 MiB (`--initial-memory=0x36000000` 固定)。renderer VmSize は計測行に保存。
- 既定で compile (検証) 後の boot 呼出に 484–545 ms かかるのは、**呼ばれた関数の lazy コンパイル**が初回呼出時に走るため。eager は compile が +3.6 s 長いが boot は 138–153 ms に縮む。総時間は既定が eager の 1/4。
- 合計は streaming 1,022–1,096 ms に対し bytes 経路 1,163–1,208 ms (fetch と compile の重なり分)。
- glue (`fleweb.mjs`, 179,157 B) の import は 8.8–13.4 ms。

## 4. warm 起動 (同一 profile, `Cache-Control: immutable`)

同一 Chrome で 3 回ロード (n=3 セット) + Chrome 再起動後 (同 profile) 1 回。

| ロード | fetch+compile ms | transferSize | boot 呼出 ms |
|---|---|---|---|
| #1 (cache 空) | 567–591 | 16,197,055 | 483–527 |
| #2 (HTTP cache hit) | 521–559 | **0** | 450–471 |
| #3 | 511–524 | 0 | 664–707 |
| #4 (再起動後) | 509–626 | 0 | 513–540 |

transferSize=0 でも **compile 時間は短縮されない** (Chrome の wasm code cache による短縮は 127MB でも headless では観測されず; RT 既存結論と同じ)。
#3 の boot が長い理由は未調査 (n=3 で再現: 664–707 ms)。

## 5. 帯域制限 (br 圧縮後 16.2 MB をサーバが 10 ms 刻みでペーシング)

| 帯域 | 算術の転送時間 (16,196,755 B×8/帯域) | resource.duration 実測 ms | fetch+compile ms | 合計 ms (boot 完了まで) |
|---|---|---|---|---|
| 10 Mbps | 12.96 s | 13,317–13,401 | 13,332–13,426 | 13,823–13,904 |
| 50 Mbps | 2.59 s | 2,673–2,684 | 2,692–2,699 | 3,379–3,389 |
| 100 Mbps | 1.30 s | 1,348–1,353 | 1,363–1,368 | 1,837–1,857 |
| 1 Gbps | 0.13 s | 452–475 | 469–493 | 1,026–1,090 |

- 10〜100 Mbps では fetch+compile − resource.duration = +15〜25 ms: compile は streaming でダウンロードに**完全に隠れ**る。fetch+compile 完了後に残る時間 (total − fetch+compile = instantiate + boot 呼出) は 10 Mbps 477–491 / 50 Mbps 680–697 / 100 Mbps 475–488 / 1 Gbps 556–605 ms。**ダウンロード支配**を確認。
- load (各回開始時の 1 分 load average, 4 vCPU): 10 Mbps 3.67–4.23 / 50 Mbps 3.13–3.32 / 100 Mbps 2.88–3.61 / 1 Gbps 3.61–4.28。計測中は帯域ペーシング用のサーバ (node) と Chrome が同居しており、1 Gbps 行の compile+boot は他の負荷の影響を受けうる。
- 50 Mbps だけ boot 呼出が 652–675 ms (10/100 Mbps は 453–468 ms, 1 Gbps は 525–562 ms) と長い。n=3 で 3 回とも高く、load は他帯域より低い (3.13–3.32) ので load では説明できない。**原因未調査** (§9-10)。
- 1 Gbps (算術の転送 0.13 s) でも実測 fetch+compile は 469–493 ms: 下限は br 復号 + 検証 + compile (§3 の無制限 489–541 ms と同程度)。
- 無圧縮 (126,995,440 B) を同じ帯域で送った場合は算術で 10 Mbps 101.6 s / 100 Mbps 10.2 s (**実測していない**)。br 事前圧縮が前提 (#170 PERF-P10)。
- 限界: localhost の単純ペーシングで RTT・TLS・CDN・並列接続・R2 の Range/圧縮応答は再現していない。

## 6. tier-up 影響 (同一 Module から連続 instance、各 boot は unit 209 まで)

各 instance は新規 (864 MiB メモリ)、Module は 1 回 compile したものを共有。n=3 セット × 6 instance。
load (開始時 1 分 load average, 4 vCPU): 既定 4.28–5.30 / `--liftoff-only` 4.71–5.04 / `--no-wasm-dynamic-tiering` 4.66–4.71。**4 vCPU がほぼ飽和**した状態の値で、動的 tier-up はバックグラウンドスレッドを使うため、空き CPU がある環境では #2〜#6 の遷移が速い可能性がある (未測)。

| 回 | 既定 boot ms | `--liftoff-only` boot ms | `--no-wasm-dynamic-tiering` boot ms |
|---|---|---|---|
| #1 | 515–558 | 440–507 | 693–794 |
| #2 | 106–108 | 118–119 | 243–249 |
| #3 | 105–123 | 115–119 | 162–190 |
| #4 | 57–86 | 118–121 | 62–94 |
| #5 | 61–66 | 124–127 | 62–65 |
| #6 | 64–67 | 124–126 | 61–62 |

- 既定: #1→#2 で **−79%** (515–558 → 106–108): 差分は初回の lazy コンパイル分。#2→#6 で更に −41% (中央値 108 → 64): TurboFan への動的 tier-up (バックグラウンドスレッド)。
- `--liftoff-only` は #2 以降 115〜127 ms で頭打ち (tier-up なし) → 既定の定常 64 ms は **TurboFan 効果が 1.8–2.0 倍**。
- 注意: これは boot コード (InitUnits 209 unit まで、GetMem/FreeMem 2,666 回など) に限った tier-up。実 FL の定常ループ (オーディオ/GUI) の tier-up は**測れていない**。
- instantiate (既定): #1 9.9–10.6 / #2 9.6–10.1 / #3 4.2–4.6 / #4 4.2–7.9 / #5 3.8–4.1 / #6 3.8–3.9 ms。#3 以降で約半減し #5 以降は 3.8–4.1 ms に落ち着く (Memory 確保が主)。`--no-wasm-dynamic-tiering` は #3 5.2–8.1 / #4 4.8–5.6 ms で、#5 以降に 3.9–4.2 ms。

## 7. 事前推定との差 (推定ラベル付き)

| 事前見積り (推定) | 出典 | 実測 |
|---|---|---|
| 実 FL の code 38.7 MB | PERF-P6 (M11 closure から K=12 外挿, 推定) | **106.5 MB** (2.75 倍) |
| 関数数 70k〜110k | 同 | **31,684** (平均 3,362 B/関数。合成 K=10 は 375 B/関数) |
| lazy compile 0.1〜0.2 s | #128 本文 / PERF-P6 | bytes compile **0.212–0.220 s** / streaming 込み 0.489–0.541 s |
| eager 4 コア 1.2 s | 同 | **4.118–4.140 s** (3.4 倍。code 比 2.75 倍 + 関数が大きい分) |
| bytes compile 1.5 ms/MiB | RT (M11×K ≤52 MiB) | 1.75–1.82 ms/MiB (wasm 全体) = 実測は外挿の +17–21% |
| brotli 3.31× (M11 6.0 MB) | RT DESIGN §3 | **7.84×** (x64c -O0 の冗長性) |

結論: 外挿の**関数数**前提は過大・**バイト数**前提は過小だった。V8 の compile は関数数でなく**バイト数で効く**。

## 8. soak (boot ループ代替)

`rt10_worker.mjs`: 同一 Module から instance 作成 → `_fle_boot_enter(0)` → 破棄を条件時間ループ。renderer RSS は `/proc/<pid>/status` を 5 s 毎に採取。
**これは「実 FL を動かし続ける soak」ではない**。boot の再実行 (毎回 InitUnits 209 unit + 864 MiB instance の確保/破棄) による instance 生成破棄のリーク検査と、同一コードの定常 tier-up の観測に限る。

| 実行 | cycle 数 | boot 呼出 ms (min–max, 中央値) | instantiate ms (min–max, 中央値) | renderer RSS MB (min–max, サンプル数) |
|---|---|---|---|---|
| 180 s (load@開始 4.44) | 2,913 | 52–138, 54 | 3.0–11.4, 3.4 | 556–656 (36) |
| 540 s (load@開始 0.21) | 8,726 | 52–167, 54 | 2.9–9.6, 3.5 | 462–684 (108) |

- 区間別 (540 s, 90 s 刻み) の RSS min–max: 569–684 / 462–659 / 512–613 / 474–607 / 477–609 / 463–597 MB。boot 中央値は 6 区間とも 54 ms。180 s 版 (30 s 刻み 6 区間) も 54 ms 不変、RSS 556–656 MB。
- 先頭 5 cycle の boot は 62–102 ms (中央値 85) → 末尾 5 cycle は 52–54 ms (中央値 54): 初回 boot (§6 #1 の中央値 520 ms) の後、数 cycle で TurboFan 到達後の定常値に落ち着き、その後 **8,726 cycle の間に退行 (deopt/再コンパイル) なし**。
- instance あたり 864 MiB の Memory を 8,726 回確保・破棄してもリークなし (RSS が下がる区間もあり単調増加でない)。全 cycle で `units_run 209`、例外・OOM・Worker crash は 0。
- RSS は `/proc` の renderer プロセス (最大 RSS のもの) の VmRSS を採取。HWM はサンプル時点で選ばれた renderer が入れ替わりうるため本書では使わない。
- 限界: 毎 cycle 同一の 209 unit を再実行するだけで、実 FL のメッセージループ・GUI・オーディオ・ファイル I/O を含まない。メモリ増加の検出対象は instance 生成破棄と shim のみ。

## 9. 未解決・測れない項目

| # | 未解決 / 測れない理由 | 影響 | 起票先 |
|---|---|---|---|
| 1 | **初回フレームまでの総時間**: boot が unit 209/942 で `unlifted 0x6a7b70` 停止 (`f_653f40` 早期 return, fill callback `0x15F34A0` 未登録)。GUI 初期化・ウィンドウ生成・初回描画に届かない | 受入条件「初回フレーム総時間」未達。§3 の合計は**下限ですらない** (unit 210 以降の実行・描画が加算される) | #253 ([FLE-2]) にコメント + 新規 #541 [RT-12] (boot 突破後の再計測) |
| 2 | **実 FL の長時間 soak** (main ループのメモリ増加/GC/tier-up) | 代替指標 (§8) のみ | #541 [RT-12] |
| 3 | **実配信 (R2/CDN)**: br 配信の応答形・Range・RTT・TLS・同時接続は未再現 | §5 は localhost ペーシング | #170 ([PERF-P10]) にコメント |
| 4 | **-O0 の 127 MB**: 本番最適化 (-O1/-O2、`-g1` 除去、wasm-opt) 後のサイズ/compile/実行は未測 | サイズ・compile 時間が変わる | #133 ([OTT-T2]) / 本番ビルド担当 (別チケット) |
| 5 | pthread 化した実 FL (`prod/flags.sh`) での計測: 本計測は単スレッド (`-pthread` なし) | pthread Worker 起動・共有 Module 配布コスト未算入 | #120 ([RT-2]) 後続 / #541 [RT-12] |
| 6 | Firefox/Safari、実 GPU/headful の Chrome、AudioWorklet 経路の 127MB 規模 | headless Chrome 154 のみ | #127 ([RT-9]) / #541 [RT-12] |
| 7 | warm #3 の boot 664–707 ms (他より長い) の原因 | 再現性はあるが原因未調査 | #541 [RT-12] |
| 8 | wasm が boot REPORT の記録と 210 B 差 (§2) | 再現性 (結果は一致) | #253 にコメント |
| 9 | m11 (RetDec) 経路の同計測: `work-m11` 未取得 (本 run の素材は `fl-win64 toolchain-emsdk`) | 経路比較は未実施 | 不要なら見送り (x64c が推奨ルート, `tools/flelift/REPORT.md` §9.3) |
| 10 | bw 50 Mbps だけ boot 呼出が 652–675 ms (10/100 Mbps は 453–468 ms, §5) | 原因不明。load は他帯域より低く、n=3 で 3 回とも再現 | #541 [RT-12] |

## 10. 検証

- **別アルゴリズムの検算** (`bash tools/runtime/rt10/verify.sh`): 
  - python 独立パーサ: total 126,995,440 B / code 106,525,508 B / data 20,432,171 B / 定義関数 31,684 → node 版 `measure.mjs sizes` と**完全一致**。
  - `.br` 往復: 復号 sha256 == 原本 sha256 (原本 126,995,440 B → br 16,196,755 B)。Chrome 側 `decodedBodySize` も cold/warm/bw 全行で 126,995,440。
  - boot 結果の突合: node 参照 (`node tools/flelift/boot/fle_boot.mjs <abs>/fleboot_plain.cjs out.json --boot-only`, 別実装の node 用 glue) = units_run 209 / units_total 942 / 停止 `unlifted` / GetMem 1,890 / FreeMem 776 / exit 0 (wall 9.76 s; brotli 圧縮と並走中の 1 回)。Chrome Worker の全 cold 15 回・soak 全 cycle と一致。
- **ネガティブコントロール**: wasm を 100,000,000 B に切り詰めて (原本 126,995,440 B) 同じハーネスへ流すと `ok:false` / `CompileError: WebAssembly.compileStreaming(): section (code 10, …` (`results/rt10_cold_neg.jsonl`)。通常 wasm は cold 15/15 が `ok:true`。
  ただしこれは「壊れた入力を検出できる」確認で、boot 動作の不一致を人工的に作った試験ではない (boot 等価性の否定試験は未実施 → 弱い点として残る)。
- **コミット済み HEAD での再現**: 計測は harness commit `3e0cd6d` の内容で実行 (`3e0cd6d` 以降、`measure.mjs` の変更は `sizes` 出力の `file` を repo 相対パスにした 1 行のみ。計測値に影響しない。他は REPORT と results の追加)。HEAD `d96fc45` で `measure.mjs cold --reps 3 --flags default --tag _headcheck` を再実行 (`results/rt10_cold_headcheck.jsonl`, load 0.36):
  合計 1,039–1,126 ms (fetch+compile 515–569 / instantiate 10.7–12.6 / boot 496–540)、units_run 209 / GetMem 1,890 / FreeMem 776 で一致。§3 の 1,022–1,096 ms と同水準だが上端が 30 ms 高く、run 間変動はこの程度ある (2 セット併せた合計の範囲 1,022–1,126 ms, n=6)。
- 検出力の確認 (本計測内): eager と既定で boot 呼出が 138–153 ms と 484–545 ms に分かれる (ハーネスが 3.5 倍差を弁別)。
- 範囲外: 上記のとおり実 FL のフレーム・soak・実ネットワーク。

## 11. 再現

```sh
export FL_WIN64_DIR=<fl-win64 展開先>            # extracted/block00031_PE.bin を含むディレクトリ
bash tools/runtime/rt10/run_all.sh [--skip-build] [--soak-sec 180]   # build → sizes → cold/warm/bw/tier/soak (build 981.4 s の実測 + 計測)
node tools/runtime/rt10/measure.mjs soak --sec 540 --flags default --tag _long   # 540 s 版
node tools/runtime/rt10/summarize.mjs            # results/rt10_*.jsonl → 本書の表
bash tools/runtime/rt10/verify.sh                # 検算 + ネガティブコントロール
```
RAM 16GB の runner では build 前に swap を追加すること (24GB の swap ファイルを `fallocate -l 24G <swapfile> && mkswap <swapfile> && swapon <swapfile>` で追加)。生成物は `tools/flelift/work/boot/` (gitignore)。
