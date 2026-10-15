# tools/flelift/boot — FLE-15 (#3770): 診断 route の有界実行と 0x6bbc20 の呼出し計数

> 測定値の正本。親 #3491 (FLE-14)・#672。REPORT §0 から参照。

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 と照合。本件は計測側の打ち切りと計数で、lift の類型は判定していない)。

## 1. 結論

- **units_run は 209 のまま** (診断 route の shim 有・ネガコンとも)。時間上限 300 秒で打ち切った時点で**停止せず**、次の停止点は**未取得** (停止しなかったことが結果)。
- 呼出点 `0x6c9380` (`f_6c9280` の `0x6c937a: call [rbx+0x118]` の戻り番地) の呼出し: 300 秒で **6,559,882 回** (shim 有) / **6,559,461 回** (ネガコン)。矩形 `(x0,y0,x1,y1)` = **(0, 0, 1048576, 1048576)** で、初回から変化なし (寸法 w = h = 2^20)。
- 既定経路 (root `0x6a7b70`・診断なし) は issue の基準と一致: shim 有 **2,314 / 1,199**、ネガコン **1,891 / 776**、units 209。

## 2. 方法 (計測側の変更。`rt/`・`x64c.py` は変えない)

- `fle_boot.mjs`:
  - `FLE_BOOT_LOG_CAP` (bytes): console 出力 (stdout/stderr) の累計がこれを超えたら JS 例外で boot を抜け、結果 JSON を出す。JSON の `log_cap` に `hit` (`bytes` / `time`)・`bytes`・`lines`・`bin_lines`・`elapsed_ms` を残す。
  - `FLE_BOOT_TIME_CAP` (秒): 出力の度に経過を見て、超えたら同じ経路で抜ける。出力が途切れない反復 (下記 §3-2) でも打ち切れる。
  - `FLE_BOOT_QUIET_BIN=1`: U+FFFD・制御文字を含む行 (ガストの生バイト列) は表示せず数えるだけにし、上限の計数に入れない (`bin_lines` / `bin_bytes`)。
  - 停止は boot 内の JS 例外 (`fle_throw_kind` と同じ経路)。`boot.threw` は `log_cap ...`。
- `fle6_measure.sh`: `run_boot` を `timeout ${FLE_BOOT_TIMEOUT:-900}` で包む (rc=124 は時間上限の打ち切りとして記録)。`diag_*` の既定ログ上限は `FLE_BOOT_LOG_CAP` (既定 256MiB)。
- `fle_boot.c`: `px_probe` (`fle_probe_dispatch` で `t == 0x6bbc20` のとき計数)。呼出し点 = `[rsp]` が `0x6c9380` のもの。矩形は `f_6c9280` の `rbp+0x2c..0x38` (`rbp` = `R[5]`。`mov rsi,rdx`→`movsq` ×2 で frame に複写されている)、画素座標は `x = rdx`・`y = r8` (呼出し直前の `movsxd` の値)。export `fle_px_stat(k)` を `build.sh`・`boot_e2e.sh`・`iterate_roots.sh` の EXPORTS に追加。

実行コマンド (`$RUNNER_TEMP` の素材展開先は `FL_WIN64_DIR`):

```sh
FLE_EXTRA_ROOTS=0x6bbc20 FLE_BOOT_WORK=$RUNNER_TEMP/fle3770/w_x FLE_BOOT_TAG=fle15x \
  FLE_BOOT_RUNS="diag_shim diag_negctl" FLE_BOOT_QUIET_BIN=1 FLE_BOOT_TIME_CAP=300 \
  FLE_BOOT_LOG_CAP=268435456 FLE_BOOT_TIMEOUT=420 bash tools/flelift/boot/fle6_measure.sh   # 診断 route
FLE_BOOT_WORK=$RUNNER_TEMP/fle3770/w_r FLE_BOOT_TAG=fle15 FLE_BOOT_RUNS="shim negctl default" \
  FLE_BOOT_TIMEOUT=300 bash tools/flelift/boot/fle6_measure.sh                              # 既定経路 (root 0x6a7b70)
```

## 3. 実測 (各 route n=1。4 vCPU・load は各工程の開始時)

### 3-1. 一覧

