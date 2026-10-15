# PY-318 (#4337): 0x45c290 の変換 helper の間接 call 先の確定

親: #3926 (PY-272)。前段: `tools/python/REPORT_PY272.md` §2 (未解決)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x45c170 の間接 call `[rax]`** (slot 0x15e3ea8 → セル 0x15f1038) の先は `oleaut32.dll!VariantChangeTypeEx`。
  セルは初期化関数 0x457c70 が `GetProcAddress` で解決して格納する (0x457c9e)。モジュール名 `oleaut32.dll` (0x457c78)、名前 `VariantChangeTypeEx` (0x457c8b)。
  - 解決関数 0x457c40 は `GetProcAddress` の結果が 0 なら既定値 (r8) を返す。VariantChangeTypeEx の既定値は 0x4572c0 (lea 解決で確定)。0x4572c0 は `cmp r8d, 0x400` で lcid を見て 0x4572b0 (slot 経由の jmp) を呼ぶ shim、という逆アセ読み (probe では未検証)。実行時に GetProcAddress が 0 を返すかは未確認。
- **0x45c040 の間接 call `[rax]`** (slot 0x15e4a68 → セル 0x15f10a0) の先は `oleaut32.dll!VarI4FromStr` (推定ではなく、格納箇所 0x457e17 と名前 0x457f8e の照合で確定)。
  - 0x45c040 の `0x7ffdfffb` (`add` 後に 0 判定) は、戻り値 `ebx == 0x80020005` の判定そのもの。`0x80020005` は Win32 の `DISP_E_TYPEMISMATCH` と一致 (定数の一致。用途は推定)。
- **0x45c1c0 の間接 call `[rip+0x1194f0f]`** (セル 0x15f1100) の先は関数 `0x45a050` (`call 0x459ef0` だけの thunk)。セルは初期化関数 0x467f00 が `lea` で求めた値を格納する (0x467f40 で rcx = 0x45a050)。
  - 0x45a050 の先は IAT の API ではない (`0x459ef0` は内部関数)。
  - 0x459ef0 (PY-338, 逆アセ確認): 戻り値を作らない (rax 非設定)。rcx は読まずに `lea rcx,[rbp+0x28]` で上書きし、0x41c820 (文字列系の生成)・0x448d40・0x411e80 (→0x411d20)・0x412d60 (参照解放) を呼ぶ。0x45c1c0 は 0x45c1eb の間接 call の戻り値 (eax) を使わず、続く 0x45c290 の戻り値を返す。よって 0x45c1c0 の戻り値は 0x459ef0 ではなく 0x45c290 由来。0x459ef0 から例外 API (IAT の RaiseException 系) への直接・2 段の到達は見えない (間接先 `[rip+X]` は未解決)。

## 0x40f540・0x40f560 と 0x7ffdfffb の扱い

- 0x40f540 (`cl=4`) と 0x40f560 (`cl=5`) は `0x4096d0` を呼ぶ薄いラッパ (逆アセ確認済み)。
- 0x4096d0 は (a) 第 2 引数 `rdx` を読む、(b) 0x15e… の hook 関数ポインタ `[rip+0x11dc925]` が非 0 なら呼ぶ、(c) 0 なら `0x41d110` → `[rax+0x210]` の値を使う、(d) `0x4096b0` を呼ぶ、の順。
  `0x4096b0` は `rdx` を大域に保存して `0x412a40` を呼び、`0x412a40` は `ecx` を大域に保存して `0x4128b0` を呼ぶ。
  PY-338 で読んだ範囲 (逆アセ): 0x4096d0 は `bl > 0x1c` のとき表引きを飛ばし (0x409709 `ja 0x40971b`)、bl をそのまま 0x4096b0 → 0x412a40 に渡す。0x412a40 は ecx を大域へ保存して 0x4128b0 を呼ぶ。0x4128b0 は `.text` 内に**戻り辺が無い** (0x412a2d・0x412a34 の ret へ直接分岐する命令が無い。0x412a28 の `jmp 0x412936` が内側ループを回す)。よって範囲外時は「例外として送出される」より「呼び出し元へ戻らない」経路が静的には見える。送出か終了かは 0x4128b0 が呼ぶ 0x412020・0x41a670・0x4127d0 の中身 (未読) に依る。
- 0x7ffdfffb は 0x80020005 の 2 の補数 (`0x7ffdfffb + 0x80020005 = 0x1_0000_0000`)。0x45c096 の `add eax, 0x7ffdfffb; test; je` は `eax == 0x80020005` の判定 (確定)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `<展開先>/extracted/block00031_PE.bin` に展開 (22 MB)。
- 逆アセは `pe_disasm.py` (capstone)。import 名は `pe_iat_name.py` と pefile の import 表照合。
- 参照探索: `.text` 全体で RIP 相対 disp32 が対象 VA を指す命令を列挙 (逐次逆アセは無効バイトでずれるため、disp32 候補の直前から再逆アセして確認)。探索スクリプトは `work/` (gitignore) に置き、commit しない。

## 1. 検証

測定 commit: 本ブランチで probe を最後に変えた commit (本ファイルと同じ commit に含む。`git log -1 -- tools/python/analysis/flapi/pe_py318_probe.py` で確認)。

