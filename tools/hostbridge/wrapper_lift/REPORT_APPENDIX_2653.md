# REPORT 付録 — #2653 (HB-H46): CreatePlugInstance の host 再構成と停止点の実測

> **正本の分担**: 結論と数値の表は `tools/hostbridge/wrapper_lift/REPORT.md` §14 (未解決表)。本付録は表に無い値 (観測ログ・呼出の形・再現手順・未解決) の正本。

測定 commit: `22625fe8c` (harness コードを変えた最後の commit。差し戻し後の修正で host 領域を PE イメージの外へ移した)。前回の測定 commit `e702caa14` は host を PE の `.text` 内 (`0x600000`) に置いていたため、停止原因の切り分けには使えない。検証起点: `origin/main` @ `72d5f3cc0` (作業ブランチ `2653-fruity-cpi-complete`、差し戻し対応の worktree `ws-3599`)。
環境: 上流 emsdk 6.0.12 (`emsdk install 6.0.12` で `$RUNNER_TEMP` に導入。`[EMSDK]` (`/opt/emsdk`) は本 run に無かった。`docs/REFERENCES.md` §4)・`fl-win64` の `extracted/block19091_PE.bin`・`block23676_PE.bin`・node v22.23.3。4 vCPU。全段直列 (並列 1)。

## 1. 受入条件の対応

| # | 受入条件 (issue #2653) | 結果 | 根拠 |
|---|---|---|---|
| 1 | block19091 の `CreatePlugInstance` が戻り値を返すまで走る | 未達 | 停止点を実測 (§3)。止まる場合の記録は達成 |
| 2 | block23676 (0x86a970) の入場を実測 | 達成 | `entered=true` (§3.2) |
| 3 | 起動経路 (LoadLibrary → GetProcAddress) から到達、または不可を実測 | 未達 | export 表の解決先のみ確認 (§4)。LoadLibrary は未実行 |
| 4 | 完走後に wasm の実行結果 (bit 一致) を判定 | 未達 | 完走していない |
| 5 | 強い NC (`cpi_enter` 無しの複製で `entered=false`) | 達成 | §3.3 |

## 2. host の再構成 (`cpi_host.c`)

- host = guest アドレス `0xA00000` (差し戻し前は `0x600000`)。PE イメージは `[0x400000, 0x9d0000)` (ImageBase `0x400000`・SizeOfImage `0x5d0000`・`.text` `0x401000`〜`0x897648`)。`0x600000` は `.text` の内側で、vtable・fake object・文字列の書込みが PE の定数データ (`onException…`・`FavoriteLink…`) を上書きしていた。
- guard: `cpi_reach.mjs` が PE ヘッダの SizeOfImage と section 表を読み、`cpi_host_setup(ImageBase, ImageBase+SizeOfImage)` に渡す。host 領域 `[0xA00000, 0xA42000)` が交差すると書かずに 0 を返し、`guard: host_overlaps_pe_image` を出して exit 3 で止まる。3 run とも交差していない (`pe_image` `0x400000-0x9d0000`)。
- vtable `0xA01000` (`qword[0]` = vtable)。スロット `i` の仮想 VA は `0x7ff00000 + 8i` (128 スロット)。fake object `0xA40000`、空文字列 `0xA41000`。
- 呼出し: slot 6 は 6 番目の引数 (`&out`。callee 入口では `R[RSP]+0x30`) に空文字列 `0xA41000` を書き、`rax = 1` を返す。それ以外の slot は fake object `0xA40000` を返す。
- 未解決 import は `ott_missing_import` の先頭で `cpi_miss_imp` が記録し、`rax = 0` で返す。HEAD の 3 run では import の捕捉は 0 件 (記録は vtable 呼びのみ)。
- lift 出力 (`x64c_wrapper.py` の生成 C) と rt (`tools/ott/rt`) は変更しない。複製 C の sed 差し込み 2 箇所 (`default` 分岐・`ott_missing_import`)、`cpi_host.o` の link 追加、`cpi_enter` の entry 引数化だけ。

## 3. 観測 (HEAD `22625fe8c`)

### 3.1 block19091 (entry 0x86ab10、host 0xa00000)

