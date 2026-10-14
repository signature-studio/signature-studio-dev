# #1317 M2p ON survey: unit 880 の停止位置の特定 (2026-10-13)

**判定: 部分達成 (Refs #1317)。** 受入 2 (停止した命令・wasm frame の特定) と受入 4 (再現の確認) は一部。停止の必要条件 (830 が先行し 880 が走る) は REPORT_1076 の結果を再確認した。停止を起こす状態 (受入 1)・修正案 (受入 3) は未達。
受入番号は issue #1317 の受入条件の番号 (1 = 830 の状態, 2 = 停止位置, 3 = 修正案, 4 = 再現)。

既知類型との関係: 該当なし (survey の停止位置の調査のみ。lift 変換の類型には触れていない)。

## 1. 測定の基準

- 検証 HEAD: `851c342e` (`origin/main`)。本ファイルを追加する commit 以外にコード差分は無い。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin`, 22 MB)。`toolchain-retdec` を `$RUNNER_TEMP/tc/retdec`、`toolchain-emsdk` を `$RUNNER_TEMP/tc/emsdk` に展開 (`RETDEC_ROOT` で指定。emsdk は `[EMSDK]` を使用)。`work-m11` を `tools/m11/work/` (233 entries)、`work-liftdiff` を `tools/liftdiff/work/` (11 entries) に展開。
- IR: `m11_gen_ir2.sh` 43 s rc=0 (OFF)。`M11_M2P=1` でも rc=0 (`[ir11][M2p] decimal inttoptr instr VA remap: 4364`)。ldfix は OFF/ON とも `F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0`。
- build: `m11_build.sh` 26 s rc=0 (OFF・ON とも `wasm-ld signature mismatch: 0, undefined symbol: 0`)。
- load average: 実行中 0.95〜0.99。

## 2. 再現 (repro_1076.sh, M2p ON, 60 s 上限)

| 条件 | 結果 | rc |
|---|---|---|
| `880` 単独 | `oob 1` | 0 |
| 0..941 から 880 を除いた全 unit (skip880) | `ok 871 / oob 14 / miss 47 / halt0 5 / abort 2 / other 1 / noproc 1` | 0 |
| `0..830` + `880` (prefix_0_830_880) | 60 s 超で打ち切り | 124 |
| `0..829` + `880` | `ok 765 / oob 13 / miss 46 / halt0 4 / abort 2 / other 1` | 0 |
| `830,880` | `oob 2` | 0 |
| `0..830` (880 なし) | `ok 765 / oob 13 / miss 46 / halt0 4 / abort 2 / other 1` | 0 |

REPORT_1076 §3 の境界 (`0..829`+880 完走 / `0..830`+880 停止) と一致。ただし run 所要秒は未計測 (60 s 上限のみ)。

対照 (OFF build の IR を再生成して build し直した後): `0..830` + `880` は `ok 764 / miss 46 / halt0 6 / oob 15 / other 1` で **完走 (rc=0)**。停止は M2p ON に固有。(REPORT_1076 §7 の「未実施」項目の裏取り。)

## 3. 停止位置 (trace, `SV_PROG=1` + `SV_TRACE_AT=880`)

- `SV_PROG` で unit 830 の完了後に `unit 880` を表示し、そのまま出力が止まる。例外・abort の表示は無い (rc=124 で打ち切り)。
- 880 の中で最後に出る trace は次の順 (`diag880p.log` 末尾):
  1. `[m11][icall] 0xe63540`
  2. `[m11][icall] 0xf960`
  3. `[m11][stub-notimpl] GetFileVersionInfoSizeW called`
  4. `[m11][UStrAsg] dest=0x10a9b188 src=0x0 old=0x0`
  5. `[m11][UStrAsg] dest=0x10a9b648 src=0x0 old=0x0`
  その後の trace は無く、ループまたは長い計算で止まっている可能性が高い。
- `[m11][VA-big] size=2143354880 (2044.1 MB)` が 2 回と `OOM want=2143.4MB used=76.3MB` が出る (`diag880p.log` の 185〜201 行)。これは `unit 830` の marker (895 行) より前、つまり unit 0〜829 の実行中の出力で、880 の停止の直接原因とは断定できない。
- `Runtime error 215` / `unresolved function call: function_535c2e` の fail-fast は unit 830 以前の出力で、880 の内部ではない。

**未解決 (受入 1・2 の残り)**:
- `icall 0xe63540` / `0xf960` は PE の VA ではなく wasm 側の icall 値。`disasm_fn.py` は PE VA (`0x400000` 基準) しか引けず、解決先の特定は未了 (`0xe63540` は PE の範囲内だが関数先頭ではない)。
- 880 の停止命令 (wasm frame) は `SV_RAW=1` の `e.stack` が trace 無しの run で取れていない (本 run では `SV_RAW` のみの run は未実施)。
- 830 が残す状態 (メモリ領域・間接 call 先・store 先) は未特定。

## 4. 未達・未実施 (起票先)

| 未解決 | 起票先 |
|---|---|
| 880 の停止命令・wasm frame の特定 (`SV_RAW=1` 単独 run、icall 0xe63540/0xf960 の wasm→PE 対応付け) | 本 issue #1317 へのコメント |
| 830 が残す状態の特定 (受入 1)・修正案 (受入 3) | 本 issue #1317 |
| 所要秒 (n≥3) と REPORT_1076 の未検証 6 件 | #1076 へのコメント |

## 4a. 追補 (2026-10-14 run): icall の解決先と停止候補

- 測定 commit: `1e3ee7af` (origin/main。以降 `a5111d06` まで `tools/m11` の差分は本ファイルのみ)。
  `git diff 1e3ee7af HEAD -- tools/m11` の出力: `tools/m11/trap_triage/REPORT_1317.md` のみ (本追補の追記)。
  §1 の検証 HEAD `851c342e` は §2〜3 の基準で、`851c342e` から `1e3ee7af` までは `tools/m11` に 56 ファイルの差分がある。
- 再現 (ON build, `prefix_0_830_880`, 60 s): rc=124 (再現)。240 s の上限でも rc=124 (単なる遅さではない)。手順は §5。
- trace の 880 内の最後の 5 行は §3 と同一。
- §3 の「`0xe63540` は PE の範囲内だが関数先頭ではない」は、変換前の値 `0xe63540` を直接引いた結果で誤り。下記の変換後 `0x1263540` が関数先頭。
- `icall` 値は PE VA への変換 `0x400000 + value` で解決する (`m11_icall` の `tkey = target + 0x400000 - M11_LB_BASE`, `M11_LB_BASE=0`):
  - `0xf960` → PE `0x40f960` (size 34): `call 0x409410` → `call 0x40fb40`。
  - `0xe63540` → PE `0x1263540` (size 58): init フラグ `[rip+0x459e29]` を減算し、`[rip+0x459e22]==-1` なら 1 回だけ初期化する小関数。停止には無関係とみる。
- 停止候補 `0x40fb40` (size 191, `disasm_fn.py 0x40fb40`): 2 つのループを持つ。
  - `40fb91〜40fbb8`: `[rax]` の件数 (`r11d`) で回る表走査。件数が大きいと長時間回る。
  - `40fbd3〜40fbde`: `rcx = [rcx-0x78]; rcx = [rcx]` を `rcx==0` まで辿る連鎖。**循環すると終わらない**。
- 呼び出し順 (`disasm_fn.py` の逆アセンブルで確認): `40f960` → `call 0x409410` (GetFileVersionInfoSizeW stub。`rcx` は `[rbx-0x80]` の 32bit 値) → `call 0x40fb40`。`40fb40` は 2 つのループに入る前に `call 0x40d210` (size 267、間接 jmp のテーブル分岐) を呼ぶ。
- trace との整合 (仮説): stub 行は `40fb40` 突入より前。一方 `UStrAsg` ×2 は `40fb40` 突入後に `40d210` 内 (または `40d210` から呼ばれる先) で出た可能性がある。よって「最後の出力の後で `40fb40` に入り、ループで停止」が呼び出し順として整合する。`40d210` の中身は未確認 (テーブル先の逆引きが必要)。
- 仮説 (未検証): 830 が残す状態は、`40fbd3` 側の連鎖 (`[rcx-0x78]` から辿る構造) に循環を作る。停止は `40fb40` 内の無限ループ。
- 次の検証 (未実施): `40fb40` の入口で `rcx` (= 880 の対象構造体) の `[rcx-0x78]` と、その先の `[rcx]` を書き出し、2 回目以降に同じアドレスに戻るかを見る。

## 5. 再現コマンド

§2 (repro_1076.sh・60 s 上限) とは別手段 (survey_units.mjs・上限 20 s) の再現手順。

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP RETDEC_ROOT=$RUNNER_TEMP/tc/retdec M11_M2P=1
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh
SV_ONLY="$(seq -s, 0 830),880" SV_PROG=1 SV_TRACE_AT=880 timeout 20 node tools/m11/trap_triage/survey_units.mjs out.json
```

§4a の rc=124 (60 s / 240 s) の再現は、同じ build の上で `repro_1076.sh` の `prefix_0_830_880` 行を使う
(`timeout 60` を 240 に替えて再実行)。`M11_M2P=1` での build が前提で、OFF build では rc=0 になる (§2 の対照)。

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP RETDEC_ROOT=$RUNNER_TEMP/tc/retdec M11_M2P=1
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh
bash tools/m11/trap_triage/repro_1076.sh   # prefix_0_830_880 が rc=124 (上限 60 s)
```

この fix run では retdec / emsdk / work-m11 が未展開のため、rc=124 は再実測していない。§4a の rc=124 (60 s / 240 s) は PR #1662 本文に記載された実測値で、本ファイルの commit 時点では再検証していない。
`disasm_fn.py` は `FL_WIN64_DIR` 配下の `extracted/block00031_PE.bin` を使う (fl-win64 は `$HOME/artifacts/fl-win64.tar.zst` を展開)。

`work/` は gitignore 対象で commit しない。

## 6. 追補 (2026-10-14・#1317 3 回目 run)

- 測定 commit: `a5111d06` (コード差分 0。本節の追記のみ)。検証は `a5111d06` 上で ON build (`M11_M2P=1`) を再生成して行った。
- `m11_gen_ir2.sh` 46 s rc=0 / `m11_build.sh` 25 s rc=0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)。ldfix は §1 と同じ `errors=0`。load 0.6〜0.8。
- 再現 (`survey_units.mjs`, 60 s 上限):
  - `0..830` + 880: rc=124 (60 s 打ち切り。本 run では 1 回測定)。
  - `0..829` + 880: rc=0、2 s、`{"ok":765,"oob":13,"miss":46,"other":1,"halt0":4,"abort":2}`。
- `0x40fb40` (PE, size 191) の逆アセンブル (`disasm_fn.py 40fb40`) の構造:
  - `0x40fb6c`〜`0x40fbde` は `rcx ← [rcx-0xc0]` の配列走査 (`0x40fb91`〜`0x40fbb8` で `[rax+8+20*i]` の qword を `[rsi+off]` へ書く) と、`rcx ← [[rcx-0x78]]` を `rcx == 0` まで回す連鎖走査 (`0x40fbcf`〜`0x40fbde`) からなる。
  - 連鎖走査は終了条件が `rcx == 0` のみで、`[rcx-0x78]` の先が循環すると終わらない。この構造は**確認済み**。
  - 循環が 880 で実際に起きているかは**未検証**。hang は例外を出さないため `SV_RAW` (e.stack) では frame が取れない。次の一手は `SV_WATCH` で `[rcx-0x78]` の連鎖を辿る (`unit 880` の直前に読む) か、連鎖長に上限を入れた計測。
- icall 値の対応 (§5 の `0xf960` → `0x40f960` 等) は前 run の記述を引き継ぐ。wasm 側の icall 番号から PE VA への対応は未確認。

### 受入の状況 (本 run 末)

| 受入 | 状態 |
|---|---|
| 1. 830 が残す状態 | 未達 (未特定) |
| 2. 停止命令・wasm frame | 部分 (PE `0x40fb40` の構造まで。実際の停止は未確認) |
| 3. 修正案 | 未達 |
| 4. 修正後の完走 | 未実施 (停止は再現済み) |

## 7. 追補 (2026-10-14・#1317 4 回目 run): 再現の再測定

- 測定 commit: `04a7ff1a` (origin/main)。本追補のみが差分 (コード差分 0)。
- 素材: fl-win64・toolchain-retdec・toolchain-emsdk ([EMSDK])・work-m11・work-liftdiff を展開。`m11_gen_ir2.sh` 42 s rc=0 / `m11_build.sh` 27 s rc=0 (`M11_M2P=1`、`wasm-ld signature mismatch: 0`)。load 0.8〜1.3。
- 再現 (`SV_ONLY` + `survey_units.mjs`、上限 60 s、各 2 回):

| 条件 | run | rc | 所要 | 結果 |
|---|---|---|---|---|
| `0..829` + 880 | 1 | 0 | 1.32 s | `{"ok":765,"oob":13,"miss":46,"other":1,"halt0":4,"abort":2}` |
| `0..829` + 880 | 2 | 0 | 1.42 s | 同上 |
| `0..830` + 880 | 1 | 124 | 60.01 s (打ち切り) | 出力なし |
| `0..830` + 880 | 2 | 124 | 60.01 s (打ち切り) | 出力なし |

- 結論: 830 を含むと 880 が 60 s 超で止まる境界は、前 run までの記録 (§4a・§6) と一致。停止は再現した。
- 未解決 (受入 1・2・3・4 は未達): 循環の有無 (`0x40fb40` の `[rcx-0x78]` 連鎖)、830 が残す状態、修正案、修正後の完走。今回は計装 (連鎖長の計測) を入れる前に時間切れのため、未着手。
- 次の一手: `0x40fb40` の入口で `rcx` の連鎖を `SV_WATCH` 相当で辿る計装を新設するか、IR 側で連鎖長に上限を入れて停止位置を変えるかを決める。