- probe: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py318_probe.py` → 21/21 PASS・終了 0。
  - 内訳: 初期化関数の名前解決 (モジュール・名前・格納セル) / 0x45c170・0x45c040・0x45c1c0 の間接 slot とセルの対応 / 0x467f00 の store と lea / 0x409709 の ja (範囲外の分岐) / 0x459ef0 が rcx を読まないこと / 0x45c1c0 の戻り値が 0x45c290 由来であること / 0x7ffdfffb の算術 / ネガティブ 2 件 (誤認した期待は偽)。
- 既存 probe: `pe_py272_probe.py` (41/41 PASS) は本 PR で変えていない。実行は本 PR の測定 commit 上で行い、結果を最終回答に書く。
- 逆アセ・到達解析の補助スクリプトは `tools/python/work/` (gitignore、commit しない)。`.text` 全体の分岐元探索は線形スイープの再同期方式 (完全ではない)。

## 2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x459ef0 の役割 (戻り値なし・0x45c1c0 は戻り値を使わない、が確定)。`0x41c820`・`0x448d40`・`0x411d20` の中身は未読 | 0x459ef0 が副作用だけの補助かの確定。0x45c1c0 の戻り値 (0x45c290 由来) の意味には影響しない | [PY-338] #4543 |
| (解消 PY-366 #4543) 範囲外時は例外送出ではなく ExitProcess。§3 参照 | — | — |
| 0x457c70 の GetProcAddress 結果が 0 になる実行時条件 (0x4572c0 の shim へ落ちる経路) | VariantChangeTypeEx が本物か shim かの確定。通常の Windows では本物と推定 | 本 PR の REPORT §2 (追跡のみ。子は起票しない) |

## 3. PY-366 (#4543): 0x4096d0 の範囲外経路 (終了か送出か)

既知類型との関係: 該当なし (PE の逆アセンブルによる解析)。

- 0x40f540 (`cl=4`) → 0x4096d0 (`bl > 0x1c`、0x409709 の `ja`) → 0x4096b0 → 0x412a40 → 0x4128b0 の順に、`bl` をそのまま大域 G へ保存する。
- 0x4128b0 の終端: 0x412a07 が G を読み、0x412a0d で `ExitProcess` (thunk 0x406fc0 = kernel32!ExitProcess) を呼ぶ。0x4128b0 の範囲内に `RaiseException` (thunk 0x406fd0) の直接 call は無い。
- エピローグ 0x412a2d-0x412a34 (`ret`) へ入る分岐は 0x4128b0 の範囲内に無く、戻り先は到達しない。
- G への書き込みは 0x412a44 (0x412a40 の `mov [G], ecx`) だけ。範囲外時の exit code は `bl` の生値。
- 0x4129f5 の `jne 0x412a12` は大域フラグ (0x15eac80) が非 0 なら ExitProcess を飛ばす。フラグの書き込み元は未特定 (静的には本ファイル内で見つからず)。フラグ非 0 の経路は 0x412936 のループへ戻る。
- 結論: 範囲外時の出口は **ExitProcess だけ** で、例外送出 (RaiseException) には届かない。exit code = bl (生値)。ただしフラグ 0x15eac80 が非 0 なら ExitProcess を飛ばして 0x412936 のループへ戻るため、「必ず終了する」とは静的には言えない (§6)。0x412020・0x41a670・0x4127d0 の中身は読み切った (0x412020 = 登録済みコールバックの逆順呼び出し、0x41a670 = リストからの要素除去、0x4127d0 = 25 文字のコンソール出力)。

## 4. PY-366 (#4543): 0x459ef0 の中身

- 0x459ef0 は戻り値を作らない (§1 と同じ)。呼び出し順は 0x41c820 → 0x448d40 → 0x411e80 → 0x412d60。
- 0x41c820 は `LoadStringW` (user32 thunk 0x407030) で文字列を作る。0x448d40 は文字列オブジェクトの組み立て。0x412d60 は参照解放。
- 0x411e80 → 0x411d20 は MSVC 形式の例外レコード (`0xeedfade`) を組み立てるが、0x411d20 の範囲内に `RaiseException` の直接 call は無い。
- 結論: 0x459ef0 は**例外を送出せず、文字列とレコードを作って解放する副作用のみ**の補助関数 (変換結果は返さない)。

## 5. 検証 (PY-366)

- 測定 commit: 本ファイルと `pe_py366_probe.py` を同じ commit に含めた commit (`git log -1 -- tools/python/analysis/flapi/pe_py366_probe.py` で確認)。
- `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py366_probe.py` → 14/14 PASS・終了 0。
- 既存: `pe_py318_probe.py` 21/21 PASS (終了 0)。`pe_py272_probe.py` は本 PR で変えていない (実行結果は PR 本文)。
- 素材: `fl-win64.tar.zst` から `block00031_PE.bin` を展開 (2.8 秒)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x4129f5 の大域フラグ (0x15eac80) の書き込み元が静的に未特定。非 0 の経路 (0x412936 のループ) が実行時にどう抜けるか | 範囲外時が必ず終了か、ループに入るかの確定 (終了説の例外条件) | 本 PR の REPORT §6 (追跡のみ。子は起票しない) |
| 0x457c70 の GetProcAddress 結果が 0 になる実行時条件 (0x4572c0 の shim へ落ちる経路) | VariantChangeTypeEx が本物か shim かの確定。通常の Windows では本物と推定 | 本 PR の REPORT §2 (追跡のみ。子は起票しない) |
