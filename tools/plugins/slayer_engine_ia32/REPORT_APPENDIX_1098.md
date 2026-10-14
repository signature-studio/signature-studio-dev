# REPORT_APPENDIX_1098 — Slayer_Engine.dll (block22434) の .text を ia32 x64c で lift (#1098)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §11 (結論 1 行)。 本付録が測定値の正本。
- 測定 commit: `c6b52428` (`mov_seg` の ia32 平坦化と区間統計 `gap_stats` を含む)。 変更前の `a7a32ea1` と lift 出力 (`ott_lifted.c`・`lift_meta.json`) は完全一致。 以降のコードは変えていない (差分の確認は PR 本文)。
- 入力: `block22434_PE.bin` (179,512 B, sha256 `84b64c43…de724a9`、fl-win64 素材)。 `.text` VirtualSize 73,002 B、VA `0x10001000`〜`0x10012d2a`。
- 関係する既知類型 (`docs/DEFECTS.md`): 新規の silent miscompile 類型の候補は無し。 絶対 VA (ia32 の jump table・IAT の disp32) は既存の D11 (VA リテラル) と同型の扱いで、`jt_check.py`・`iat_check.py` で実データと突合した。 `fs:` の TEB 参照と `sahf` の AF は silent divergence の候補で、§7 の通り #1223 へ送る。
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
- `.text` 内の reloc 値 (jump table の外) は root に**入れない**。 理由は §3。
- 逆アセンブル (線形掃引) は使わない。 data-in-code で命令境界がずれ、線形掃引の起点は lift の起点と一致しないため (例: VA `0x1000a3db` は掃引で命令の先頭にならない)。 命令の起点は lift の再帰降下に従う。

## 2. 実測 (測定 commit `c6b52428`・HEAD で再現)

| 項目 | 値 | 再現・所要 |
|---|---|---|
| lift (x64c `--arch ia32 --closure 999`) | functions 465, insns 20,632, unlifted callees 0, imports 38, jt 22 | `python3 tools/plugins/slayer_engine_ia32/lift_text.py`。 wall 4,349 / 4,447 / 4,763 ms (n=3)。 load 1 分 0.45 (実行後 0.36)、並列 1 (cpu 4) |
| 被覆 | 命令の起点 20,212 (distinct VA)、被覆 61,654 / 73,002 B (84.46%)、未被覆 11,348 B (239 区間) | `lift_text.py` の `[coverage]` 行。 命令数 20,632 との差 420 は、同じ VA が複数の関数に重複して lift されるため (VA 362 個が複数の関数に出現、最大 5 重。 例: 0x1000a4f4 は `f_1000a4f1` と `f_1000a4f4` の両方に出る)。 `ninsn` は関数ごとの和 |
| `emcc -c` | 代替: `gcc -c -O1 -w` を `emcc` 名のラッパで呼んだ (本 runner に emcc 無し)。 rc 0、object 880,904 B | 前版 (emcc 6.0.12) の rc 0・594,830 B は本版で再現しない (代替と比較しない)。 生成 C がコンパイルできることの確認のみ |
| jump table (22 表) | switch 表 22 本、case 値合計 181、生データ一致 **22/22** | `python3 tools/plugins/slayer_engine_ia32/jt_check.py <C> <lift_meta.json> <PE>`。 `[jt] OK`。 ネガコンは前版で FAIL を確認 (本版では再実行していない。 判定ロジックは未変更) |
| dispatcher 0x100014a4 (既存 gate) | `tools/ott/lift/verify_ia32_jt.py` (変更なし) | 前版で `[jt] OK`。 本版では未再実行 |
| IAT 参照 (絶対 disp32) | IAT slot を指す絶対 disp32 の参照 75 件。 75/75 で `imp_<name>` が PE import directory の名前と一致 | `python3 tools/plugins/slayer_engine_ia32/iat_check.py <C> <PE>`。 `[iat] OK`。 ネガコンは前版で FAIL を確認 (本版では未再実行) |
| gate C1〜C4 (既存) | `[measure] OK (4/4)`。 wall 589 / 595 / 602 ms (n=3) | `FL_WIN64_DIR=… python3 tools/plugins/slayer_engine_ia32/measure.py` |
| ネガコン N1〜N3 (既存) | `nega: 0/3 miss`。 wall 1,612 / 1,619 / 1,621 ms (n=3) | `measure.py --nega` |
| ia32 closure 2 (root 0x10007ca0) | 変更前 (`a7a32ea1`) と新 (`c6b52428`) で C 出力・lift_meta が完全一致 (8 関数・301 命令) | `cmp` (作業ファイルは `$RUNNER_TEMP`) |
| x64 回帰 | PR の分岐元 `26f90ada` と新で、素材 x64 PE (`*_PE.bin`、machine 0x8664、258 本) のうちサイズ順の先頭 8 本を EntryPoint root・closure 2 で lift。 `ott_lifted.c`・`lift_meta.json` が一致 8/8。 うち 7 本は 23 関数・593 命令、1 本は 1 関数・0 命令 | 同じ入力を旧版 `x64c.py` (`git archive 26f90ada`) と新版で実行して `cmp` |

## 3. 未被覆域の内訳と取りこぼし

`lift_text.py` の `[gap]` 行 (測定 commit `c6b52428` の出力)。 定義は `gap_stats` の docstring。

```
[gap] 未被覆区間 239 個 (計 11348 B)。 最大 0x1000ed9d〜0x1000f3e5 (1608 B)
[gap] jt 表 22 本 (計 800 B) のうち未被覆域 766 B (区間ごとの和。 表どうしの重なりを除いた一意バイトは 754 B)
[gap] reloc (jt の外・値が .text) 76 本のうち、未被覆域の値を含む区間 4 個
[gap] 直接 call/jmp/jcc の先を含む区間 5 個 (7 本)
[gap] 上記のどちらも含まない区間 230 個 (9220 B)
```

