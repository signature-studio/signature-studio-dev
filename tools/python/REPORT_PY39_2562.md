# PY-75 追補 (#2562): setChannelPitch の callback と効果関数の PE 解析 (REPORT_PY39.md から分離)

本体は `REPORT_PY39.md`。本ファイルは 250 行上限のため、#2562 の節を `REPORT_PY39.md` の末尾に足さず独立させた。

## 追加解析 (PY-75 / #2562): setChannelPitch の callback と効果関数の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2542 (PY-72)。PR #2559 (PY-72 の節) は open で本節と末尾が衝突し得るが、本節は PE バイナリだけに依存する。

### 結論

- setChannelPitch の呼び出し連鎖 (ハンドラ → `0xd843d0` → callback `0xd5a720`) と引数の対応を確定した。
- callback の分岐を確定した: guard (大域オブジェクトの vtable `[+0x98]`)・値検査 (`0x477180`)・pitchUnit 0/1/2 の 3 系統と、それ以外 (効果なし)。
- pitchUnit 0/1 は値を `n = cvtsd2si(clamp01(…) × 2^30 + (0.5−ε))` (0..2^30) に変換して効果関数 `0x1051d20` を呼ぶ。pitchUnit 2 は効果関数を呼ばず、`[chan+0x2f4]` (N) に `clamp(round(value), 1, 48)` を書く。
- 効果関数 `0x1051d20` の 7 引数を確定した。本呼び出しの経路 (5 番目の引数 = 0) では float 0.0 (6 番目) は読まれない。最終書込み候補は `0x104cf90` だが、本体は未読のため**書込みか否かは未確定**。
- 未確定 (次節): guard の大域オブジェクトの実体、`0xd84f30`・`0xf81ce0`・`0x1051720`・`0xf824b0`・`0x1051c90`・`0x104cf90` の本体、`0x450c10` (値検査の分類)、N の既定値、一覧 A/B の要素型、`0x425210`・`0x526190`。子 issue [PY-77] に移送した。

### 測定

- 測定 commit: `84c1ccde` (コード変更の最後。`pe_rip_consts.py` の参照先デリファレンス追加)。`pe_rip_consts.py` は本節で新規に追加 (issue 本文が参照する名前。`pe_disasm.py` と同じ方式)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/fl extracted/block00031_PE.bin` (2.9 秒)。`--wildcards '*block00031_PE.bin'` 形式は本 run の環境で 0 件展開になったため、メンバー名を直接指定した。`tools/python/work/` は gitignore 対象。
- 実行: `FL_WIN64_DIR=<絶対パス>/tools/python/work/fl python3 analysis/flapi/pe_disasm.py <VA> <N>` と `pe_rip_consts.py <VA> <N>`。8 回の実行は全て終了 0、合計 0.64 秒、load average 0.09 (15:15 時点)。
- 差分 0 の証跡: 本節の commit 以降で `tools/python/analysis/flapi/` に触れる commit は無い。`git diff 84c1ccde HEAD -- tools/python/analysis/flapi` の出力は 0 行 (検証 HEAD は本節の docs commit)。

### 1. 呼び出し連鎖 (`0xd5aa30`、`pe_disasm.py d5aa30 83`)

- `0xd5aadf` の間接呼び出し (`[rip+0x889ac9]`。書式 `if|iii` を渡す解析関数と推定) の出力先: index `[rbp+0xa8]`、value (float) `[rbp+0xac]`、pitchUnit `[rbp+0xa4]`、pickupMode `[rbp+0xa0]`、useGlobalIndex `[rbp+0x9c]`。既定値は 0 (`0xd5aa68`〜`0xd5aa7c`)。
- `0xd5aaf3` で callback の VA を `lea r8,[rip-0x3da]` で渡す → `0xd5a720` (`0xd5aafa − 0x3da`)。
- `0xd5ab47`: `call 0xd843d0` の stack 引数は 7 個: index・`&value`・pitchUnit・pickupMode・useGlobalIndex・0・byte 1。
- `0xd5ab55`: 戻り値は `call 0xd82c20` (ecx = `[rbp+0x80]` の値、または解析失敗時の PyArg 戻り値)。

### 2. callback `0xd5a720` の分岐 (`pe_disasm.py d5a720 152`、定数は `pe_rip_consts.py d5a720 152`)

rbx = callback の第 1 引数 (ctx)。ctx のフィールドは使い方からの推定 (`0xd843d0` での格納元は未読): `+0x18` index、`+0x20` value のポインタ、`+0x28` pitchUnit、`+0x30` byte (`0xf81ce0` の第 2 引数)、`+0x38` (`>0` を bool で渡す)、`+0x60` 状態 (status)。

| 段階 | VA | 内容 |
|---|---|---|
| 初期化 | `0xd5a733` | `[ctx+0x60] = -2` (未設定の sentinel) |
| guard | `0xd5a74f` | `G=[rip+0x88a04e]` (`0x15e4790`) の指す値の `+8` のオブジェクト O の vtable `[+0x98]` を呼ぶ。al=0 なら `0xd5a9cf` で終了 (status は −2 のまま) |
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
- ebx=0 のため `0x1051f45`。sil=0 → `0x1051f98`: `n1 = 0xf824b0([rbp+0x90], n)`、`n2 = 0x1051c90(rbp, n1)`、`0x104cf90(key, n2, flags)`。sil≠0 → `flags & 0x20` (flags = 0x3fd は bit 0x20 を持つ) → `0x1051720(rbp, 0)` の戻り値が 2 なら上と同じ chain、それ以外は書込み無しで終了。
- 0x4000 の OR (`0x1051d9e`) は key が −33/−32 の変換分岐 (`0x1051d55`〜) だけの処理。本呼び出しの key (packed handle) は負にならないので通らない。
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
