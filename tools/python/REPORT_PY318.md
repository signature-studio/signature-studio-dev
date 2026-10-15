# PY-318 (#4337): 0x45c290 の変換 helper の間接 call 先の確定

親: #3926 (PY-272)。前段: `tools/python/REPORT_PY272.md` §2 (未解決)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- **0x45c170 の間接 call `[rax]`** (slot 0x15e3ea8 → セル 0x15f1038) の先は `oleaut32.dll!VariantChangeTypeEx`。
  セルは初期化関数 0x457c70 が `GetProcAddress` で解決して格納する (0x457c9e)。モジュール名 `oleaut32.dll` (0x457c78)、名前 `VariantChangeTypeEx` (0x457c8b)。
  - 解決関数 0x457c40 は `GetProcAddress` の結果が 0 なら既定値 (r8) を返す。VariantChangeTypeEx の既定値は 0x4572c0 (lea 解決で確定)。0x4572c0 は `cmp r8d, 0x400` で lcid を見て 0x4572b0 (slot 経由の jmp) を呼ぶ shim。実行時に GetProcAddress が 0 を返すかは未確認。
- **0x45c040 の間接 call `[rax]`** (slot 0x15e4a68 → セル 0x15f10a0) の先は `oleaut32.dll!VarI4FromStr` (推定ではなく、格納箇所 0x457e17 と名前 0x457f8e の照合で確定)。
  - 0x45c040 の `0x7ffdfffb` (`add` 後に 0 判定) は、戻り値 `ebx == 0x80020005` の判定そのもの。`0x80020005` は Win32 の `DISP_E_TYPEMISMATCH` と一致 (定数の一致。用途は推定)。
- **0x45c1c0 の間接 call `[rip+0x1194f0f]`** (セル 0x15f1100) の先は関数 `0x45a050` (`call 0x459ef0` だけの thunk)。セルは初期化関数 0x467f00 が `lea` で求めた値を格納する (0x467f40 で rcx = 0x45a050)。
  - 0x45a050 の先は IAT の API ではない (`0x459ef0` は内部関数)。0x459ef0 の中身 (例外か・変換か) は未確定 (下の表)。

## 0x40f540・0x40f560 と 0x7ffdfffb の扱い

- 0x40f540 (`cl=4`) と 0x40f560 (`cl=5`) は `0x4096d0` を呼ぶ薄いラッパ (逆アセ確認済み)。
- 0x4096d0 は (a) 第 2 引数 `rdx` を読む、(b) 0x15e… の hook 関数ポインタ `[rip+0x11dc925]` が非 0 なら呼ぶ、(c) 0 なら `0x41d110` → `[rax+0x210]` の値を使う、(d) `0x4096b0` を呼ぶ、の順。
  `0x4096b0` は `rdx` を大域に保存して `0x412a40` を呼び、`0x412a40` は `ecx` を大域に保存して `0x4128b0` を呼ぶ。
  「範囲外の値で呼ばれる」(0x45c290 の 0x40f540 の呼出し) ことと合わせると、例外送出 (範囲外エラー) の経路と推定する。ただし `0x4128b0` 以下の中身を読み切っていないので確定ではない。
- 0x7ffdfffb は 0x80020005 の 2 の補数 (`0x7ffdfffb + 0x80020005 = 0x1_0000_0000`)。0x45c096 の `add eax, 0x7ffdfffb; test; je` は `eax == 0x80020005` の判定 (確定)。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で `<展開先>/extracted/block00031_PE.bin` に展開 (22 MB)。
- 逆アセは `pe_disasm.py` (capstone)。import 名は `pe_iat_name.py` と pefile の import 表照合。
- 参照探索: `.text` 全体で RIP 相対 disp32 が対象 VA を指す命令を列挙 (逐次逆アセは無効バイトでずれるため、disp32 候補の直前から再逆アセして確認)。探索スクリプトは `work/` (gitignore) に置き、commit しない。

## 1. 検証

測定 commit: 本ブランチで probe を最後に変えた commit (本ファイルと同じ commit に含む。`git log -1 -- tools/python/analysis/flapi/pe_py318_probe.py` で確認)。

- probe: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py318_probe.py` → 17/17 PASS・終了 0。
  - 内訳: 初期化関数の名前解決 (モジュール・名前・格納セル) / 0x45c170・0x45c040・0x45c1c0 の間接 slot とセルの対応 / 0x467f00 の store と lea / 0x7ffdfffb の算術 / ネガティブ 2 件 (誤認した期待は偽)。
- 既存 probe: `pe_py272_probe.py` (41/41 PASS) は本 PR で変えていない。実行は本 PR の測定 commit 上で行い、結果を最終回答に書く。

## 2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x459ef0 (0x45c1c0 の間接先 0x45a050 の本体) の役割。`0x41c820`・`0x448d40`・`0x411e80`・`0x412d60` を読み切っていない | 0x45c1c0 の戻り値 (型 0x101 の式) が変換結果か例外かの確定 | 未起票 (PY-318 の残り。次 round で扱う) |
| 0x4096d0 → 0x4096b0 → 0x412a40 → 0x4128b0 の末尾 (範囲外時の送出経路) | 0x40f540 (範囲外) の確定。例外送出は推定のまま | 未起票 (同上) |
| 0x457c70 の GetProcAddress 結果が 0 になる実行時条件 (0x4572c0 の shim へ落ちる経路) | VariantChangeTypeEx が本物か shim かの確定。通常の Windows では本物と推定 | 未起票 (同上) |
