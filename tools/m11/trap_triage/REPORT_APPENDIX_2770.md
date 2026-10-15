# 付録: #2770 (LD-129) — native 側 0x5ac308 の書込み監視 (ld_native)

> **正本**: `tools/m11/trap_triage/REPORT_1783.md`。本付録は REPORT_1783.md の PR 側の節 (旧 §8) を 250 行上限のため分割移動したもの (`docs/DOC_MAP.md` §1)。節番号 (§8) は分割前のまま。REPORT_1783.md の §8 は #2769 の節で、本付録の §8 とは別。

## 8. #2770 (LD-129): native 側 0x5ac308 の書込み監視 (ld_native)

**判定**: 受入 1 は実装済み (`rt/ld_native.c` の `LD_WATCH_ADDR`)。非摂動性は**未確認** (§8.4・§8.8)。rsp を揃えた組では、arm の有無による boot 状態の差は `0x11e69bf` の 1 byte のみで、その byte は unarmed でも揺れる。旧 216 要素環境の 11 byte 差は現環境の img (215 要素) に出ず、観測できなかった。原因は未確定。trace 比較は未実施。受入 2 の記録は本付録。監視付き F の 3 run で `0x5ac308` への書込みの記録は 0 件 (監視 page への書込み fault も 0 回)。残り: (a) 942 unit のうち 14 unit は走っていない (§8.2)、(b) 書込み元は未特定 (wasm 側は #2769)。

### 8.1 測定条件

- 測定 commit: `8db3c10c` (コードを変えた最後の commit)。再測定の HEAD: `01e767de` (round 3 の指摘時点)。`git diff 8db3c10c 01e767de -- tools/liftdiff` は 0 行。
- ビルド: `tools/liftdiff` で `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm`。警告 3 件はすべて既存の `rt/ld_core.h` 由来 (`ld_native.c` は 0 件)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)、`work-m11`・`work-liftdiff` を `tools/*/work/` に展開。`--nobuild` のため `toolchain-emsdk` は不要。
- 実行: 直列 (並列 1)。16 run の所要は 13.2〜17.7 s (python 起動込み)、1 分 load average は 0.63〜1.39。
- 監視: `LD_WATCH_ADDR`・`LD_WATCH_OUT` の両方がある時だけ有効。監視 page を read/exec にし、書込みの SIGSEGV で書込み命令の RIP・書込み先を採る。TF で 1 命令実行してから page を戻す。書込みは通常どおり行われる (値を変えない設計。読取りだけの監視ではない)。ただし page の元の保護は保存せず、arm 時も TF の後も R|X に固定する (`wp_prot(0)`)。
- 行形式 `wp case=... rip_rva=... old=... new=... chg=...`。末尾に `wpsum faults=N timeouts=M alrm_def=K`。faults = 監視 page への書込み fault の総数 (page 単位で、窓の判定とは無関係)。timeouts = SIGALRM で打ち切った call 数。alrm_def = TF 待ち中に SIGALRM が保留された回数。
- 窓: wp 行は、書込み先の開始アドレス (SIGSEGV の si_addr) が va-15〜va+7 のものだけ。`rt/ld_native.c` のコメントと同じく、書込み幅 16 以下を前提とする。幅 16 を超える書込みが窓の外から監視 8 バイトに重なると wp 行は出ないが、faults には入る。カーネル内の書込み (syscall の読込み先) は SIGSEGV を起こさないため faults に入らない。代わりに、arm 中の page へのカーネル内書込みは EFAULT で失敗しうる (下記 page 保護)。
- F の 0 件の強さ: wpsum faults = 0 は、その run で監視 page への書込みが 0 回だったことを示す。窓の仮定 (幅 16 以下) には依らない。上記のカーネル内書込みを除く。
- page 保護 (実行結果への影響): `wp_arm` は元の保護を見ずに page を R|X にし、`wp_finish` も毎回 R|X に戻す。元が書込み可能な page では、arm 中の書込みはすべて SIGSEGV を経由し、カーネル内の書込み (read(2) の宛先など) は EFAULT で失敗しうる。R|X の page へのカーネル内書込み (`read(2)` の宛先など) が EFAULT (errno 14) で失敗するのは Linux の仕様として想定しており、本 PR では再現していない。監視 page が実 run でカーネルに書かれたかは未確認。InitCount の page の元の保護も未確認 (監視は元の保護によらず書込みを 1 命令ずつ通すため、この測定からは区別できない)。元の保護を保存して戻す修正は本 PR では行わない (§8.6 未解決)。
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
  - C vs X6 (3 run とも同じ): `0x11e69bf` の揺れに加え、`0x11ead38`〜`0x11ead52` の 11 byte (`00`↔`ff` の交互、3 run で同じ位置・同じ値。旧 216 要素環境の値。現環境の 215 要素の img には出ず、観測できなかった (§8.8)。C の監視 page は `System.InitCount` の page。監視 page への書込み fault は 726 回 (各 run)、うち InitCount の窓 (va-15〜va+7) への書込みは 248 件。F の監視 page への書込み fault は 0 回。

### 8.3 解釈

- C の wp 248 件 (3 本とも同じ) で、検出器が働くことは確認した。
- F の記録 0 件は「監視付き F の 3 run で `0x5ac308` への書込みが記録されず、監視 page への書込み fault も 0 回だった」ことを示す。「native boot では書かれない」とは書かない (§8.4)。
- 集計 (entry・k・ok+N・fail・最初・units_run) は 16 run で同一。unit 単位の status・件数の比較は未実施。旧版の「unit ごとの status と件数は全 run で同一」は裏付けが無いため取り下げる。
- 記録 0 件の範囲は、実際に走った 928 unit に限られる (未走 14 unit は §8.2)。
- wasm 側の 0 件の根拠は REPORT_1783.md §2 run2 の `.aw` の `grep -c '\[aw\] '` = 0 だけ (`[aw]` 検出経路は確認済み。wasm 側の陽性対照ではない)。REPORT_1783.md §7.3 は unit 境界の値比較で書込みの証拠ではない。REPORT_1783.md §7.5 は `SV_ERR_LOG` 未指定の run1 のため根拠にしない。
- 書込み元は未特定。wasm 側は #2769、native 側は #2770。

### 8.4 未確認 (非摂動性・受入 1)

- 非摂動性は**未確認**のまま。受入 1 の「実行結果を変えない」は未達として扱う (§8.6 未解決)。
- 確認できたこと (§8.8): rsp を揃えた組で、arm した run と arm なしの run の boot 状態 (img・heap) は `0x11e69bf` の 1 byte のみ違う。その byte は unarmed でも揺れるので、arm の効果とは読めない。
- 確認できていないこと:
  - 旧 216 要素環境の 11 byte 差 (§8.2b)。現環境の img (215 要素) では観測できず、原因未確定。
  - trace (呼出し列) の比較。
  - カーネル内書込みの EFAULT。strace で見たのは C の 1 run (対象 syscall のみ・0 件) だけ。
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
- round 3 の fix: REPORT §8 の文言と表だけを直した。`rt/ld_native.c` は変えていない。16 run は HEAD `01e767de` で取り直した (§8.2)。
- round 6 の fix: `rt/ld_native.c` のコメント 1 行 (`806c60779`。バイナリ同一は §8.7.1)、C の監視 page の書込み回数の文言 (726 と窓の 248 を分けた)。
- round 7 の fix (レビュー差し戻し): 「page 保護: 解決」を未解決に戻した (`wp_arm` は R|X、`wp_finish` は毎回 R|X に戻す。元の RWX には戻らない)。§8.4・§8.8 を書き直した (表 1・表 2 で `0x11e69bf` の揺れを示し、216 要素の扱いを未確定と書いた)。`cmp_img_2770.py` に rsp の一致確認・要素数・片側だけの要素数を足した。`rt/ld_native.c` は変えていない。164 行のコメント「結果が変わらないことは未確認」は §8.4 (未確認) と一致する。
- レビュー round 2 の fix (差し戻し): §8.8 の run 数を 23 run (直列 21 run と strace 付き 2 run) に直した。表 1 の bc80 行の env を「LD_PAD なし」に直した。216 要素の扱いと img の列挙の定義を書き直した。§8.1 の EFAULT の記述から「確認した」を外した。`cmp_img_2770.py` は rsp が取れない時に `UNKNOWN: not comparable` と出す。DOC_MAP の行を本付録の現行の内容に合わせた。`rt/ld_native.c` は変えていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 旧 216 要素環境の 11 byte 差 (§8.2b・§8.7)。現環境の 23 run の img (全 run 215 要素。rsp 8 種) には出ず、観測できなかった | 旧環境の差が arm 由来か環境差かが未確定。非摂動性 (§8.4) の判定に効く | #2770 (open のまま。追跡) |
| trace (呼出し列) の比較。受入 1 の「読取りのみ」も未達 (監視は page 保護を変えて書込みを通す) | 呼出し列が変わったかは未確認 | #2770 (open のまま。Refs) |
| page 保護: arm 後の page は R\|X に固定 (元の RWX に戻さない) | カーネル内書込みの EFAULT は C の 1 run (strace・対象 syscall のみ) で 0 件。他の syscall・他の run は未検査。元の保護の保存・復元は未修正 | #2770 (修正は実装の子 issue 候補) |
| `0x11e69bf` の 1 byte (unarmed でも値が揺れる) | 非摂動性の判定に使えない。揺れの原因は未特定 | #2770 |
| 未走 14 unit (942 中 928 完走。skip 10 件の内訳は未分解) | この 14 unit の書込みは未観測 | #2770 |
| SIGALRM 窓の負の対照 (alrm_def の検出経路) と、幅 16 超の書込み・カーネル内書込みの扱い | 0 件の信頼性 (窓を踏んだ run は無く、検出経路は未検証) | #2770 |
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
- 例外: commit `806c60779` で `rt/ld_native.c` の 1 行 (コメント) を変えた。`git diff bda3d706 806c60779 -- tools/liftdiff` の出力は次の 2 行だけ (コメントの行)。
  ```diff
  - * TF で書込み 1 命令だけ実行させてから page を戻す (書込みはそのまま行われ、結果は変わらない)。
  + * TF で書込み 1 命令だけ実行させてから page を戻す (書込みはそのまま行う。結果が変わらないことは未確認。REPORT_APPENDIX_2770.md §8.4)。
  ```
  同じ作業ディレクトリで `gcc -O1 -g -Wall -Wno-unused-function -o <out> rt/ld_native.c rt/ld_ms_call.S -lm` を変更前後に行い、出力を `cmp` で比べた結果は一致 (151,016 byte・バイナリ同一)。よって §8.7 の測定 (`bda3d706`) は現 HEAD のバイナリに対しても有効で、再測定は行わない。
- `git diff 806c60779 HEAD -- tools/liftdiff` は 0 行 (以後の commit は文書のみ)。

### 8.8 boot 状態の比較 (rsp を揃えた組・再測定)

- 測定 commit: `bf9f349f4` (本 fix 前の検証 HEAD)。`tools/liftdiff` は `e7cff966b` と差分 0 (`git diff e7cff966b bf9f349f4 -- tools/liftdiff` の出力は空)。ビルドは §8.1 と同じ `gcc -O1 -g -Wall -Wno-unused-function` (警告 3 件は `rt/ld_core.h` 由来)。素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)、`work-m11`・`work-liftdiff` (リポジトリ直下に展開)。作業 dir は `ws-3421` (worktree)。
- entry の rsp は env 長 (`LD_PAD`・`LD_WATCH_*` の有無) と作業 dir の長さで決まる。この環境の rsp は §8.2・§8.7 と違う。比べるのは entry の rsp が同じ組だけ。`cmp_img_2770.py` は rsp が違うと `DIFFERENT: not comparable`、取れないと `UNKNOWN: not comparable` と出す。
- 測定: `LD_PAD` (140 文字) の有無と `LD_WATCH_ADDR` を変えて `liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild` を 23 run (直列 21 run と strace 付き 2 run。表 1 の全行)。全 run で units_run 928/942、img 215 要素。img の byte 数 (要素の byte 数の合計。§8.2 と同じ定義) は cmp の集計で 48,532 byte と出た。§8.2 の X0 は同じ 215 要素で 48,484 byte と byte 数が違う。この差の原因は未確認 (どの要素のどの区間が違うかは比べていない)。

