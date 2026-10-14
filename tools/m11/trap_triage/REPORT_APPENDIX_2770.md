# 付録: #2770 (LD-129) — native 側 0x5ac308 の書込み監視 (ld_native)

> **正本**: `tools/m11/trap_triage/REPORT_1783.md`。本付録は REPORT_1783.md の PR 側の節 (旧 §8) を 250 行上限のため分割移動したもの (`docs/DOC_MAP.md` §1)。節番号 (§8) は分割前のまま。REPORT_1783.md の §8 は #2769 の節で、本付録の §8 とは別。

## 8. #2770 (LD-129): native 側 0x5ac308 の書込み監視 (ld_native)

**判定**: 受入 1 は実装済み (`rt/ld_native.c` の `LD_WATCH_ADDR`)。受入 2 は部分的: 監視付き F の 3 run で `0x5ac308` への書込みの記録は 0 件 (監視 page への書込み fault も 0 回)。ただし (a) 非摂動性は未確認 (§8.4)、(b) 942 unit のうち 14 unit は走っていない (§8.3)、(c) 書込み元は未特定。

### 8.1 測定条件

- 測定 commit: `8db3c10c` (コードを変えた最後の commit)。再測定の HEAD: `01e767de` (round 3 の指摘時点)。`git diff 8db3c10c 01e767de -- tools/liftdiff` は 0 行。
- ビルド: `tools/liftdiff` で `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm`。警告 3 件はすべて既存の `rt/ld_core.h` 由来 (`ld_native.c` は 0 件)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)、`work-m11`・`work-liftdiff` を `tools/*/work/` に展開。`--nobuild` のため `toolchain-emsdk` は不要。
- 実行: 直列 (並列 1)。16 run の所要は 13.2〜17.7 s (python 起動込み)、1 分 load average は 0.63〜1.39。
- 監視: `LD_WATCH_ADDR`・`LD_WATCH_OUT` の両方がある時だけ有効。監視 page を read/exec にし、書込みの SIGSEGV で書込み命令の RIP・書込み先を採る。TF で 1 命令実行してから page を戻す。書込みは通常どおり行われる (値を変えない設計。読取りだけの監視ではない)。
- 行形式 `wp case=... rip_rva=... old=... new=... chg=...`。末尾に `wpsum faults=N timeouts=M alrm_def=K`。faults = 監視 page への書込み fault の総数 (page 単位で、窓の判定とは無関係)。timeouts = SIGALRM で打ち切った call 数。alrm_def = TF 待ち中に SIGALRM が保留された回数。
- 窓: wp 行は、書込み先の開始アドレス (SIGSEGV の si_addr) が va-15〜va+7 のものだけ。`rt/ld_native.c` のコメントと同じく、書込み幅 16 以下を前提とする。幅 16 を超える書込みが窓の外から監視 8 バイトに重なると wp 行は出ないが、faults には入る。カーネル内の書込み (syscall の読込み先) は SIGSEGV を起こさないため faults に入らない (未確認)。
- F の 0 件の強さ: wpsum faults = 0 は、その run で監視 page への書込みが 0 回だったことを示す。窓の仮定 (幅 16 以下) には依らない。上記のカーネル内書込みを除く。
- アドレスの基底: §8 のアドレスは断りがない限り VA (= `0x400000` + RVA)。§8.2 の k の番地 `0x11eac98` と §8.2b の img の番地は RVA。

### 8.2 実測と定義

定義 (`ldlib/boot.py` の `build_state` と `liftdiff.py bootstate` の出力):
- entry: `ep` case の status (`entry_status`) と、その時の `System.InitCount` (RVA `0x11eac98`) の値 k (log の `InitCount=`)。
- 単位フェーズ ok+N = `detail.units_ok` − k。fail M = `detail.units_fail`。最初 P = `fails_head` の先頭の InitTable 添字。
- 分母 = InitTable の全件 942。units_run = `detail.units_ok` (= k + ok+N)。未走 = 942 − units_run。
- img_runs = STATE JSON の `img` の要素数。img bytes = その byte 数の合計。wp 件数 = `grep -c '^wp '`。

