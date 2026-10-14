# liftdiff REPORT 付録: LD-96 (#2258) heap 持ち越しによる sample:800 (shard 1) の件数揺れの切り分け

親 issue #1637 (LD-58)。前提は `REPORT_APPENDIX_LD58.md` §3・§7。

## 結論

- 受入 (a) 仮説検証: **部分達成**。shard 1 の全体 run で 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` の `s1` 列 mismatch) が揺れることを再現した。単独 run (同 19 関数のみ) では 19/19 `match`。
- 揺れは 19 関数を末尾に足す run の組み合わせに依存する (表 §2)。ただし `cmd_batch` の 400 件 chunk 境界と runner の作り直しが各 run で変わるため、**二分の結果は chunk 境界と交絡しており、原因範囲は特定できなかった**。
- 受入 (b) 原因の分類 (heap の残りか、別の状態か): **未達**。
- 受入 (c): 測定 commit と差分は §4・§8.7。
- 追補 (§8・計測 commit `7d434168`): 高水位外の heap 残存は wasm 側だけに出る (数値は `results/ld96_heap_residue_summary.tsv`)。残存 0 の関数も揺れるため、残存だけでは揺れを説明できない。(a)(b) は未達のまま。

## 1. 測定条件

- 測定 commit: `a1d55799` (origin/main)。前版 (#2296) は `tools/liftdiff/REPORT_APPENDIX_LD96.md` と `results/ld96_heap_carryover_s1.tsv` のみ変更 (コード変更なし)。
- 測定 runner: 4 vCPU。`uptime` の load は全体 run 前後で 0.9 程度 (11:03 時点 0.94)。
- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`・`FL_WIN64_DIR`)。`work/` 側は `tools/liftdiff/work/m11`・`tools/m11/work` の既展開物を使用。
- 生データ: `tools/liftdiff/work/ld58/` (gitignore)。
- 本 PR 前版 (run A〜H) の詳細 (件数・wall) は **n=1** の記録。

## 2. 測定 (全て `--shards 1 --nobuild --state auto`)

shard 1 は 1 つの runner で順に流れる (`ldlib/session.py` `run_functions`)。`cmd_batch` は 400 件 chunk ごとに `run_functions` を呼ぶため、chunk 内だけで持ち越しが起きる。

| run | 流した関数 | 19 関数の mismatch | match |
|---|---|---|---|
| A | sample:800 全体 (shard 1, 2 chunk) | **19** | 0 |
| B | 19 関数のみ (`file:`) | 0 | 19 |
| C | 先頭 100 件 + 19 関数 | 0 | 19 |
| D | 先頭 200 件 + 19 関数 | 0 | 19 |
| E | 全体 run の順で 781 件 + 19 関数 | **19** | 0 |
| F | 先頭 390 件 + 19 関数 | 0 | 19 |
| G | 後半 391 件 + 19 関数 | **9** | 10 |
| H | G の前半 195 件 + 19 関数 | **1** | 18 |

- run A の件数: 342 / 248 / 210 (REPORT_APPENDIX_LD58 §7 の shard 1 と一致)。
- `wall` (実測): A 6m38.6s (`time` 出力)。B 25s (`done 25s`)。**C・D・E・F・G・H の wall は未記録** (`[batch] done` の値を本節に転記していない)。load は A 開始時点 (11:03) の `uptime` 0.94 のみ記録。
- ログの所在: 生ログ `work/ld58/*.log` は gitignore 対象 (`**/work/`) のためローカル保存のみ。repo 外で再現不可。
- 注: run E は 781 件 (run A から 19 関数を除いた順) の後ろに 19 関数を足したもの。run A と完全に同じ並びではない (19 関数が run A では途中に挟まる)。

## 3. 読み取り

- 19 関数だけ (B) や先頭 200 件までを前置した run (C・D) では揺れない。一方、781 件を前置した run (E) と、同じ 800 件の全体 run (A) では 19 件すべて揺れる。
- 後半 391 件 (G) では 9 件、その前半 195 件 (H) では 1 件だけ揺れる。揺れは段階的に変わるが、chunk 境界の影響を分離していないため、「どの関数の状態が効いたか」は言えない。
- 結論: 揺れは「どの関数が先に走ったか」に依存する。ただし heap 全域比較を入れていないため、heap の残りが原因かは未確定。
- 次の一手 (未実施): chunk 境界を固定する (`--chunk` 相当の引数追加、または `run_functions` を直接呼ぶ小さな driver) うえで、case 後に heap 全域を pristine と比較する計測を入れる。