表 1 (`0x11e69bf` と監視の集計。rsp の群ごと)

| rsp | run | arm | wp 件数 / wpsum faults | `0x11e69bf` |
|---|---|---|---|---|
| bc80 (LD_PAD なし) | X6, X6b2, X6b3 | なし (`LD_WATCH_ADDR=000000`) | — | 00, 00, 02 |
| bc80 | C | `15eac98` (System.InitCount) | 248 / 726 | 00 |
| bc80 | F, F2 | `5ac308` (受入 1 の対象) | 0 / 0 | 03, 00 |
| bbe0 (`LD_PAD`) | X6p, X6p2, X6p3 | なし | — | 02, 00, 01 |
| bbe0 | Cp, Cp2 | `15eac98` | 248 / 726 | 01, 02 |
| bbe0 | Fp, Fp2 | `5ac308` | 0 / 0 | 00, 03 |
| bce0 (`LD_WATCH_*` なし) | B, B2, B3 | なし | — | 02, 02, 00 |
| bc60 (strace 下) | X6s | なし | — | 01 |
| bc60 | Cs | `15eac98` (strace 下) | 248 / 726 | 03 |
| bca0・bc90・bc80・bc70・bc50 (`LD_PAD` 16・32・48・64・96 文字) | scan16・32・48・64・96 | なし | — | 03, 03, 03, 02, 03 |

