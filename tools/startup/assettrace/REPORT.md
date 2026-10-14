# REPORT — ST-T5 (#105): asset trace → 起動必須 asset 最小集合の自動生成

検証起点: 親 `main` = `2847625`。本 REPORT の数値は PR HEAD で `bash tools/startup/assettrace/e2e.sh` を再実行した実測 (§3)。
既知類型 (`docs/DEFECTS.md`) との関係: **該当なし** (lift/逆アセ/IR pass を扱わない)。

## 0. 結論

1. **本 ticket は部分達成 (Refs #105・Closes しない)**。「boot 中の `open()` trace からの最小 manifest 自動生成」の**変換器**は実装・検証したが、
   **実 FL の trace は未取得**。`CreateFruityInstance` に未到達 (`tools/flelift/boot/REPORT.md` §0: unit 進行 209 止まり) のため FL が何を開くかは出ない。
   よって §2 の出力は**合成 fixture での機能検証**であり、FL の実要求集合を示す数値ではない。
2. 名前空間定義 (`C:\Program Files\Image-Line\FL Studio 2026` → `/fl` RO ほか) と `shimx_set_path_mapper` 登録関数は **既に別 ticket で達成済み** のため再実装していない:
   `tools/shimx/pathreg/REPORT.md` §2.2 (既定表 8 本)、`tools/assets/wvfs/REPORT.md` (`/c/home`・`/c/tmp`)、`tools/startup/glue/REPORT.md` (stage 結線)。
   本ツールは pathreg の JS ミラー (`createMapper`) を import して写像する (規則の複製なし)。
3. 静的推定 tier (`tools/assets/bootset/BOOTSET.md` = 推定) との差分 (promote / unseenT0) を出せるので、実 trace が取れた時点で推定の答え合わせができる。

## 1. 成果物

| パス | 内容 |
|---|---|
| `assettrace.mjs` | `parseTrace` / `analyze` / `observedTiers` / `diffTiers` + CLI。入力 = trace JSONL + inventory (`tools/assets/work/inv_win.jsonl`)・任意で `tiers.json`。出力 = JSON (`files`/`unknown`/`missing`/`dirs`/`other`/`roWrites`) + `--tiers-out` (観測 asset を T0 に固定した path→tier。`tools/assets/pack/pack.ts --tiers` の入力形式) |
| `test/assettrace.test.mjs` + `test/fixtures/` | 単体 10 件 (うちネガコン 2) |
| `e2e.sh` | 1 コマンド検証 (単体 → CLI → 件数照合 → RO 違反ネガコン) |

### trace 形式 v1 (shimx 側フックの契約)

`{"op":"open"|"stat"|"enum","path":"<Win または POSIX 絶対>","ok":bool,"w":bool}` を 1 行 1 JSON。`enum` の path は `dir\*.ext` 形。
**現 shimx にこの出力口は無い**: `SHX_TRACE` は `CreateFile` の失敗時 1 箇所 (`tools/shimx/src/file.c` の `open(%s) failed`) とメッセージ形式の自由文のみ。成功 open・FindFirstFile・GetFileAttributes の構造化出力が必要 (§4)。

### 処理規則

写像 = pathreg `createMapper().map` (非対応は `unmapped`)。`/fl` 配下のみ asset。大小無視で inventory と照合し元ケースを返す。
`ok=false` → `missing`。`w=true` の `/fl` 書込み → `roWrites` (RO 違反・CLI は exit 1)。inventory に無い読取 → `unknown` (ディレクトリ自体は除外)。
`enum` はワイルドカード (`*`/`?`) を inventory の同一ディレクトリ直下に展開して全件を `files` に入れる (列挙された=後で開かれ得る、の保守側)。

## 2. fixture での出力 (合成・FL の実数値ではない)

fixture trace 12 行 / inventory 8 件: files **5** (Title.png は 3 表記で n=3、`*.txt` 展開 2 件含む) / unknown **1** / missing **1** / roWrites **0** /
other = persist 2・tmp 1・unmapped 1。`diffTiers`: promote 1 (`Thumbnails/a.png` T1→T0) / unseenT0 1 (`BigFruit.png`)。

## 3. 検証 (実測)

| 項目 | 結果 |
|---|---|
| `bash tools/startup/assettrace/e2e.sh` (コミット `c61a16b` を `git worktree add --detach` で展開して実行) | exit 0 / **0.208 秒** (`time`) / load average 開始 0.00 0.08 0.05 / 並列 1 / 単体 pass 10 fail 0。作業ツリーでの先行実測は 0.203 秒 (load 0.01 0.10 0.06) |
| ネガコン NC1 (installDir を別パスに) | files 5 → 1 (POSIX 直指定のみ残る)。写像を壊すと検査が落ちる |
| ネガコン NC2 (inventory から 1 件除去) | files 5 → 4・unknown 1 → 2 |
| ネガコン CLI (`/fl` への書込み open) | exit 1 |

検証範囲: 変換ロジックと CLI (node v22.23.3)。範囲外: 実 FL trace、全 inventory (`inv_win.jsonl` は `tools/assets/work/` 生成物で本 run に無く、26,000 件規模での実行は未実施)、shimx 側フック実装。
`pathmap.mjs` の C 一致は pathreg REPORT §2.3 の 16 fixture に依存 (本 ticket で再測定していない)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shimx に構造化 file trace (trace 形式 v1: 成功 open / stat / FindFirstFile / `w` フラグ) の出力口が無い (m11 wasm の CreateFileW だけは #2905 で trace 済み: `tools/gui/flengine/REPORT_APPENDIX.md` §8) | shimx 経路の実 trace を採る手段がない | 新規子チケットを PM が起票 (本 issue #105 にコメント済み) |
| 実 FL boot の trace 取得 (`CreateFruityInstance` 到達が前提) | 最小 manifest の実数値が出ない。#105 の Closes 条件 | #105 (T1 待ち・Backlog 維持) / 依存: `[FLE]`・`[ICALL-1]` #227 |
| 実 inventory での実行・`tiers-out` を `pack.ts` に渡した 1 chunk 範囲 (groups.T0) の実測 | tier 昇格による boot chunk 総量の変化が未測定 | 同上 (実 trace 取得後) |
| #39 (言語/スキン/Help 経路) への入力 | 実 trace 待ち | #39 に本 REPORT へのリンクを提案 (PM 判断) |
