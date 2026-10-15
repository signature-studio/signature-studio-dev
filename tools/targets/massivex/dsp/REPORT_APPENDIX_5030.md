# MX-55 (#5030) 付録: 既知の非 vectorcall float 関数と呼出元

本付録は `REPORT_MX33.md` §9 から分割移動した。


- 実装: `scripts/mx55_nonvec_float.py` (判定は `mx33_xmm03.py` の `classify_fn` / `classify_read` をそのまま使う)。
  母集合: seeds と 1-round の vectorcall rows のうち、xmm0〜3 の入口 livein ≥ 1・xmm4/5 の入口 livein = 0・範囲 ≤ 600 B。
  このうち `scalar`、RIP 相対の読み (定数テーブル) あり、float 演算 (`*ss`/`*sd`) あり、を候補にする。
- 母集合 (≤600 B・seeds と 1-round の行数の和) の判定件数: **scalar 15 / 128 bit 75 / 判定不能 36** (行数。重複を含む)。
  候補 (scalar + RIP + float 演算) は **14 行 = 一意 13 関数** (0x17b680 が seeds と 1-round の両方に出るため)。
  内訳: pdata 始点 1 件 (0x17b680 = §2 の #10 と同一)、pdata 始点でない内部入口 12 件。
- **同定 (受入 1)**: `0x18017b680` (`0x17b680`〜`0x17b7ed`・79 命令・pdata 始点・seeds と 1-round の両方に含まれる)。
  - 入口 livein: **xmm2 のみ** (xmm0・xmm1・xmm3 は入口で未定義)。CFG 上の xmm2 の読み: `0x18017b6a5 movaps xmm6, xmm2` (reg-reg 複写)。
  - 複写先 xmm6 の後続は `maxss xmm1, xmm6` (0x18017b7c0)・`minss xmm0, xmm1` (0x18017b7cc) の scalar 読みのみ。
    `follow()` の結果は `S` (CFG 後続の読みが全て scalar)。
  - 関数内の float 演算: `divss` / `maxss` / `minss` / `subss` / `movss` / `movsd`、RIP 相対 3 件 (定数)。
  - 入口の xmm2 は VEX 3 オペランドの上位保持ではなく、複写先で scalar 演算 (`maxss`/`minss`) に使われる。
    「xmm2 は単精度 float 1 個の引数」は推定で、引数の型は確認していない。
  - **非 vectorcall の確定はしていない**: 「vectorcall の規約に乗らない引数」かどうかは呼出元 (引数の渡し方) を見ないと言えない。
    本節は「scalar 読みの型を持つ内部関数 1 件 (0x17b680) の同定」までを記録する。
- **scalar 落ちの有無 (受入 2)**: **なし** (scalar が正しく scalar と判定された)。ただし以下の注意が要る:
  - 線形走査 (CFG を使わない) では P 読み 3 件 (`0x18017b6ab`・`0x18017b6bf`・`0x18017b6f5`) が出る。
    いずれも `movups xmmword ptr [rbp-...], xmm0` の **xmm0 の stack spill** (k=0) で、入口 livein (k=2) の読みではない。
    k=2 の P 読みは線形でも 0 件。
  - 呼出元: 直接 `E8`/`E9` の rel32 参照は .text 全体で 0 件 (`0x17b680` を含む 4 件すべて)。引数の渡し方は未確定。
    間接 call・vtable・pdata 経由で呼ばれるとみられるが、呼出元の引数幅は解析していない (U3e・MX-37 側)。
- **呼出元の探索 (MX-55 #5030 の残件・`scripts/mx55_callers.py`)**: 直接参照は 0 件のため、vtable 経由を見た。
  - `0x18017b680` は `.rdata` の 2 つの vtable (`0x183976038`・`0x1841836a8`) の **index 32 (disp `0x100`)** に登録されている (`.rdata` の 8 バイト照合で 2 件のみ)。
  - `call qword ptr [reg + 0x100]` は 56 件 (disp 一致のみ・型は未追跡)。直前 40 命令の窓で xmm2 を書くのは **1 件**: `0x18017b4af` (`movss xmm2, [rsp+0x2c]` → `mov rax, [rbx]` → `call [rax+0x100]`)。
    この呼出元は `0x18017b460` の関数内にあり、`rbx` は関数の第 1 引数 (`rcx`) 由来。
  - **確定できないこと**: `rbx` が指す型が 2 つの vtable のどちらか (つまり slot 32 が `0x17b680` を指すか) は未確認。
    disp 一致の 56 件のうち残り 55 件の呼出元は xmm2 を書かず、この 1 件とは別。よって「xmm2 単精度 1 個を渡す呼出し」は 1 件の仮想呼出でのみ支持される。
  - **結論**: 非 vectorcall は **部分的に支持** (呼出元 1 件が xmm2 に float を載せて呼ぶ)。型の確定 (`rbx` の vtable) と、他の呼出元の除外は未了。残件は #5030。
- **残件 (U3g の範囲外)**: 非 vectorcall の確定 (呼出元で xmm2 を渡すこと) は未確認。内部入口 12 件は
  `classify_fn` で scalar だが、いずれも直接 call 0 件で引数の出所を確かめていない。判定の正しさの確認は MX-37 の残件に残す。
- **import 名**: VST3 の import (318 件) に libm/CRT の float 関数 (sin・cos・exp・pow・sqrt 等) は無い (再確認)。
  よって同定は内部の関数のみ。

## 2 回目 (残件の分類・`scripts/mx55_callers_fn.py`)

- 方法: `call [reg+0x100]` の 56 件 (disp 一致) を、所属関数 (`.pdata` の始点から) の先頭から呼出し直前まで読み、
  call/ret を跨いで xmm2 が有効かを見る。`.pdata` は `pefile` が例外ディレクトリを読めないため (DATA_DIRECTORY[3] を直接読む)。
  判定は線形 (分岐の合流を見ない)。
- 分類 (56 件):
  - `xmm2_written` **1 件**: `0x18017b4af` (関数 `0x18017b460`)。call 直前に xmm2 を書く。
  - `livein_passthrough` **6 件**: 関数入口の xmm2 がそのまま届く (呼出元の引数が通過)。関数: `0x180198700`・`0x1801e47c0`・`0x1801ef4b0`・`0x1801f36a0`・`0x1803bef80`・`0x18104aea0`。呼出元の引数は未追跡。
  - `clobbered_by_call` **49 件**: 関数内で先に call があり、その後 xmm2 を書いていない (Win64 では xmm0-5 は揮発)。線形判定のため、分岐で call を経由しない経路の可能性は残る。
- `0x18017b460` の位置: `.rdata` の IInstrument 系 vtable (`0x1841836a8`) の index 30 に登録。直接 E8 は 0 件。
  その `this` (rcx → rbx) から `[this+0x100]` を呼ぶ (slot 32 は両 vtable とも `0x17b680`)。
  rbx の動的型は未確定 (IInstrument を実装する他クラスの vtable は見ていない)。
- **結論 (受入 3)**: 未達。`0x17b680` に xmm2 を渡す呼出しは **1 件の仮想呼出 (`0x18017b4af`) でのみ支持される**。
  ただし (a) `0x18017b460` の呼出元、(b) `livein_passthrough` の 6 関数の呼出元、(c) `clobbered_by_call` の線形判定の穴、を見ていない。
  よって「非 vectorcall の確定」はしていない。残件は #5030 に残す。
