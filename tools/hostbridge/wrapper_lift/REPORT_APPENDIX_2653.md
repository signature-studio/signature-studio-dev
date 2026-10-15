# REPORT 付録 — #2653 (HB-H46): CreatePlugInstance の host 再構成と停止点の実測

> **正本の分担**: 結論と数値の表は `tools/hostbridge/wrapper_lift/REPORT.md` §15。本付録は表に無い値 (観測ログ・呼出の形・再現手順・未解決) の正本。

測定 commit: `e702caa14` (harness コードを変えた最後の commit)。検証起点: `origin/main` @ `72d5f3cc0` (作業ブランチ `2653-fruity-cpi-complete`、worktree `ws-2653`)。
環境: `[EMSDK]` 6.0.12 (`/opt/emsdk`)・`fl-win64` の `extracted/block19091_PE.bin`・`block23676_PE.bin`・node v22.23.3。4 vCPU。全段直列 (並列 1)。

## 1. 受入条件の対応

| # | 受入条件 (issue #2653) | 結果 | 根拠 |
|---|---|---|---|
| 1 | block19091 の `CreatePlugInstance` が戻り値を返すまで走る | 未達 | 停止点を実測 (§3)。止まる場合の記録は達成 |
| 2 | block23676 (0x86a970) の入場を実測 | 達成 | `entered=true` (§3) |
| 3 | 起動経路 (LoadLibrary → GetProcAddress) から到達、または不可を実測 | 未達 | export 表の解決先のみ確認 (§4)。LoadLibrary は未実行 |
| 4 | 完走後に wasm の実行結果 (bit 一致) を判定 | 未達 | 完走していない |
| 5 | 強い NC (`cpi_enter` 無しの複製で `entered=false`) | 達成 | §3.3 |

## 2. host の再構成 (`cpi_host.c`)

- host = guest アドレス `0x600000`。`qword[0]` = vtable `0x601000`。vtable の各スロット `i` は仮想 VA `0x7ff00000 + 8i` (128 スロット)。
- lift 出力の `ott_dispatch` の `default` 分岐 (未 lift の間接 call) に `cpi_miss` を差し込む。仮想 VA なら記録して返し、それ以外は従来どおり `ott_unlifted` で abort する。
- 戻り値: 既定は fake object `0x640000` (`qword[0]` = vtable)。slot 6 だけは、6 番目の引数 `&out` (呼出側 RSP の `+0x28`。callee 入口では `R[RSP]+0x30`) に空文字列 `0x641000` を書き、`rax = 1` を返す。
- 未解決 import は `ott_missing_import` の先頭で `cpi_miss_imp` が記録し、`rax = 0` で返す。HEAD の 3 run では import の捕捉は 0 件 (記録は vtable 呼びのみ)。
- lift 出力 (`x64c_wrapper.py` の生成 C) と rt (`tools/ott/rt`) は変更しない。複製 C の sed 差し込み 2 箇所 (`default` 分岐・`ott_missing_import`)、`cpi_host.o` の link 追加、`cpi_enter` の entry 引数化だけ。

## 3. 観測 (HEAD `e702caa14`)

### 3.1 block19091 (entry 0x86ab10、host 0x600000)

