# liftdiff REPORT 付録: LD-96 (#2258) heap 持ち越しによる sample:800 (shard 1) の件数揺れの切り分け

親 issue #1637 (LD-58)。前提は `REPORT_APPENDIX_LD58.md` §3・§7。

## 結論

- 受入 (a) 仮説検証: **部分達成**。shard 1 の全体 run で 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` の `s1` 列 mismatch) が揺れることを再現した。単独 run (同 19 関数のみ) では 19/19 `match`。
- 揺れは 19 関数を末尾に足す run の組み合わせに依存する (表 §2)。ただし `cmd_batch` の 400 件 chunk 境界と runner の作り直しが各 run で変わるため、**二分の結果は chunk 境界と交絡しており、原因範囲は特定できなかった**。
- 受入 (b) 原因の分類 (heap の残りか、別の状態か): **未達**。
- 受入 (c): 測定 commit と差分は §4・§8.7。
- 追補 (§8・計測 commit `5acd3ea8`): 高水位外の heap 残存は wasm 側だけに出る (数値は `results/ld96_heap_residue_summary.tsv`)。残存 0 の関数も揺れるため、残存だけでは揺れを説明できない。(a)(b) は未達のまま。

## 1. 測定条件

- 測定 commit: `a1d55799` (origin/main)。本 PR は `tools/liftdiff/REPORT_APPENDIX_LD96.md` と `results/ld96_heap_carryover_s1.tsv` のみ変更 (コード変更なし)。
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
- §8 の測定 commit: **`5acd3ea8`** (`rt/ld_core.h`・`ld96_heap_audit.py`・`ld96_summarize.py` を最後に変えた commit)。
- `git diff a1d55799 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py` は rt 変更のため 0 行ではない (§8.7 の差分は `5acd3ea8` 以降で 0 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| heap 残り (`ld_model_reset` の hw 範囲外) が原因かの確定 (case 後に heap 全域を pristine と比較する計測) | 件数 360/361 の揺れの説明 | #2258 (残作業) |
| chunk 境界を固定した二分 (run H の 1 件の特定) | 揺れの個別特定 | #2258 (残作業) |
| 受入 (b) の原因分類 | LD-96 の完了条件 | #2258 を `Refs` のまま残す |

## 8. 追加測定 (本 PR): 高水位外の heap 残存の計測

計測 commit: **`5acd3ea8`** (`rt/ld_core.h` の計数に対照 `audit=2` と末尾 (8 の倍数でない部分) の計数を入れた commit。`ld96_heap_audit.py --control`・`ld96_summarize.py` の全関数対応を含む)。
本節の数値はすべて `5acd3ea8` の HEAD で得た。前版 (`eeed0ced`・計測 commit `e7fec1b2`) の数値は、今回の再測定で置き換えた (§8.6)。

### 8.1 方法

- `rt/ld_core.h`: `audit=1` の case は、復元 (`ld_restore_all`) の前に **高水位 `max(ld_heap_hw, LD_HEAP_RESERVED)` より外側の非 0 バイト数**を
  `heap_left` (`n`・`first`・`last`) として出す。前 case の書込みが復元されずに残った量 (= 復元が見ない範囲) を見る。
  `audit` の無い case の挙動・出力は変えていない。
- 対照 `audit=2` (ネガティブコントロール): 計数の直前に、高水位より外の 8 の倍数の位置へ既知の 1 B (`0x5a`) を置き、計数の後に消す。
  `heap_left.n` が 1 になれば検出器は既知の残存を拾える。`ld96_heap_audit.py --control` は solo の先頭関数の先頭 case (pattern `z`) にだけ付ける。
- `ld96_heap_audit.py`: 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` で r1=match かつ s1=mismatch) の全 case に `audit=1` を付ける。
  - `--mode solo`: 19 関数だけを 1 回の run で流す (対照)。
  - `--mode full --only-part N --audit-part N`: `cmd_batch` と同じ 400 件 chunk (N = 0・1) の全関数の先頭 case (pattern `z`) に `audit=1` を付ける。
    chunk は `run_functions` ごとに新しいランナーを立てるので、chunk 1 だけを流しても全体 run と同じ初期状態になる。
