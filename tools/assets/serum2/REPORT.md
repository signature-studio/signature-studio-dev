# SR-6 Serum 2 コンテンツ配信 — manifest + LazyVfs + wasm libFLAC (node 層 e2e)

検証起点 commit `953e3fa` (branch `70-serum2-content-delivery`)。wasm 経路の再実行 (toolchain-emsdk 付き) は HEAD `24c22fc` の worktree で行い、§2 末尾・§3 に記録。
既知類型との関係: 該当なし (lift/逆アセ/IR pass 系ではない。§4 の SlotCache 欠陥は lift 欠陥類型 (DEFECTS.md) の外)。
再現: `SERUM2_INSTALLER=<Install_Xfer_Serum2_2.1.5.exe> EMSDK_ENV=<emsdk_env.sh> bash tools/assets/serum2/e2e.sh`
(展開済みなら `SERUM2_EXTRACTED=<7z x の出力 dir>`)。pass 1 本 + ネガコン 3 本を走らせ、1 本でも期待と違えば exit 1。

## 1. 結論

- **node 層は達成**: 素材 (R2 `plugins-serum2`) の NSIS を `7z x` で全展開し、content 7 グループを既存 `tools/assets` の pack → manifest → HTTP 配信 → LazyVfs (SAB loader + SlotCache) で読み、**全 7,357 files の sha256 が原本と一致**。
- **FLAC は upstream libFLAC 1.5.0 を wasm32 に再ビルド** (58,008 B, 17 ソース, emcc 6.0.12 = `toolchain-emsdk`) して復号。**全 4,747 FLAC の PCM が libsndfile 1.2.2 (別実装) の PCM と一致**、全件 STREAMINFO MD5 検証込みで rc=0。
- **未達 (Refs 止まりの理由)**: 実 Chrome 上の OPFS/Range 経路、R2 非公開 + Access 配信、Serum 2 本体 (lift 後) からの FS shim 接続は未実施 (§5)。issue に明示の受入条件が無いため、本 PR の受入条件は §2 の 6 項目とした。

## 2. 受入条件と実測 (clean HEAD `953e3fa`, `e2e.sh` 1 回)

| # | 条件 | 結果 |
|---|---|---|
| 1 | inventory が issue 実測と完全一致 (7 グループの files・bytes) | 一致。content 7,357 files / 1,392,825,417 B。issue の 7,370 files / 1,413,375,641 B との差 13 files / 20,550,224 B は `$COMMONFILES64` (VST3/AAX 本体・ico・desktop.ini = 8 files) と `$PLUGINSDIR` (NSIS 部品 5 files) で、content ではない |
| 2 | manifest tree が全 files を size 付きで列挙 | stat 一致 7,357/7,357 |
| 3 | VFS 経由の全 files 内容一致 | sha256 一致 7,357/7,357 (read error 0) |
| 4 | 全 FLAC を wasm 復号し別実装と PCM 一致 | 4,747/4,747 一致。bps 分布 16bit 3,770 / 24bit 977 |
| 5 | Tables (wavetable) の再起動 warm で network 0 | 289 files, cold chunk request 273 → warm 0 |
| 6 | 各検査にネガコン | §3 の 3 本 + SlotCache 回帰 1 本 (§4) |

主要実測 (pass 1 回, 4 vCPU, node v22.23.3):

| 項目 | 値 |
|---|---|
| pack | 3,072 chunk (1 MiB), 格納 1,334,078,136 B (br 352 object 199,142,917 B / raw 2,719 object 1,134,935,219 B)。FLAC は incompressible 判定で raw。pack 所要 9.3 s (compressSec, concurrency 4) |
| manifest | json 470,358 B → br 126,344 B |
| 全 files VFS 読み + FLAC 復号 | 36.7 s (うち VFS 読み 8.0 s / wasm 復号 27.9 s)。復号 PCM 7,320,477,924 B (int32 換算) |
| Tables cold / warm | 1,950 ms / 128 ms (173,372,140 B) |
| e2e 1 本の所要 | pass 42 s、neg-flac 44 s、neg-ref 43 s、neg-chunk 44 s (load average 0.97–1.80、並列 1) |
| 準備 (展開済み素材から pack + wasm ビルド + libsndfile 参照) | 21 s (初回の別実行は 29 s) |

