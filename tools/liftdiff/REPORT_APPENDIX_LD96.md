# liftdiff REPORT 付録: LD-96 (#2258) heap 持ち越しによる sample:800 (shard 1) の件数揺れの切り分け

親 issue #1637 (LD-58)。前提は `REPORT_APPENDIX_LD58.md` §3・§7。

## 結論

- 受入 (a) 仮説検証: **部分達成**。shard 1 の全体 run で 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` の `s1` 列 mismatch) が揺れることを再現した。単独 run (同 19 関数のみ) では 19/19 `match`。
- 揺れは 19 関数を末尾に足す run の組み合わせに依存する (表 §2)。ただし `cmd_batch` の 400 件 chunk 境界と runner の作り直しが各 run で変わるため、**二分の結果は chunk 境界と交絡しており、原因範囲は特定できなかった**。
- 受入 (b) 原因の分類 (heap の残りか、別の状態か): **未達**。heap 全域比較の計測は未実施 (本 run の時間内に入らなかった)。
- 受入 (c): 測定 commit と差分は §4。
- 追補 (§8・計測 commit `e7fec1b2`): 高水位外の heap 残存は wasm 側だけに出る。19 関数中 3 件で 11 B。残存 0 の 16 件も全体 run でだけ揺れるため、残存だけでは揺れを説明できない。0x959a40 の差分は case 中の wasm 側の heap 書込みで、出所は未特定。(a)(b) は未達のまま。

## 1. 測定条件

- 測定 commit: `a1d55799` (origin/main)。本 PR は `tools/liftdiff/REPORT_APPENDIX_LD96.md` と `results/ld96_heap_carryover_s1.tsv` のみ変更 (コード変更なし)。
- 測定 runner: 4 vCPU。`uptime` の load は全体 run 前後で 0.9 程度 (11:03 時点 0.94)。
- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`・`FL_WIN64_DIR`)。`work/` 側は `tools/liftdiff/work/m11`・`tools/m11/work` の既展開物を使用。
- 生データ: `tools/liftdiff/work/ld58/` (gitignore)。

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

- 測定 commit: `a1d55799`。
- `git diff a1d55799 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py` は本 PR の時点で空 (コード変更なし)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| heap 残り (`ld_model_reset` の hw 範囲外) が原因かの確定 (case 後に heap 全域を pristine と比較する計測) | 件数 360/361 の揺れの説明 | #2258 (残作業) |
| chunk 境界を固定した二分 (run H の 1 件の特定) | 揺れの個別特定 | #2258 (残作業) |
| 受入 (b) の原因分類 | LD-96 の完了条件 | #2258 を `Refs` のまま残す |

## 8. 追加測定 (本 PR): 高水位外の heap 残存の計測

計測 commit: **`e7fec1b2`** (`rt/ld_core.h` に case フラグ `audit=1` と `ld96_heap_audit.py` を追加した commit)。
本文の数値はすべて `e7fec1b2` の HEAD で得た (§8.7 の差分は 0)。

### 8.1 方法

- `rt/ld_core.h`: `audit=1` の case だけ、復元 (`ld_restore_all`) の前に **高水位 `max(ld_heap_hw, LD_HEAP_RESERVED)` より外側の非 0 バイト数**を
  `heap_left` (`n`・`first`・`last`) として出す。前 case の書込みが復元されずに残った量 (= 復元が見ない範囲) を見る。
  `audit` の無い case の挙動・出力は変えていない。
- `ld96_heap_audit.py`: 19 関数 (`results/ld58_m11_sample800_shards_t1.tsv` で r1=match かつ s1=mismatch) の全 case に `audit=1` を付ける。
  - `--mode solo`: 19 関数だけを 1 回の run で流す (対照)。
  - `--mode full --only-part N`: `cmd_batch` と同じ 400 件 chunk (sample:800 を order_key で並べ替えた列の chunk 0・1) の一方を流す。
    chunk は `run_functions` ごとに新しいランナーを立てるので、chunk 1 だけを流しても全体 run と同じ初期状態になる。
  - `--audit-part 1`: chunk 1 の全関数の先頭 case (pattern `z`) にも `audit=1` を付ける (書き手の探索用)。
- 素材: `fl-win64`・`work-m11`・`work-liftdiff` を展開。`--state auto` (`work/m11/boot_state.json`)・`--nobuild` 相当。
- wasm の再ビルド: `liftdiff.py build` は `simd.c` を `m11_simd2.py` で再生成し、素材版と内容が違った (§8.5)。
  素材版の `simd.c` に戻して `build_wasm.build(t, False)` で再リンクした。native は `gcc -O1` で再ビルド。

### 8.2 19 関数の結果 (`results/ld96_heap_residue_19.tsv`)

| 測定 | 19 関数の verdict | 残存 (wasm・case 開始時) | 残存 (native) |
|---|---|---|---|
| solo (19 関数だけ) | 19/19 `match` | 全 case で 0 | 全 case で 0 |
| full (chunk 0 の 1 関数 + chunk 1 の 18 関数) | 19/19 `mismatch` | 3/19 関数で 11 B (0x4bf600・0xb77200・0x7850d0、offset `0x353eeb`〜`0x37fffb`) | 0 |