同一 HEAD (`01e767de`) で 16 run を取り直した。`LD_WATCH_*` の値は VA。`LD_WATCH_OUT` は arm 時のみ作られる。

| run 群 | 環境変数 | n (run 名) | entry | 単位フェーズ | units_run | img_runs・bytes | wp 件数 | wpsum faults/timeouts/alrm_def (run 別) |
|---|---|---|---|---|---|---|---|---|
| F | `LD_WATCH_ADDR=5ac308` | 3 (F, r2F, F3) | segv (rip RVA `0x26833d`)・k=246 | ok+682 / fail 3 / 最初 830 | 928/942 | 216・48,516 | 0 (各 run) | F 0/0/0・r2F 0/0/0・F3 0/0/0 |
| C (陽性対照) | `LD_WATCH_ADDR=15eac98` (`System.InitCount` の VA) | 3 (C, r2C, C3) | 同左 | 同左 | 928/942 | 216・48,516 | 248 (各 run) | C 726/0/0・r2C 726/0/0・C3 726/0/0 |
| B (監視なし) | なし | 6 (B, B2, B3, B4, r2B, r2B2) | 同左 | 同左 | 928/942 | 216・48,516 | — | — |
| E2 | `LD_WATCH_OUT` のみ (arm なし) | 1 (E2) | 同左 | 同左 | 928/942 | 216・48,516 | — | — |
| X6 | `LD_WATCH_ADDR=000000` (arm なし・F と同じ長さの OUT) | 1 (X6) | 同左 | 同左 | 928/942 | 216・48,516 | — | — |
| X0 | `LD_WATCH_ADDR=0` (arm なし) | 2 (X0, X0b) | 同左 | 同左 | 928/942 | 215・48,484 | — | — |

- 16 run 全てで entry (segv・rip RVA `0x26833d`)・k=246・ok+682・fail 3・最初 830・units_run 928/942 が同一。
- 旧版の表の img_runs 215 (48,484 byte) は X0・X0b の値だった。F・C・B 系は 216 (48,516 byte)。旧版の「F 行の 216 は再現せず」は取り消す。
- 未走 14 unit (942 − 928): 単位フェーズの fail 3 件 (最初 830)、添字 246 (`start = k+1` で飛ばす) 1 件、残り 10 件は `units[i]==0` または `*proc==0` で飛ばした unit (2 種の内訳は未分解)。
- SIGALRM 窓 (TF 待ち中の timeout): 監視付き 6 run は timeouts 0・alrm_def 0。窓を踏んだ run は無い。alrm_def の検出経路は、窓を踏ませる負の対照を取っていないため未検証。

### 8.2b img の比較 (STATE JSON の img、RVA)

- 215 要素の X0・X0b は 216 要素の他の run と要素数が違う (32 byte 少ない)。以下の比較は 216 要素の run 同士で行う。
- 環境変数長: entry 時の rsp が run 群で違う (F・C・X6 系 `0x7fffffffbc50`、B 系 `0x7fffffffbcd0`、E2 `0x7fffffffbc80`、X0 系 `0x7fffffffbc60`)。B 系と F 系の差 (`0x11eac80` 付近のポインタ領域と `0x11f9451` の計 23 byte) は、arm されない X6 にも出る (X6 vs B: 23 byte)。arm の有無は X6 と比べて読む。
- `0x11e69bf` (1 byte): 監視なしの B 系でも値が揺れる (B 03・B2 00・B3 01・B4 00・r2B 01・r2B2 01)。arm と無関係に変わるので、この 1 byte は arm の効果とは読めない。他の値: F 01・r2F 03・F3 02・C 00・r2C 03・C3 02・E2 00・X6 00。
- arm の有無 (環境長を揃えた組):
  - F vs X6: `0x11e69bf` の 1 byte のみ (01 と 00)。
  - F3 vs X6: `0x11e69bf` の 1 byte のみ (02 と 00)。
  - C vs X6 (3 run とも同じ): `0x11e69bf` の揺れに加え、`0x11ead38`〜`0x11ead52` の 11 byte (`00`↔`ff` の交互、3 run で同じ位置・同じ値)。C の監視 page は `System.InitCount` の page で、248 回書込まれる。F の監視 page は書込み 0 回。

