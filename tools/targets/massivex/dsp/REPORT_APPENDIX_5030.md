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
    (注: この 0 件の確認に使ったスクリプトは記録に残っていない。本付録の `mx55_callers.py`・`mx55_callers_fn.py` は `ff /2` の間接 call だけを数え、E8/E9 は数えない。E8/E9 の再確認は未了。)
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

## 測定 (2 回目・`mx55_callers_fn.py` と `mx6_e2e.sh`)

- 測定 commit: **`97d274d5e`** (`feat(massivex): classify call sites of 0x17b680 by xmm2 liveness (MX-55 #5030)`)。コードを変えた最後の commit。
- 測定 run: 測定 commit の PR #5246 の run。素材 `plugins-massivex` → `Massive X.vst3` 95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` 一致。
  - `MX_PE='<展開先>/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh`:
    exit 0・elapsed 53 s・load 0.39 0.44 0.23 → 0.76 0.54 0.28・U3c 118・U3b seeds 12 / one_round 14 で PASS。
  - `python3 tools/targets/massivex/dsp/scripts/mx55_callers_fn.py '<展開先>/VST3/Massive X.vst3'`: sites 56 (`xmm2_written` 1 / `livein_passthrough` 6 / `clobbered_by_call` 49)。
- 再測定の状況: 指摘対応の run (review fix) では `plugins-massivex` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、上の 2 つは再実行していない。上の値は測定 commit の run の記録。
- E8/E9 の 0 件: 上の 2 スクリプトは `ff /2` の間接 call だけを数える。E8/E9 の rel32 の件数は、この記録からは再確認できない (未了)。
- 測定 commit から HEAD までのコード差分: `git diff 97d274d5e HEAD -- tools/targets/massivex/dsp/scripts` は 0 バイト (出力なし)。`git diff 97d274d5e HEAD -- tools/targets/massivex` は本付録の文書追記のみ。

## 3. 残件の確定 (MX-60 #5498・`scripts/mx60_callers.py`)

- 測定 commit: **`15c79a54d`** (`feat(massivex): decode-based callers scan ... (MX-60 #5498)`)。コードを変えた最後の commit。
- 素材: `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` → `parse_setup_headers.py` / `extract_massivex.py <exe> <work> key` で `Massive X.vst3` (95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca` 一致)。展開先は `$RUNNER_TEMP` (repo 外)。
- 再現: `python3 tools/targets/massivex/dsp/scripts/mx60_callers.py '<展開先>/VST3/Massive X.vst3'` (約 2 分 21 秒・単一プロセス・出力は `grep` で整理)。

### 3.1 受入 3: 直接 E8/E9 の再確認 (確定)

- 命令デコード (capstone・.pdata の全関数) と生バイト scan (E8/E9 rel32) の両方で、`0x17b460`・`0x17b680`・P1〜P6 への直接 call/jmp は **0 件**。
- 2 つの方法が一致したので、§2 の「E8/E9 は .text 全体で 0 件」は確定扱いにしてよい (元の記録の確認スクリプトは残っていなかった)。

### 3.2 受入 2 の一部: `rbx` の vtable 候補 (未確定)

- `0x17b460` は `.rdata` の vtable `0x1841836a8` の **index 30** だけに登録 (`.rdata` 8 byte 照合・`.data` は 0 件)。もう一方の `0x183976038` には無い。
- `0x17b680` は両 vtable の index 32。
- 未確定の理由: `0x17b460` を呼ぶ側 (`call [reg+0xf0]` の 17 関数) のオブジェクトの動的型を、どの vtable が指すかまでは追っていない。よって `rbx` の型 (2 候補のどちらか) は確定できない。

### 3.3 受入 1 の一部: 呼出元の確定

- `0x17b460`: 直接参照 0 件・RIP 相対の関数ポインタ 0 件。vtable 経由のみ (index 30)。その呼出元 (`call [reg+0xf0]`) は **17 関数・全 17 サイト**で、線形判定により呼出し時点の xmm2 は **有効でない** (xmm2_live=False が 27 行・True は 0 行。全 27 サイトは `mx60.out` の `call site` 行)。
  - よって「`0x17b460` の呼出元が xmm2 に float を載せて渡す」は、この線形判定の範囲では支持されない。
- 重要な訂正: §2 の `0x18017b4af` (xmm2 を書く呼出し) は **`0x17b460` の内部**にある (`movss xmm2, [rsp+0x2c]` → `call [rax+0x100]` = index 32 = `0x17b680`)。つまり xmm2 は外部の呼出元から渡されたものではなく、`0x17b460` が自分のローカル値を `0x17b680` に渡している。「非 vectorcall の float 引数」の根拠を、外部呼出元の引数ではなく内部の計算に読み替える必要がある。
- P1〜P6 (`0x180198700`・`0x1801e47c0`・`0x1801ef4b0`・`0x1801f36a0`・`0x1803bef80`・`0x18104aea0`): 直接 call 0 件・RIP 相対 0 件・`.rdata`/`.data` の slot 0 件。**静的に参照する箇所が見つからない**。呼出元は未確定 (ヒープや計算で作られる関数ポインタの可能性)。
  - これは「呼出元 0 件」ではなく「静的に追える参照が 0 件」。確定扱いにしない。

### 3.4 未了 (残件・起票先)

| 未了 | 理由 | 次の確認 |
|---|---|---|
| `rbx` の動的型 (受入 2) | 呼出元 17 関数のオブジェクト型を追っていない | `0x17b460` を呼ぶ 17 関数それぞれの `this` の出所を解析 |
| P1〜P6 の呼出元 (受入 1 の残り) | 静的参照 0 件 | 実行時の関数ポインタ登録の追跡 (動的解析 or 文字列/初期化の追跡) |
| 線形判定の穴 | 分岐を跨ぐ xmm2 の書込みを落とす可能性 | CFG 上の合流を見る版 (`mx55_callers_fn.py` と同じ限界) |

- 非 vectorcall の確定 (受入 1) は **未達**。上の表の 3 件が残る。
