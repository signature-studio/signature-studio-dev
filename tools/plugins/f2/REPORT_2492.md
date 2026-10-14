# tools/plugins/f2 REPORT_2492 — PLG-F3-29 (#2492): 0x407a20 の間接呼出し元の道具の修正と検算 (測定 commit 5c25928b、block19148)

- 測定 commit: **5c25928b** (`fptr_callers.py` に VA 自身の参照検索を追加、`rawref_scan.py` を新規追加。道具 2 本のコードを変えた最後の commit。`unicorn_trace.py` は main 取り込みの merge 6b59426f で変わった)。base は aa30a245 (`0x407a20` の旧 §17 を追加した commit。REPORT_1305 の §17 は main の #2493 の節に置き換わったため、本件の正本は本ファイル)。本ファイル・REPORT_1305.md・docs/DOC_MAP.md は文書のみの commit。
- 既知類型との関係: (DEFECTS.md) 該当なし。capstone の disp 依存は (icall §4) D9 と同じ依存先。§5 参照。
- 担当 dir: `tools/plugins/f2/` のみ。素材の抽出物と NC コピーは `$RUNNER_TEMP/ex/` (リポジトリ外・gitignore 対象外だが commit しない)。
- 範囲: 静的解析のみ。unicorn の実経路は main 取り込み後の HEAD (30dd79d0) で測定し、検証 HEAD 6b59426f で再実行した (§3。取り込みで `unicorn_trace.py` が main 側の版に変わった)。

## 0. 結論

1. 道具 `fptr_callers.py` は、指定 VA 自身について **qword 格納・rip 相対/絶対 disp・IMM (rel32・即値。call/jmp/jcc を含む)・4 バイト即値一致** の件数を出すようになった (指摘 B1)。実 PE で `0x407a20` は 4 種すべて **0 件**。
2. ネガティブコントロール (指摘 B2): `.data` の空き qword `0x867e78` に `0x407a00` を書いた PE で格納元 **2 件**、`0x407a20` を書いた PE で VA 自身の qword **1 件** を検出 (§2)。
3. capstone を使わない生バイト走査 (`rawref_scan.py`) は `0x407a20` の rip 相対・rel32 を **1 件** 返す。これはデータ表の偶然の一致で、命令ではない (§4)。`0x407a00` は道具の直接 call 9 件と一致。
4. 結論は不変: `0x407a00` の格納元は `.data` `0x867c88` (表 6 要素) の 1 件、要素 0 を呼ぶ間接 call は 3 件、実経路上は `0x4093ae` の 1 件。
5. 未解決 `[0x5bac78]` (= 0x40eb30) の表の特定は子 #2574 にコメントで追記 (§7)。#2468 は PR #2526 で閉じた。

## 1. 道具の変更 (5c25928b)

- `fptr_callers.py`: 各 VA について「VA 自身への参照」節を追加 (qword 格納 / rip 相対・絶対 disp / IMM / .text 内の 4 バイト即値一致)。囲む関数 F の出力 (格納元・表・直接 call/jmp 元) は従来どおり。`git diff aa30a245 5c25928b -- tools/plugins/f2/fptr_callers.py` = +14 −4。
- `rawref_scan.py` (新規、41 行): capstone を使わず、`.text` の全バイト位置 p で disp32 を符号付きで読み、直後の即値長 k ∈ {0,1,2,4} を仮定して飛び先 `p+4+k+disp32` を計算する。rip 相対と rel32 の検算に使う。

## 2. ネガティブコントロール (NC)

PE コピーの作り方 (リポジトリ外 `$RUNNER_TEMP/ex/nc/`):

- 入力: `block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`、5,904,384 B)。
- 埋め位置: VA `0x867e78` (`.data` VA 0x867000 ↔ raw 0x466000 より file offset `0x466e78`)。埋める前の値は `0000000000000000` を確認 (`.data` の空き)。
- 書く値: `0x407a00` (pos407a00.bin) と `0x407a20` (pos407a20.bin) を 8 バイト little-endian で上書き。

```sh
PY=$RUNNER_TEMP/f2venv/bin/python
mkdir -p $RUNNER_TEMP/ex/nc
$PY -c "import struct; d=open('$RUNNER_TEMP/ex/extracted/block19148_PE.bin','rb').read(); \
  [open('$RUNNER_TEMP/ex/nc/pos%x.bin'%v,'wb').write(d[:0x466e78]+struct.pack('<Q',v)+d[0x466e80:]) for v in (0x407a00,0x407a20)]"
$PY tools/plugins/f2/fptr_callers.py $RUNNER_TEMP/ex/nc/pos407a00.bin 0x407a00   # (a)
$PY tools/plugins/f2/fptr_callers.py $RUNNER_TEMP/ex/nc/pos407a20.bin 0x407a20   # (b)
```

