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

## 追加解析 (PY-75 / #2562): setChannelPitch の callback と効果関数の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2542 (PY-72)。前段は本ファイル上の「解析 (PY-72 #2542)」節。PR #2559 (PY-72 の節) は main に merge 済み。本節は PE バイナリだけに依存する。

### 結論

- setChannelPitch の呼び出し連鎖 (ハンドラ → `0xd843d0` → callback `0xd5a720`) と引数の対応を確定した。
- callback の分岐を確定した: guard (大域オブジェクトの vtable `[+0x98]`)・値検査 (`0x477180`)・pitchUnit 0/1/2 の 3 系統と、それ以外 (効果なし)。
- pitchUnit 0/1 は値を `n = cvtsd2si(clamp01(…) × 2^30 + (0.5−ε))` (0..2^30) に変換して効果関数 `0x1051d20` を呼ぶ。pitchUnit 2 は効果関数を呼ばず、`[chan+0x2f4]` (N) に `clamp(round(value), 1, 48)` を書く。
- 効果関数 `0x1051d20` の 7 引数を確定した。本呼び出しの経路 (5 番目の引数 = 0) では float 0.0 (6 番目) は読まれない。最終書込み候補は `0x104cf90` だが、本体は未読のため**書込みか否かは未確定**。
- 未確定 (次節): guard の大域オブジェクトの実体、`0xd84f30`・`0xf81ce0`・`0x1051720`・`0xf824b0`・`0x1051c90`・`0x104cf90` の本体、`0x450c10` (値検査の分類)、N の既定値、一覧 A/B の要素型、`0x425210`・`0x526190`。子 issue [PY-77] に移送した。

### 測定