- full の 19/19 mismatch は §7 (前回 shard 1) と一致した。audit の計測で揺れの有無は変わっていない。
- **残存を持たない 16/19 関数は、残存 0 のまま mismatch**。高水位外の残存は 19 関数全体の揺れを説明しない。
- 残存のある 3 関数は、同じ 11 B が見える。残存が揺れの原因かは未確定 (残存を消して結果が変わるかは未検証)。

### 8.3 chunk 1 全体の残存 (`--audit-part 1`・400 関数)

- 先頭 case で残存がある関数: **120/400**。残存量は 1 B 〜 53,463,188 B (offset `0x1f0000` 以降に広がる)。
  1000 B を超えるのは index 244 (0x85a950) 以降で 46 関数。
- **native は audit した 575 case のすべてで残存 0**。残存は wasm 側だけに出る。
- 残存の最初の出現: index 183 (0x47b4a0・unexec・16 case) の直後の index 184 (0x6bba60) の先頭 case で **1 B** (offset `0x4b0c45`)。
  0x47b4a0 の `z` case は `both_fault` (native segv・wasm trap)。書き手は 0x47b4a0 の 16 case のいずれか (推定。case 単位の再計測は未実施)。
- 残存は wasm ランナの再起動 (hang・crash・timeout) で消えると推定 (未検証)。

### 8.4 0x959a40 の full 限定の diff (受入 (b))

- full の `p1`・`pall`・`qall` で `ret`・`mem`・`trace` が不一致。`mem` は 3000 ブロックで打ち切り。solo では同じ 3 case が `equal`。
- case 開始時の残存は 0 (§8.2)。**残存は 0x959a40 の差分の原因ではない**。
- `mem` の差分はすべて heap 領域 (offset `0x10000` 以降) で、wasm 側だけが `0xcccccccccccc…` (int3 パディングに見える) や機械語に見えるバイト列を書き、native は `unchanged(0x0)`。
  19 関数中 13 関数で `mem` 差分が 3000〜3002 ブロック (打ち切り上限 3000 付近) 出る。全体 run だけの現象 (solo では 0)。
- `trace` の `entry_arg`: `p1` の pos 1 で native `0x22476000` / wasm `0x5000`、`pall` の pos 0 で native `0x22472000` / wasm `0x1000`。
  `p1`・`pall` の引数は `a:0x5000`・`a:0x1000` (arena 相対)。native は絶対アドレス、wasm は相対値に見える。
  solo では同じ case が `equal` のため、比較の正規化の差か、文脈依存の wasm 側の値かは未確定。
- **出所は未特定**。文脈 (前の関数) への依存は確認できた (solo と full で結果が変わる)。残る候補は、wasm 側だけが持つ状態
  (IR モジュール自身の global・復元対象外の書込み可能領域) だが、未検証。

### 8.5 観察: `liftdiff.py build` の simd.c 再生成

- `liftdiff.py build targets/m11.json` は `work/m11/simd.c` を再生成し、素材 (`work-liftdiff`) と内容が違った
  (sha256 `4c9ed1ff…` ≠ `d82e2759…`)。`ir_instr.ll`・`stubs.c`・`sigs.json`・`stubs.json` は素材と一致。
- 本測定は素材版の `simd.c` に戻して再リンクした。差の原因 (生成の非決定性か入力差か) は未確認。

### 8.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残存を持たない 16/19 関数の揺れの原因 (case 中に wasm 側だけが heap へ書く経路) | 受入 (a)・(b) | #2258 (残作業) |
| 0x959a40 の wasm 側の書込みの書き手 (文脈として効いた前の関数・状態) | 受入 (b) | #2258 (残作業) |
| 残存の書き手の確定 (0x47b4a0 の faulting case は推定)・wasm ランナ再起動による消去の検証 | 受入 (a) | #2258 (残作業) |
| `entry_arg` の表示差 (native 絶対 / wasm 相対) が比較の正規化の問題か | 比較結果の妥当性 | #2258 (残作業) |
| `liftdiff.py build` の simd.c 再生成と素材版の差 | 再現性 | #2258 (残作業・観察) |

### 8.7 再現と差分

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"          # fl-win64 を展開した先
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 -c "import sys; sys.path.insert(0,'.'); from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
python3 ld96_heap_audit.py --mode solo --out work/ld96/solo_final.jsonl
python3 ld96_heap_audit.py --mode full --only-part 0 --out work/ld96/p0_final.jsonl
python3 ld96_heap_audit.py --mode full --only-part 1 --audit-part 1 --out work/ld96/p1_audit.jsonl
python3 ld96_summarize.py                              # results/ld96_heap_residue_19.tsv
git diff e7fec1b2 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py | wc -l   # 0 (コード差分なし)
```

- 生データは `work/ld96/` (gitignore)。TSV は `results/ld96_heap_residue_19.tsv`。
- 所要: solo 28 s・full chunk 0 142 s・full chunk 1 (audit-part 付き) 276 s。load は 0.3〜0.9 (4 vCPU)。
- 負のコントロール: solo (残存 0・19/19 match) と full (19/19 mismatch) の差が、文脈依存の証拠になる。残存の量を人為的に入れる対照は未実施。