- `entered=true`、命令数 134 (NULL host 版の 49 から増加。#829 の付録 §2.2 の値)。
- 記録 (`host_log`): `[cpi] host slot 0 rcx=0xa00000 rdx=0 r8=0x47` → `[cpi] host slot 6 rcx=0xa40000 rdx=0x40f r8=0x77fba8`。
- 停止: 命令 VA `0x409b9a` (`rep movsb byte ptr [rdi], byte ptr [rsi]`)、`RuntimeError: memory access out of bounds`。直近 16 命令は `0x4122ea`・`0x4122ed` の後に `0x409b70`〜`0x409b9a` (`f_409b70` 内)。
- 最初に失敗する関数: `f_409b70` (memmove 系。src=rcx、dst=rdx、件数 `r8 − rax` を `0x409b7d` で計算する)。
- 経路 (実測): `f_77fbb0` が vtable[0] を呼ぶ (slot 0) → 戻り値 (fake object) を引数に `f_77faf0` → `f_77faf0` が `obj->vtable[6]` を呼ぶ (slot 6) → 応答 `eax = 1` を受けて後続の copy 経路へ → `f_409b70`。直前の `0x4122ea`・`0x4122ed` が呼出元の候補 (関数は未特定)。
- 停止の理由 (推定・未検証): slot 6 は `&out` に文字列の番地を書くだけで、copy の件数 (`r8 − rax`) を決める値を返していない。件数の実値は未記録。
- 切り分け (本 HEAD で実施): host を `0x600000` から `0xa00000` へ移しても、停止点・命令数・host_log は前回と同一。よって PE 定数の上書きは停止の原因ではない。残る候補は host 応答 (slot 6 の `&out` の文字列と `rax = 1`) だが未検証。

### 3.2 block23676 (entry 0x86a970、host 0xa00000)

- `entered=true`、命令数 134。`host_log` は同じ形 (slot 6 の `r8` のみ `0x77fa18`)。
- 停止: 同じ `0x409b9a` (`f_409b70`)、同じ `memory access out of bounds`。

### 3.3 強い NC (block19091、`CPI_NOENTER=1` で `cpi_enter` 行を入れない複製)

- `entered=false`、命令数 133、停止は §3.1 と同じ `0x409b9a`。入場タグ `[cpi] enter 0x86ab10` が出ないことで、`entered` は probe 行に依存する。

## 4. 起動経路 (LoadLibrary → GetProcAddress) の静的確認

- `block19091_PE.bin` の export 表 (`pefile`): 3 件。`CreatePlugInstance` は RVA `0x46ab10` = VA `0x86ab10` (ImageBase `0x400000`)。GetProcAddress 相当の解決先は harness の入場 VA と一致する。
- LoadLibrary・DllMain は未実行。経路での到達は未検証 (受入条件 3 は未達)。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/r2653/extracted EM_CONFIG=<EMSDK>/.emscripten PATH=<EMSDK>/upstream/emscripten:$PATH   # <EMSDK> = 上の環境行の導入先
python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py block19091_PE.bin $RUNNER_TEMP/r2653/x64c19091      # 74 s (block23676 も同じ手順で 74 s)
W=$RUNNER_TEMP/r2653/cpi19091; mkdir -p $W/x64c && ln -sf $RUNNER_TEMP/r2653/x64c19091/ott_lifted.c $W/x64c/ott_lifted.c
bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin $W                              # 3.1 (host 0xa00000 = 既定)
bash tools/hostbridge/wrapper_lift/cpi_reach.sh block23676_PE.bin $RUNNER_TEMP/r2653/cpi23676 0x86a970   # 3.2 (W/x64c/ott_lifted.c は block23676 の x64c 出力への symlink)
CPI_NOENTER=1 bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin $RUNNER_TEMP/r2653/nc19091  # 3.3 (W/x64c も 19091 への symlink)
```

## 6. 所要と load (n=1、HEAD `22625fe8c`)

| 段 | 秒 | load (1 分値・開始→終了) |
|---|---|---|
| `x64c_wrapper.py` block19091 | 74 | 未計測 |
| `x64c_wrapper.py` block23676 | 74 | 0.88 → 0.96 |
| `cpi_reach.sh` block19091 (3.1) | 79 | 0.70 → 0.95 |
| `cpi_reach.sh` block23676 (3.2) | 80 | 0.89 → 0.97 |
| `cpi_reach.sh` NC (3.3) | 82 | 0.89 → 0.98 |

`cpi_reach.sh` の秒は emcc 2 回・link・node 実行の全体。前回 (`e702caa14`) の 41 s とは runner が異なるため直接比較しない。n=1 のため min–max は未評価。

## 7. 測定 commit から HEAD までのコード差分

`git diff 22625fe8c HEAD -- tools/hostbridge/wrapper_lift/*.sh tools/hostbridge/wrapper_lift/*.mjs tools/hostbridge/wrapper_lift/*.c tools/hostbridge/wrapper_lift/*.py` の出力は、この文書の commit 時点で空 (文書のみの変更)。
前回測定 (`e702caa14`) から測定 commit までの差分: `cpi_host.c` (14 行変更)・`cpi_reach.mjs` (35 行)・`cpi_reach.sh` (6 行)。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| host 応答の内容 (slot 6 の文字列と copy 件数) を呼出側の想定に合わせ、`f_409b70` を越えて CreatePlugInstance を完走させる | 戻り値・Dispatcher 実行は未検証 | 子 issue #3597 (`[HB-H51]`) |
| 停止の呼出元 (`0x4122ea`・`0x4122ed` の関数) の特定と copy 件数 (`r8 − rax`) の実値の記録 | 停止の原因は推定のまま | #3597 |
| LoadLibrary → GetProcAddress 経路からの到達 | 起動経路からの到達は未検証 | #3597 |
| 完走後の wasm 実行結果 (bit 一致) | 未検証 | #3597 |