- 測定 commit: `60530e14` (コード変更の最後。`pe_rip_consts.py` は main の版 (#2559 由来) を使い、`.bss` 修正を加えた)。前回の測定 (`a605aaa0` までの版) は、`.bss` を指す参照の先の値が偽だった。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/fl extracted/block00031_PE.bin`。`--wildcards '*block00031_PE.bin'` 形式は本 run の環境で 0 件展開になったため、メンバー名を直接指定した。`tools/python/work/` は gitignore 対象。
- 実行: `FL_WIN64_DIR=<絶対パス>/tools/python/work/fl python3 analysis/flapi/pe_disasm.py <VA> <N>` と `pe_rip_consts.py <VA> <N>`。8 回の実行 (VA `d5aa30 83`・`d5a720 152`・`1051d20 700`・`d843d0 80` × 2 ツール) は全て終了 0・Traceback 0 件、合計 1.05 秒、load average 0.03 (1 分値)。
- 差分の証跡: `git diff 60530e14 HEAD -- tools/python/analysis/flapi/pe_disasm.py tools/python/analysis/flapi/pe_rip_consts.py` の出力は 0 行 (測定 commit より後も測定対象は変わっていない。後続は main 取り込み merge と docs commit のみ)。`tools/python/analysis/flapi` 全体には main 側の別ファイルの変更が入っているが、測定対象外。
- 修正前 (main の版 `ad4c27b3` の `pe_rip_consts.py`) との比較: 同じ 4 VA の RIP 参照命令の行 103 行のうち変わったのは 53 行だけ。`*ptr` の番地が `.bss` にある 48 件の値を削除 (file 上の別バイトだった偽の値)、`.bss` を直接参照する 5 件を「PE ファイル上に実体なし」に変更。`.data`・`.text` 内の値 (本節の引用値を含む) と `pe_disasm.py` の出力は変わらない。

### 1. 呼び出し連鎖 (`0xd5aa30`、`pe_disasm.py d5aa30 83`)

- `0xd5aadf` の間接呼び出し (`[rip+0x889ac9]`。書式 `if|iii` を渡す解析関数と推定) の出力先: index `[rbp+0xa8]`、value (float) `[rbp+0xac]`、pitchUnit `[rbp+0xa4]`、pickupMode `[rbp+0xa0]`、useGlobalIndex `[rbp+0x9c]`。pitchUnit・pickupMode・useGlobalIndex の既定値は 0 (`0xd5aa68`〜`0xd5aa7c` で初期化)。index と value は初期化されず、解析関数が書く出力 (`lea` で渡す)。
- `0xd5aaf3` で callback の VA を `lea r8,[rip-0x3da]` で渡す → `0xd5a720` (`0xd5aafa − 0x3da`)。
- `0xd5ab47`: `call 0xd843d0` の stack 引数は 7 個: index・`&value`・pitchUnit・pickupMode・useGlobalIndex・0・byte 1。
- `0xd5ab55`: 戻り値は `call 0xd82c20` (ecx = `[rbp+0x80]` の値、または解析失敗時の PyArg 戻り値)。

### 2. callback `0xd5a720` の分岐 (`pe_disasm.py d5a720 152`、定数は `pe_rip_consts.py d5a720 152`)

rbx = callback の第 1 引数 (ctx)。ctx のフィールドは使い方からの推定 (`0xd843d0` での格納元は未読): `+0x18` index、`+0x20` value のポインタ、`+0x28` pitchUnit、`+0x30` byte (`0xf81ce0` の第 2 引数)、`+0x38` (`>0` を bool で渡す)、`+0x60` 状態 (status)。

| 段階 | VA | 内容 |
|---|---|---|
| 初期化 | `0xd5a733` | `[ctx+0x60] = -2` (未設定の sentinel) |
| guard | `0xd5a74f` | 参照鎖は `0xd5a73b`〜`0xd5a74f` の順に `P = *(G)`、`Q = *(P)`、`O = *(Q+8)`、`call [*(O)+0x98]` (G = `[rip+0x88a04e]` = `0x15e4790`)。al=0 なら `0xd5a9cf` で終了 (status は −2 のまま) |
| 索引解決 | `0xd5a774` | `0x1005730(ecx=[ctx+0x18], dl=([ctx+0x38]>0), r8=&chan)`。al=0 なら終了 (status 0) |
| handle | `0xd5a781`〜`0xd5a7d8` | `esi = ((chan+0x794) & 0xffff) << 16 | 4` (効果関数の key) |
| 値検査 | `0xd5a796` | `0x477180(value)` が非 0 なら `[ctx+0x60] = -1` で終了。`0x477180` は `0x450c10(&value)` の戻り値が 8 か (`cmp al,8; sete`) を返す。8 の意味は未確定 |
| 分岐 | `0xd5a7b2`〜`0xd5a7c4` | `eax = pitchUnit − 1`。`eax=−1` → unit 0、`eax=0` → unit 1、`eax=1` → unit 2 (`0xd5a958`)、それ以外は終了 (効果なし) |

- unit 0 (`0xd5a7cf`): `x = clamp01(value × 0.5 + 0.5)` (0.5 は `*(0x13e7540)` の参照先、`0xd5a7db`。加算の 0.5 は `[0xd5a9e0]`)。`n = cvtsd2si(float(x × 2^30) + 0.49999999999999994)` (2^30 は `[0xd5a9e8]`、`0xd5a9f0`、`cvtsd2si` は `0x40c660`)。`0xf81ce0(esi, byte[ctx+0x30])` の後、`0x1051d20(esi, n, 0x3fd, 0, 0, 0.0f, 0)` (`0xd5a880`)。
- unit 1 (`0xd5a88a`): `N = [chan+0x2f4]`、`x = clamp01(value / (N×100) × 0.5 + 0.5)` (N×100 は `lea` 2 回)。以降は unit 0 と同じで `0x1051d20` を `0xd5a951` で呼ぶ。
- unit 2 (`0xd5a958`): `[chan+0x2f4] = clamp(cvtsd2si(value), 1, 48)` (`0xd5a97c`)。効果関数は呼ばない。続けて `0x117baa0` の戻り値 rbx が非 0 なら `0x40fe90(rbx, [0xf55e80])` が真のとき `0x617920(rbx)` (未読)。
- 定数の確認 (`pe_rip_consts.py` 出力): `[0xd5a9e0] = 0.5 (double)`、`[0xd5a9e8] = 2^30 (float)`、`[0xd5a9f0] = 0.49999999999999994 (double)`。`[0x15e4000] → 0x13e7540` の参照先は float 0.5。

### 3. 効果関数 `0x1051d20` (`pe_disasm.py 1051d20 700`)

- 引数 (プロローグ `0x1051d20`〜`0x1051d34` と `[rbp+...]` 参照から): rcx → `[rbp+0x60]` = key、edx → `[rbp+0x68]` = n、r8d → `[rbp+0x70]` = flags、r9d → ebx = bool、5 番目 (stack) → `[rbp+0x80]` = int、6 番目 → `[rbp+0x88]` = float、7 番目 → `[rbp+0x90]` = ptr。`rbp = entry_rsp − 0x58` から導いた。
- 本呼び出しは 5 番目 = 0 なので `0x1051da8` の `cmp [rbp+0x80],0; jle` で `0x1051e7e` に入る。float (`[rbp+0x88]`) を読むのは `0x1051de5` と `0x1051e4b` だけで、どちらも 5 番目 > 0 の経路。**本経路では float 0.0 は読まれない**。
- `0x1051e7e`: sil = `byte[[[G_a]]+0xf30 + 0x49e] != 0` または `[[G_b]]+0x10 > 0` (G_a=`[rip+0x58f533]`、G_b=`[rip+0x58e179]`)。状態フラグ。意味は未確定。
- ebx=0 のため `0x1051f45`。sil=0 → `0x1051f98`: `n1 = 0xf824b0([rbp+0x90], n)`、`n2 = 0x1051c90(rbp, n1)`、`0x104cf90(key, n2, flags)`。sil≠0 → `flags & 0x20 = 0` なら `je 0x1051f98` (`0x1051f52`) で chain に進み、chain の後に `0xf82c20` を呼ぶ。`flags & 0x20 ≠ 0` (flags = 0x3fd はこちら) なら `0x1051720(rbp, 0)` の戻り値が 2 のとき chain (`0xf82c20` は呼ばない)、それ以外は書込み無しで終了。sil=0 は chain の後に何も呼ばず終了。
- 0x4000 の OR (`0x1051d9e`) は key が −33/−32 の変換分岐 (`0x1051d55`〜) だけの処理。本呼び出しの key は `((chan+0x794)&0xffff)<<16 | 4` で下位 16 bit が 0x0004 のため、−33/−32 (下位 16 bit が 0xffdf/0xffe0) と一致せず、入口の unsigned 比較 (`0x1051d49`〜`0x1051d53`、key が 0xFFFFFFDF/0xFFFFFFE0 のときだけ変換分岐 `0x1051d55` へ入る) を通らない。key の上位ビットが立つと負になるが、判定は下位 16 bit で決まるので結論は同じ。よって `mov dil, 1` (`0x1051da5`) は通らず edi=0。
- 解釈 (推定): `0x3fd` は param id ではなく flags の語 (bit 0x20 を見る・0x4000 を立てる)。`0x104cf90(key, n2, flags)` が書込み口の候補。未読のため「値の書込み」とは確定できない。

### 4. 未確定と移送先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| guard の大域オブジェクト O の実体 (ランタイム値・vtable `+0x98` の実装) | status −2 の条件が PE だけで確定しない | [PY-77] (子) |
| `0xd84f30` の判定内容、`0xd843d0` での ctx フィールド格納元 (`+0x30` が pickupMode か useGlobalIndex か) | pitchUnit 以外の入力の意味が未確定 | [PY-77] |
| `0x104cf90`・`0x1051c90`・`0xf824b0`・`0x1051720`・`0xf81ce0` の本体 | 効果関数が n を書くか、書く先、0x3fd の flags の意味が未確定 | [PY-77] |
| `0x450c10` (値検査の分類 8) | 値 −1 の条件 (NaN・範囲外の別) | [PY-77] |
| N の既定値 (`[chan+0x2f4]` の初期化元)、一覧 A (`[rip+0x5dcad3]`)・B (`[rip+0x5da9a8]`) の要素型 | C provider の初期状態が決まらない | [PY-77] |
| `0x425210` (ids `0x550`・`0x562`)、`0x526190` (同期/非同期) | 受入条件 2 の残り | [PY-77] |
| C provider / mock の状態モデル | 推測で実装しない | [PY-76] #2563 (本節の結論を入力にする) |

## 追加解析 (PY-169 / #3212): guard の O・判定入力 X の PE 解析

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。前段: 本ファイル上の「追加解析 (PY-75 / #2562)」節。親 #2576 の本文が指す「追加解析 (PY-77 / #2576)」節は main に存在しなかった。本節を PY-77 系の PE 結果の記録先とする。

### 結論

- guard の大域 G = `0x15e4790` (.data) のファイル上の値は Q スロット `0x141d6b8` (.data、ファイル上 0) の VA。鎖は `P=[G]=0x141d6b8`・`Q=[P]`・`O=[Q+8]`・`call [O.vtbl+0x98]` (`0xd5a73b`〜`0xd5a74f`)。
- O への非 0 書込みは PE 上 2 箇所 (`0x1263571`・`0x1264145`)。どちらも `mov [rcx+8], rax`、rcx = Q、rax = `call 0x125da90` の戻り値。ctor `0x976b60` の +8 書込みは 0 のみ。
- **未確定**: `0x125da90` の戻り値 (O の実体) と O の vptr。よって vtable `[O+0x98]` の本体と、guard が偽になる条件は PE だけでは確定しない。
- `0xd5e620` の間接先は `.bss` の関数ポインタ `0x16b8300` の値。その値は init `0xc395a0` の `0xc39831` で `call 0x4235f0` の戻り値として格納される。0x4235f0 は実行時の表を引くため、静的には確定しない。
- `0xd84f30` の判定式 (X = rcx の各フィールド) は PE で確定した (§6)。X の実体 `[this+0x50]` の書込み元は未解析。

### 測定

- 測定 commit: `bfceba9e` (`tools/python/analysis/flapi/pe_chain_stores.py` を追加した commit。コードを変えた最後の commit)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/fl extracted/block00031_PE.bin` (2.9 秒。`tools/python/work/` は gitignore)。
- 再現コマンド: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_chain_stores.py 0x15e4790 8` (陽性)、同 `0x13a5000 8` (陰性対照。G の値 0 で鎖が切れる)。既存ツール: `pe_xref.py 0x15e4790,0x141d6b8`・`pe_xref.py 0x15e05b8,0x16b8300`・`pe_callgraph.py callers 0x976b60,0x976a90,0x976af0`・`pe_slot_writers.py 0x141d6b8 8` (候補 0 件。直接参照だけでは O の書込みを拾えない)。
- 実測 (`bfceba9e`): 陽性 `intra_store=2 intra_load=277 callee_refs=5 callee_store=0 sec=73.4`。陰性 `intra_store=0 intra_load=0 callee_refs=0 callee_store=0 sec=72.5`。load average (1 分値) 0.21 → 0.78。陽性の読出し例: `0xd5a745 load mov rax, qword ptr [rax + 8]` (guard の O 読出し)。
- 差分の証跡: `git diff bfceba9e HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は測定後のコミットが本ファイルだけなので 0 行 (後続の commit は本ファイルのみ)。

### 1. Q スロットと Q 本体

- `0x141d6b8` の直接参照 (RIP 相対) は 6 件: load `0x976a95` (cmp)・store `0x976aad` (`[Q]←rax`、init `0x976a90` の ctor 戻り値)・load `0x976acf`・`0x976af5`・`0x976b09`・store `0x976b10` (`[Q]←0`、shutdown `0x976af0`)。
- init `0x976a90`: `if [Q]==0 { [Q] = ctor 0x976b60(rcx=[0x976410], dl=1) }`、続けて `[Q+0x40]` の vtbl[0] を呼ぶ。init の呼出元は 6 件 (`0x977114`・`0x11b32de`・`0x1253c39`・`0x1263554`・`0x1264112`・`0x1374364`)。
- ctor `0x976b60` (this = Q 本体) の呼出元は `0x976aa8` の 1 箇所。ctor の範囲 (`0x976b60`〜`0x976d86`) で `+8` への書込みは `0x976b9c` の `mov [rax+8], 0` の 1 件だけ。

### 2. O (`[Q+8]`) の非 0 書込み

| VA | 関数 | 書込み | 文脈 |
|---|---|---|---|
| `0x1263571` | `0x1263540` | `mov [rcx+8], rax` | `0x126354b` の `cmp [0x459e22],-1` が成立したときだけ実行 (O の既存値は見ない)。`0x1263554` init → `0x1263562` `call 0x125da90` → `0x126356e` で rcx = `[[G]]` = Q |
| `0x1264145` | `0x1264050` | `mov [rcx+8], rax` | `0x1264126` `cmp [Q+8],0; jne 0x1264149`。O が 0 のときだけ `0x126412d` `call 0x125da90` → `0x1264142` で rcx = Q |

- 両方とも `0x125da90` を `rcx = [0x125b0f8]`・`dl=1` で呼ぶ (`0x1263559`・`0x126412d` の `mov rcx,[rip+…]` の先が同じ `0x125b0f8`)。
- 陽性の chain 追跡では、Q 本体を rcx に載せて直接 call した 5 件の先頭 40 命令にも +8 書込みは無い (`callee_store=0`)。
- 範囲外: 間接 call・レジスタ以外 (メモリ経由) で Q を受け渡す経路・vtable 経由の dispatch。

### 3. O の生成関数 `0x125da90` (未確定)

- 戻り値は `this` (`0x125e75d` の `mov rax,[rbp+0x4220]`)。逆アセ 4000 命令 (`0x125da90` から) に、任意のベースと任意のソースによる 8 バイト `mov [reg], reg` 形式の書込みは 0 件。`lea rax,[rip+…]` は 2 件 (`0x125fd5a`・`0x1261263`) だが、いずれも関数末尾 `0x125e76e` より後の別の関数内。
- `this` 引数の値 `[0x125b0f8]` = `0x125b1c0` は .text 内の関数ポインタ 8 個 (`0x1262140`・`0x12620b0`・`0x125e9a0`・…) を並べた表で、O 本体ではなく vtable 様。`0x410320` は `call [this-0x30]` を行う。
- 推定: `0x125b0f8` の内容と `this` の意味が一致していない (`mov` と `lea` の取り違えか、別の意味の引数)。どちらかは PE だけでは確定できない。O の実体は実行時にしか決まらない。

### 4. guard の vtable と偽になる条件 (未確定)

- vtable `[O+0x98]` は O の vptr が未確定のため読めない。status −2 のまま終わる条件 (guard が偽) の PE 上の本体は未確定。

### 5. `0xd5e620` の間接先と `this`

- `0xd5e620(self)`: `mov rax,[0x15e05b8]` (`0xd5e624`)・`call [rax]` (`0xd5e62b`)。rcx (self) は素通し。`[0x15e05b8]` のファイル値は `0x16b8300` (.bss)。間接先は `*(0x16b8300)`。
- `0x16b8300` への RIP 相対 store は `0xc39831` の 1 件 (`mov [rip+0xa7eac8], rax`)。rax は直前 `0xc3982c` の `call 0x4235f0` (rcx = `[rip+0xa7edbd]` (`0xc39804`)、rdx = `lea 0xc8c` = `0xc404b8`)。init は `0xc395a0` (`pe_callgraph func`)。
- `0x4235f0` は `rdx>>16` で分岐する表引き (`0x423608`〜`0x423614`)。戻り値は表の内容 (実行時の値) に依存。間接先の確定は実行時に限る (推定)。
- `this` は呼出元 `0xd5aa30` の `0xd5e620(self)` 戻り値 `rax` の指す値 (`mov rbx,[rax]`)。

### 6. `0xd84f30` の判定式 (入力 X = rcx、PE 確定)

- X = `[this+0x50]`: `0xd843f0` `mov rax,[rbx+0x50]`・`0xd843fc` `call 0xd84f30` (rcx = X)。
- 戻り値 = A ∨ B。A = `[X+0x2d8]==0 ∧ [X+0x3b8]==0 ∧ [X+0x2da]!=0 ∧ [X+0x2d9]!=0`。B = `[X+0x410]!=0`。(`0xd84f37`〜`0xd84f5b`。A の分岐は `0xd84f4b`・`0xd84f52`)。
- X の実体 (`[this+0x50]` の書込み元) は未解析。`this` が実行時にしか決まらないため、X の値も実行時に限る (推定)。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| O の生成関数 `0x125da90` の this の実体と O の vptr (§3) | vtable `[O+0x98]` の本体と偽になる条件が確定しない。status −2 の PE 条件が出ない | #3212 (open のまま継続) |
| `0x4235f0` の表引き結果 (`0xc39831`・§5) | `0xd5e620` の間接先が確定しない | #3212 |
| X = `[this+0x50]` の書込み元 (§6) | `0xd84f30` の入力の実体が確定しない | #3212 |
