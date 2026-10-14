# REPORT 付録 — VSTGUI 14.0〜14.3 の版確定 (#1350, 2026-10-14 run)

- 親: `REPORT.md` §11 (差分リテラル法は不可と確定)。本付録は §11 の残件を逆アセンブル突合で扱った結果。
- 入力: `work/Serum2_win64.vst3` (本 run で `plugins-serum2` から再展開し、sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B を照合して一致)。
- 基準: `work/vstgui4` (blobless clone, tag `vstgui4_14_0` 〜 `vstgui4_14_3`)。
- 測定 commit: `100cff73` (測定したスクリプトは `4a834e8c` と同一。`git diff 4a834e8c 100cff73 -- tools/targets/serum2/gui/cursor_switch_*.py` = 0 行)。検証 HEAD は §6 参照。

## 1. 結論

| 版 | 判定 | 根拠 |
|---|---|---|
| 14.3 | **除外** | `setMouseCursor` の jump table 範囲検査が `cmp eax,0xA` (case 値 1〜11)。14.3 は enum 追加で最大 case が 13 (`kCursorMoveObject`) となり `cmp eax,0xC` になるはず |
| 14.0 | **確定 (確度: 高)** | §3。`CustomFonts` 構築が `std::call_once` (`InitOnceBeginInitialize`) の直後にあり、14.0 の `getCustomFonts` と同構造。14.1 以降の `vstgui/` には `call_once` が 0 件 |
| 14.1 / 14.2 | **除外 (§3 の結論から)** | 上記の `call_once` 構造は 14.1 以降に存在しない。ただし §2-3 の通り差分関数側では 14.1 と 14.2 を分けられない |
| 14.3 | **除外** | §2 の `setMouseCursor` の範囲検査 (`cmp eax,0xA`) |

- 14.x 全体の確定 (§10) と 13.x 除外 (§10) は変更無し。
- **#1350 の受入条件 1 (14.0〜14.3 のどれかを確定) を達成。** 14.0 を確定し、14.1〜14.3 を除外した。ただし 14.1 / 14.2 の除外は §3 の 1 手法 (`call_once` 構造) に依る。確度は中で、§3 の注意に記す。

## 2. 手法と実測

### 2-1. enum と switch の対応 (ソース)

| tag | `CCursorType` の最大 case | `setMouseCursor` 内 `IDC_SIZEALL` の case 数 |
|---|---|---|
| 14.0 | 11 (`kCursorCrosshair`) | 1 (`kCursorSizeAll`) |
| 14.2 | 11 | 1 |
| 14.3 | 13 (`kCursorMoveObject`、`kCursorMovableObject`=12 を追加) | 2 (`kCursorSizeAll` と `kCursorMoveObject`) |

- 14.3 では `kCursorMovableObject` と `kCursorMoveObject` が enum の末尾に追加される。`kCursorHand` は alias (`= kCursorPointingHand`) となり case 値は変わらない。
- `IDC_SIZEALL` の case は 14.3 で 2 件になるが、コンパイラは同一本体の case を統合するため、即値の出現数では区別できない (`cursor_switch_scan.py` の初版で確認)。

### 2-2. バイナリの jump table 範囲 (実測, 測定 commit `100cff73`)

`gui/cursor_switch_scan.py` (実行出力は `work/scan_out.txt`):

- `.text` 内で `mov edx/eax, 0x7F86` (IDC_SIZEALL = 32646) を含む関数は **2 件**。
  - RVA `0x172140`〜`0x1727f1` (1,713 B): カーソル ID 即値 11 件 (`IDC_NO` 2 件を含む)
  - RVA `0x172800`〜`0x1729b5` (437 B): カーソル ID 即値 10 件
- カーソル ID の一意集合は両者とも同じ 10 種 (`IDC_ARROW` `IDC_WAIT` `IDC_CROSS` `IDC_HAND` `IDC_NO` `IDC_SIZEALL` `IDC_SIZENS` `IDC_SIZENWSE` `IDC_SIZENESW` `IDC_SIZEWE`)。Win32 `setMouseCursor` の LoadCursor 集合と一致。