### 8.3 解釈

- C の wp 248 件 (3 本とも同じ) で、検出器が働くことは確認した。
- F の記録 0 件は「監視付き F の 3 run で `0x5ac308` への書込みが記録されず、監視 page への書込み fault も 0 回だった」ことを示す。「native boot では書かれない」とは書かない (§8.4)。
- 集計 (entry・k・ok+N・fail・最初・units_run) は 16 run で同一。unit 単位の status・件数の比較は未実施。旧版の「unit ごとの status と件数は全 run で同一」は裏付けが無いため取り下げる。
- 記録 0 件の範囲は、実際に走った 928 unit に限られる (未走 14 unit は §8.2)。
- wasm 側の 0 件の根拠は REPORT_1783.md §2 run2 の `.aw` の `grep -c '\[aw\] '` = 0 だけ (`[aw]` 検出経路は確認済み。wasm 側の陽性対照ではない)。REPORT_1783.md §7.3 は unit 境界の値比較で書込みの証拠ではない。REPORT_1783.md §7.5 は `SV_ERR_LOG` 未指定の run1 のため根拠にしない。
- 書込み元は未特定。wasm 側は #2769、native 側は #2770。

### 8.4 未確認 (非摂動性・受入 1)

- 「監視が実行結果を変えない」は**未確認**。
  - F (監視 page への書込み 0 回): img は X6 と `0x11e69bf` の 1 byte だけ違い、その byte は監視なしの run 間でも揺れる。ただし trace (呼出し列) は比較していない。
  - C (監視 page への書込み 248 回): X6 と img の 11 byte が 3 run で同じ位置・同じ値で違う (§8.2b)。書込みが起きる条件では、arm が img を変えうる。原因は未確認。
- 集計の一致は unit 単位の比較の代わりにならない (§8.3)。
- 窓の仮定 (書込み幅 16 以下)・カーネル内の書込み (§8.1) は未検証。
- SIGALRM 窓の alrm_def の検出経路は未検証 (§8.2)。

### 8.5 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>   # [WIN64] (docs/REFERENCES.md §4)
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
rm -f work/wp_F.txt
LD_WATCH_ADDR=5ac308 LD_WATCH_OUT=$PWD/work/wp_F.txt python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild
grep -c '^wp ' work/wp_F.txt; tail -1 work/wp_F.txt     # wp 件数・wpsum
# 陽性対照: LD_WATCH_ADDR=15eac98 (System.InitCount)
# arm 無し・環境長を揃える対照: LD_WATCH_ADDR=000000 (OUT は F と同じ長さのパス)
# 監視なし: 環境変数を付けない。実行ごとに work/m11/boot_state_hybrid.json を別名に退避してから次を回す
```

### 8.6 本 fix での変更と未解決

- commit `8db3c10c` (fix): `wp_fault` で SIGALRM の元のマスクを保存し、`wp_finish` は元から block されていなかった時だけ解除する。TF 待ち中に保留された SIGALRM の回数を `alrm_def` に出す (`rt/ld_native.c` 単独、+5/−3)。
- round 3 の fix (本 commit): REPORT §8 の文言と表だけを直した。`rt/ld_native.c` は変えていない。16 run は HEAD `01e767de` で取り直した (§8.2)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| trace (呼出し列) を含む非摂動性の比較。C の arm で出る 11 byte の img 差 (§8.2b) の原因 | 受入 1 が未確定 | #2770 (本 issue に残す) |
| 未走 14 unit の内訳 (skip 10 件の `units[i]==0` と `*proc==0` の分解) | 未走範囲の確定 | #2770 |
| 窓の負の対照 (窓を踏ませる run・alrm_def の検出経路)、幅 16 を超える書込みとカーネル内書込みの扱い | 0 件の信頼性 | #2770 |
| 全 942 unit の wasm 側 `[aw]` 採取と、書込み元の特定 | 書込み元が未確定 | #2769 |

### 8.7 main 取り込み後の再測定 (merge `bda3d706`)

- 測定 commit: `bda3d706` (`origin/main` `a7ea7667` を取り込んだ merge commit)。コードは merge 結果をそのまま測った。
- 前の測定 commit `8db3c10c` からの変更 (main 側。`git diff --stat 8db3c10c bda3d706 -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets/m11.json`): `ldlib/build_wasm.py` (変更 4 行)、`ldlib/irtool.py` (変更 69 行)。`rt/ld_native.c`・`rt/ld_ms_call.S`・`liftdiff.py`・`targets/m11.json` は差分 0。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11`・`work-liftdiff` を `tools/m11/work/`・`tools/liftdiff/work/` に展開。
- ビルド: `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm`。警告 3 件はすべて `rt/ld_core.h` 由来 (`ld_native.c` は 0 件)。
- 実行: `python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild`、直列 16 run。合計 302 s (`date` の差)。終了時 1 分 load 1.00。

