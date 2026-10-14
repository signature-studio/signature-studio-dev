# REPORT_2235 — DROP 候補 13105d0 の IR 側確認 (undef 読み) (#2235 / 親 #2185)

## 1. 測定条件

- 測定 commit: `7d15ceab` (origin/main)。監査スクリプト・ldfix・IR 生成物は無変更。
- 素材: `work-m11` (`tools/m11/work/`) のみ使用。`fl-win64` の PE は読んでいない (機械語は `boot3.drc.dsm` の逆アセンブルを使った)。
- 確認対象: `function_13105d0` (`boot3`。`boot0〜2`・`boot4` には定義が無い)。
- 機械語の DROP site (REPORT_2185 §3.1): 読み `1310837 add eax, dword [rbp+0x48]`、全経路の store `1310826 mov qword [rbp+0x44], rax`。
- 手順は REPORT_2186 §2.1 (#2214) と同じ: `boot3.norm0.ll` → `boot3.lift.ll` → `boot3.drc.dsm` → `boot_final.ll` / `boot_final3.ll` の順に確認した。

## 2. 結果

### 2.1 受入条件 1: 13105d0 の該当 read が undef であることの確認

- **norm0** (`boot3.norm0.ll` 167069〜167458): 読みは `%4 = load i32, ptr %1` (`%1` は `alloca i32`)。
  - `%1` を参照するのはこの 1 行だけで、関数内に `%1` への store は無い。よって store の無い alloca からの load (undef 相当)。
  - `%4` の使い手は `%124 = add i32 %123, %4` (`insn.addr 19990583`)。直前の `%120 = load [rsi+0x7ac]`・`+0x9c` の load (`%123`) と合わせて、機械語 `131082a mov rax,[rsi+0x7ac]` → `1310831 mov eax,[rax+0x9c]` → `1310837 add eax,[rbp+0x48]` の並びに対応する。**`%4` と `1310837` の対応は、この consumer の並びからの推定**で、`%4` 自体には `insn.addr` が付いていない。
- **store の欠落 (機械語 vs IR)**: 機械語の `1310826 mov qword [rbp+0x44], rax` は 8 バイト store で `[rbp+0x44..0x4b]` を覆う。IR は `store i32 %119, ptr %stack_var_-52` (`insn.addr 19990566`) の 4 バイトだけで、上位 4 バイト `[rbp+0x48..0x4b]` への store が IR に無い。`%4` の読みはこの上位 4 バイトに当たる。
- **lift** (`boot3.lift.ll` 157801〜158145): `%4 = xor i32 0, 0`。B1 (未初期化 alloca load → 0) で 0 に固定された。
- **drc** (`boot3.drc.dsm`): `1310826` の 8 バイト store と `1310837 add eax, dword ptr [rbp+0x48]` を確認 (§2.1 の機械語は上記 2 行の逆アセンブル出力)。
- **最終 IR** (`boot_final.ll` 97438〜97789 / `boot_final3.ll` 100005〜100356): どちらも `%4 = xor i32 0, 0`、`%124 = add i32 %123, %4`。
- **結論**: DROP 候補 13105d0 の機械語の読み (`1310837`) は、IR では store の無い alloca からの load になっている。最終 IR でも `xor i32 0, 0` に固定されている。REPORT_2185 の DROP 判定 (機械語上の store あり) と整合する。10628a0 / c38bd0 (REPORT_2186 §2.1) と同じ型。

### 2.2 受入条件 2: 手順

REPORT_2186 §2.1 と同じ段 (norm0 → lift → drc → final) で確認した。

### 2.3 受入条件 3: 測定 commit と HEAD 差分

測定 commit `7d15ceab` から、この REPORT を含む HEAD までの `tools/m11/ldfix` のコード差分は 0 行
(追加は REPORT_2235.md のみ)。差分出力は PR 本文の検証結果に載せる。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 13105d0 の store 欠落の起点 (`[rbp+0x44]` の 8 バイト値が IR のどの段で `%stack_var_-52` などに分かれて落ちるか) と修復 | IR 側の undef は確認した。起点と修復の方式は未決。コード変更は本 issue の範囲外 | #2144 (親・PM 判断) |
| 未判定 44 関数の確定 | 脱落か live-in か未確定 | #2211 [LD-87] |

## 4. 参照

- 親: `REPORT_2185.md` (§3.1 の DROP 3 関数・§5 の未解決)。
- 同型: `REPORT_2186.md` §2.1 (10628a0 / c38bd0)。