- 区間 = `cov==0` の連続域。 reloc 値 = `.text` 内の HIGHLOW (type 3) のうち、位置と値が共に jt の外で、値が `.text` を指すもの。 直接分岐 = 線形掃引 (CS_MODE_32) の call/jmp/jcc の rel 先 (掃引の境界ずれを含む上限)。
- 未被覆 11,348 B には jump table の生データ (766 B) が含まれる。 表はデータであり命令ではないため、被覆の定義上は未被覆に入る。
- 撤回: 前版の「未被覆 11,348 B のうち 204 B は jump table」は算出根拠を再現できないため撤回する。 前版の区間数 (reloc 17 区間・値 86 本・直接分岐 5 区間・217〜222 区間) も定義を書かずに算出したもので再現できなかったため、上の定義で再計算した値に置き換えた。
- 撤回: 前版にあった「`.text` 内 reloc 86 本を roots に加える試験 (330 roots・被覆 87.32%)」は再現手順が無いため本版から外す。 採用しない方針は変わらない (加えると arpl・pop ss・popfd の unsup が出る。 data を命令として読む兆候)。
- 区間の判定 (命令か data か) は子 #2814 (PLG-G2-22) へ送る。

## 4. unsup の内訳 (lift 出力 `lift_meta.json`)

- 合計 4,136 件。 うち x87 (`f*`) 4,134 件 → #1099 (PLG-G2-9) の範囲。 (`x87 は ott_unsup に落としてよい` (#1098 備考))
- 非 x87 は 2 件: `std` 1 (DF 未モデル化) と `shld` 1 (32bit 二重シフト)。 → #2814。
- 本 PR で ia32 に追加した命令 (x64 は不変): `wait` (no-op)・`sahf` (AF は runtime が持たないため未反映)・`xlatb`・`repne scasb`・非 rep の `movsb`/`movsw`/`movsd`(文字列)/`stosb`/`stosw`/`stosd`・`fs:` 読み・`es/ds/cs/ss` 読み (`mov_seg`・`ea` とも平坦)。 (修正前 4,273 件 → 修正後 4,136 件)

## 5. 変更点 (`tools/ott/lift/x64c.py`・`tools/plugins/slayer_engine_ia32/lift_text.py`)

- すべて `IA32` の条件下でのみ有効 (`ia32_only` / `IA32 and ...`)。 x64 の出力は §2 の x64 回帰 8/8 で不変。
- commit `c6b52428`: `mov_seg` の ia32 分岐を `fs` だけから `fs/es/ds/cs/ss` に広げ、`ea()` と同じ経路にした (前版は `mov` 経由の `es/ds` だけ `Unsup`、他命令は平坦で不整合だった)。 現 closure に `es/ds` の mov 読みは出現せず、出力は変化なし (C・lift_meta が `a7a32ea1` と一致)。
- commit `c6b52428`: `lift_text.py` に `gap_stats` (§3 の `[gap]` 行) を追加。
- DF は前提 0 (`rep()` と同じ)。 `std` は未対応 (§4)。
- 新規ファイル (前版から): `lift_text.py` (roots 作成→ lift → `emcc -c` → 被覆 → 区間内訳)、`iat_check.py`、`jt_check.py`。

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64      # extracted/block22434_PE.bin を展開済みであること
# emcc が無い環境: `emcc` 名で `gcc -c -O1 -w "$@"` を呼ぶラッパを PATH に置く (本版はこれで実行。 object サイズは emcc と一致しない)
python3 tools/plugins/slayer_engine_ia32/measure.py --dump        # gate C1〜C4
python3 tools/plugins/slayer_engine_ia32/lift_text.py             # roots → x64c → emcc -c → 被覆 → [gap]
O=tools/plugins/slayer_engine_ia32/work/lift_text
python3 tools/plugins/slayer_engine_ia32/jt_check.py $O/ott_lifted.c $O/lift_meta.json $FL_WIN64_DIR/extracted/block22434_PE.bin
python3 tools/plugins/slayer_engine_ia32/iat_check.py $O/ott_lifted.c $FL_WIN64_DIR/extracted/block22434_PE.bin
FL_PE=$FL_WIN64_DIR/extracted/block22434_PE.bin python3 tools/ott/lift/verify_ia32_jt.py $O/ott_lifted.c
```

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` の未被覆 11,348 B (239 区間) の判定と lift | 受入 1 の「`.text` 全体」は 84.46% (§2) | #2814 (PLG-G2-22、親 #1098) |
| `.text` 内 reloc 値 (jt の外) の扱い (§3 の 76 本) | 区間判定と合わせて #2814 で決める | #2814 |
| `std` (DF) と `shld` の lift | unsup 2 件 | #2814 |
| x87 (`f*` 4,134 件) | 本 issue の対象外 (ott_unsup のまま) | #1099 (PLG-G2-9) |
| 実行時の間接 call 先 (`ott_dispatch`) と、native との差分 | 実行の正しさは未検証。 `emcc -c` (代替) と静的検査のみ | #1223 (PLG-G2-11) |
| `sahf` の AF 未反映 (runtime に fAF が無い) | AF を読む命令 (BCD 系) は本 lift で未確認 (推定: 出現しない)。 silent divergence の候補 | #1223 (PLG-G2-11) へ送る |
| `fs:` (TEB) の読みは `tools/ott/rt/ott_cpu.c` の `ott_teb_blk` (0 埋め模型) を指す | TEB の実値を読む命令があれば silent divergence の候補 | #1223 (PLG-G2-11) へ送る |