`gui/cursor_switch_bound.py` の範囲検査 (両関数で実行):

```
# cursor_switch_bound.py 172140 1727f1
17247b: lea eax, [r13 - 1]
17247f: cmp eax, 0xa
172482: ja 0x1801724d3     ; default へ
172484: lea rcx, [rip + 0x8d3e09]   ; jump table
172492: jmp rax

# cursor_switch_bound.py 172800 1729b5
17280b: lea eax, [rdi - 1]
17280e: cmp eax, 0xa
172811: ja 0x180172862     ; default へ
172813: lea rcx, [rip + 0x8d3aa6]   ; jump table
172821: jmp rax
```

- 両関数とも `cmp eax, 0xa` / `ja` を 1 組ずつ持つ。`cmp eax, dword ptr [rcx + 0x28]` (`172900`、関数 `172800` 系の範囲内) は即値比較ではないため、本判定の対象外。

**ネガティブコントロール** (switch を含まない範囲に同じ検査を当てる):

| 範囲 | `cmp eax` / `ja` の一致 | `83 f8 0a` (`cmp eax,0xa`) の出現 |
|---|---|---|
| `172869`〜`172897` (`call` 2 件のみ) | 0 件 | 0 件 |
| `1721a1`〜`1721e7` (`cmp qword ptr [rdi], 0` 等) | 0 件 | 0 件 |

**バイト列の検算** (逆アセンブルとは別経路の `83 f8 ib` の数え上げ、`pefile` で `.text` を直接走査):

| 範囲 | `83 f8 0a` | `83 f8 0b` | `83 f8 0c` | `83 f8 0d` |
|---|---|---|---|---|
| `172140`〜`1727f1` | 1 | 0 | 0 | 0 |
| `172800`〜`1729b5` | 1 | 0 | 0 | 0 |
| `172869`〜`172897` | 0 | 0 | 0 | 0 |
| `1721a1`〜`1721e7` | 0 | 0 | 0 | 0 |

- 解釈: switch の case 値は 1〜11。14.0〜14.2 の enum (最大 11) と整合し、14.3 (最大 13 → `cmp 0xc`) とは整合しない。`0xc` の出現 0 件は 14.3 の想定と食い違う。
- 注: 本判定は「バイナリの switch がソースの `setMouseCursor` に対応する」前提に依る。関数名は stripped で未確定。2 関数とも同じ case 集合のため、対応は高確度と判断するが、確定は未実施。

### 2-3. 他の手段で区別できなかったもの

| 手段 | 結果 |
|---|---|
| `VSTGUI_VERSION_*` マクロ | `getVstGuiVersion()` のみ使用。14.x では全て `(4<<16)+14` の同一値 (バイナリ内 10 件) |
| クラス宣言集合 (`class`/`struct` 808 件) | 14.0 と 14.3 で同一 |
| `D2DFont::initialize` (14.1 で追加) | バイナリに該当 mangled 名 0 件 (名前は stripped と推定)。14.0 と 14.1 の区別は未実施 |
| 14.0→14.1 の差 | CRowColumnView・vst3editor 等にコード差あり。ただし即値・定数として残る差分は確認できず (未確定) |

## 3. 14.0 の確定 (差分 `d2dfont.cpp` の `call_once` 突合)

§2-3 で残件とした (1) を実施した。`d2dfont.cpp` の `CustomFonts` 構築が 14.0 のみ `std::call_once` 内にある (14.0 の `getCustomFonts`)。14.1 以降は `call_once` が 0 件 (`vstgui/` の `tests/` 除外) で、`D2DFont::initialize()` が直接構築する。

| 観測 (バイナリ, 測定 commit は §5) | 結果 | 判定 |
|---|---|---|
| `"Fonts\\*"` 文字列の出現 | RVA `0xfd82a4` に 1 件 | 唯一の参照元 `0x1a0c15` (関数 `0x1a0b40`) |
| `InitOnceBeginInitialize` の呼び出し箇所 | 2 件 (`0xf8ec2`, `0x182ccc`) | `0x182ccc` の直後 0x40 B 以内に `0x1a0b40` (`CustomFonts` 構築) の直接 call |
| `0x182ccc` 周辺の順序 | `InitOnceBeginInitialize` → `new` (`0x9a4b80`) → `0x1a0b40` → 保存 | 14.0 の `call_once` 内 `make_unique<CustomFonts>` と一致 |
| `0xf8ec2` 側 | 直接 call 先は thunk `0x9ad7ac` のみ | 別の一次初期化。`CustomFonts` 構築は含まない |

