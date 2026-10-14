# freshair FA-32 (#2306): FA_NODE1=1 の setter ERR 8 行の原因 (判定まで)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の類型ではなく、harness の注入オブジェクトの配線欠落)。
FA-22〜FA-30 (`REPORT_APPENDIX_FA22.md`・`REPORT_APPENDIX_FA29.md`・`REPORT_APPENDIX_FA30.md`) の続き。
判定基準 (`run_fa9.sh` (a) の期待値・`fa9_check.py`) は変更していない。

## 1. 結論 (実測)

- **issue 本文の前提を訂正する。** 「`FA_NODE1` + probe の ERR 8 行は `rip=180c9d74c addr=50`」は再現しない。
  probe の有無・guard の有無に依らず、`FA_NODE1=1` の ERR は `rip=180c9d741 addr=0 rcx=a5a5a5a5a5a5a5a5` (8/8)。
  `rip=180c9d74c addr=50` は `FA_ALT9=1` (静的分岐の negative control) でのみ出る (`rax=0` → `call [0+0x50]`)。
- **ERR の原因は FA_NODE1 の配線である。** 注入 node の値オブジェクト Z (`gr_alloc(0x40)`) を、setter の再帰 (`C=Z`) が snapin として扱う。
  2 回目の `ca1480` は key 無し分岐で `out[0]=Z+0x2b0` を返し、setter は `[out0+0x10]=[Z+0x2c0]` を読んで vtable 呼出しを行う。
  Z は 0x40 バイトしか無いので `Z+0x2c0` は guard の 0xa5 に当たり、非正準アドレス `0xa5a5…` の読みが #GP になる。
  Linux はこれを `sig=11 addr=0` と報告する (FA-22 §3 の「`addr=0` と `rcx=a5a5…` の不一致」はこれで説明がつく)。
- **切り分けの実測**: (G1) Z を 0x2400 の zero 埋めにすると、同じ命令の `rcx` は `0` になる → 読み先は注入オブジェクトの外。
  (G5) `Z+0x2c0` に vtable 付きの偽オブジェクトを置くと、ERR は **0/8** で、8 シナリオとも setter の再帰が最後まで進む。
  よって、ERR の原因は「注入 node の下位オブジェクト (`C+0x2b0+0x10` の位置) が本ハーネスで構築されていないこと」。
- **受入 2 (C と out[0] の同時記録)**: 2 回目の `ca1480` の `C` と `out[0]` を `CHAIN9` の同一行で記録し、8/8 で `C==Z`・`out0==C+0x2b0`。
- **判定**: 原因は harness 配線 (FA_NODE1)。setter の読み先 (`0x180c9d741` の `[rcx]`) は、配線の下では正しい値を読めない。
  実機の `C+0x2b0` の中身 (vtable 付きの下位オブジェクトが実在するか) は本ハーネスでは未観測。起票先は既存の #2207 (FA-31)。

## 2. 観測 (測定 commit `19766fff`・`fa32_node1.sh`)

全条件とも epf 8 本 (S900〜S907)。`ERR` は `ERR=n/8`、`first` は先頭 ERR の `rip`・`addr`・`rcx`。

| 条件 | 変数 | ERR | first (rip / addr / rcx) | 読み |
|---|---|---|---|---|
| R1 | `FA_NODE1=1` | 8/8 | `180c9d741` / `0` / `a5a5…` | 注入 node の既定の ERR (issue 本文の `74c/50` とは異なる) |
| R2 | R1 + `FA_ALT9=1` | 8/8 | `180c9d74c` / `0x50` / (`rax=0`) | negative control。静的分岐で vtable 0 を呼ぶ |
| P_noguard | R1 + `FA_PROBE9=1` | 8/8 | host の rip (`55…`) / `0` | probe 自身が `[ctl+0xa8]` を読んで落ちる (host 側) |
| P_guard | R1 + `FA_PROBE9=1 FA_P9GUARD=1` | 8/8 | `180c9d741` / `0` / `a5a5…` | probe は落ちない。ERR は guest の 741 (probe 非依存) |
| G1 | `FA_NODE1_ZBIG=1` (Z=0x2400 zero) | 8/8 | `180c9d741` / `0` / `0` | 読み先が 0 に変わる → 読み先は Z の外 |
| G5 | `FA_NODE1_ZOBJ=1` (Z+0x2c0 に偽オブジェクト) | **0/8** | — | setter が再帰まで最後まで進む |
| C | `FA_PROBE9=1 FA_CHAIN9=1 FA_OUT0=1` | 8/8 | `180c9d741` / `0` / `a5a5…` | 2 回目の照合: C==Z 8/8・out0==C+0x2b0 8/8 |

