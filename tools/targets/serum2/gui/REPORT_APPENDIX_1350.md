# REPORT 付録 — VSTGUI 14.0〜14.3 の版確定 (#1350, 2026-10-14 run)

- 親: `REPORT.md` §11 (差分リテラル法は不可と確定)。本付録は §11 の残件を逆アセンブル突合で扱った結果。
- 入力: `work/Serum2_win64.vst3` (前 run の記録 sha256 `501e7bb3dd9cafe4…` / 19,236,864 B)。**本 run では `plugins-serum2` が無く `work/` が空のため、sha256 の照合と §2-2・§5 の再実行は未実施** (§6 参照)。
- 基準: `work/vstgui4` (blobless clone, tag `vstgui4_14_0` 〜 `vstgui4_14_3`)。
- 検証起点: `388bf469` (本 PR の唯一の commit = 測定時点のコード変更の最後)。以降の差分は §6 に記録。

## 1. 結論

| 版 | 判定 | 根拠 |
|---|---|---|
| 14.3 | **除外** | `setMouseCursor` の jump table 範囲検査が `cmp eax,0xA` (case 値 1〜11)。14.3 は enum 追加で最大 case が 13 (`kCursorMoveObject`) となり `cmp eax,0xC` になるはず |
| 14.0 / 14.1 / 14.2 | **未確定 (残る)** | 同じ範囲検査 (0xA) と整合。14.1→14.2 は Win32 のファイルに変更無し (`compare/vstgui4_14_1...vstgui4_14_2` の 9 ファイル: `vstguibase.h` の `PATCHLEVEL` 1→2、`lib/platform/linux/` の 3 ファイル、cmake 3 ファイル)。Win32 バイナリには入らないため、コード側に区別点が無い |

- 14.x 全体の確定 (§10) と 13.x 除外 (§10) は変更無し。
- **#1350 の受入条件 1 (14.0〜14.3 のどれかを確定) は未達。** 14.3 を除外したのみ。部分達成のため `Refs #1350`。

## 2. 手法と実測

### 2-1. enum と switch の対応 (ソース)

| tag | `CCursorType` の最大 case | `setMouseCursor` 内 `IDC_SIZEALL` の case 数 |
|---|---|---|
| 14.0 | 11 (`kCursorCrosshair`) | 1 (`kCursorSizeAll`) |
| 14.2 | 11 | 1 |
| 14.3 | 13 (`kCursorMoveObject`、`kCursorMovableObject`=12 を追加) | 2 (`kCursorSizeAll` と `kCursorMoveObject`) |

- 14.3 では `kCursorMovableObject` と `kCursorMoveObject` が enum の末尾に追加される。`kCursorHand` は alias (`= kCursorPointingHand`) となり case 値は変わらない。
- `IDC_SIZEALL` の case は 14.3 で 2 件になるが、コンパイラは同一本体の case を統合するため、即値の出現数では区別できない (`cursor_switch_scan.py` の初版で確認)。

### 2-2. バイナリの jump table 範囲 (実測)

`gui/cursor_switch_scan.py`: `.text` 内で `mov edx/eax, 0x7F86` (IDC_SIZEALL = 32646) を含む関数は **2 件** (RVA `0x172140`〜`0x1727f1`、`0x172800`〜`0x1729b5`)。両者ともカーソル ID 即値の集合が一致 (`IDC_SIZENS` `IDC_SIZENWSE` `IDC_SIZEWE` `IDC_NO` `IDC_HAND` `IDC_SIZEALL` `IDC_SIZENESW` `IDC_CROSS` `IDC_ARROW` `IDC_WAIT`) し、Win32 `setMouseCursor` の LoadCursor 集合と一致。

`gui/cursor_switch_bound.py 172800 1729b5` の逆アセンブル抜粋:

```
17280b: lea eax, [rdi - 1]
17280e: cmp eax, 0xa
172811: ja 0x180172862     ; default へ
172813: lea rcx, [rip + 0x8d3aa6]   ; jump table
172821: jmp rax
```

(`0x172140` 系の関数の範囲検査は本 run では未確認。`cursor_switch_bound.py` は `172800 1729b5` の 1 関数のみ実行した。)

