# PY-123 (#3028) 付録: 0 化の命令の特定 (REPORT_PY123.md §2-5 の全文)

本文 `REPORT_PY123.md` は 250 行上限のため、§2-5 を分割移動した (内容は削除していない。Git 履歴にも残る)。

## 2-5. 0 化の命令の特定 (3 回目・WWATCH 測定 commit `009855d26`・HEAD `cd2166181` で両ビルドを再現)

計測: `rt/fle_cpu.h` の ST8〜STF64・STX・STY に、`FLE_WWATCH` 定義時だけ働く書込みフックを入れた (既定は無効)。`fle_cpu.c` の `fle_wwatch` は、監視 slot (`0x15e1c78`・`0x15e4790`) に重なる書込みのうち値が変わるものだけ `__FILE__:__LINE__` 付きで出す。`build.sh` は `FLE_EXTRA_CCF=-DFLE_WWATCH` で有効化する。

```
[fle_wwatch] slot=0x15e1c78 a=0x15e1c70 n=16 old=0x16bb068 new=0 at .../rt/fle_cpu.h:78
[fle_wwatch] slot=0x15e4790 a=0x15e4790 n=16 old=0x141d6b8 new=0 at .../rt/fle_cpu.h:78
```

- 2 件とも 16 バイト書込み (STX/STY 系)。`__LINE__` が inline 関数の中を指すため、呼出元は次の 2 点で対応づけた (行番号は `009855d26` では fle_cpu.h:78、HEAD のコメント 1 行追加後は :79)。
- 直前の `[fill6a7b70]` 行 (fill コールバック `0x6a7b70` の dispatch 時の引数) は 6 件だけ。呼出し #5 が `dst=0x1400000`・`val=0x0`・`cnt=0x100000` (DWORD 個数 = 4 MiB)。#0〜#4 は dst=0x0 から 0x400000 刻みで、6 回で guest 0x0〜0x1800000 を 0 にする (PE image の VA 0x400000 以降を含む)。hit は #5 だけ (`old≠new` の書込みは #5 内の 2 件)。
- 陰性対照: #0〜#4 は guest 0x0〜0x1400000 だけを覆い、監視 slot (0x15e1c70 以上) に重ならない。ヒット 0 件はこの対照どおり。
- 命令 (PE の逆アセンブル `pe_disasm.py 0x6a7b70 40`・§7。lift 出力 `work/boot/lift/` は gitignore のため根拠にしない): `movd xmm0, edx` で値を 4 バイトずつ広げ、`r8` (DWORD 個数 >> 4) 回、rcx から 0x40 刻みで 4 本の `movdqu` を書く。ループ内に `call` は無い。

| VA | 命令 | 監視 slot との対応 |
|---|---|---|
| `0x6a7b84` | `movdqu xmmword ptr [rcx], xmm0` | (対象外) |
| `0x6a7b88` | `movdqu xmmword ptr [rcx + 0x10], xmm0` | `0x15e4790` (a=`0x15e4790`) |
| `0x6a7b8d` | `movdqu xmmword ptr [rcx + 0x20], xmm0` | (対象外) |
| `0x6a7b92` | `movdqu xmmword ptr [rcx + 0x30], xmm0` | `0x15e1c78` (a=`0x15e1c70`) |

- 対応の根拠 (算術・直接観測ではない): dst=`0x1400000` は 0x40 の倍数で、rcx は 0x40 刻みに進む。`0x15e1c70 − 0x1400000 = 0x1E1C70` は mod 0x40 で `0x30` → VA `0x6a7b92`。`0x15e4790 − 0x1400000 = 0x1E4790` は mod 0x40 で `0x10` → VA `0x6a7b88`。
- 結論: **0 化を行う命令は `f_6a7b70` の `movdqu` (VA `0x6a7b88`・`0x6a7b92`)** (静的は PE の VA 表で確認。動的ヒットとの対応は上の算術による)。前 run の「間接書込み・未特定」は、fill 関数の 16 バイト書込みで解消した (前 run の §2-3 の窓 `f_412c90` の外)。
- 残り: fill の幅 (`r8` = 0x100000 DWORD) と rect (w=h=1048576) の源は、呼出元 `0x815920` (callerRbp の +0x214/+0x218) で、未確定。#3090 [FLE-12] が追う。0 化と unit 209 の icall-miss・exit の因果は未確認 (§2-4)。
- 既定ビルド (`FLE_EXTRA_CCF` 無し・shim 有・HEAD `cd2166181`・`fle6_measure.sh`): units_run 209 / 942・停止 `MessageBoxA`→`exit(0)`・getmem 2314 / freemem 1199 (WWATCH 版と同じ)。`py_events` も同じ (unit 209・site 8 で両 slot が 0)。`[fle_wwatch]` は 0 件 (フック無効)。`FLEBOOT_IPP_CHECK ok:false` は既知の NG で rc=3 (変更前と同じ)。結果 JSON は `results/boot_summary_py123def.json`。同条件の前測定 (`fee239ea2`・main 取り込み前) も units_run 209・停止同じ。
- WWATCH 版 (HEAD `cd2166181` で再現): `[fle_wwatch]` 2 件・fill 6 件・units_run 209 / 942・停止 `MessageBoxA`→`exit(0)` (前測定と同じ)。
- 最初のウィンドウ無し。`FLE_WWATCH` は計測用の既定無効フックで、`ST*`/`STX`/`STY` は未定義時に従来と同じ展開になる (コード検査。既定ビルドは上で実測)。