- `0x11e69bf` は、rsp・env が同じ unarmed run の間でも値が揺れる (bbe0: 02・00・01、bc80: 00・00・02、bce0: 02・02・00)。arm の有無による 1 byte の差は、arm の効果とは読めない。
- 表 1 の値から導いた比較の結論: rsp を揃えた組の差は、どの組でも `0x11e69bf` の 1 byte か 0 件のみ。表 2 の全組で、その他の byte と heap は一致した。

表 2 (rsp を揃えた組の byte 差。`cmp_img_2770.py`)

| 組 (rsp) | byte 差 | 差の位置 | heap |
|---|---|---|---|
| C vs X6 (bc80) | 0 | — | 一致 |
| F vs X6 (bc80) | 1 | `0x11e69bf` (03 と 00) | 一致 |
| F2 vs F (bc80) | 1 | `0x11e69bf` (00 と 03) | 一致 |
| X6 vs X6b3 (bc80・unarmed) | 1 | `0x11e69bf` (00 と 02) | 一致 |
| Cp vs X6p (bbe0) | 1 | `0x11e69bf` (01 と 02) | 一致 |
| Fp vs X6p (bbe0) | 1 | `0x11e69bf` (00 と 02) | 一致 |
| Cp2 vs X6p2 (bbe0) | 1 | `0x11e69bf` (02 と 00) | 一致 |
| Fp2 vs X6p3 (bbe0) | 1 | `0x11e69bf` (03 と 01) | 一致 |
| X6p vs X6p3 (bbe0・unarmed) | 1 | `0x11e69bf` (02 と 01) | 一致 |
| B vs B3 (bce0・unarmed) | 1 | `0x11e69bf` (02 と 00) | 一致 |
| Cs vs X6s (bc60・strace 下) | 1 | `0x11e69bf` (03 と 01) | 一致 |

