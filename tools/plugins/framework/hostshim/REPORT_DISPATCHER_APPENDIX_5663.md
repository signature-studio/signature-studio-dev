# PLG-P0b-64 (#5663, 親 #4940) — Dispatcher (0x13173a0) の HostTag 供給元

部分達成 (`Refs #5663`)。受入 1 は既測 (`REPORT_DISPATCHER_APPENDIX.md` §B-2)。受入 2 は未達 (供給元の呼出元を特定できず)。

## 1. 測定

- 基点: `origin/main` f195a93a9。追加は `hs_disp_callers.py`・`hs_disp_refs.py` と本ファイルのみ。
- ベースライン `hs_disp_emu.py` (`HS_DISP_PATH=1`・既定 0 埋め・全 256 ID): real 70.21 秒、終了時 load 1.04 (`uptime` 1 分平均)。distinct (rax, path) = 109、rbp_ok 229 / mismatch 0 / unreached 27 で、既存 §D と一致。

## 2. 確定した事実

| 項目 | 結果 | 測定 |
|---|---|---|
| Dispatcher への直接 E8/E9 | **0 件** | `hs_disp_callers.py` (全 .text を rel32 で走査) |
| Dispatcher を指す絶対 qword | **1 件**: `0x1314178` (vtable VMT+0x70 = slot 0) | `hs_disp_refs.py` (a) |
| Dispatcher を指す rip 相対参照 | 0 件 | `hs_disp_refs.py` (b) |
| 検算: `0x1321e12 call 0x40fe90` (REPORT の既知 call) | 生バイトの E8 rel32 走査で一致 | capstone の線形逆アセンブルは同じ call を 0 件と返した (解析器の走査が不完全)。直接呼出しの列挙は生バイト走査の値を採る |

- 直接呼出が無いので、Dispatcher は vtable slot 0 (間接) 経由でのみ呼ばれる。rdx (HostTag) は plugin 側 `[plug+0x08]` から来る (`tools/plugins/ABI.md` の Dispatcher 呼出列 (`rdx=this->HostTag([+8])`)・`hostshim.c` の `PLUG_HostTag`)。その値は `CreatePlugInstance(Host, Tag)` の Tag (ABI.md §1.1: `mov [rax+8], rcx(=Tag)`)。
- 注意: `hs_disp_refs.py` の初版は `ImageBase` を二重に足して 0 件を返した。修正後の値を上に載せた。

## 3. 未確定 (供給元不明)

- FLEngine (block00031) の plugin ローダで `CreatePlugInstance` を呼ぶ箇所は**未特定**。
  - 文字列 `CreatePlugInstance` (UTF-16) は block00031 に RVA `0x98ceee`・`0xf2c7c2` の 2 箇所あるが、この VA を指す絶対 qword・abs32・rva32・rip 相対のいずれも検出されなかった。
  - ASCII 版と `GetProcAddress` の ASCII 文字列は、block00031 で `GetProcAddress` が 1 箇所見つかっただけ。ローダの取得経路の本体は未解析。
- よって Tag の実値 (HostTag の値) と、その生成元 (定数・ファイル内の文字列・呼出し側の計算) は**未確定**。

## 4. 次に必要な作業

1. block00031 の `GetProcAddress` の IAT 参照 (`call [rip+...]`) を列挙し、その戻り値を呼ぶ箇所 (`call rax`・`call [reg+disp]`) を追う。
2. その呼出し側で `CreatePlugInstance` の第 2 引数 (rdx) を作る命令を、直前の書込みから逆向きに出す。
3. 得た供給元の値で `hs_disp_emu.py` の `TAG` を差し替えて再測定する (HostTag 依存の r8d・応答への影響を見る)。

## 5. 使い方

```
FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone・unicorn 入り lib> \
  python3 tools/plugins/framework/hostshim/hs_disp_callers.py
FL_WIN64_DIR=... PYTHONPATH=... python3 tools/plugins/framework/hostshim/hs_disp_refs.py
```