- 再現: `bash tools/targets/freshair/lift2/fa32_node1.sh` (前提: `build_ctrl.sh` 済・素材 `plugins-freshair` を `fetch.sh` で展開済)。
- 偽オブジェクト (G5) は host 関数を slot に持つ: `call [vtbl+0x50]` は `out` に shared_ptr `{obj, ctrl}` (16B) を書く。
  `call [vtbl+0x18]` は `{NULL, NULL}` を返す。ctrl の use count は 0x40 (dispose されない)。
  途中版 (出力を書かない slot) では、順に `180c9d77e` (`call [rax+8]`, addr=8)・`180c9d7e9` (`lock xadd [rbx+8]`, 制御ブロック未初期化) で落ちた。
  この連鎖は、setter が `[C+0x2b0+0x10]` の先で shared_ptr を 2 組受け取る契約であることを示す。

### 2.1 setter の該当箇所 (SlateCore.core_64 の逆アセンブル・VA)

```
180c9d724: call 0x180ca1480          ; ca1480(C, &out[0]=rsp+0x48, key)
180c9d737: je 0x180c9d813            ; out[0]==0 なら再帰分岐 (C=out[2], key=out[4])
180c9d73d: mov rcx, [rcx+0x10]       ; rcx = out[0]+0x10   (out0=C+0x2b0 なら Z+0x2c0)
180c9d741: mov rax, [rcx]            ; ← R1/P_guard/G1/C の ERR (rcx=a5a5… / 0)
180c9d74c: call [rax+0x50]           ; ← R2 の ERR (rax=0 → addr=0x50)
180c9d75d: call [rax+0x18]           ; 2 段目 (shared_ptr {[rsp+0x28],[rsp+0x30]})
180c9d77e: call [rax+8]              ; 途中版の偽 slot で落ちた箇所
```

## 3. 受入条件との対応

| 受入 (issue #2306) | 結果 |
|---|---|
| ERR 8 行 (rip=180c9d74c, addr=50) の原因を特定 | 前提を訂正。実際の ERR (`741`) の原因は FA_NODE1 配線 (§1・§2)。`74c/50` は ALT9 の署名 (R2) |
| 2 回目の `ca1480` で `C` と `out[0]` を同時に記録し `out[0]=C+0x2b0` を照合 | 達成 (`CHAIN9` 同一行・8/8) |
| 判定基準 (`run_fa9.sh` (a) の期待値) は変更しない | 達成 (`run_fa9.sh`・`fa9_check.py` は未変更。`git diff origin/main HEAD -- …` が空) |
| 測定 commit と `run_fa9.sh` / `run_ctrl 2 5` の実測を REPORT に残す | 達成 (§4) |

## 4. 測定 (測定 commit `19766fff`)

- 測定 commit: `19766fff` (lift2 のコードを変えた最後の commit。`e524d332` が診断の追加、`19766fff` が `fa32_node1.sh`)。
- `bash tools/targets/freshair/lift2/run_fa9.sh` (HEAD `19766fff`): wall 6 s, load 0.07→0.31, **GATE PASS**
  - (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0
  - (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8
  - (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出
- `run_ctrl 2 5` (同 run): **BIT-EXACT 15/15** (epf 8 + structured 2 + random 5, fma0+fma1), wall 5 s, rc=0
- `bash tools/targets/freshair/lift2/fa32_node1.sh` (同 HEAD): §2 の表どおり。G5 は ERR 0/8、C は 8/8・8/8。
- wall の n≥3 レンジは未取得 (単発値のため `WORKFLOW.md` §5 の min–max は書かない)。
- 測定 commit からの lift2 差分: `git diff 19766fff HEAD -- tools/targets/freshair/lift2` (本付録の commit は `tools/targets/freshair/REPORT_APPENDIX_FA32.md` と `docs/DOC_MAP.md` のみで、lift2 配下に触れない)。
- 検証起点: `ws-2306` (worktree, 起点 `origin/main` = `26f90ada`)。素材は `$HOME/artifacts/plugins-freshair.tar.zst` を `$RUNNER_TEMP` に展開し `fetch.sh` で `work/win` を作成。`work/` は gitignore。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実機の `C+0x2b0` に vtable 付きの下位オブジェクトが実在するか (本ハーネスの G5 の偽オブジェクトは仮定) | 再帰の実機挙動 (setter が 2 段目の shared_ptr を返すか) は未判定。G5 の ERR 0 は配線の欠落の確認であり、setter の出力の正しさは判定しない | #2207 (FA-31, open) |
| G5 の偽 slot (`fz_set`/`fz_ret`) の返す値は host の仮定 | 同上。`fz_set` は obj・ctrl を固定値で返すだけ | #2207 (FA-31, open) |