| 対象 | 入力 | 期待 | 実測 (道具 5c25928b。36c6eef2 で実行。道具は 6b59426f でも不変のため有効 (§6)) |
|---|---|---|---|
| (a) 正の対照 | pos407a00.bin・0x407a00 | 格納元 2 件 | `qword 格納 (0x407a00): 2 件 ['0x867c88', '0x867e78']` |
| (b) 検出能力 | pos407a20.bin・0x407a20 | VA 自身の qword 1 件 | `VA 自身 qword 格納: 1 件 ['0x867e78']` |
| 実 PE | block19148・0x407a20 | VA 自身の 4 種 0 件 | qword 0・disp 0・IMM 0・4 バイト一致 0 |

## 3. 実測 (実 PE block19148、道具 5c25928b、逐次・単独。検証 HEAD 36c6eef2 と 6b59426f)

- `fptr_callers.py $PE 0x407a20 0x40eb30` (36c6eef2 で測定): n=3 (各回 rc 0)。wall **17.4・17.8・17.4 秒** (min 17.4 – max 17.8)、load (`/proc/loadavg` の 1 分値) 開始→終了 0.39→0.60・0.60→0.72・0.72→0.78。3 回の出力は md5 一致 (49 行)。
  - 0x407a20: 「VA 自身」の 4 種すべて 0 件。囲む関数 0x407a00。格納元 `0x867c88` 1 件 (表 6 要素)。要素 0 の参照 `0x4093ae`・`0x409455`・`0x41b294` (REPORT_1305 §15 の 3 件と一致)。
  - 0x40eb30: qword 格納 1053 件 (すべて `.text` 内 `0x401000`〜`0x866a4c` の埋め込み表。`.data` 0 件)、IMM 1 件 (`0x41b1a4`)。
- 検証 HEAD 6b59426f で再測定: `fptr_callers.py $PE 0x407a20 0x40eb30` n=3 (各回 rc 0)。wall **49.3・50.3・49.6 秒** (min 49.3 – max 50.3)、load (1 分値) 3.96→4.49・4.49→5.37・5.37→4.74。ランナーは 4 vCPU で、`dns-resolver`・`systemd-resolved` 等の他プロセスが CPU を使っていた。3 回の出力は md5 `7803f15c` (49 行) で一致。VA 自身の 4 種 0 件、格納元 `0x867c88` 1 件、要素 0 の参照 3 件、0x40eb30 の qword 格納 1053 件 (36c6eef2 の測定と同値)。wall は 36c6eef2 の 17.4〜17.8 秒より長いが、道具は 5c25928b から不変で、差は負荷によるもの。
- `unicorn_trace.py $PE 0x83efb0 -H -t 0x40f4fe -t 0x40eb30 -t 0x4093ae -q 0x8c3ca8 -m 2000000` (unicorn 2.1.4。30dd79d0 で測定し、検証 HEAD 6b59426f で再実行): 6b59426f で rc 0・wall 3.1〜3.8 秒 (n=3、load 4.3→5.2)。出力 md5 `c9061eee` (13 行) が 3 回一致。`trace 0x40f4fe` → `trace 0x40eb30` → `trace 0x4093ae` → `UC_ERR_READ_UNMAPPED rip=0x407a5e`。REPORT_1305 §15 の実経路の行と一致。
  - `git diff 30dd79d0 6b59426f -- tools/plugins/f2/unicorn_trace.py` = 30 行追加・13 行削除 (main 取り込み)。30dd79d0 版 (`git show 30dd79d0:…` を同じ引数で実行) と停止点・trace の順序は同じで、6b59426f 版では trace 3〜5 行に `([[rcx]+0x28] 未マップ) rax=… rbp=… [rax+0x28]=…` の欄が増える。
  - 「取り込み前 (1bda005d) と出力が全文一致」は 30dd79d0 時点の記録で、6b59426f では成立しない。

## 4. 生バイト走査の検算 (rawref_scan.py、capstone 不使用)

```sh
$PY tools/plugins/f2/rawref_scan.py $PE 0x407a20 0x407a00
```