## 4. 測定 commit と差分

- 前版の測定 commit: `a1d55799` (§1〜§5 の時点)。
- §8 の測定 commit: **`7d434168`** (`ld96_heap_audit.py`・`ld96_summarize.py` を最後に変えた commit。`rt/ld_core.h` は `5acd3ea8` から変えていない)。
- `git diff a1d55799 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py` は rt 変更のため 0 行ではない (§8.7 の差分は `7d434168` 以降で 0 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| heap 残り (`ld_model_reset` の hw 範囲外) が原因かの確定 (case 後に heap 全域を pristine と比較する計測) | 件数 360/361 の揺れの説明 | #2258 (残作業) |
| chunk 境界を固定した二分 (run H の 1 件の特定) | 揺れの個別特定 | #2258 (残作業) |
| 受入 (b) の原因分類 | LD-96 の完了条件 | #2258 を `Refs` のまま残す |

## 8. 追加測定 (本 PR): 高水位外の heap 残存の計測

計測 commit: **`7d434168`**。`rt/ld_core.h` の計数と対照 `audit=2` は `5acd3ea8` で入れた。`7d434168` は `ld96_heap_audit.py` と `ld96_summarize.py` だけを変え、対照を run `control` に分け、監査件数を側ごとに出す (rt は `5acd3ea8` と同一)。
本節の数値はすべて `7d434168` の HEAD で得た。前版 (`eeed0ced`・計測 commit `e7fec1b2`) の数値は、今回の再測定で置き換えた (§8.8)。

### 8.1 方法

- `rt/ld_core.h`: `audit=1` の case は、復元 (`ld_restore_all`) の前に **高水位 `max(ld_heap_hw, LD_HEAP_RESERVED)` より外側の非 0 バイト数**を
  `heap_left` (`n`・`first`・`last`) として出す。前 case の書込みが復元されずに残った量 (= 復元が見ない範囲) を見る。
  `audit` の無い case の挙動・出力は変えていない。
- 対照 `audit=2` (ネガティブコントロール): 計数の直前に、高水位より外の 8 の倍数の位置へ既知の 1 B (`0x5a`) を置き、計数の後に消す。
  `heap_left.n` が 1 になれば検出器は既知の残存を拾える。`ld96_heap_audit.py --control` は solo の先頭関数の先頭 case (pattern `z`) にだけ付ける。その関数は TSV では run `control` の行になり、solo の集計からは外す (§8.7)。
- `ld96_heap_audit.py`: 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` で r1=match かつ s1=mismatch) の全 case に `audit=1` を付ける。
  - `--mode solo`: 19 関数だけを 1 回の run で流す (対照)。
  - `--mode full --only-part N --audit-part N`: `cmd_batch` と同じ 400 件 chunk (N = 0・1) の全関数の先頭 case (pattern `z`) に `audit=1` を付ける。
    chunk は `run_functions` ごとに新しいランナーを立てるので、chunk 1 だけを流しても全体 run と同じ初期状態になる。
- `ld96_summarize.py`: `work/ld96/{solo,p0,p1}.jsonl` を集計し、`results/ld96_heap_residue.tsv` (関数ごと・819 行) と `results/ld96_heap_residue_summary.tsv` (run × side・対照行) を出す。
- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-m11`・`work-liftdiff` を展開。`--state auto` (`work/m11/boot_state.json`)・`--nobuild` 相当。
- wasm の再ビルド: `build_wasm.build(t, False)` は `work/m11/simd.c` が有れば再生成しない。素材版 (sha256 `d82e2759…`) をそのまま使う (§8.5・§8.7)。

### 8.2 対照 (ネガティブコントロール)

- `solo --control` で、先頭関数 `0x4150d0` の先頭 case に既知の 1 B を置いた。
  `results/ld96_heap_residue.tsv` の run `control` 行と `results/ld96_heap_residue_summary.tsv` の `control` 行: native `n=1`・wasm `n=1` (first = last = `0x160010`)。
- 同じ関数の chunk 1 (対照なし) の先頭 case は native・wasm とも `n=0` (`chunk1` 行の `native_z_n`・`wasm_z_n`)。対照の 1 B は実残存ではない。
- よって検出器は既知の残存を拾える。以下の「残存 0」は、この検出器で 0 と出たという意味。

### 8.3 19 関数 (solo と full) の結果

- solo (19 関数・1 run): 19/19 `match` (`ld96_heap_residue.tsv` の `verdict`。対照の `0x4150d0` は run `control`、残り 18 関数は run `solo`)。監査 case は solo 18 関数で native 198・wasm 194 (`ld96_heap_residue_summary.tsv` の `solo` 行。wasm の hang は 2 関数 `0x4bf600`・`0xb77200` の各 2 case (`p0`・`pall`) で、その 2 関数の wasm 監査は各 9 件)。solo 18 関数は全 case で残存 0 (`solo` 行の `native_z_n`・`wasm_z_n`・`native_max_n`・`wasm_max_n` がすべて 0)。
- full (`chunk0` の該当 1 関数 + `chunk1` の 18 関数): 19/19 `mismatch` (§7 と一致。`chunk0`・`chunk1` 行の `verdict`)。wasm の先頭 case で残存がある関数は **3/19** (11 B。`0x4bf600`・`0xb77200`・`0x7850d0`。`chunk1` 行の `wasm_z_n` 列)。native は 0。
- **残存を持たない 16/19 関数は、残存 0 のまま mismatch**。高水位外の残存は 19 関数全体の揺れを説明しない。
- 上の 3 関数が持つ同じ 11 B (`wasm_z_first` 0x353eeb・`wasm_z_last` 0x37fffb) は、chunk1 全体では 14 関数に見える (`chunk1` 行で `wasm_z_n` = 11)。残存が揺れの原因かは未確定 (残存を消して結果が変わるかは未検証)。
- 19 関数の `mem_blocks` (列の定義は §8.7): 14 件に差分あり (3000 ブロックが 10 件・3002 ブロックが 3 件・1 ブロックが 1 件 = `0x7850d0`)。5 件は `-` (差分なし)。3000 と 3002 は rt の上限 `LD_MAX_BLOCKS` (3000) と一致するため、総数ではなく下限として扱う (§8.7)。

### 8.4 chunk 0・1 の全関数 (400 関数ずつ)

- chunk 0: 400 関数中 399 関数に先頭 case がある (`0x442b90` は `unexec` で case が無い。TSV で `native_audited_cases`・`wasm_audited_cases` が 0)。監査 case は native 409・wasm 409 (summary の `chunk0` 行)。**残存 0 (native・wasm とも全件)**: `native_max_n`・`wasm_max_n` は case のある 399 行すべて 0。
- chunk 1: 400 関数すべてに先頭 case がある。監査 case は native 580・wasm 576 (summary の `chunk1` 行。wasm の 4 case は `0x4bf600`・`0xb77200` の `p0`・`pall` で `hang`)。
  - native: 全 580 case で残存 0 (`chunk1` の 400 行すべて `native_max_n` = 0。非 19 関数は先頭 case のみ監査)。
  - wasm: 先頭 case で残存があるのは **124/400 関数** (summary の `chunk1 wasm` 行 `z_with_residue`)。残存量は **8 B 〜 53,463,205 B** (`z_n_min`・`z_n_max`)。1000 B を超えるのは 47 関数 (`z_n_gt_1000`)。残存量の合計は 2,512,771,101 B (`z_n_sum`)。`wasm_max_n` の非 0 行は 124 で、すべて `wasm_z_n` と一致する。
- 関数ごとの値は `results/ld96_heap_residue.tsv` の `chunk1` 行 (`wasm_z_n`・`wasm_z_first`・`wasm_z_last`)。
- 残存の大きさは 2 種類ある (同じ 124 行から集計): (i) 小 = 77 関数 (8 B が 63 件・11 B が 14 件・合計 658 B。いずれも 1000 B 以下)。(ii) 大 = 47 関数 (`first` 0x160010〜`last` 0x345c8e3 を両端含めて数えると 53,463,252 B。そのうち非 0 は 53,463,205 B (31 件) または 53,463,193 B (16 件)、すなわち 0 は 47 B または 59 B だけの dense な領域。合計 2,512,770,443 B)。合計 2,512,771,101 B の大半は (ii)。124 関数を 1 種類の残存として並べない。
- 残存は wasm 側だけに出る。native は 0。
- 残存の書き手・出現順は今回の計測では特定していない (未実施)。§8.8 の前版の観察も再確認していない。

### 8.5 観察: `liftdiff.py build` の simd.c 再生成

- `liftdiff.py build targets/m11.json` は `work/m11/simd.c` を再生成し、素材 (`work-liftdiff`) と内容が違った
  (sha256 `4c9ed1ff…` ≠ `d82e2759…`)。`ir_instr.ll`・`stubs.c`・`sigs.json`・`stubs.json` は素材と一致。
- 本測定は素材版の `simd.c` を使う (§8.7 の手順で `tar` から復元し sha256 を確認)。差の原因 (生成の非決定性か入力差か) は未確認。

### 8.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残存を持つ 124/400 関数 (wasm 側だけ) の書き手。残存を持たない 16/19 関数の揺れの原因 | 受入 (a)・(b) | #2258 (残作業) |
| 0x959a40 の wasm 側の書込みの書き手 (文脈として効いた前の関数・状態) | 受入 (b)。出所は同 runner で先行する 0x50abe0 の case 列 (`REPORT_APPENDIX_LD122.md` §4)。機構は未特定 | #2681 |
| 残存 (wasm) の出現元の確定と、wasm ランナ再起動による消去の検証 | 受入 (a) | #2258 (残作業) |
| `entry_arg` の表示差 (native 絶対 / wasm 相対) が比較の正規化の問題か | 比較結果の妥当性 | #2258 (残作業) |
| `liftdiff.py build` の simd.c 再生成と素材版の差 | 再現性 | #2258 (残作業・観察) |
| wasm の `hang` で heap_left が欠測した監査 case は、コミット済み測定で 4 件 (`0x4bf600`・`0xb77200`)。全 case の hang (再実行の raw で p0 101・p1 153 件) は TSV に入らない | 監査の対象外・欠測 | #2258 (残作業) |
| wasm の `hang` は run ごとに揺れる (§8.7 の再実行で `0xa9ece0` の先頭 case が hang し、残存が欠測) | 残存集計の再現性 | #2258 (残作業) |
| `0x7850d0` (chunk1) の mem 差分 1 ブロックの位置 (`r`・`o`) と、先頭 case の残存 11 B との関係 | 受入 (b) | #2258 (残作業) |

### 8.7 再現と差分

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"          # fl-win64 の extracted/block00031_PE.bin を含む展開先 ($ARTIFACTS_DIR は素材の置き場)
cd "$(git rev-parse --show-toplevel)"
tar --zstd -xf "$ARTIFACTS_DIR/work-liftdiff.tar.zst" tools/liftdiff/work/m11   # 素材版 simd.c・boot_state.json (--state auto が読む)・sigs.json など
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst"      # tools/m11/work (boot_final3.ll・m11_image.bin)
mkdir -p "$RUNNER_TEMP/fl-win64"
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" extracted/block00031_PE.bin
sha256sum tools/liftdiff/work/m11/simd.c | cut -c1-16   # d82e27592c03a316 でなければ停止
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
sha256sum work/m11/simd.c | cut -c1-16                  # 再ビルド後も d82e27592c03a316 のまま
python3 ld96_heap_audit.py --mode solo --control --out work/ld96/solo.jsonl
python3 ld96_heap_audit.py --mode full --only-part 0 --audit-part 0 --out work/ld96/p0.jsonl
python3 ld96_heap_audit.py --mode full --only-part 1 --audit-part 1 --out work/ld96/p1.jsonl
python3 ld96_summarize.py          # results/ld96_heap_residue.tsv・results/ld96_heap_residue_summary.tsv
git diff 7d434168 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/ld96_heap_audit.py tools/liftdiff/ld96_summarize.py | wc -l   # 0 (測定後のコード差分なし)
```

- 前提: `[EMSDK]` (`docs/REFERENCES.md`・素材 `toolchain-emsdk`) が展開済みであること。`build_wasm` は `emsdk_env.sh` を読む。`oc_artifacts` に `toolchain-emsdk` を含める。
- 生データは `work/ld96/` (gitignore)。集計 TSV は `results/ld96_heap_residue.tsv` と `results/ld96_heap_residue_summary.tsv` (コミット済み)。
- 所要 (**n=1**): solo 55.0 s。chunk 0 と chunk 1 を並列に流し、両方の完了まで 319.8 s (load 0.7〜1.2、4 vCPU)。wasm ビルド 8.9 s (link 3.3 s)。
- 再実行 (**n=2**・同じ手順を clean な worktree で直列に実行。2026-10-14): sha256 は再ビルド前後とも `d82e2759…`。solo 49.9 s・chunk 0 184 s・chunk 1 294 s (直列)・wasm ビルド 8.5 s。
  - 集計 TSV は、コミット済みの TSV と 819 行中 818 行が一致 (solo・chunk 0 と control は全行一致)。
  - 1 行だけ違う: `0xa9ece0` (chunk 1) の wasm 先頭 case が `hang` で欠測した (コミット済み測定では残存 53,463,193 B)。その結果、再実行の chunk 1 wasm は 123/400 関数・1000 B 超 46 関数・合計 2,459,307,908 B になる。
  - 本節の数値は、hang が出なかったコミット済み測定 (`7d434168` 時点) の TSV を指す。再実行の TSV は採用していない。
- 注: 所要は n=1 (solo・chunk) と n=2 (再実行) の値であり、min–max レンジは未計測。
- 列の定義 (`results/ld96_heap_residue.tsv`・1 行 = 1 関数 × run。run = `solo` / `chunk0` / `chunk1` / `control`。`control` は対照 `0x4150d0`):
  - `native_audited_cases`・`wasm_audited_cases`: 監査した case 数 (側ごと)。19 関数は全 case、非 19 関数は先頭 case の 1 件、`unexec` は 0。`control` 行は 11 件。
  - `native_z_n`・`native_z_first`・`native_z_last` (wasm 側も同じ): 先頭 case (pattern `z`) で高水位より外に残った非 0 バイト数 (`n`)。`first`・`last` は残存の最初と最後の非 0 バイトのオフセット。`-` は先頭 case が無い (`unexec`)。
  - `native_max_n`・`wasm_max_n`: 監査した全 case の `n` の最大。
  - `mem_blocks`: 監査 case のうち最初に `diffs.mem.count` を持つ case の値。`count` は `ldlib/compare.py` の `cmp_mem` が返す mem 差分ブロックの数 (`first` は先頭 8 件まで)。rt は 1 case の mem 差分の記録数を `LD_MAX_BLOCKS` (3000・`rt/ld_core.h:532`) で打ち切り、`mem_trunc`=1 を出す (`rt/ld_core.h:539`・`543`・`746`。カウンタは case ごとに 0 に戻る)。TSV に `mem_trunc` 列は無い (raw 非収録) ため、上限と一致する 3000・3002 の 13 件は総数ではなく下限として扱い、打ち切りの有無は未確認。`-` の意味は関数の種類で違う: 19 関数は詳細を取るので `-` = 差分なし。それ以外の関数は詳細を取らないので `-` = 未記録。
  - `0x7850d0` (chunk1) の `mem_blocks` は 1 (差分 1 ブロック)。この関数は先頭 case で wasm 残存 11 B も持つ。ブロックの位置は raw データ (非収録) にあり、残存との対応は未確認 (§8.6)。
- 列の定義 (`results/ld96_heap_residue_summary.tsv`・run × side): `functions` = 先頭 case を監査した関数数 (`solo` は対照を除く 18)。`audited_cases` = 監査 case 数。`z_with_residue` = 先頭 case で `n` > 0 の関数数。`z_n_min`・`z_n_max` = その `n` の最小・最大。`z_n_gt_1000` = `n` > 1000 の関数数。`z_n_sum` = `n` の合計。`control` 行は §8.2 の対照。

### 8.8 前版との差 (`eeed0ced`)

- 前版 (`eeed0ced`) の chunk 1 の残存件数・量は、今回の再測定で置き換えた (旧値は raw データが無く再現できないため記載しない)。差の原因 (計数の末尾の扱い・ビルドの違い・測定の揺れ) は未確認。
- 同じ rt・同じ素材・同じ手順で `7d434168` から測り直した結果、TSV の 819 行の `verdict`・`z`・`mem` の各列は `5acd3ea8` で得た TSV と 1 件も変わらなかった (対照行の run 名だけ `solo` から `control` に変えた)。`5acd3ea8` と `7d434168` の 2 回の測定は一致した。
- 前版の書き手の観察 (case の位置を示した記述) は、今回の TSV からは確認できないため撤回し、再確認していない扱いにする。
