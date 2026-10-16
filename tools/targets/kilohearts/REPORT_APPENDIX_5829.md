# REPORT 付録 (#5829 KH-176): `FUN_180fb5dd0` 本体の `[rbp+0x30]` 読出し欠落・`FUN_180fb5e6c` への引数欠落を機械語で確定 (部分)

親 #4917 (KH-135) の追跡。受入 1〜3 を達成し、受入 4 (直した生成 C と Delay の emcc 件数の前後) は未着手。

**結論**: 欠落は 2 段にまたがる。(a) 呼出し規則: `FUN_180fb5dd0` の宣言は `void(void)` で、本体の呼出し `FUN_180fb5e6c()` も引数 0 件。機械語では 6 引数を渡している。(b) 本体の読出し: `[rbp+0x30]` の読出しは C に出ていない。どちらも生成 C の意味を変える silent miscompile の疑いで、4917 の呼出側の規則では直らない。

**測定 commit**: 本 PR の commit (コードを変えるのは `ghidra_route/callref_scan.py` の新規 1 本だけで、測定経路 `closure.py`・`ghidra_to_c.py`・`patches.py`・`emcc_census.py` は 0 行変更)。`git diff a5340d27e HEAD -- tools/targets/kilohearts/ghidra_route/{closure,ghidra_to_c,patches,emcc_census}.py` = 0 行。

## 1. 機械語の確定 (受入 1)

素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、REPORT_APPENDIX_4917 と同サイズ)。`scripts/extract_installer.sh` は dmg 側 (mac) で止まるため、win 側だけを同じ手順で手展開した。

逆アセンブル: `ghidra_route/callsite_disasm.py <core> 180fb5dd0 180fb5e6c` (capstone)。

| 位置 | 機械語 | 意味 |
|---|---|---|
| 180fb5e14 | `mov rax, [rbp+0x30]` | 5 番目の引数 (呼出側 `[rsp+0x20]`) を読む |
| 180fb5e18 | `mov [rsp+0x20], rax` | 5 番目の引数として積む |
| 180fb5e0f | `mov [rsp+0x28], rax` (rax = `&[rbp-0x40]`) | 6 番目の引数 (ローカル番地) を積む |
| 180fb5e1d | `call 180fb5e6c` | `FUN_180fb5e6c` へ 6 引数を渡す |

`FUN_180fb5e6c` 入口 (180fb5e6c〜) は rcx・rdx・r8・r9 を読んで関数内で使う (`mov rbp,rcx`・`mov ebx,r9d`・`mov rdi,r8`・`mov rsi,rdx`)。

呼出元 (全 `.text` 走査): `callref_scan.py <core> 180fb5dd0` = **バイト走査による候補 2 件** (call 命令位置 180fb5f50・180fb5f70)。`callref_scan.py` は命令境界を見ない (E8/E9 のバイト列を全走査) ため、この 2 件は命令として確認した数ではない。`[rsp+0x20]` = 0 は前 run の読みで、本 fix run では `plugins-kilohearts` が無く機械語を再確認していない。前 run の `callsite_disasm.py` で同じ 2 件の位置を確認した記録は無い。#4917 の呼出元表記 (180fb5f3c・180fb5f5c) は呼出元関数の先頭、本 REPORT の 180fb5f50・180fb5f70 は call 命令位置で、同じ呼出しの別表記。

## 2. 生成 C の突合 (受入 2)

測定: `closure.py delay` = 139 関数・FAIL 0・反復 1・実測 32.2 秒 (REPORT_APPENDIX_4883 の 28.7 秒と同じ規模)。`ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` の生成 C (`work/gr/delay_base/delay.c`):

| 関数 | 生成 C | 機械語 | 差 |
|---|---|---|---|
| `FUN_180fb5dd0` 宣言 | `void FUN_180fb5dd0(void)` | 5 引数 (rcx・rdx・r8・r9・[rsp+0x20]) | 引数を落とした |
| `FUN_180fb5dd0` 本体 | `FUN_180fb5e6c();` (2489) | 6 引数 (5 番目 `[rbp+0x30]`・6 番目 `&local`) | **`[rbp+0x30]` の読出し欠落**・6 引数の呼出し欠落 |
| `FUN_180fb5e6c` 宣言 | 6 引数 (690・2508 行) | 6 引数 | 一致 |
| 呼出元 2535・2546 | `FUN_180fb5dd0();` | 0 件 (`[rsp+0x20]` = 0 を含む) | 4917 の規則どおり一致 |

生成 C の本体に `[rbp+0x30]` の読出しが無い。`patches.py` の宣言規則 (`FUN_180fb5dd0` の `void(void)` への合わせ) がその形を固定している。

