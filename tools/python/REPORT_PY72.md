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

## 追加解析 (PY-77 / #2576): guard・効果関数本体・N 既定値の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2562 (PY-75)・#2542 (PY-72)。

### 結論

- 確定: pickupMode は `ctx+0x30`、useGlobalIndex は `ctx+0x38` (B)。値検査の分類 8 は NaN (D)。`0x425210` は `user32!PostMessageW` の thunk (D)。`0x526190` は呼出しスレッドが所有者なら callback を同期実行 (D)。flags `0x3fd` の 0x20・0x10・0x4 の作用 (C)。N の既定値 2 (reset 関数 `0xfe9090` 内、E)。
- 一部確定: guard の O は `G(0x15e4790) → 0x141d6b8 → Q → O=Q+8` の鎖まで確定。O の実体と vtable `+0x98` は未確定 (A)。status -2 の経路は 2 つ確定 (A・B)。
- 未確定: O の生成元と vtable 本体、効果関数 `0x1046a30` の書込み先、message 0x550/0x562 の意味、同期性の所有者スレッド値 (実行時)。下表。

### 受入 A: guard の O と status -2 の条件

- G = `0x15e4790` は `.data` (静的値 `0x141d6b8`)。`pe_xref.py` で G への store は 0 件。
- callback guard (`0xd5a73b`〜`0xd5a74f`): `rax=[G]` (= スロット `0x141d6b8` の番地) → `Q=[0x141d6b8]` → `O=[Q+8]` → `call [[O]+0x98]` (rcx=O)。
- Q (`0x141d6b8`) への store は 2 件のみ: `0x976aad` (`0x976a90` の遅延生成。`0x976b60` の戻り値を格納) と `0x976b10` (`0x976af0` の解放で 0)。
- Q の ctor `0x976b60` は `[Q+8]=0` を `0x976b9c` で書く。非 0 の O 書込みは `pe_slot_writers.py 141d6b8 8` で候補 0 件。この tool は RIP 直接読みの直後の `[reg+8]` store だけを検出するため、間接経路は検出外。**O の生成元は未確定**。vtable `+0x98` の本体も O が未確定のため未読。
- status -2 のまま終わる経路 (どちらも文言は `Operation unsafe at current time`):
  1. guard 偽: `0xd5a755` `test al,al`・`0xd5a757 je 0xd5a9cf` (status は -2 のまま)。
  2. task を作らない早期終了: `0xd843e9` で `out=-2`。`[this+0x50]≠0` かつ `0xd84f30([this+0x50])=0` なら `0xd84403 je 0xd84500` で out=-2 のまま戻る (callback は呼ばれない)。

### 受入 B: ctx の格納元と `0xd84f30`

- 呼出し側 `0xd5ab04`〜`0xd5ab42` の stack 引数: 5 番目 `[rbp+0xa8]` (index)、6 番目 `&[rbp+0xac]` (value)、7 番目 `[rbp+0xa4]` (pitchUnit)、8 番目 `[rbp+0xa0]` (pickupMode)、9 番目 `[rbp+0x9c]` (useGlobalIndex)、10 番目 0、11 番目 byte 1。
- `0xd843d0` の格納 (`0xd84430`〜`0xd84467`): `task+0x18`←5、`+0x20`←6、`+0x28`←7、`+0x30`←8、`+0x38`←9、`+0x40`←10、`+0x58`←r8 (callback)。
- よって **ctx+0x30 = pickupMode** (callback は `0xf81ce0(esi, byte[ctx+0x30])` の第 2 引数で 1 byte 読む)、**ctx+0x38 = useGlobalIndex** (`0xd5a768` `cmp qword[rbx+0x38],0; setg dl`)。flapi 署名の順 `(int, float, int=0, int=PIM_None, bool)` と一致。
- `0xd84f30(X)` (X = `[this+0x50]`) の戻り al は `[X+0x410]≠0 ∨ ([X+0x2d8]=0 ∧ [X+0x3b8]=0 ∧ [X+0x2da]≠0 ∧ [X+0x2d9]≠0)` (`0xd84f30`〜`0xd84f63`)。
- `this` は `0xd5aa65` `mov rbx,[rax]` (rax = `0xd5e620(self)`)。`0xd5e620` は `call [rip+0x881f8d]` の間接呼出しで、実体は実行時値。**this・X の実体は未確定**。

### 受入 C: 効果関数の本体 (flags `0x3fd` の作用)

