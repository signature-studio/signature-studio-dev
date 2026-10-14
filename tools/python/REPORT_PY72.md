# PY-72 (#2542): channels.setChannelPitch の PE 意味論

前段: `tools/python/REPORT_PY39.md` (7 関数の書式・ハンドラ位置)。既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルによる解析)。

## 解析 (PY-72 #2542)

- 対象: `channels.setChannelPitch` (flapi `(int, float, int=0, int=PIM_None, bool=False)`)。本ファイルが PY-72 の記録の正本 (子 #2562・#2576 の記録もここに節を立てる)。
- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>` と `analysis/flapi/pe_rip_consts.py <VA> <命令数>` (`pe_rip_consts.py` は本 run で追加。`pe_disasm.py` は `<命令数>`×16 バイトの窓内で最大 `<命令数>` 命令を出す (`0xd5a720` の 180 は窓内の 173 命令)。`pe_rip_consts.py` は `<命令数>` 命令で打ち切る)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (`-C` は `-xf` の直後に置く。`--wildcards` の後ろに置くと GNU tar 1.35 でカレントに展開される。正しい順では `<展開先>/extracted/block00031_PE.bin` に出る)。実測 1.7 秒 (`00a01625`)・2.9 秒 (`3787c3d0`)。
- 既知類型との関係: 該当なし (lift 作業ではない)。
- 測定 commit: `3787c3d0` (`origin/main` (`ea407723`) を取り込んだ merge commit。コードを変えた最後の commit)。測定対象の `analysis/flapi/pe_disasm.py`・`pe_rip_consts.py` は `00a01625` から変更なし (`git diff 00a01625 3787c3d0 -- tools/python/analysis/flapi/pe_disasm.py tools/python/analysis/flapi/pe_rip_consts.py` は 0 行)。差分 0 の証跡: `git diff 3787c3d0 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (後続の commit は本ファイルのみ)。
- 再実行 (`3787c3d0`・展開 2.9 秒・load 0.31): `pe_disasm.py 0xd5aa30 75` 終了 0 (75 行)・`pe_disasm.py 0xd5a720 180` 終了 0 (call 14 件、`0xffac20` 0 件、`ret` は `0xd5a9dc`)・`pe_rip_consts.py 0xd5a720 180` 終了 0 (RIP 参照 12 件。`260` でも 12 件)。前回測定 (`00a01625`・展開 1.7 秒) と同じ結果。

### 結論 (PE 実測で確定した範囲)

- 戻り値・範囲外・value の検査・pitchUnit の 3 分岐は PE から確定した (下表)。
- 確定していないもの: 効果関数 (`0x1051d20`・`0xf81ce0`・`0x425210`・`0x526190`) の中身。観測できる副作用 (パラメータ値の読出し口) が flapi に無いため、C 側の実装に必要な状態モデルは未確定。推測では実装しない。

### ハンドラ `0xd5aa30` (PyArg 書式と委譲)

| 項目 | PE 実測 |
|---|---|
| 書式 | `if\|iii` (参照: `0xd5aa8e` `lea r8, [rip+0x10f]` → 文字列 `0xd5aba4`。`0xd5aaaa`〜`0xd5aadf` の出力先 `[rbp+0xa8]`=index・`[rbp+0xac]`=value(float)・`[rbp+0xa4]`=pitchUnit・`[rbp+0xa0]`=pickupMode・`[rbp+0x9c]`=useGlobalIndex) |
| 既定値 | 省略時は pitchUnit=0・pickupMode=0・useGlobalIndex=0 (`0xd5aa68`〜`0xd5aa7c` で 0 を書く)。flapi の既定 `PIM_None` が 0 かは未確認 |
| 委譲 | `0xd5e620(self)` の戻り値 `rax` が指す値を `rbx` に読む (`0xd5aa65` `mov rbx, [rax]`)。`0xd843d0(rbx, &out, r8=0xd5a720, r9=0, index, &value, pitchUnit, pickupMode, useGlobalIndex, 0, 1)` を呼ぶ (`0xd5aaf3` で `r8 = 0xd5a720` = callback を確認) |
| 戻り値 | `out` の下位 32bit を `0xd82c20` に渡し、その戻り値を返す (`0xd5ab4c`〜`0xd5ab5a`) |
| 解析失敗の経路 | 書式解析の戻り値 `eax` が 0 以下 (`0xd5aae7` の `jle 0xd5ab53`) のとき、`out` を経由せず `mov ecx, eax` (`0xd5ab53`) で**その戻り値をそのまま** `0xd82c20` の第 1 引数にする。`0xd82c20` の戻り値を返す経路は成功時と同じ。この経路の status 解釈は未確定 (未確定 6) |

### task 生成 `0xd843d0`

- `out := -2` で初期化 (`0xd843e9`)。`[rbx+0x50]` が非 0 で `0xd84f30` が偽なら、task を作らずに `out=-2` で戻る (`0xd84500`)。
- task (`0xd841e0`) に index / &value / pitchUnit / pickupMode / useGlobalIndex を `+0x18/+0x20/+0x28/+0x30/+0x38` で格納し、`+0x58 = callback` を書く (`0xd8446b`)。
- `0x526190` で task を登録した直後に `out := [task+0x60]`、`out+8 := [task+0x10]` を読む (`0xd844d7`〜`0xd844db`)。**`0x526190` が callback を同期に実行するか未確認** (推定: 同期。根拠は直後に status を読むこと)。

### callback `0xd5a720` (意味論の本体)

判定順 (上から順。`[task+0x60]` が status):

1. `status := -2` (`0xd5a733`)。
2. guard: 大域オブジェクトの vtable `[+0x98]` が偽なら終了 (status は -2 のまま → 「Operation unsafe at current time」)。`0xd5a755`。guard の中身は未確認。
3. `status := 0` (`0xd5a75d`)。
4. index 解決 `0x1005730(index, dl=(useGlobalIndex>0), &chan)`。
   - `dl=0` は一覧 B (`[rip+0x5da9a8]`)、`dl≠0` は一覧 A (`[rip+0x5dcad3]`) の要素 `[index]` (`0xfe8bb0`。`0 ≤ index ≤ 件数-1`)。範囲外・負値は偽。
   - 偽なら `status := -4` (`0xd5a9c7`)。
   - 一覧 A/B の中身 (同一 channel 列か) は未確認。
5. value 検査 `0x477180(value)`: `0x450c10` の分類が 8 (NaN) なら `status := -1` (`0xd5a79f`)。**NaN → -1**。±inf は検査されず、後段のクランプで処理される。
6. pitchUnit (`[task+0x28]`):
   - **0**: `v' = clamp(0.5·v + 0.5, 0, 1)` (float 演算。定数 `*[0x15e4000]`=0.5、`[0xd5a9e0]`=0.5 (double)、`[0xd5a9e8]`=2^30)。`n = cvtsd2si(v'·2^30 + (0.5-2^-54))` (`0x40c660` = `cvtsd2si`)。`0xf81ce0(key, pickupMode)` を呼んだ後、`0x1051d20(key, n, 0x3fd, 0, 0, 0.0f, 0)`。`key = ((chan+0x794) & 0xffff) << 16 | 4` (`0xd5a7cf`〜`0xd5a880`)。
   - **1**: `N = [chan+0x2f4]`。`v' = clamp(0.5·(v / (100·N)) + 0.5, 0, 1)` (`divss` で `N·100`。`0xd5a88a`〜`0xd5a956`)。以降は 0 と同じ tail。N が 0 なら 0 除算になる (商は ±inf または NaN。未確定 5)。
   - **2**: `N := clamp(cvtsd2si(v), 1, 48)` (`0xd5a958`〜`0xd5a97c`)。続けて `0x117baa0` → `0x40fe90` → `0x617920` → `0x425210(…, 0x550, chan+0x794, 0)` (通知。中身未読)。
   - その他の値: 何もせず終了 (status 0 のまま = 成功扱い。`0xd5a7c4`)。
7. 注意: value は Python の `float` 引数なので、float32 に丸めてから検査・演算する (`movss` 系)。pitchUnit=2 で `cvtsd2si` が int64 範囲外なら `0x8000000000000000` になり、`clamp(…, 1, 48)` で 1 になる。

### status → Python (`0xd82c20`)

| status | 文言 (PE の文字列) | 由来 |
|---|---|---|
| 0 | (`0xc38bc0(0)` 経由。戻り値の型は未確認。None と推定) | callback の成功 |
| -1 | `Unspecified error` (`0xd82e24`) | value が NaN |
| -2 | `Operation unsafe at current time` (`0xd82e44`) | guard が偽 (callback 未実行) |
| -3 | `Range error` (`0xd82e74`) | setChannelPitch の callback からは現れない |
| -4 | `Index out of range` (`0xd82e8c`) | index 解決の失敗 |

- 例外の型 (`[rip+0x85e38a]` の先) は未確認。C provider の `FL_E_RANGE` (4) が -4 に、`Index out of range` の文言が一致する。

### 未確定 (次に読む対象・起票先は下記 issue)

1. 効果関数: `0x1051d20` (key・n・param `0x3fd`・float 0.0 の意味。パラメータ値の書込みか)、`0xf81ce0` (pickupMode の扱い)、`0x425210` (ids `0x550`・`0x562`)、`0x526190` (同期か)。
2. guard: `0xd5a74f` の大域オブジェクトの vtable `[+0x98]` と、`0xd84f30` の判定 (`[item+0x50]` 系)。
3. path C の後段: `0x117baa0`・`0x40fe90`・`0x617920` (N の更新後の処理)。
4. 一覧 A/B の中身 (`0x5dcad3` / `0x5da9a8` が指す一覧の要素型と、両者の関係)。
5. `N = [chan+0x2f4]` の初期値 (channel 生成時の既定)。pitchUnit=1 の `divss` で N が 0 だと 0 除算になる。N が 0 になり得るか (初期値・更新経路) と、0 のときの商 (±inf/NaN) の後段 clamp での扱いは未確認。0 除算を避ける処理は推測で書かない。
6. 成功時の戻り値 `0xc38bc0(0)` の型と、`0xd82c20` の `[rip+0x860485]` 分岐の意味。

### 受入条件 (#2542) の判定

- [x] setChannelPitch の戻り値・範囲外 code・value (`0x477180`)・pitchUnit の各分岐を PE 解析箇所つきで REPORT に残す — 本節で達成 (未確定の項目は上の 1〜6)。
- [ ] `useGlobalIndex=1` の表 (`0x1005730` の dl≠0) と `0xffac20` を PE で確定 — 部分達成。`dl≠0` の一覧 A は `0x1005730` で確定した。一覧 A/B の中身は子 #2562 の範囲外 (PY-77 #2576) へ移した。`0xffac20` は setChannelPitch の経路外のため本 issue の対象外: callback `0xd5a720` の全 call 14 件 (guard の間接 call 1 件を含む) の直接先に `0xffac20` は無い (`pe_disasm.py 0xd5a720 180` で実測、`ret` は `0xd5a9dc`)。
- [ ] `provider/fl_engine.c` と `host/fl_mock.mjs` に実装・`channels_diff` の diffs 0 — 未達。効果関数が未確定のため、本 PR では実装しない。子 issue へ移す。
- [ ] `provider_check.mjs` の pe39 集合・`all_tools.mjs` 48/48 — 未達 (実装後の作業)。子 issue へ移す。