**切り分けは未確定 (Ghidra 段か変換段か)**: 生成 C の本体 (2489) は `FUN_180fb5e6c()` を 0 引数で出しており、`patches.py` の規則 (宣言 `void(void)`・呼出元 2 件の 0 件化) が宣言側の形を固定している。本 run では Ghidra の raw 出力 (`DecompEach`) を個別に確認していないため、どちらの段で `[rbp+0x30]` が落ちたかは未確定。次 run で `DecompEach` の出力 (`work/ghidra/delay/180fb5dd0.c`) と `ghidra_to_c.py` の入力の差を見て切り分ける。

## 3. 欠陥類型との照合 (受入 3)

`docs/DEFECTS.md` を確認: D4 (disp=0 の引数 reg 経由 deref の脱落) は近いが、本件は `[rbp+0x30]` のスタック読出しで、同型と断定できない。D7 (callee が読むスタック引数が 8B ずれる) も近いが、本件は読出し自体が無く、ずれではない。**既存類型には当てはまらない**。類型は未確定のまま、新規類型の候補として残す。

## 4. 修復 (受入 4): 未着手

修復は次の 3 点を同時に変える必要がある。この run では実施せず、次の run の作業とする。

1. `FUN_180fb5dd0` の宣言を `void FUN_180fb5dd0(undefined8, undefined8, undefined8, undefined4, undefined8)` 相当の 5 引数にする (または 6 引数の入力を持つ形にする)。
2. 本体の `FUN_180fb5e6c();` (2489) を 6 引数の呼出しに書き換える。5 番目は `[rbp+0x30]` の値 (= 呼出側の 5 番目の引数)、6 番目は `&alStack_48`。
3. 呼出元 2 件 (2535・2546) の `FUN_180fb5dd0();` を 5 引数の呼出しに戻す (4917 の 0 件規則を撤回するのではなく、宣言の引数数と揃える)。

emcc 件数の前後は、修復 commit の後に測定する。本 PR では測らない (件数の推定値は書かない)。

## 5. 件数の注意 (測定値の突合)

`ghidra_to_c.py delay` (HEAD・修正前) を `emcc -c -ferror-limit=0 -w` で流した件数は **392** (`emcc_census.py`: 引数数不一致 62・128bit レーン型 166・演算・代入・ポインタの型不一致 164)。REPORT_APPENDIX_4917 の 312 (引数数不一致 63) とは一致しない。原因は未特定。候補: 本 run の emcc 6.0.12 のフラグ差 (4917 の測定は `-w` なし・`ghidra_shim.h` 経路の差の可能性)、または 4917 以降の `main` 上の変換段変更。本 PR は件数の比較の前後差を取らないため、この数値を REPORT の結論に使わない。次 run の修復 commit では、同一 commit・同一フラグで before/after を取る。

## 6. 解析道具

- `ghidra_route/callref_scan.py` (新規): 実行セクションの E8/E9 rel32 を解決して、指定 VA への参照元を出す。命令境界は見ないので、出力は「バイト走査による候補」であり、命令として確認した数ではない。素の byte 検索より誤ヒットは少ないが、0 にはならない (本 run で誤ヒット 1 件を確認)。
- `ghidra_route/callsite_disasm.py` (既存・4917): 機械語の逆アセンブル。

## 7. 本 run の範囲外 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復 (受入 4): 宣言・本体呼出し・呼出元 2 件の 3 点の同時変更と before/after の emcc 件数 | Delay の silent miscompile が残る | #4917 の残件へ移管 (#4917 本文に記載済み) |
| emcc 件数 392 と 312 の差の原因 | 件数の比較の基準が定まらない | #4917 の残件へ移管 (修復の before/after と同時に確定) |
| `FUN_180fb5e6c` の他の呼出元の引数数 (`.text` 全体のバイト走査候補 53 件。命令境界で未確認) | 呼出元の規則の要否が未確定。本件の 5 番目の引数の扱いが他にも及ぶかは未確認 | #4917 の残件へ移管 (同じ本文に記載済み) |

## 8. 再現

1. `ghidra_route/closure.py delay <out> <core>` (絶対パスで渡す。Ghidra は `..` を含むプロジェクトパスを拒否する)。`GHIDRA_HOME` = `[GHIDRA]` (`docs/REFERENCES.md`)。
2. `ghidra_to_c.py delay <gr> <decomp_dir> <core> --fix bitcast,intload,stackpair,assoc,concat`。
3. `emcc -c -ferror-limit=0 -w -I ghidra_route delay.c -o delay.o 2> emcc.log` → `emcc_census.py emcc.log`。
4. `callsite_disasm.py <core> 180fb5dd0 180fb5e6c`。`callref_scan.py <core> 180fb5dd0 180fb5e6c`。

素材: `plugins-kilohearts`・`toolchain-emsdk` (`fl-win64` は不使用)。
