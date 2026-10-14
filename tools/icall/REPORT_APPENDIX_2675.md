# 付録: icall #2675 (ICALL-80) — SlateCore.core_64 205 B (0x181057b38) の sha256 照合 (plugins-freshair)

> 親: #2508 (ICALL-78)。`tools/icall/REPORT_APPENDIX_2508.md` §6 の未解決 1 件目 (受入 3: `plugins-freshair` が無く未実施) を解く。
> 測定 commit: `6bf05f6a` (`tools/icall/diff/fa_va_sha.py` を追加した commit。コードを変えた最後の commit)。

## 1. 結論

- `SlateCore.core_64` の `0x181057b38`–`0x181057c05` (205 B) と `rw.dll` の同 VA の bytes は **一致**。sha256 は両方 `9294534282e8ea79736ba1e8febf7311f0301fd9c491cb4e383063de80f0e1c3`、file offset は両方 `0x1056f38`。
- 一致は 3 系統で確認した (§3)。`dsm` (元 PE の逆アセンブル元) の bytes とも一致する。
- PE 全体の比較では、2 ファイルの差は **ヘッダ 22 B (`0x136`–`0x377`) のみ**。`.text` 以下の全セクションは 1 byte も違わない。`rw.dll` は元 PE に対し、ヘッダ (セクション数 7→8) と末尾の `.icall` セクション (`0x12800` B) を足しただけで、機械語は書き換えていない。
- 受入条件 (205 B の sha256 照合と REPORT への記載) は満たした。`#2508` の残件 (受入 1 の残り・受入 4 ほか) は変わらない (§6)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 検証起点 | `origin/main` `208b4ef9` から作った worktree (`2675-slatecore-core64-sha256`) |
| 素材 | `plugins-freshair` (`Fresh Air.Win.zip` を `tools/targets/freshair/fetch.sh` で展開 → `SlateCore.core_64` 36,285,952 B)。`work-icall` (`tools/icall/work/rt_freshair-core/rw.dll` 36,361,728 B・`before.0.drc.dsm`)。`fl-win64`・`toolchain-*`・`work-liftlib` は未使用 |
| 素材の鮮度 | `rw.dll` は `work-icall` の展開物と、リポジトリ作業ディレクトリに既にあった `tools/icall/work/rt_freshair-core/rw.dll` の sha256 が一致 (`2098d2f37d5dd135a12d9fbdd6caa1f98ba5a91fe38cec58d9b7a7816baa6c71`) |
| 所要・load | `fa_va_sha.py` 3 回 0.03 s・0.03 s・0.03 s (`/usr/bin/time`)。load 1 分平均 0.11 → 0.11 (並列 1)。素材展開は plugins-freshair 0.09 s、`work-icall` の `rw.dll` のみ 6.6 s、`work-icall` 全体 9.8 s |

## 3. 照合結果

| 系統 | 手段 | 結果 |
|---|---|---|
| A | `python3 tools/icall/diff/fa_va_sha.py` (pefile で section table から file offset を得て、VA 範囲の bytes を sha256) | 両者 `ImageBase=0x180000000` `fileoff=0x1056f38` `size=205` `sha256=9294…e1c3` → **一致** (exit 0) |
| B | `dd` で file offset を直接読む。offset は objdump の `.text` (File off `0x400`・VMA `0x180001000`) から手計算 `0x181057b38 - 0x180001000 + 0x400 = 0x1056f38` | 両者 `9294…e1c3` → **一致** |
| C | `python3 tools/icall/frame_slot_probe.py mc --dsm tools/icall/work/rt_freshair-core/before.0.drc.dsm --va 0x181057b38 --pe <PE>` (dsm の関数 `0x181057b38` は 48 命令・205 B) | `SlateCore.core_64`・`rw.dll` とも「dsm の bytes と 一致」 |
| D | 全体比較 `cmp -l` (`SlateCore.core_64` と `rw.dll` の先頭 36,285,952 B) | 差分 22 B。全て `0x136`–`0x377` (PE ヘッダ・セクションテーブル。`SizeOfHeaders` `0x400` の内側)。`.text` 以下は差 0 |

ネガティブコントロール: `rw.dll` のコピー (`$RUNNER_TEMP` 下) の `+100` (VA `0x181057b9c`) の 1 bit (`^0x01`) を反転すると、A は `first diff at +100 (VA 0x181057b9c)`・`sha256=f5bd28d5944e15b5b3288309d32fcd22cf7c65f8cc4ddd272a30b6c4bb4f04c2`・`不一致`・exit 1 になった。照合器は差を検出する。

## 4. 再現

```sh
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C . tools/icall/work/rt_freshair-core/rw.dll
python3 tools/icall/diff/fa_va_sha.py "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" tools/icall/work/rt_freshair-core/rw.dll 181057b38 181057c05
# 期待: 両者 sha256=9294534282e8ea79736ba1e8febf7311f0301fd9c491cb4e383063de80f0e1c3 → 一致 (exit 0)
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .          # dsm 系統 (C) 用に work-icall 全体を展開 (約 10 s)
python3 tools/icall/frame_slot_probe.py mc --dsm tools/icall/work/rt_freshair-core/before.0.drc.dsm --va 0x181057b38 --pe tools/icall/work/rt_freshair-core/rw.dll | tail -1
```

## 5. 検証範囲 / 範囲外

- 範囲: 205 B の bytes の一致 (受入 3)。`.text` 以下の全体一致 (D) は副次的な確認。
- 範囲外: 0x181057b38 の xmm0 の挙動 (#2508 付録 §3 で扱い済み)、`rw.dll` の `.icall` セクションの内容、wasm と native の実行差分。
- `fa_va_sha.py` は PE 2 つの同じ VA 範囲を比べるだけで、逆アセンブルや意味の比較はしない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `#2508` の残件: 受入 1 の残り (0x180da6e60 の「誤り疑い」6 件)・受入 4 (merge 規則の他関数での検証)・`0x180da4030`・`0x1803dee20`・`0x18105d9fc` の扱い | #2508 の受入は未達のまま。本 issue の範囲外 | #2508 (既存 issue に残す) |
| lift の ABI 仮想化: 関数 entry で `BLK+0x88 := BLK+0x28` が無い (`REPORT_APPENDIX_2508.md` §3.3) | xmm0 素通しの nested 呼出しで、後続の caller が xmm0 を読む場合の不一致の可能性。未確認 | #2508 (既存の残件) |

`REPORT_APPENDIX_2508.md` §6 の 1 件目 (受入 3) は、この付録で解決した。2508 付録は測定時点の記録のため本文は書き換えない。