- 解釈: switch の case 値は 1〜11。14.0〜14.2 の enum (最大 11) と整合し、14.3 (最大 13 → `cmp 0xc`) とは整合しない。
- 注: 本判定は「バイナリの switch がソースの `setMouseCursor` に対応する」前提に依る。関数名は stripped で未確定。2 関数とも同じ case 集合のため、対応は高確度と判断するが、確定は未実施。

### 2-3. 他の手段で区別できなかったもの

| 手段 | 結果 |
|---|---|
| `VSTGUI_VERSION_*` マクロ | `getVstGuiVersion()` のみ使用。14.x では全て `(4<<16)+14` の同一値 (バイナリ内 10 件) |
| クラス宣言集合 (`class`/`struct` 808 件) | 14.0 と 14.3 で同一 |
| `D2DFont::initialize` (14.1 で追加) | バイナリに該当 mangled 名 0 件 (名前は stripped と推定)。14.0 と 14.1 の区別は未実施 |
| 14.0→14.1 の差 | CRowColumnView・vst3editor 等にコード差あり。ただし即値・定数として残る差分は確認できず (未確定) |

## 3. 残件

- 14.0 / 14.1 / 14.2 の確定。方法候補: (1) 14.0→14.1 の `d2dfont.cpp` `CustomFonts` コンストラクタ差 (`once_flag` 除去・引数化) を関数本体で突合する。`getCustomFonts` の `std::call_once` 有無がバイナリ側で見えるかが分かれ目。(2) 14.1→14.2 はコード差なしのため、確定にはこの手法では不可 (Linux 側 `cairographicscontext` のみ差があり、Win32 バイナリには入らない)。
- 起票先: #1350 (本 issue の残作業として継続)。

## 4. 再現手順

```sh
# tools/targets/serum2/ を cwd・work/ は gitignore。§9-1 で work/Serum2_win64.vst3 と work/vstgui4 を用意
python3 gui/cursor_switch_scan.py     # IDC_SIZEALL 含有関数の列挙
python3 gui/cursor_switch_bound.py 172800 1729b5   # 関数範囲の switch 範囲検査
```

## 5. 実測 (本 run, コミット済み HEAD の worktree で再実行)

| スクリプト | 所要 (real, 逐次) | maxrss | 出力 |
|---|---|---|---|
| `cursor_switch_scan.py` | 1.31 s | 51,504 KB | 関数 2 件・各 10〜11 件のカーソル ID 即値 |
| `cursor_switch_bound.py 172800 1729b5` | 0.07 s | 51,164 KB | `cmp eax, 0xa` を含む範囲検査 |

- 実行時の system load: `uptime` の 1 分平均 0.00 (23:19 時点)。計測は単発 (逐次 1 回)。
- 出力先は gitignore の `work/` (`scan_out.txt` / `bound_out.txt`)。
- **注: §5 の数値は 388bf469 のスクリプトで取った前 run の値。** 後続 commit (`4a834e8c`) で `cursor_switch_scan.py` の数値抽出を正規表現に変えたため、§5 の再測定は未実施 (素材無し)。

## 6. 検証起点と証跡 (レビュー指摘 5・6・7 への対応)

- 測定起点 commit: `388bf469` (§5 の数値の取得元)。
- 後続の修正: `4a834e8c` (DOC_MAP 索引・本付録の記述訂正・スクリプトの operand 解析修正・括弧追加)。
- `git diff 388bf469 HEAD -- tools/targets/serum2` (実測の入力側に当たるのは `cursor_switch_scan.py` のみ):
  `REPORT_APPENDIX_1350.md` 8 行、`cursor_switch_bound.py` 1 行、`cursor_switch_scan.py` 12 行の変更 (コード変更は `4a834e8c` の 1 commit)。
- `git status --porcelain` (PR ブランチの worktree): 変更なし (commit 後)。
- `find tools/targets/serum2 -size +20M`: 0 件。
- **素材不在の確認**: `$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ。`plugins-serum2` 無し・`Serum2_win64.vst3` は `find /` でも無し。よって sha256 照合・§2-2 の両関数の再実行・§5 の n=3 再測定は **本 run では未実施**。PR 本文に `oc_artifacts: plugins-serum2` を入れて次回 run で行う。
- 新しい operand 解析は合成入力で確認: Capstone が出す `eax, dword ptr [rax + 0x7f00]` に対し、旧コード (`split` + `int(tok,16)`) は `ValueError: invalid literal for int() with base 16: '0x7f00]'` で落ち、新コードは `0x7f00` を抽出する。