- `ld96_summarize.py`: `work/ld96/{solo,p0,p1}.jsonl` を集計し、`results/ld96_heap_residue.tsv` (関数ごと・819 行) と `results/ld96_heap_residue_summary.tsv` (run × side・対照行) を出す。
- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-m11`・`work-liftdiff` を展開。`--state auto` (`work/m11/boot_state.json`)・`--nobuild` 相当。
- wasm の再ビルド: `build_wasm.build(t, False)` は `work/m11/simd.c` が有れば再生成しない。素材版 (sha256 `d82e2759…`) をそのまま使う (§8.5・§8.7)。

### 8.2 対照 (ネガティブコントロール)

- `solo --control` で、先頭関数 `0x4150d0` の先頭 case に既知の 1 B を置いた。
  `results/ld96_heap_residue_summary.tsv` の `control` 行: native `n=1`・wasm `n=1` (first = last = `0x160010`)。
- よって検出器は既知の残存を拾える。以下の「残存 0」は、この検出器で 0 と出たという意味。

### 8.3 19 関数 (solo と full) の結果

- solo (19 関数だけ・1 run): 19/19 `match`。監査した case は native 209・wasm 205 (wasm の 4 case は `hang` で heap_left が出ない)。対照行を除き残存 0 (`summary` の solo 行の `z_with_residue` は対照の 1 件のみ)。
- full (`chunk0` の該当 1 関数 + `chunk1` の 18 関数): 19/19 `mismatch` (§7 と一致)。wasm の先頭 case で残存がある関数は **3/19** (11 B。`0x4bf600`・`0xb77200`・`0x7850d0`。TSV の `chunk1` 行の `wasm_z_n` 列)。native は 0。
- **残存を持たない 16/19 関数は、残存 0 のまま mismatch**。高水位外の残存は 19 関数全体の揺れを説明しない。
- 残存のある 3 関数は、同じ 11 B が見える。残存が揺れの原因かは未確定 (残存を消して結果が変わるかは未検証)。
- 19 関数の `mem` 差分 (`mem_blocks` 列) は 1・3000・3002 ブロック、または差分なし (`-`)。前版 (§8.4 旧) の「13 関数で 3000〜3002」の数え直しは今回行っていない。

### 8.4 chunk 0・1 の全関数 (400 関数ずつ)

- chunk 0: 400 関数中 399 関数に先頭 case がある (`0x442b90` は `unexec` で case が無い)。監査 case は native 409・wasm 409。**残存 0 (native・wasm とも全件)**。
- chunk 1: 400 関数すべてに先頭 case がある。監査 case は native 580・wasm 576 (wasm の 4 case は `0x4bf600`・`0xb77200` の `p0`・`pall` で `hang`)。
  - native: 全 580 case で残存 0。
  - wasm: 先頭 case で残存があるのは **124/400 関数**。残存量は **8 B 〜 53,463,205 B**。1000 B を超えるのは 47 関数。残存量の合計は 2,512,771,101 B。
- 具体的な値は `results/ld96_heap_residue.tsv` の `chunk1` 行 (`wasm_z_n`・`wasm_z_first`・`wasm_z_last`) と `results/ld96_heap_residue_summary.tsv` の `chunk1 wasm` 行を参照。
- 残存は wasm 側だけに出る。native は 0。
- 残存の書き手・出現順 (前版の観察: index 183 `0x47b4a0` の直後の case) は今回の計測で再確認していない。書き手の特定は未実施。

### 8.5 観察: `liftdiff.py build` の simd.c 再生成

- `liftdiff.py build targets/m11.json` は `work/m11/simd.c` を再生成し、素材 (`work-liftdiff`) と内容が違った
  (sha256 `4c9ed1ff…` ≠ `d82e2759…`)。`ir_instr.ll`・`stubs.c`・`sigs.json`・`stubs.json` は素材と一致。
- 本測定は素材版の `simd.c` を使う (§8.7 の手順で `tar` から復元し sha256 を確認)。差の原因 (生成の非決定性か入力差か) は未確認。

### 8.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残存を持つ 124/400 関数 (wasm 側だけ) の書き手。残存を持たない 16/19 関数の揺れの原因 | 受入 (a)・(b) | #2258 (残作業) |
| 0x959a40 の wasm 側の書込みの書き手 (文脈として効いた前の関数・状態) | 受入 (b) | #2258 (残作業) |
| 残存 (wasm) の出現元の確定と、wasm ランナ再起動による消去の検証 | 受入 (a) | #2258 (残作業) |
| `entry_arg` の表示差 (native 絶対 / wasm 相対) が比較の正規化の問題か | 比較結果の妥当性 | #2258 (残作業) |
| `liftdiff.py build` の simd.c 再生成と素材版の差 | 再現性 | #2258 (残作業・観察) |
| wasm の `hang` 4 case (`0x4bf600`・`0xb77200`) で heap_left が出ない | 監査の対象外 | #2258 (残作業) |

### 8.7 再現と差分

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"          # fl-win64 の extracted/block00031_PE.bin を含む展開先
export ARTIFACTS_DIR="${ARTIFACTS_DIR:-$HOME/artifacts}"
cd <repo root>
tar --zstd -xf "$ARTIFACTS_DIR/work-liftdiff.tar.zst" tools/liftdiff/work/m11/simd.c   # 素材版 simd.c に戻す
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst"      # tools/m11/work (boot_final3.ll・m11_image.bin)
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
git diff 5acd3ea8 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/ld96_heap_audit.py tools/liftdiff/ld96_summarize.py | wc -l   # 0 (測定後のコード差分なし)
```

- 生データは `work/ld96/` (gitignore)。集計 TSV は `results/ld96_heap_residue.tsv` と `results/ld96_heap_residue_summary.tsv` (コミット済み)。
- 所要 (**n=1**): solo 54.9 s (load 0.36)。chunk 0 と chunk 1 を並列に流し、両方の完了まで 321 s (load 0.5〜1.2、4 vCPU)。wasm ビルド 8.7 s。
- 注: n=1 の値であり、min–max レンジは未計測。

### 8.8 前版との差 (`eeed0ced`)

- 前版の数値 (「残存あり 120/400」「1 B 〜 53,463,188 B」「1000 B 超は 46 関数」) は、今回の再測定で「124/400」「8 B 〜 53,463,205 B」「47 関数」に置き換えた。差の原因 (計数の末尾の扱い・ビルドの違い・測定の揺れ) は未確認。
- 前版の raw データ (`work/ld96/`) は runner に残っていないため、前版の数値を再確認することはできない。
