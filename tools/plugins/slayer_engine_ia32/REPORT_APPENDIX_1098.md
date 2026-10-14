# REPORT_APPENDIX_1098 — Slayer_Engine.dll (block22434) の .text を ia32 x64c で lift (#1098)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §11 (結論)。 本付録は測定の全文。
- 測定 commit: `85c51739` (x64c 拡張と検査スクリプトを含む。以後コードは変えていない。 差分の確認は REPORT.md §11)
- 入力: `block22434_PE.bin` (179,512 B, sha256 `84b64c43…de724a9`、fl-win64 素材)。 `.text` VirtualSize 73,002 B、VA `0x10001000`〜`0x10012d2a`。
- 関係する既知類型 (`docs/DEFECTS.md`): 新規の silent miscompile 類型の候補は無し。 絶対 VA (ia32 の jump table・IAT の disp32) は既存の D11 (VA リテラル) と同型の扱いで、`jt_check.py`・`iat_check.py` で実データと突合した。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 関数境界の決め方 (根拠)

| 起点 | 取り方 | 実測 (distinct) | 根拠 |
|---|---|---:|---|
| R1 export | PE の export 表 | 1 (`main` = `0x10007ca0`) | `pe.DIRECTORY_ENTRY_EXPORT` |
| R2 データ中の関数ポインタ | `.reloc` の HIGHLOW 箇所のうち、場所が `.rdata`/`.data` で、値が `.text` を指すもの | 243 | vtable・関数ポインタ表 (`.reloc` は pefile で読む) |
| R3 code 中の即値 | 逆アセンブル (`mov`/`push`/`lea`) の即値で、値が `.text` を指すもの | 10 | AEffect の 5 本 (0x10001000・0x100010a0・0x10001080・0x10001060・0x100010c0) と global store 等 |
| R4 直接 call | x64c の closure (再帰降下・深さ無制限) | roots 254 から到達可能な分を追加し、計 465 | `call rel32` の先 |
| jump table | `jmp [idx*4+tbl]` の表 (x64c `jump_table`) | 22 表 (計 800 B) | case 値は表の生データと照合 (§2) |

- 合計 root は 254 (R1+R2+R3 の和)。 closure で 465 関数 (命令 20,632) になった。
- `.text` 内の reloc 値 (jump table の外、86 本) は root に**入れない**。 理由は §3。
- 逆アセンブル (線形掃引) は使わない。 data-in-code で命令境界がずれ、線形掃引の起点は lift の起点と一致しないため (例: VA `0x1000a3db` は掃引で命令の先頭にならない)。 命令の起点は lift の再帰降下に従う。

## 2. 実測 (測定 commit `85c51739`・HEAD で再現)

| 項目 | 値 | 再現・所要 |
|---|---|---|
| lift (x64c `--arch ia32 --closure 999`) | functions 465, insns 20,632, unlifted callees 0, imports 38, jt 22 | `python3 tools/plugins/slayer_engine_ia32/lift_text.py`。 wall 4,855 / 4,900 / 4,993 ms (n=3)。 load 1 分 0.22 → 0.25、並列 1 (cpu 4) |
| 被覆 | 命令の起点 20,212、被覆 61,654 / 73,002 B (**84.46%**)、未被覆 11,348 B (239 区間) | `lift_text.py` の `[coverage]` 行。 命令長は生バイトの capstone 単独デコードで求める |
| `emcc -c` | rc 0、object 594,830 B | `emcc -c -O1 -w -I tools/ott/rt ott_lifted.c` (toolchain-emsdk 6.0.12) |
| jump table (22 表) | switch 表 22 本、case 値合計 181、生データ一致 **22/22** | `python3 tools/plugins/slayer_engine_ia32/jt_check.py <C> <lift_meta.json> <PE>`。 ネガコン (表 1 本の 1 entry を XOR) で `[jt] FAIL` (21/22) |
| dispatcher 0x100014a4 (既存 gate) | `[jt] OK` (case 値集合 == 25 entry) | `tools/ott/lift/verify_ia32_jt.py` (変更なし)。 ネガコンで FAIL |
| IAT 参照 (絶対 disp32) | `call`/`jmp` の abs disp32 89 件のうち IAT slot 75 件。 75/75 で `imp_<name>` が PE import directory の名前と一致 | `python3 tools/plugins/slayer_engine_ia32/iat_check.py <C> <PE>`。 import 表は pefile を使わず生バイトで読む。 ネガコン (slot 名を 1 つ壊す) で FAIL |
| gate C1〜C4 (既存) | PASS 4/4、wall 634 / 640 / 638 ms (n=3) | `FL_WIN64_DIR=… python3 tools/plugins/slayer_engine_ia32/measure.py` |
| ネガコン N1〜N3 (既存) | `nega: 0/3 miss` ×3、wall 1,643 / 1,626 / 1,640 ms | `measure.py --nega` |
| ia32 closure 2 (root 0x10007ca0) | 旧 (`origin/main`) と新で C 出力が**完全一致** (8 関数・301 命令) | `cmp` (作業ファイル `$RUNNER_TEMP`) |
| x64 回帰 | x64 PE 8 本 (素材 `fl-win64` の `*_PE.bin`、EntryPoint を root・closure 2) で旧/新の `ott_lifted.c` と `lift_meta.json` が一致 8/8 | 2 本は 25 関数・660〜667 命令。 残り 6 本は 1 関数・命令 0 件 (回帰の範囲は小さい) |