| run 群 | 環境変数 | n (run 名) | rsp | units_run | img_runs・bytes | wp 件数 | wpsum faults/timeouts/alrm_def |
|---|---|---|---|---|---|---|---|
| F | `LD_WATCH_ADDR=5ac308` | 3 (F, r2F, F3) | `0x7fffffffbc60` | 928/942 | 215・48,484 | 0 (各 run) | 0/0/0 (各 run) |
| C (陽性対照) | `LD_WATCH_ADDR=15eac98` | 3 (C, r2C, C3) | `0x7fffffffbc60` | 928/942 | 215・48,484 | 248 (各 run) | 726/0/0 (各 run) |
| B (監視なし) | なし | 6 (B, B2, B3, B4, r2B, r2B2) | `0x7fffffffbce0` | 928/942 | 216・48,516 | — | — |
| E2 | `LD_WATCH_OUT` のみ | 1 (E2) | `0x7fffffffbc70` | 928/942 | 216・48,516 | — | — |
| X6 | `LD_WATCH_ADDR=000000` | 1 (X6) | `0x7fffffffbc60` | 928/942 | 215・48,484 | — | — |
| X0 | `LD_WATCH_ADDR=0` | 2 (X0, X0b) | `0x7fffffffbcc0` | 928/942 | 215・48,484 | — | — |

- 16 run 全てで entry (segv・rip RVA `0x26833d`)・k=246・ok+682・fail 3・最初 830・units_run 928/942 が同一。PR 側の 01e767de の表と集計は一致する。
- rsp は 8.2 の値 (`0x7fffffffbc50`・`bcd0` 等) と違う。rsp は環境変数と cwd・OUT パスの長さで決まり、worktree の path が違うためで、arm の有無の比較は rsp を揃えた組 (F・C・X6 は `bc60`) で読む。
- img (RVA、rsp を揃えた組): F vs X6 は `0x11e69bf` の 1 byte のみ (PR 側と同じ)。F3 vs X6 は 0 byte (`0x11e69bf` は揺れる byte)。C vs X6 も `0x11e69bf` の 1 byte のみ。
- **8.2b の C 固有の 11 byte (`0x11ead38`〜`0x11ead52`) は、この rsp の組の img (215 要素) に含まれず、観測できなかった**。PR 側の 216 要素の組 (rsp `bc50`) で見えた差を、この測定で再現も反証もしていない。rsp を `bc50` に揃える (または 216 要素の rsp `bce0` の組に C を入れる) 追加測定が要る。それまで §8.4 の「非摂動性は未確認」は変えない。
- 同じ組内の差 (run 間): F 群・C 群・B 群の全組の対 (`F`・`r2F`・`F3`・`X6`、`C`・`r2C`・`C3`・`X6`、B 系 6 run) で、差は `0x11e69bf` の 1 byte か 0 件のみ。

#### 8.7.1 差分証跡と鮮度

- 測定 commit `bda3d706` から作成時 HEAD までの `tools/liftdiff` の差分 (REPORT を除く) は 0 byte (`git diff bda3d706 HEAD -- tools/liftdiff ':(exclude)*REPORT*'` の出力は空)。