- `0x1051c90(rbp, n)` (flags & 0x20 の経路): 条件は `key ≤ 0x0fffffff` (`0x1051ca4`)・`key&0xffff == 4` (`0x1051caf`)・`flags&0x20` (`0x1051cb7`)・`0 ≤ key>>16 < 件数` (`0x1051cc5`〜`0x1051cd6`)。`chan = 0xfe8bb0(配列, key>>16)` (`0x1051ce7`)。満たせば `n2 = 0x661450(n−0x20000000, [chan+0x2f4], 0x30) + 0x20000000` (`0x1051cf7`〜`0x1051d09`)。`0x661450` は `imul rdx`・`idiv r8` の符号付き `(a·b)/c`。**N (`[chan+0x2f4]`) はピッチ範囲 (半音) で、0x30=48 は unit 2 の clamp 上限と一致**。
- `0xf824b0(ptr, n)`: `ptr=0` なら n をそのまま返す (`0xf824b4`〜`0xf8250b`)。効果関数の 7 番目引数 (ptr) は本経路で 0 なので n1 = n。
- `0x104cf90(key, n2, flags)`: `edi = 0x1046a30(key, n2, flags & ~0x14)` (`0x104cfa5`)、戻り値は edi。`flags&0x10` で `0x6667f0(…, edx=6, r8=key, r9=0)` (`0x104cfae`〜`0x104cfca`)。`flags&4` で `0x6667f0(…, edx=0x13, r8=key, r9=edi)` (`0x104cfd5`〜`0x104cfec`)。flags=0x3fd は 0x10・0x4 を両方含むので、イベント 6 と 0x13 (値 edi) を発行する。イベントの受け手は未確定。
- flags `0x3fd` は param id ではなく bit 集合。0x20 は N 換算の gate (`0x1051cb7`)、0x10・0x4 はイベント発行。`0x1046a30` へは 0x3e9 が渡る。0x4000 は節 3 のとおり key −33/−32 変換でのみ参照。
- `0x1046a30` (n の書込み先): 0x590 バイトのフレームで key の型により分岐し、`0xfe8bb0` を 7 箇所以上で呼び、`call [rbx+0x1f0]` の仮想呼出しを持つ。全量は未読。先頭 700 命令の範囲に `[reg+0x2f4]` への直接 store は無い (grep 目視)。**n の最終書込み先は未確定**。
- `0xf81ce0(key, pickupMode)` (`0xf81ce0`〜`0xf81d58`): `al = 0xf8ecd0([0xf81cef], key)` (登録判定)。登録済みで mode=0 → `0xf8eb10(…, key)`、mode≠0 → 変更なし。未登録で mode=1 → `0xf8ea80(…, key, …)`、mode=2 かつ `byte [[[0x65f68f]]+0xf30+0x49e]≠0` → 登録、それ以外は変更なし。`0xf8ecd0`・`0xf8eb10`・`0xf8ea80` の本体は未読 (役割名は推定)。
- `0xf824b0`・`0x1051c90` は本節で確定。`0x1051720` は `0x1046a30(key, 0, 2)` を呼ぶ読取り相当の経路 (推定)。戻り値判定の全量は未読。

### 受入 D: 値検査・PostMessage・task 登録

- `0x450c10(&value)` (上位 16bit `cx` と全体を見る) の戻り al: 0=+0、1=−0 (`0x80000000`)、2=+subnormal (`cx≤0x7f`)、3=−subnormal (`0x8000≤cx≤0x807f`)、4=+normal (`0x0080≤cx≤0x7f7f`)、5=−normal (`0x8080≤cx≤0xff7f`)、6=+inf (`0x7f800000`)、7=−inf (`0xff800000`)、**8=それ以外 = NaN** (`0x450c8f`)。`0x477180` は `al==8` (`0x477194`〜`0x477196`)。よって値 −1 は NaN のみ。
- `0x425210` は `jmp [0x1970b10]` = **user32!PostMessageW** の thunk。`0xd84495` の `(…, 0x562, 0, 0)` と pitchUnit 2 の `(…, 0x550, chan+0x794, 0)` は PostMessageW(hwnd, msg, wParam, lParam)。**非同期** (メッセージ投入)。msg 0x550・0x562 の意味 (window proc の分岐先) は未読。
- `0x526190`: item = {owner=this, fn=`0xd84290`, ctx=task} を作り `0x525ec0(sched, &item, r8=0, r9=0)` (`0x526190`〜`0x5261dc`)。`0xd84290` は `call [task+0x58]` (rcx=task、`0xd8429b`) なので callback を呼ぶ。`0x525ec0`: `0x525940` の戻り値 +8 と `[[rip+0x10befcf]]` を比較 (`0x525f42`〜`0x525f4e`)。一致し r8&r9=0 なら `0x525f60`〜`0x525f7d` で `fn(ctx)` を**同期**実行。不一致なら `0x525faf` 以降でキュー投入 (非同期)。`0xd844d7` が直後に status を読むので同期が前提の設計。**`[[rip+0x10befcf]]` は実行時値で、Python 呼出しが所有者スレッドかは未確定**。

