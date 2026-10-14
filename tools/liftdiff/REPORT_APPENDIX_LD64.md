# liftdiff REPORT 付録: LD-64 (#1854) OTT 旧 chain 1801c5e84 系の wasm 側 IR block 入口 trace

親 issue #1636 (LD-57)。前提は `REPORT_APPENDIX_LD57.md` §2・§3・§4。

## 結論

- 受入条件は**部分達成**。wasm 側の trace は **IR basic block 入口単位**で入れた (命令単位ではない)。
- 6 関数 × vm0/u16 で block trace を取得した。ただし、`1c0b6f` (je) と `1c0b82` (HeapFree) の IR block への対応付け (§3) は、入力 (`blk_all.json`・IR `ott.ll`・`block_coverage.py` の出力) を本 PR に commit していないため、**本 PR の資料では再現できない (未検証)**。
- native 側の事実 (`1c0b6f` が je、`1c0b82` が HeapFree の call で、この順に並ぶこと) は `results/ld57/insn_1801c5e84_u16.txt` で確認できる。block 対応はこれとは別の主張である。
- **計装版は vm0 の wasm 戻り値を変える** (§4)。`blk=0` で計装を入れても戻り値が変わるため、計装 (`call @ld_blk`) 自体が wasm の挙動を変えている。よって計装版の block trace は、現時点では結果の根拠にできない。
- 既定 build (`ott_old`) は HEAD で再 build した 12 case (6 関数 × vm0/u16) では、変更前 baseline と outcome・diff が一致した (§5)。ただし baseline 比較の出力も本 PR に commit していない。既定 build 全体への無影響は主張しない (§5)。
- 命令単位 (per-instruction) の wasm trace は、IR に元の VA が無いため本 PR の範囲外 (§6)。

## 1. 測定条件