- **結論: 版は 14.0 と判定する (確度: 高)。** 根拠は 2 点。(a) バイナリの `CustomFonts` 構築が `InitOnceBeginInitialize` (= `std::call_once`) の直後にある。14.1 以降の `vstgui/` (`tests/` 除外) には `call_once` が 0 件のため、この形は 14.1〜14.3 からは生成されない。(b) 14.0 の `getCustomFonts` と同じ構造。
- したがって **14.1 / 14.2 / 14.3 は除外** (14.3 は §2 でも除外済み)。§2-3 で「14.1→14.2 は区別不可」としたのは差分関数側の話で、`call_once` の有無はそれを迂回して 14.0 vs 14.1+ を分ける。
- 注意: 関数名は stripped のため、`0x1a0b40` が `CustomFonts` であるとの同定は `Fonts\*` 文字列の参照元による推定。`call_once` の対象が `CustomFonts` であることも同じ推定に依る。

### 3-1. 再現手順

```sh
# tools/targets/serum2/ を cwd・work/ は gitignore。§9-1 で work/Serum2_win64.vst3 と work/vstgui4 を用意
python3 gui/callonce_probe.py    # 約 98 s (n=3, 96.8〜99.6 s, maxrss ~15 GB)
```

- 出力の判定: `site 0x182ccc -> direct calls within +0x40` に `0x1a0b40` が含まれれば 14.0 の `call_once` 構造と整合する。

### 3-2. 実測 (n=3, load 1 分平均 1.06〜1.14)

| 段 | real (s, n=3) | maxrss |
|---|---|---|
| `callonce_probe.py` | 98.34 / 96.81 / 99.63 | 15.07〜15.22 GB |

