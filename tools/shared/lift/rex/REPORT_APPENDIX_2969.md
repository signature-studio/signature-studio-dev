# REX 中核閉包の所有者限定 tier 配置とビルドフラグ除外 — T-SH-48 (#2969) 付録

親: `tools/shared/lift/rex/REPORT.md` §8 (#2734 の中核閉包 lift)・§10 (#2896 の REX_SIDE 機構)。

測定 commit: `9593fe1c1` (`tools/shared/lift/rex/` の最後のコード変更: `lift_core.sh`)。以降の差分は本付録と REPORT の文言だけ (差分 0 の証跡は §A.5)。
既知類型との関係: 該当なし (差分テストは未実施。配信物の一覧と内容の一致だけを検査する)。

## A.1 結論と方法
- **結論 (1 行)**: 部分。中核閉包 (REXCreate / REXGetInfoFromBuffer / REXRenderSlice・519 関数) の wasm (854,208 B) を所有者限定 tier の `owner/rex_core_side.wasm` に複製し、`REX_SIDE=0` で `owner/` から除外できるようにした。両フラグで `lift_core.sh all` が ALL OK。**SIDE_MODULE 形式 (dlopen 形) は未達** (§A.3・#3630 の PM 判断待ち。#2896 と同じ扱い)。**公開 tier への結線は未実施** (D11。PM が手元で行う)。
- フラグ `REX_SIDE` (既定 `1`、0/1 以外は exit 2)。`REX_SIDE=1` = `$W/owner/rex_core_side.wasm` (`rex_core.wasm` の複製)。`REX_SIDE=0` = `owner/` は空。`$W` = `tools/shared/work/lift/rex-core` (gitignore)。`rex_core.wasm` は両フラグとも `$W` 直下に残る (ビルドの中間物。配信物ではない。`lift_x64c.sh` と同じ扱い: REPORT §10.1)。
- `ok`: `owner/` を作り直し、一覧が期待値 (`1` で `owner/rex_core_side.wasm` の 1 行、`0` で空) と一致し、`owner/` の中で `rex_core.wasm` と同じ sha256 のファイル数が期待値 (1 / 0) と一致すること。`neg-owner`: `owner/rex_glue.c` (ダミー) を足して突合し、FAIL を検出すれば期待どおり。`all` = `ok` + `neg-owner`。

## A.2 受入条件ごとの結果
| 受入 (#2969) | 結果 |
|---|---|
| 1. 中核閉包を FL 本体と別の side module としてビルドする | **部分**: `owner/rex_core_side.wasm` は `-sSTANDALONE_WASM=1 --no-entry` でビルドした `rex_core.wasm` の同一バイト複製で、dlopen 形の side module ではない (§A.3 (a))。 |
| 2. ビルドフラグ 1 つで除外。除外時の成果物に REX 由来のバイト列が無い | **達成** (`REX_SIDE=0`): `owner/` の一覧は空、REX と同内容の配信物は 0 件 (§A.4)。 |
| 3. 測定 commit と実測値 (wasm サイズ・除外の確認結果) を REPORT に記録する | **達成**: 本付録 §A.4・§A.5 と REPORT §8 の結論行からの導線。 |

## A.3 検証範囲 / 範囲外 / 未解決
- 検証した: 2 フラグ × 3 回の `all` (`ok` と `neg-owner`)。配信物の一覧・内容の sha256・ネガコン。`REX_SIDE=1` と `0` の wasm の sha256 は 6 回とも `540cd66b…` で一致 (決定的ビルド)。
- 範囲外: 差分テスト (#2970・素材の REX 入力が無い)、成功経路、公開 tier の配信 (`deploy/`・release guard の deny-list。D11)。REX と同内容の配信物の検査は sha256 の完全一致だけを見る (glue 等の別内容の混入は一覧の突合で見る)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 中核閉包の dlopen 形 (`-sSIDE_MODULE=2`・固定 VA・global 再配置) | side module の形式が未決。`rex_core_side.wasm` を読む経路が無い | #3630 [T-SH-91] (PM 判断待ち。既定案は現状の standalone 複製。#2896 と同じ判断に従う) |
| (b) 公開 tier の配信 (`deploy/`・release guard の deny-list) への結線 | `REX_SIDE=1` の配信物が公開 tier に載る経路は塞がれていない | PM (D11・#2896 本文の「範囲外の PM 作業」) |

## A.4 実測 (測定 commit `9593fe1c1`・コミット済み HEAD で `REX_SIDE=1` と `0` をそれぞれ 3 回。各回 `REX_SIDE=$s bash tools/shared/lift/rex/lift_core.sh all`)
| 項目 | `REX_SIDE=1` | `REX_SIDE=0` |
|---|---|---|
| `all` の wall (`date` の差) / rc | 10.43–10.85 s / 0 (3 回) | 10.53–10.80 s / 0 (3 回) |
| 本検査 `ok` の配信物の一覧 | `owner/rex_core_side.wasm` (3 回とも) | 空 (3 回とも) |
| REX と同内容の配信物 (期待値) | 1 (期待 1)・`cmp` 一致 | 0 (期待 0) |
| `neg-owner` (一覧突合のネガコン) | `owner/rex_core_side.wasm owner/rex_glue.c` ≠ 期待 → FAIL (期待どおり) | `owner/rex_glue.c` ≠ 期待 (空) → FAIL (期待どおり) |
| wasm | 854,208 B・sha256 `540cd66b841d6ce8a73d35543e0d6d4d456b9f548eed6bc7300c38937327eed7` (6 回とも同値) | 同左 (`$W` 直下に残る中間物) |
| lift の所要 (`elapsed`、各モードの値) | 5–6 s | 5–6 s |
| load average (1 分値、各 `all` の開始時) | 0.36 / 0.45 / 0.54 | 0.61 / 0.70 / 0.74 |

- 再現 (n=3 は同じ入力での繰り返し): `FL_WIN64_DIR=<fl-win64 展開先> REX_SIDE=1 bash tools/shared/lift/rex/lift_core.sh all` (`REX_SIDE=0` も同じ)。`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir> extracted/block24351_PE.bin`)。
- 配信物の確認: `cd tools/shared/work/lift/rex-core && find owner -type f | sort && sha256sum rex_core.wasm owner/rex_core_side.wasm`。
- lift の出力は `lift_core.sh` の従来の出力と同じ (519 関数・22,987 命令・unlifted callee 0・unsup 50・間接 register dispatch 101)。

## A.5 測定後のコード差分 (差分 0 の証跡)
`git diff 9593fe1c1 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし。以降は本付録と REPORT の文言のみ)。