## 3. 被覆の内訳と取りこぼし

- 未被覆 11,348 B は 239 区間。 うち 204 B は jump table (`jt_ranges` 外の表が残る)。
- 区間の参照を調べた (`work/gapref.py` 相当。 線形掃引の直接分岐と `.reloc` 値):
  - 直接分岐 (call/jmp) の先が区間内にある区間は **5** (掃引の境界ずれを含むため上限)。
  - `.reloc` の絶対値 (`.text` を指す、jump table の外) が区間内にある区間は **17** (値 73 本)。
  - 上の 2 条件のどちらにも当たらない区間は 217〜222 区間 (2 条件の重なりは未集計のため幅で示す)。 これは被覆内の命令からも reloc からも参照が無い区間で、prologue `55 8b ec` を持つものも含む (例: `.text+0xdd9d` 1,608 B)。
- 試験: `.text` 内の reloc 値 86 本 (jump table の外) を root に加えると 330 roots・544 関数・命令 25,312・被覆 **87.32%** (63,745 B) になるが、`arpl` 1・`pop ss` 1・`popfd` の追加 unsup が出る。 data を命令として lift した兆候のため採用しない。 区間ごとの判定は子 issue **#2814** に送る。
- 採用しなかった候補の扱い: 「`.text` 内 reloc」は、命令の即値・ポインタ・jump table の case 値が混在する。 jump table の外の値だけでは関数先頭と区別できない。

## 4. unsup の内訳 (lift 出力 `lift_meta.json`)

- 合計 4,136 件。 うち x87 (`f*`) 4,134 件 → #1099 (PLG-G2-9) の範囲。 (`x87 は ott_unsup に落としてよい` (#1098 備考))
- 非 x87 は 2 件: `std` 1 (DF 未モデル化) と `shld` 1 (32bit 二重シフト)。 → #2814。
- 本 PR で ia32 に追加した命令 (x64 は不変): `wait` (no-op)・`sahf` (AF は runtime が持たないため未反映)・`xlatb`・`repne scasb`・非 rep の `movsb`/`movsw`/`movsd`(文字列)/`stosb`/`stosw`/`stosd`・`fs:` 読み (`mov_seg`)・`es/ds/cs/ss` の平坦な上書き (`ea`)。 (修正前 4,273 件 → 修正後 4,136 件)

## 5. 変更点 (`tools/ott/lift/x64c.py`、commit `85c51739`)

- すべて `IA32` の条件下でのみ有効 (`ia32_only` / `IA32 and ...`)。 x64 の出力は、§2 の x64 回帰 8/8 で不変。
- DF は前提 0 (`rep()` と同じ)。 `std` は未対応 (§4)。
- 新規ファイル: `lift_text.py` (roots 作成→ lift → `emcc -c` → 被覆)、`iat_check.py`、`jt_check.py`。

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64      # extracted/block22434_PE.bin を展開済みであること
source /opt/emsdk/emsdk_env.sh
python3 tools/plugins/slayer_engine_ia32/measure.py --dump        # gate C1〜C4
python3 tools/plugins/slayer_engine_ia32/lift_text.py             # roots → x64c → emcc -c → 被覆
O=tools/plugins/slayer_engine_ia32/work/lift_text
python3 tools/plugins/slayer_engine_ia32/jt_check.py $O/ott_lifted.c $O/lift_meta.json $FL_WIN64_DIR/extracted/block22434_PE.bin
python3 tools/plugins/slayer_engine_ia32/iat_check.py $O/ott_lifted.c $FL_WIN64_DIR/extracted/block22434_PE.bin
FL_PE=$FL_WIN64_DIR/extracted/block22434_PE.bin python3 tools/ott/lift/verify_ia32_jt.py $O/ott_lifted.c
```

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` の未被覆 11,348 B (239 区間) の判定と lift | 受入 1 の「`.text` 全体」は 84.46% | #2814 (PLG-G2-22、親 #1098) |
| `.text` 内 reloc 値の 86 本 (jump table の外) の扱い (73 値は未被覆内) | 被覆 84.46% → 87.32% (未採用) | #2814 |
| `std` (DF) と `shld` の lift | unsup 2 件 | #2814 |
| x87 (`f*` 4,134 件) | 本 issue の対象外 (ott_unsup のまま) | #1099 (PLG-G2-9) |
| 実行時の間接 call 先 (`ott_dispatch`) と、native との差分 | 実行の正しさは未検証。 `emcc -c` と静的検査のみ | #1223 (PLG-G2-11) |
| `sahf` の AF 未反映 (runtime に fAF が無い) | AF を読む命令 (BCD 系) を本 lift で確認していない (推定: 出現しない) | 起票しない (限界の記述のみ) |