### 2-b. wasm 経路の再実行 (HEAD `24c22fc`、`toolchain-emsdk` 付き、n≥3)

素材 `plugins-serum2` と `toolchain-emsdk` を `$ARTIFACTS_DIR` から取得 (`toolchain-emsdk` は `[EMSDK]`、emcc 6.0.12)。
`SERUM2_INSTALLER=<7z 展開元 exe> EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/assets/serum2/e2e.sh` 1 回目で
pass + neg 3 件すべて OK (`SERUM2 E2E OK`、全体 4 分 01 秒)。pass は追加で 2 回回した (計 3 回)。

| 項目 (pass 3 回の min–max) | 値 |
|---|---|
| pass 所要 (`totalMs`、3 回) | 48,502 / 49,414 / 49,151 ms (min 48.5 s – max 49.4 s)。wall 49.4–49.6 s |
| 全 files VFS 読み (`vfsReadMs`) | 9.4–10.1 s |
| 全 FLAC 復号 (`flacDecodeMs`) | 32.6 s (32,583–32,610 ms) |
| Tables cold / warm | 2,473–2,626 ms / 148–152 ms。chunk request 273 → 0 |
| load average (pass 開始時) | 0.68–1.82 (1 分値) |

pass 3 回とも `failures=0`、FLAC 4,747/4,747 PCM 一致、MD5 有り 4,747、Range 4/4 + 45/45 一致。
ネガコン 3 件は 1 回ずつ (期待どおり exit 1 / failures=1): neg-flac 48 s、neg-ref 50 s、neg-chunk 49 s (各 1 回)。

### 2-c. 旧 `cache.ts` でも SlotCache 回帰が落ちることの実測

`slotcache-tail-test.ts` を旧 `cache.ts` (blob `483e058b`、`546c54b` の親) に対して 1 回実行: 通常 rc=1 (4/5 復元)、`--neg` rc=1。
修正版 (`cache.ts` 現行 HEAD) は通常 rc=0 (5/5)、`--neg` rc=1。`--neg` の切り詰め擬似検査に加え、実旧 blob でも 4/5 で不合格になることを確認した。

数え方: 「files」= `find <root> -type f` から `$COMMONFILES64`/`$PLUGINSDIR` を除いた regular file。「FLAC」= 拡張子 `.flac` (4,747 = Multisamples 3,977 + Samples 661 + Impulses 109)。「PCM 一致」= wasm の int32 PCM を left-justified (bps<32 は (32−bps) bit 左シフト) にした sha256 と、`soundfile.read(dtype='int32')` の sha256 が一致し、かつ ch/rate/frames/bps も一致 (frames は STREAMINFO total_samples とも一致)。

## 3. ネガティブコントロール (各 1 件だけ壊す。期待: exit 1 かつ failures=1 ちょうど)

| mode | 壊し方 | 実測 |
|---|---|---|
| neg-flac | `Impulses/Factory/Cab/Electric Guitar Cab 2.flac` の中央 1 byte を反転して wasm に渡す | exit 1, failures=1 (rc=1 の復号エラー 1 件。復号 rc 分布 {0:4746, 1:1}) |
| neg-ref | `Impulses/Factory/Coloration/Suitcase EPiano 2.flac` の参照 sha256 の先頭 1 文字を変える | exit 1, failures=1 (PCM 不一致 1 件) |
| neg-chunk | pkg の chunk#2819 (`Samples/.../Rising Wind.flac` の先頭、raw) の格納物を 1 byte 反転 (原本 pkg は不変、symlink view で差し替え) | exit 1, failures=1 (内容ハッシュ不一致で VFS read error 1 件) |