- `0x407a20`: rel 1 件 `('0x403929', k=1)`、4 バイト一致 0 件。(検証 HEAD 6b59426f で再実行: rc 0、同じ結果)
- `0x407a00`: rel 9 件 (すべて k=0)。道具の直接 call/jmp 9 件 (先頭 8 件: `0x40796b`・`0x4079b9`・`0x408038`・`0x40807f`・`0x4081bd`・`0x408303`・`0x408371`・`0x418ecd`) と、命令先頭 + 1 の位置で一致 (9 件目は `0x418ece` 側)。
- `0x403929` の判定 (偽陽性): pdata 関数の外の `.text` 内データで、ここから線形逆アセンブルすると `add byte ptr [rax], al` の列になる。読まれる disp32 は `0x000040f2` で、周辺は qword `0x40f240`・`0x40f250`・`0x40f260`・`0x40f230` の列 (`40 f2 40 00 00 00 00 00` …)。k=1 を仮定したときだけ `0x40392e + 0x40f2 = 0x407a20` になる偶然の一致で、命令としての参照ではない。よって 0x407a20 の命令参照は 0 件。

## 5. capstone の disp との関係 (icall §4 D9)

- 道具は capstone の `op.mem.disp` をそのまま使い、`disp_size` は見ない。D9 (66/F2 prefix 付き SSE rip 相対で capstone の結果が誤る) の形式の命令があると、その参照を取りこぼしうる。
- 本 PE では、同じ対象 (0x407a20) を capstone 非依存の走査で検算し、命令としての rip 相対・rel32 参照は 0 件で一致した。0x407a00 は道具の 9 件と一致。実害は確認していない。

## 6. 検証記録 (WORKFLOW §6)

- 依存 (REPORT_1305 §14 と同じ): `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone` (unicorn 2.1.4・pefile 2024.8.26・capstone 5.0.9)。
- 検証 HEAD: **6b59426f** (fc79dcf8 に main 81799351 を取り込んだ merge。競合は `docs/DOC_MAP.md` の表の行の追加のみ)。
- `git status --porcelain=v1 -- tools/plugins/f2` (検証 HEAD 6b59426f): 空。
- `git diff 5c25928b 6b59426f -- tools/plugins/f2/fptr_callers.py tools/plugins/f2/rawref_scan.py` = 0 行 (道具 2 本は測定 commit 以降変更なし)。`write_origin.py` (main の #2493) は本測定の対象外。
- `git diff 30dd79d0 6b59426f -- tools/plugins/f2/unicorn_trace.py` = 30 行追加・13 行削除 (§3)。
- `git diff aa30a245 5c25928b -- tools/plugins/f2`: `fptr_callers.py` (+14 −4) と `rawref_scan.py` (新規 +41) のみ。
- `git diff 5c25928b 30dd79d0 -- 'tools/plugins/f2/*.py'` = `unicorn_trace.py` のみ (main 取り込みで入った a70461d6 版)。`fptr_callers.py`・`rawref_scan.py` は 5c25928b から不変。unicorn 経路は取り込み後に再測定した (§3)。
- 20 MiB 超 blob: `find tools/plugins/f2 -type f -size +20M -not -path '*/work/*'` = 0 件。
- 生成物 (PE 抽出・NC コピー) は `$RUNNER_TEMP/ex/` に置き、リポジトリに入れていない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実経路の `0x40f4fe call [rax-0x30]` が読む表 `[0x5bac78]` (= 0x40eb30) の特定。0x40eb30 の qword 格納は 1053 件で、すべて `.text` 内の埋め込み表 (`0x5bac78` もその 1 件)。この道具では絞れない | `0x83efb0` から `0x4093a0` までの上流の一段が未確定 | #2574 (子 issue。2026-10-14 にコメント追記。`0x83efb0` を `0x411a80` まで届かせる経路の一部) |

## 8. 再現

```sh
PY=$RUNNER_TEMP/f2venv/bin/python
PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin
$PY tools/plugins/f2/fptr_callers.py $PE 0x407a20 0x40eb30     # §3 (n=3。wall は負荷依存: 17.4〜17.8 秒 (load 0.4〜0.8) / 49.3〜50.3 秒 (load 4〜5))
$PY tools/plugins/f2/rawref_scan.py $PE 0x407a20 0x407a00      # §4
$PY tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -t 0x40f4fe -t 0x40eb30 -t 0x4093ae -q 0x8c3ca8 -m 2000000   # §3
```