- `entered=true`、命令数 134 (NULL host 版の 49 から増加。#829 の付録 §2.2 の値)。
- 記録 (`host_log`): `[cpi] host slot 0 rcx=0x600000 rdx=0 r8=0x47` → `[cpi] host slot 6 rcx=0x640000 rdx=0x40f r8=0x77fba8`。
- 停止: 命令 VA `0x409b9a` (`rep movsb byte ptr [rdi], byte ptr [rsi]`)、`RuntimeError: memory access out of bounds`。直近 16 命令は `0x409b8b`〜`0x409b9a` (`f_409b70` 内)。
- 最初に失敗する関数: `f_409b70` (memmove 系。src=rcx、dst=rdx、件数 `r8 − rax` を `0x409b7d` で計算する)。
- 経路 (実測): `f_77fbb0` が vtable[0] を呼ぶ (slot 0) → 戻り値 (fake object) を引数に `f_77faf0` → `f_77faf0` が `obj->vtable[6]` を呼ぶ (slot 6) → 応答 `eax = 1` を受けて後続の copy 経路へ → `f_409b70`。`f_409b70` は直接 call されず、間接 call (`ott_dispatch` 経由) で入る。**呼出元は未特定**。
- 停止の理由 (推定・未検証): slot 6 は `&out` に文字列の番地を書くだけで、copy の件数 (`r8 − rax`) を決める値 (文字列の長さや端の番地) を返していない。件数が不正になり、`rep movsb` が範囲外へ出た。件数の実値は記録していない (次の作業で最初に記録する)。

### 3.2 block23676 (entry 0x86a970、host 0x600000)

- `entered=true`、命令数 134。`host_log` は同じ形 (slot 6 の `r8` のみ `0x77fa18`)。
- 停止: 同じ `0x409b9a` (`f_409b70`)、同じ `memory access out of bounds`。

### 3.3 強い NC (block19091、`CPI_NOENTER=1` で `cpi_enter` 行を入れない複製)

- `entered=false`、命令数 133、停止は §3.1 と同じ `0x409b9a`。入場タグ `[cpi] enter 0x86ab10` が出ないことで、`entered` は probe 行に依存する。

## 4. 起動経路 (LoadLibrary → GetProcAddress) の静的確認

- `block19091_PE.bin` の export 表 (`pefile`): 3 件。`CreatePlugInstance` は RVA `0x46ab10` = VA `0x86ab10` (ImageBase `0x400000`)。GetProcAddress 相当の解決先は harness の入場 VA と一致する。
- LoadLibrary・DllMain は未実行。経路での到達は未検証 (受入条件 3 は未達)。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/r2653/extracted EM_CONFIG=/opt/emsdk/.emscripten PATH=/opt/emsdk/upstream/emscripten:$PATH
python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py block19091_PE.bin $RUNNER_TEMP/r2653/x64c19091      # 61 s (block23676 も同じ手順で 61 s)
W=$RUNNER_TEMP/r2653/cpi19091; mkdir -p $W/x64c && ln -sf $RUNNER_TEMP/r2653/x64c19091/ott_lifted.c $W/x64c/ott_lifted.c
bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin $W                              # 3.1 (host 0x600000)
bash tools/hostbridge/wrapper_lift/cpi_reach.sh block23676_PE.bin $RUNNER_TEMP/r2653/cpi23676 0x86a970   # 3.2 (x64c は block23676 で生成)
CPI_NOENTER=1 bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin $RUNNER_TEMP/r2653/nc19091  # 3.3
```

## 6. 所要と load (n=1、HEAD `e702caa14`)

| 段 | 秒 | load (1 分値・開始→終了) |
|---|---|---|
| `cpi_reach.sh` block19091 (3.1) | 41 | 0.28 → 0.63 |
| `cpi_reach.sh` block23676 (3.2) | 41 | 0.63 → 0.81 |
| `cpi_reach.sh` NC (3.3) | 41 | 0.81 → 0.91 |

x64c 生成 (61 s) は x64c_wrapper.py の変更が無いため HEAD での再測定はしていない (測定 commit 前の値・同じ生成物 66,774,883 B)。n=1 のため min–max は未評価。

## 7. 測定 commit から HEAD までのコード差分

`git diff e702caa14 HEAD -- tools/hostbridge/wrapper_lift/*.sh tools/hostbridge/wrapper_lift/*.mjs tools/hostbridge/wrapper_lift/*.c tools/hostbridge/wrapper_lift/*.py` の出力は、この文書の commit 時点で空 (文書のみの変更)。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| host 応答の内容 (slot 6 の文字列と copy 件数) を呼出側の想定に合わせ、`f_409b70` を越えて CreatePlugInstance を完走させる | 戻り値・Dispatcher 実行は未検証 | 子 issue #3597 (`[HB-H51]`) |
| LoadLibrary → GetProcAddress 経路からの到達 | 起動経路からの到達は未検証 | #3597 |
| 完走後の wasm 実行結果 (bit 一致) | 未検証 | #3597 |