初回実装では neg-flac/neg-ref が failures=2 になった (ファイル単位の不合格と集計行の二重計上)。判定が曖昧になる = 0 件/過大でも通りうるため、`failures` を「不合格ファイル数」に統一し、wrapper は **failures が期待値ちょうど**を要求する形に直した (`953e3fa`)。pass が 0 件の検査 (対象 0 件) を通さないため、FLAC 件数は参照側 4,747 と突合する。

## 4. 副産物: 既存 SlotCache の欠陥 1 件 (修正済み)

- 症状: 永続キャッシュを開き直すと**末尾 slot が復元されない**。Tables の warm 再起動で chunk request が 1 件発生 (期待 0)。
- 根本原因: `SlotCache.scan()` が `floor(fileSize / slotBytes)` を slot 数にしていた。末尾 slot の chunk は 1 MiB 未満なのでファイルが slotBytes の整数倍に満たず、末尾が数えられない。
- 修正: `tools/assets/vfs/cache.ts` で `floor((size − HDR) / slotBytes) + 1` (size ≥ HDR のとき)。
- 回帰: `node tools/assets/test/slotcache-tail-test.ts` (修正版: 5 件中 5 件復元 exit 0) / `--neg` (旧 scan 相当の切り詰め: 4/5 で exit 1)。
- 影響範囲: 既存 asset e2e (`tools/assets/e2e.sh`) は本 PR で再実行していない (§5)。

## 5. 検証範囲 / 範囲外 (未解決は起票先付き)

検証範囲: node 上のローカル HTTP サーバ (`tools/assets/test/server.ts`) への配信、SAB loader + node fs SlotCache、wasm (node 内 `WebAssembly`) での FLAC 復号、原本 (7z 展開物) との全件照合。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 Chrome (OPFS SyncAccessHandle + SAB + Range) での同等 e2e が無い | ブラウザでの cold/warm・容量・所要は未実測 | #70 に残す (受入に含めるなら別 run で `tools/assets/test/browser-test.ts` 系へ拡張) |
| **VFS 自体は Range リクエストを発行しない** (chunk object 全体を GET)。Range は raw 格納 chunk へのサーバ側 GET のみ検証 (4/4 で 206 + bytes 一致、br 格納は `Accept-Ranges: none`) | issue 文言「HTTP Range」は chunk 単位取得で満たしている解釈 (推定)。FLAC (raw) をファイル途中から Range で読む経路は未実装 | #70 にコメント (PM 判断: chunk 取得で足りるか) |
| R2 非公開バケット + Access 配信・実 URL 配信は未実施 (`cf` CLI/認証が runner に無い) | 本番配信経路の実測なし | #63 (配備 manifest)。#18 は CLOSED のため起票先から外した |
| Serum 2 本体 (lift 後) の FS 呼び出し (Windows パス・ユーザ領域の既定 content dir) と VFS の接続 | データ層が音声経路に載るかは未確認 | #71 (OSS 境界) / SR-4 側 |
| FLAC wasm は memory→memory 復号 (全体をメモリ展開)。大物の逐次復号 (stream) は未対応 | 最大 FLAC のピークメモリ未実測 | #70 にコメント |
| libFLAC 版は 1.5.0 を採用。Serum 2 実体が使う版は未確定 (serum2 REPORT §9 既知の未解決) | PCM は全件別実装と一致しており復号結果への影響は無いが版整合は未確認 | #71 |
| 既存 `tools/assets/e2e.sh` は作者環境の固定絶対パス (repo 外) 前提で runner では実行不可。SlotCache 修正の既存 e2e への影響は未確認 | 既存テストが回帰していない確認が無い (cache.ts の変更は scan の slot 数のみ) | 新規子チケット案 [E2E-n] 「tools/assets/e2e.sh の runner 対応」 |

素材: R2 `plugins-serum2` (2,633,162,886 B) の `Install_Xfer_Serum2_2.1.5.exe` を使用 (FL/プラグイン由来のバイトは commit していない。`tools/assets/serum2/work/` と `$RUNNER_TEMP` のみ)。