### 受入 E: N の既定値と一覧 A/B

- N の既定値: `0xfe9090(obj)` (reset 関数) の `0xfe948d` で `mov dword [obj+0x2f4], 2` (同時に `0xfe9486` で `[obj+0x6f4]=1.0`)。wrapper は `0xffe290` (`[obj+0x79d]=0`、`0xffe2a0`) と `0x1001b70` (`[obj+0x2f0]=-1`、`0x1001b80`)。**既定値 2 は reset 内で確定**。obj が chan (`0xfe8bb0` の要素) と同一か、channel 生成時に reset が呼ばれるかは**未確定** (推定: +0x794・+0x79d と同じ構造体)。
- `dword [reg+0x2f4]` への store は 30 件 (`0x609339`・`0x60f096`・`0x60f120`・`0x722024`・`0xd1c434`・`0xd5a97c`・`0xe8c98d`・`0xfe948d` 他)。構造体型は各件未確認。走査は `pe_scan_store.py` の dword 版 (リポジトリ外の一時複製で正規表現の型だけ変更)。
- 一覧 A (`[rip+0x5dcad3]`系) と B (`[rip+0x5da9a8]`系): `0x1005730` (`0x100573e`〜`0x10057a8`) が `0xfe8bb0(配列, idx)` を呼ぶ。`0xfe8bb0` は `[obj+0x10]` = 件数−1 で範囲検査し、`[obj+8][idx]` を返す (`0xfe8bbc`〜`0xfe8bcd`)。**要素は 8 byte ポインタ**。要素の構造体型 (chan と推定) は未確定。

### 測定

- 測定 commit: `25d323ca` (記録直前の HEAD)。解析対象は未変更: `git diff 25d323ca HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行。
- 実測コマンド (`FL_WIN64_DIR=<worktree>/tools/python/work/fl`):
  - `pe_disasm.py 0xd5a720 200`: 0.067 秒 (終了 0)。
  - `pe_xref.py 15e4790,141d6b8`: 47.2 秒 (命令 5,022,467・hits 2,428・store 2)。
  - `pe_slot_writers.py 141d6b8 8`: 48.4 秒 (slot_loads 3・candidates 0)。
  - dword 版 `0x2f4` 走査 (`pe_scan_store.py` の複製): 27.2 秒 (hits 30)。
  - `pe_callgraph.py func / callers`、`pe_disasm.py` 他は所要を測っていない (1 件ずつ数秒未満)。
- load average (1 分値): 開始時 0.23 (23:28 UTC)、終了時 0.56 (23:41 UTC)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| O (`[Q+8]`) の生成元と vtable `+0x98` の本体 | guard 偽 (status -2) の条件が PE だけで確定しない | [PY-169] #3212 |
| `0x1046a30` の書込み先 (n が `[chan+0x2f4]` か) | 効果関数の状態モデル | [PY-170] #3213 |
| `0xf8ecd0`・`0xf8eb10`・`0xf8ea80`・`0x1051720` の本体 | pickupMode の登録・イベント受け手の意味 | [PY-170] #3213 |
| message 0x550・0x562 の意味 (window proc) | PostMessageW 通知の内容 | [PY-171] #3214 |
| `[[rip+0x10befcf]]` (所有者スレッド値) | Python 呼出しの同期性 (実行時にしか決まらない) | [PY-171] #3214 |
| `this` (`0xd5e620` の間接先) と X (`[this+0x50]`) の実体 | `0xd84f30` の入力 | [PY-169] #3212 |
| reset `0xfe9090` の obj と chan の同一性・呼出し箇所、一覧 A/B 要素の型 | N 既定値の適用範囲 | [PY-171] #3214 |

## 追加解析 (PY-170 / #3213): 書込み先 (`0x1046a30`)・登録表・`0x1051720` の戻り値

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。測定・結論の全文と未解決の表は付録 `REPORT_PY72_APPENDIX_3213.md` が正本。

- 確定: setChannelPitch の key 枝 (下位 16bit = 4) で `0x1046a30` が n を書く先は `[chan+0x174]` (`[chan+0x2f4]` ではない)。`0x104cf90` はラッパ (通知のみ)。
- 確定: `0xf8ecd0` (contains)・`0xf8eb10` (erase)・`0xf8ea80` (insert) と `0xf81ce0` (pickupMode 0/1/2) の登録・解除の意味。
- 分岐のみ確定: `0x1051d20` の flags&0x20 経路は、`0x1051720` の戻り値 2 のときだけ `0x104cf90` へ進む。戻り値の生成元 (`0xf82a10`・`0xf82c20`) は #3253 へ移送。