- 測定 commit: `ab190bbd` (`feat(liftdiff): opt-in IR block-entry trace for wasm`。コード差分の最終 commit)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。load average (測定終了時) 0.04 / 0.09 / 0.12。
- 素材: `work-liftdiff`・`work-m6-ott`・`analysis-ott-binaries` (`[ANALYSIS-PLUGINS]` の `ott/binaries/`)・`toolchain-emsdk` (`[EMSDK]`)。`fl-win64` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` に展開して指定。
- 実行コマンド (6 関数 × pattern):
  `python3 liftdiff.py run targets/ott_old_blk.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --verbose --json work/ld64/blk_all.json`
- 所要 (**n=1 の参考値。結論には使わない**): 6 関数 × 2 pattern の run は `ott_old` 5.553 s・`ott_old_blk` 5.551 s (`--nobuild --notrace`)。`ott_old_blk` の wasm link は 0.6 s (`build_wasm.py --force` のログ `link 0.6s`)。n=1 のため min–max レンジは出せない (`docs/WORKFLOW.md` §5)。

## 2. 実装

| 変更 | 内容 |
|---|---|
| `rt/ld_core.h` | `blk=1` case key を追加。IR block 入口 VA を `ld_blks` (malloc・上限 65536) に記録し、`blk` / `blk_over` を JSON に出す。compare は読まない |
| `rt/ld_wasm.c` | `ld_blk(u64)` の定義 |
| `ldlib/irtool.py` | `instrument(..., blocks=True)` のとき `dec_label_pc_<VA>:` の直後に `call @ld_blk(VA)` を挿入。既定は `False` |
| `ldlib/build_wasm.py` | target の `block_trace` を `instrument` に渡す |
| `ldlib/session.py` | `block_trace` の target では case 行に `blk=1` を付ける |
| `liftdiff.py` | `trim_case` の raw に wasm の `blk` / `blk_over` を追加 |
| `targets/ott_old_blk.json` | `ott_old` と同じ lift・stub に `block_trace: true` を付けた計装版 (work dir は `work/ott_old_blk/`) |
| `targets/ott_old_blk_off.json` | 切り分け用。`block_trace: false` (`ott_old` と同一の IR) |

既定 target (`ott_old`) の build の IR・wasm は変更前と同一の経路を通る (`block_trace` が無いため `blocks=False`)。

## 3. block trace の結果 (未検証の参考値・結論に使わない)

**この節の表と下の block 対応は、本 PR に入力も出力も commit していないため未検証である。結論・判定の根拠にしない。** 再現するには `blk_all.json` (6 関数 × vm0/u16 の raw)、IR `ott.ll` (`tools/ott/work/` 配下。`work-m6-ott` 素材で展開)、`block_coverage.py` の出力を揃える必要がある (子 #1907 で扱う)。

`blk_all.json` の block 入口列 (`verdict` は計装版の判定。§4 の注意つき)。

| 関数 | pattern | outcome | block 入口数 | 異なり数 | 末尾 block |
|---|---|---|---|---|---|
| 1801ab1d0 | vm0 / u16 | equal / equal | 4 / 4 | 4 / 4 | 1ab245 |
| 1801ab258 | vm0 / u16 | equal / equal | 4 / 4 | 4 / 4 | 1ab2d3 |
| 1801c5e84 | vm0 | diff | 27 | 15 | 1c5ecc |
| 1801c5e84 | u16 | wasm_trap | 4 | 4 | 1c0b71 |
| 1801c621c | vm0 | diff | 287 | 18 | 1c6323 |
| 1801c621c | u16 | wasm_trap | 6 | 6 | 1c0b71 |
| 1801c682c | vm0 | diff | 42 | 22 | 1c0ba8 |
| 1801c682c | u16 | diff | 43 | 23 | 1c0ba8 |
| 1801c69cc | vm0 | diff | 304 | 23 | 1c6a01 |
| 1801c69cc | u16 | wasm_trap | 10 | 10 | 1c0b71 |

- (未検証) native `1c0b6f` (je) が IR block `1c0b6c` の末尾 (`icmp eq %arg1, 0` の `br`) にあたる、という主張は、上記の入力を揃えて確認するまで採らない。
- (未検証・結論に使わない) wasm の `1c5e84` u16 の trace の block 列と、`HeapFree` 経路での trap との関係は、本 PR では照合していない。LD-57 の「u16 は HeapFree 経路」との一致も確認していない。
- native `1c0b82` (HeapFree の call) が IR block `1c0b71` の中にある、という主張も未確認 (上と同じ入力が要る)。
- (未検証) vm0 の `1c0b6c` → `1c0ba8` が早期 return に当たる、という読みは採らない。wasm の block 列に両 block が現れることは表の転記にとどまり、§4 のとおり vm0 の計装版の戻り値は変わっている。
- **`1801c621c` の vm0 は 287 block、`1801c69cc` の vm0 は 304 block**。残り 4 関数の分岐点 (受入条件 3) は、block 列の比較までは示せたが、native 側 (`insn_*.txt`) の対応付けは未了。

`tools/liftdiff/results/ld64/block_coverage.py` は native の rva が IR block label と一致する割合を数える (入力: IR `ott.ll` と `results/ld57/insn_*.txt`)。本 PR では、この出力 (一致率) を commit していない。以前の記述の 9.5〜25.5% は、再現可能な出力として本 PR に残っていない。**命令単位の対応付けには使えない** (block 入口にしか当たらないため)。

## 4. 計装が wasm の結果を変える (未解決・本 PR の最重要)

`ott_old_blk` (計装版) と `ott_old` (既定) を、同じ 6 関数 × vm0/u16 (12 case) で比べた。

| 比較 | 結果 |
|---|---|
| `ott_old` を 2 回 run | 12 case すべて一致 (再現性あり) |
| `ott_old_blk` を 2 回 run | 12 case すべて一致 (再現性あり) |
| `ott_old` vs `ott_old_blk` (計装あり) | **vm0 の 2 case (1c5e84・1c621c) の `wasm_rax` が変わる**。`0x0` → `0x1801c5eb8`、`0x1801c5e84` → `0x1801c5eb8`。値は block VA |
| `ott_old_blk_off` (`block_trace: false`・IR は計装あり) vs `ott_old` | 一致 (`ld_blk` 呼出しが無ければ差は無い) |
| `ott_old_blk` の `blk=1` を外した run (`LD_BLK_NOREC` 試験。`ld_blk` 呼出しは残す) | **差が残る** (同じ 2 case)。記録の有無は原因ではない |
| `ld_blks` を static 配列から malloc に変更 | 差が残る。static 配置の変化が原因ではない |

結論: **`ld_blk` 呼出しを IR に入れると、vm0 の一部 case の wasm 戻り値が変わる**。記録処理 (`blk=1`)・静的配置のいずれでもない。推定 (未検証): 対象の関数は未初期化の shadow stack・レジスタ spill 相当の値に依存し、呼出しの追加で -O0 の stack 配置か spill 位置が変わる。この推定は本 run で確認していない。

このため計装版の block trace は、**判定や戻り値の根拠にしない**。§3 の block 列は「どの block に入ったか」の参考にとどめる。

> **追記 (LD-67 / #1906)**: 差の原因は `ld_blk` の call 命令の挿入そのもの (空定義でも同じ差・stack fill に非依存) と切り分けた。call を volatile store に替えると既定 build と 12 case 差 0。詳細は [`REPORT_APPENDIX_LD67.md`](REPORT_APPENDIX_LD67.md)。上の「推定」は否定された。

## 5. 既定経路への影響 (ネガティブコントロール相当)

- `ott_old` を HEAD (`ab190bbd`) で `build_wasm.py --force` して再 build し、6 関数 × vm0/u16 を run した。
- 変更前 baseline (`work/ld64/rep_ott_old_1.json`) と **この 12 case では outcome・diffs が一致** (`HEAD ott_old cases == baseline: True`)。baseline の比較出力は本 PR に commit していない (再現には `work/ld64/rep_ott_old_1.json` が要る)。
- verdict は `match, match, mismatch, mismatch, mismatch, mismatch` (変更前と同一)。
- `rt/ld_core.h` は既定 build も含む共有ヘッダで、static 変数と関数を追加している。static 配置の変化で wasm 戻り値が変わりうる (§4) ため、**既定 build 全体への無影響は言い切れない**。主張は「この 12 case では baseline と一致」に限る。

## 6. 測定 commit と差分

- 測定 commit: `ab190bbd`。
- `git diff ab190bbd HEAD -- tools/liftdiff/rt tools/liftdiff/ldlib` は **0 件** (HEAD は `ab190bbd`。本 PR の以降の commit は REPORT と `results/ld64/` のみ)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ld_blk` 呼出しで vm0 の wasm 戻り値が変わる (§4) | 計装版 block trace を判定に使えない。`1c5e84`・`1c621c` の vm0 の wasm 側挙動が未確定 | 子 issue (LD-64 の残り、下記) |
| 命令単位 (per-instruction) の wasm trace | native の `1c0b6f` (je) と `1c0b82` (HeapFree) を、block 境界より細かく対応付けできない。受入条件 1・2 の残り | 子 issue (LD-64 の残り、下記) |
| 残り 4 関数の native 対応 (受入条件 3) | block 列のみで、native `insn_*.txt` との対応は未了 | 子 issue (LD-64 の残り、下記) |
