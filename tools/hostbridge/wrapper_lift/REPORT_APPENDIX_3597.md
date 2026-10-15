# REPORT 付録 — #3597 (HB-H51): CreatePlugInstance の停止点の追跡 (slot 6 応答の修正)

> **正本の分担**: 前段の停止点 (`f_409b70`) の観測は `REPORT_APPENDIX_2653.md` §3 が正本。本付録は slot 6 応答を直した後の停止点と、その呼出元の確認を記録する。

測定 commit: `dec2ec7a0` (harness `cpi_host.c` を変えた最後の commit)。検証起点: `origin/main` @ `4f3c0ad46`。
環境: x64c 生成 (`block19091_PE.bin`) と emsdk 6.0.12 (`toolchain-emsdk` 素材の展開先)・`fl-win64` の `extracted/`・node v22.23.3 (`PATH` 上のもの)。4 vCPU。全段直列。

## 1. 受入条件の対応

| # | 受入条件 (issue #3597) | 結果 | 根拠 |
|---|---|---|---|
| 1 | block19091 の CreatePlugInstance が戻り値を返すまで走る | 未達 | 停止点を `f_4079e0` まで前進 (§3)。戻り値は未取得 |
| 2 | 起動経路 (LoadLibrary → GetProcAddress) から到達、または不可を実測 | 未達 | 未着手 |
| 3 | 完走後に wasm の実行結果 (bit 一致) を判定 | 未達 | 完走していない |

## 2. 変更点 (`dec2ec7a0`)

- slot 6 の応答を、`&out` に文字列の**番地**ではなく NUL 終端の実文字列 (`A`〜の 127 字 + NUL) を書く形にした。
- 理由: 呼出側 `f_77faf0` は `out` (`rbp+0x50`・上限 0x400) を `f_412c10` (`rcx`=長さ格納先・`rdx`=`out`・`r8`=上限 0x400) に渡す。`f_412c10` は `out` を NUL まで走査して長さを決め、`f_4122c0` にその長さを渡す。番地 `0xA41000` の先頭バイトは 0 のため長さは 0 となる、と読める。修正後に `f_409b70` を越えたことは、この読みと整合する観測である。ただし `f_412c10` の長さ 0 は直接観測していない (推定)。また修正後の応答は `'A' + (k % 26)` の 127 字の合成文字列で、実 host の応答を観測したものではない。

## 3. 観測

### 3.1 修正前 (`REPORT_APPENDIX_2653.md` §3.1 の引用・本 run では再実行していない)

- `entered=true`・`insn_count=134`・停止 `0x409b9a` (`f_409b70`・`rep movsb`)・`memory access out of bounds`。本 run では再実行していない (引用元の値)。

### 3.2 修正後 (測定 commit `dec2ec7a0`)

- `entered=true`・`ret=null`・`insn_count=908`・`host_calls=2`・`trap=memory access out of bounds`。
- `host_log`: `[cpi] host slot 0 rcx=0xa00000 rdx=0 r8=0x47` → `[cpi] host slot 6 rcx=0xa40000 rdx=0x40f r8=0x77fba8` (修正前と同じ)。
- 停止: 命令 VA `0x407a3e` (`f_4079e0` 内の `and rcx, qword ptr [rax - 8]`)。直近は `0x407a21`〜`0x407a3e` で、`[rbx+8]` から辿ったチャンクのヘッダ (`[rax-8]`) を読む箇所。
- 呼出連鎖の `f_409b70` を通過したため、copy の件数の問題は解消した。新しい停止は guest の割当て管理 (malloc 系) 側の読み出しに見えるが、原因は未特定。応答の内容を変えたため、割当て側の入力が変わった可能性があり、host 応答との関係は未検証。

### 3.3 所要と load (n=1)

| 段 | 秒 | load (1 分値・開始→終了) |
|---|---|---|
| `x64c_wrapper.py` block19091 | 75 | 未計測 |
| `cpi_reach.sh` (修正後、`dec2ec7a0`) | 79 | 0.34 → 0.83 (`uptime` の 1 分値。開始 10:03:58・終了 10:05:17) |

`cpi_reach.sh` の秒は emcc 2 回・link・node 実行の全体。runner の差があるため比較の精度は低い。n=1 のため min–max は未評価。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `f_4079e0` (guest 割当て管理) の停止原因の特定と、slot 6 応答または割当て初期化の修正 | CreatePlugInstance の完走は未達 | 子 issue #4582 (`[HB-H56]`) |
| LoadLibrary → GetProcAddress 経路からの到達 (受入 2) | 起動経路からの到達は未検証 | #3597 (本 issue・部分達成のため open) |
| 完走後の wasm 実行結果 (bit 一致) (受入 3) | 未検証 | #3597 |