| route | 診断 | units | GetMem / FreeMem | 呼出点 0x6c9380 の回数 | 矩形 (x0,y0,x1,y1) | 停止 | 結果 JSON |
|---|---|--:|--:|--:|---|---|---|
| 診断 shim (root `0x6bbc20`) | on | 209 | 2,314 / 1,200 | 6,559,882 | (0,0,1048576,1048576) | **300 s で打ち切り (停止せず)** | `boot_summary_fle15x_diag_shim.json` |
| 診断 ネガコン (root `0x6bbc20`) | on | 209 | 1,891 / 777 | 6,559,461 | (0,0,1048576,1048576) | **300 s で打ち切り (停止せず)** | `boot_summary_fle15x_diag_negctl.json` |
| 既定 shim (root `0x6a7b70`) | off | 209 | **2,314 / 1,199** | — | — | exit (MessageBoxA → ExitProcess)・IPP 判定 NG (rc=3・既知) | `boot_summary_fle15.json` |
| 既定 ネガコン (root `0x6a7b70`) | off | 209 | **1,891 / 776** | — | — | exit・IPP 判定 OK | `boot_summary_fle15_negctl.json` |
| 既定 (FLE_IPP 未指定・root `0x6a7b70`) | off | 209 | 1,891 / 776 | — | — | exit・IPP 判定 OK | `boot_summary_fle15_default.json` |

- 工程 (診断 route): lift 80 s (load 0.86)・clang 8 shard + link 85 s (load 2.34)。boot は shim 300 s・ネガコン 300 s (いずれも時間上限)。
- 工程 (既定経路): lift 81 s・clang 99 s・boot 24 s / 25 s / 25 s。
- 診断 shim の FreeMem は既定 shim (1,199) より +1 (原因は未確認)。

### 3-2. 診断 route の出力 (shim 有・時間上限 300 s 時点)

- 出力は 2 種類: 通常の診断行 **11,228 行 (740,626 B)** と、**U+FFFD (`EF BF BD`) を含む生バイト列の行 11,057,543 行** (`QUIET_BIN` で除外)。
- 生バイト列は通常行の 11,225 行目から始まる。直前は `[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss, call site ret=0x6c9c6c)`。**出所は未特定** (guest の書込み系 import から fd 1 への出力と推定。未確認)。同じ診断を LOG_CAP のみ (256MiB・211 s・本 run の事前実行) で止めた時も、生バイト列は同じ位置から始まった。
- `[fill6a7b70]` は既存の上限 (先頭 200 件)。`diag_skip` = 1,048,576 (buf = 0 の呼出しを戻した数。#672 の §11 と同値)。

### 3-3. 導出値 (計算。測定値ではない)

- 呼出し速度: 6,559,882 回 / 300 s ≈ 21,866 回/s (計算)。
- 矩形 (0,0,2^20,2^20) の画素数 = 2^40 ≈ 1.10e12 (寸法からの計算)。`f_6c9280` の走査が矩形全体を覆うことは**未確認**。
- 矩形全体を 1 回走査するのに要る時間: 約 5.0e7 s (推定 = 画素数 ÷ 観測速度。全画素を走査する前提)。**よって現在の root 集合では、この loop は時間内に終わらない** (推定)。
- x の min–max は 0–1,048,575、y の min–max は 1–68 (300 s 時点・全呼出しの範囲)。行の進み方は未確認。

## 4. 解釈 (推定。実測の範囲外)

- `0x6bbc20` を root 化すると、unit 209 の後の `unlifted 0x6bbc20` は消えるが、直後の `f_6c9280` (`0x6c9280`) の矩形走査が 2^20 × 2^20 で終わらず、**次の停止点は現れない**。
- 寸法 2^20 の源は `f_815050` の幅 r8 (即値 `0x4130000000000000` 由来の推定・#3090)。上流の修復 (#3112 [FLE-13]) が本体で、`boot_roots.json` への追加だけでは 209 を超えない (推定)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 矩形 2^20 × 2^20 の源 (`f_815050` の幅 r8・即値由来の推定) | `0x6bbc20` の走査が終わらず、次の停止点が出ない | 既存 #3112 [FLE-13] |
| `[obj+0x118]` へ `0x6bbc20` を書く元 (実行時設定・未特定) | `0x6bbc20` の root 化の是非の判断 (boot_roots か lift 修正か) | 既存 #3771 [FLE-16] (親 #3491) |
| 生バイト列 (U+FFFD) の出所 (fd 1 への書込み元) | 診断 route の出力の解読。ログ上限が無いと 20GB 級になる | 親 #3491 (コメントで追記) |
| 診断 route の FreeMem +1 の内訳 | 既定 (診断なし) との差の説明 | 未調査 (影響は 1 件・既定経路には無い) |