- rsp が違う組 (Cs bc60 vs X6 bc80) では、`0x11e69bf` に加えて 10 byte (`0x11eac80`・`0x11eacc0`・`0x11eacc8`・`0x11eacd0`・`0x11eacd8`・`0x11eacf0`・`0x11eacf8`・`0x11ead00`・`0x11ead01`・`0x11f9450`) と heap が違う。差はすべて +0x20 (rsp の差 `bc80` − `bc60`) で、スタックのアドレスを保持する値と読める。rsp を揃えた組 (Cs vs X6s) では出ない。よってこの差は arm とは無関係。
- 旧 11 byte 差 (`0x11ead38`〜`0x11ead52`、§8.2b) は、この環境の全 23 run の img (215 要素) に出なかった。`ld_state_dump` の img は、pristine と異なる byte を含む区間 (差分を 8 byte 境界に広げ、32 byte 以内に続く差分は 1 要素にまとめる) を列挙する。列挙されない byte は pristine と同じ値。`0x11e6000` 以降の `.bss` は writable 範囲 (`ldlib/pe.py` の `write_ranges`) に入るので、dump の対象。旧 216 要素の img (§8.2 の bc50) は、rsp を 8 種 (bbe0・bce0・bca0・bc90・bc80・bc70・bc60・bc50) 変えた現環境の run でも一度も出なかった。旧値は現環境では観測できなかった。原因は未確定。
- strace (Cs、bc60): 対象は read・pread64・readv・preadv・recvfrom・recvmsg・getrandom・mprotect・mmap・munmap。EFAULT は 0 件 (mprotect は 1,782 行)。fstat・ioctl・clock_gettime 等 (カーネルが user memory に書くもの) は trace していない。

結論 (この環境の範囲):
- rsp を揃えた組で、arm の有無による boot 状態 (img・heap) の差は `0x11e69bf` の 1 byte のみ。その byte は unarmed でも揺れる。
- 旧 216 要素環境の 11 byte 差は、現環境の img には出ず観測できなかった。旧環境の差が arm 由来かどうかは示せていない (旧環境の再現ができない)。
- trace (呼出し列) は未比較。よって非摂動性は未確認のまま (§8.4)。F の 0 件は「監視 page への guest の書込みが 0 回」のみを示す (§8.2)。

再現 (`tools/liftdiff` で。`FL_WIN64_DIR` は §8.5):

```sh
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
mkdir -p work/probe
LD_WATCH_ADDR=15eac98 LD_WATCH_OUT=$PWD/work/probe/wp_C.txt python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild
cp work/m11/boot_state_hybrid.json work/probe/C_state.json
LD_WATCH_ADDR=000000 LD_WATCH_OUT=$PWD/work/probe/wp_X.txt python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild
cp work/m11/boot_state_hybrid.json work/probe/X6_state.json
python3 ../m11/trap_triage/cmp_img_2770.py work/probe/C_state.json work/probe/X6_state.json
```

- 出力の 1 行目で entry の rsp を見る。`DIFFERENT: not comparable` なら、`LD_PAD` で env 長を揃えてから比べる。