- 出力は 3 回とも一致。初版は全命令の二重ループで 5 分 (1 回) を要したため、近傍の逆アセンブルに直した。
- 残件: 14.1 / 14.2 の確定 (起票先: #1350 に残す)。

## 4. 再現手順

```sh
# tools/targets/serum2/ を cwd・work/ は gitignore。§9-1 で work/Serum2_win64.vst3 と work/vstgui4 を用意
python3 gui/cursor_switch_scan.py     # IDC_SIZEALL 含有関数の列挙
python3 gui/cursor_switch_bound.py 172800 1729b5   # 関数範囲の switch 範囲検査
python3 gui/cursor_switch_bound.py 172140 1727f1   # 同上 (2 件目)
```

## 5. 実測 (測定 commit `100cff73`、n=3)

| スクリプト | 所要 (real, 逐次, n=3) | maxrss | 出力 |
|---|---|---|---|
| `cursor_switch_scan.py` | 1.04 / 1.05 / 1.06 s (min 1.04, max 1.06) | 51,664〜51,704 KB | 関数 2 件・各 10〜11 件のカーソル ID 即値 |
| `cursor_switch_bound.py 172800 1729b5` | 0.07 / 0.07 / 0.07 s | 51,308〜51,320 KB | `cmp eax, 0xa` を含む範囲検査 |

- 測定時の system load: `uptime` の 1 分平均 0.50〜0.54 (23:36 時点)。計測は逐次。
- 所要の参考: 前 run (`388bf469` 時点、n=1) は scan 1.31 s / bound 0.07 s。本 run の scan は 1.04〜1.06 s で、同じスクリプト・同じ入力でも環境差がある。
- 出力先は gitignore の `work/` (`scan_out.txt` / `timing.txt`)。

## 6. 検証起点と証跡 (レビュー指摘 5・6・7 への対応)

- 測定 commit: `100cff73` (§2-2・§5 の数値の取得元)。測定時点の `tools/targets/serum2` のコードは `4a834e8c` と同一 (`git diff 4a834e8c 100cff73 -- tools/targets/serum2/gui/cursor_switch_*.py` = 0 行)。
- コード変更の最後の commit: `4a834e8c` (DOC_MAP 索引・本付録の記述訂正・スクリプトの operand 解析修正・括弧追加)。
- 素材: `$ARTIFACTS_DIR/plugins-serum2.tar.zst` を `tar --zstd -xf` で展開し `Install_Xfer_Serum2_2.1.5.exe` を取り出し、`7z x` で展開。`Serum2.vst3/Contents/x86_64-win/Serum2.vst3` = 19,236,864 B、sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` (REPORT §0 と一致)。
- `git diff 388bf469 HEAD -- tools/targets/serum2` の出力 (測定起点 `388bf469` からの差分、非空): `REPORT_APPENDIX_1350.md` 8 行、`cursor_switch_bound.py` 1 行、`cursor_switch_scan.py` 12 行の変更 (`4a834e8c` の 1 commit)。スクリプト部分の出力:

```diff
diff --git a/tools/targets/serum2/gui/cursor_switch_bound.py b/tools/targets/serum2/gui/cursor_switch_bound.py
index b8418ad9..f73bcbd0 100644
--- a/tools/targets/serum2/gui/cursor_switch_bound.py
+++ b/tools/targets/serum2/gui/cursor_switch_bound.py
@@ -25,7 +25,7 @@ def main():
     md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
     for i in md.disasm(data[off0:off1], base + start_rva):
         s = f"{i.address - base:x}: {i.mnemonic} {i.op_str}"
-        if i.mnemonic in ("cmp", "ja", "jbe", "jmp", "lea") or "[" in i.op_str and "rip" in i.op_str:
+        if i.mnemonic in ("cmp", "ja", "jbe", "jmp", "lea") or ("[" in i.op_str and "rip" in i.op_str):
             print(s)
     return 0
 
diff --git a/tools/targets/serum2/gui/cursor_switch_scan.py b/tools/targets/serum2/gui/cursor_switch_scan.py
index 57eefde8..b3c3eb7e 100644
--- a/tools/targets/serum2/gui/cursor_switch_scan.py
+++ b/tools/targets/serum2/gui/cursor_switch_scan.py
@@ -4,6 +4,7 @@
 入力: work/Serum2_win64.vst3 (REPORT §9-1 で展開)。
 出力: 各ヒットの関数開始 RVA (直前の int3/nop 境界から推定)、関数内の cursor ID 即値の一覧。
 """
+import re
 import sys
 import struct
 
@@ -40,12 +41,11 @@ def main():
                 break
         ids = []
         for i in md.disasm(data[start:end], va0 + start):
-            if i.mnemonic in ("mov", "lea", "cmp") and "0x7f" in i.op_str:
-                for tok in i.op_str.replace(",", " ").split():
-                    if tok.startswith("0x7f"):
-                        v = int(tok, 16)
-                        if 0x7F00 <= v <= 0x7FFF:
-                            ids.append((hex(i.address), v))
+            if i.mnemonic in ("mov", "lea", "cmp"):
+                for m in re.finditer(r"(?<![0-9a-fx])0x([0-9a-f]+)", i.op_str):
+                    v = int(m.group(1), 16)
+                    if 0x7F00 <= v <= 0x7FFF:
+                        ids.append((hex(i.address), v))
         print(f"hit RVA 0x{va0 + off:x}: func 0x{va0 + start:x}..0x{va0 + end:x} "
               f"({end - start} B), cursor-ID imm {len(ids)} 件")
         for addr, v in ids:
```
- `git diff 100cff73 HEAD -- tools/targets/serum2`: 本 commit で追加される差分は本付録 (docs) のみ。スクリプトの差分は 0 行。
- `find tools/targets/serum2 -size +20M`: 0 件。
- 新しい operand 解析は合成入力で確認: Capstone が出す `eax, dword ptr [rax + 0x7f00]` に対し、旧コード (`split` + `int(tok,16)`) は `ValueError: invalid literal for int() with base 16: '0x7f00]'` で落ち、新コードは `0x7f00` を抽出する。
