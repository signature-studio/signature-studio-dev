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

- 測定 commit: **`3832a1f7e`** (測定時の HEAD)。`mx60_callers.py` を最後に変えた commit は `75026a5ac` (`fix(massivex): unify mx60_callers TARGETS keys to RVA`)。`3832a1f7e` は REPORT のみの変更で、scripts は `75026a5ac` と同一。
- 素材: `plugins-massivex` (`$ARTIFACTS_DIR/plugins-massivex.tar.zst`・3.4 GB) を `tar --zstd -xf` で `$RUNNER_TEMP/massivex-art` に展開 → `Native Instruments Massive X v1.7.1.exe` を `scripts/parse_setup_headers.py <exe> <work>` → `scripts/extract_massivex.py <exe> <work> key` で `$RUNNER_TEMP/massivex-work/extracted/VST3/Massive X.vst3` (95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca` 一致)。展開先は repo 外。extract の `md5-ok 0/125` は既知事象 (§8.1)。
- 再現: `python3 tools/targets/massivex/dsp/scripts/mx60_callers.py '<展開先>/extracted/VST3/Massive X.vst3' > out.txt` (exit 0・実測 2 分 46 秒・load 0.62 → 0.98・単一プロセス)。

### 3.1 受入 3: 直接 E8/E9 の再確認 (測定 `3832a1f7e`・RVA 統一後)

- 修正前の `15c79a54d` の `mx60_callers.py` は、`TARGETS` が RVA と絶対 VA を混在させていた。照合は全て RVA で行うため、その時の P1〜P6 の 0 件は偽陰性の可能性があり、**無効**。`0x17b460`・`0x17b680` の 0 件は RVA 統一のため影響を受けない。
- 修正後 (`3832a1f7e`) の実測:
  - **P2 `0x1e47c0`: 直接 E8 call 2 件** (デコード・生バイトの 2 方法で一致)。`0x17a3151` と `0x17a3192`、いずれも呼出元の fn は `0x17a2ac0`。
  - P2 `0x1e47c0`: `.rdata` の vtable slot 5 件 (index 32・vtable `0x1842336b8`・`0x1842366f8`・`0x1842368b8`・`0x184944be8`・`0x184add2f8`)。
  - P1・P3〜P6 (`0x198700`・`0x1ef4b0`・`0x1f36a0`・`0x3bef80`・`0x104aea0`): 直接 call・生バイト・RIP 相対・`.rdata`/`.data` slot の全方法で **0 件**。
  - `0x17b460`: 直接 0 件・RIP 相対 0 件・`.rdata` slot 1 件 (vtable `0x1841836a8` index 30)。`0x17b680`: 直接 0 件・RIP 相対 0 件・`.rdata` slot 2 件 (index 32・両 vtable)。
- 受入 3 の状態: **部分達成** (再確認は完了。P2 に直接呼出し 2 件あり。P1・P3〜P6 は 0 件)。前回の「達成 (全対象 0 件)」の表記は誤り。

### 3.2 受入 2 の一部: `rbx` の vtable 候補 (未確定)

- `0x17b460` は `.rdata` の vtable `0x1841836a8` の **index 30** だけに登録 (`.rdata` 8 byte 照合・`.data` は 0 件)。もう一方の `0x183976038` には無い。
- `0x17b680` は両 vtable の index 32。
- 未確定の理由: `0x17b460` を呼ぶ側 (`call [reg+0xf0]` の 17 関数) のオブジェクトの動的型を、どの vtable が指すかまでは追っていない。よって `rbx` の型 (2 候補のどちらか) は確定できない。

### 3.3 受入 1 の一部: 呼出元の確定

- `0x17b460`: 直接参照 0 件・RIP 相対の関数ポインタ 0 件。vtable 経由のみ (index 30)。
  - 注意: `call [reg+0xf0]` (index 30) を含む関数は **17 関数・27 サイト** あるが、これは vtable index 30 を呼ぶ全サイトで、`0x17b460` に限った呼出元ではない。index 30 は別の vtable (`0x183976038` 側を含む) の slot も指しうるため、`0x17b460` の呼出元を個別に特定できていない。
  - よって「`0x17b460` の呼出元が xmm2 に float を載せて渡す」も「渡さない」も、この結果からは言えない。27 サイトの線形判定 (xmm2_live=False) は index 30 全体の傾向であり、`0x17b460` の確定根拠にしない。
- 重要な訂正: §2 の `0x18017b4af` (xmm2 を書く呼出し) は **`0x17b460` の内部**にある (`movss xmm2, [rsp+0x2c]` → `call [rax+0x100]` = index 32 = `0x17b680`)。つまり xmm2 は外部の呼出元から渡されたものではなく、`0x17b460` が自分のローカル値を `0x17b680` に渡している。「非 vectorcall の float 引数」の根拠を、外部呼出元の引数ではなく内部の計算に読み替える必要がある。
- P2 (`0x1e47c0`): **静的に追える参照あり**。直接 E8 call 2 件 (呼出元 fn `0x17a2ac0` 内の `0x17a3151`・`0x17a3192`)、`.rdata` の vtable slot 5 件 (index 32)。呼出元 fn `0x17a2ac0` の個別の引数・this の出所は未確定。
- P1・P3〜P6 (`0x198700`・`0x1ef4b0`・`0x1f36a0`・`0x3bef80`・`0x104aea0`): 直接 call 0 件・RIP 相対 0 件・`.rdata`/`.data` の slot 0 件。**静的に参照する箇所が見つからない**。呼出元は未確定 (ヒープや計算で作られる関数ポインタの可能性)。
  - これは「呼出元 0 件」ではなく「静的に追える参照が 0 件」。確定扱いにしない。

### 3.4 未了 (残件・起票先)

| 未了 | 理由 | 次の確認 |
|---|---|---|
| `rbx` の動的型 (受入 2) | 呼出元 17 関数のオブジェクト型を追っていない | `0x17b460` を呼ぶ 17 関数それぞれの `this` の出所を解析 |
| P2 の呼出元 (受入 1 の残り) | 直接 call 2 件 (fn `0x17a2ac0`)・vtable slot 5 件 | fn `0x17a2ac0` の呼出元を個別に確定 (受入 1) |
| P1・P3〜P6 の呼出元 (受入 1 の残り) | 静的参照 0 件 | 実行時の関数ポインタ登録の追跡 (動的解析 or 文字列/初期化の追跡) |
| 線形判定の穴 | 分岐を跨ぐ xmm2 の書込みを落とす可能性 | CFG 上の合流を見る版 (`mx55_callers_fn.py` と同じ限界) |

- 非 vectorcall の確定 (受入 1) は **未達**。上の表の 3 件が残る。

### 3.5 追補 (MX-60 #5498・`scripts/mx60b_xrefs.py`・測定 commit は本節の commit)

- 素材と展開は §3 と同じ (md5 `622993e7…` 一致)。`mx60_callers.py` の再実行 (exit 0・2 分 44 秒) で §3.1〜§3.3 の数値を再現。
- `0x17b460` の入口: `rcx` → `rbx` (this)、`edx`・`r9`・`r8` を引数として受ける。`xmm2` は **入口で読まれず**、関数内で `call 0x18038dfe8` の出力 (`[rsp+0x2c]`) を `movss xmm2` で載せてから `call [rax+0x100]` (index 32)。よって「呼出元が xmm2 に float を載せて渡す」経路は外部の呼出元には無い (§3 の訂正を支持)。
- `0x17b460` の直接 E8/E9 呼出元: **0 件**。RIP 相対・即値での関数ポインタ参照: **0 件**。`vt_IInstrument` (`0x1841836a8`) の index 30 からのみ参照される。
- `0x1841836a8` の vptr 書込み: `0x17a4b0` の `lea rax,[rip+...]; mov [rcx],rax` の **1 箇所のみ** (RIP 相対 1 件)。`0x17a4b0` 自身の直接呼出元・即値参照は **0 件**。よって `0x17a4b0` は静的に追える呼出元が無いコンストラクタ候補。
- `0x183976038` の vptr 書込み候補: `0xe4e0`・`0xe900` の 2 箇所 (RIP 相対)。`0x17b460` は含まない。
- P2 `0x1e47c0` の入口: `rcx = this` から `[this+8]` を取り、非 null なら `[obj]` の slot 32 (`call [rax+0x100]`) に `rdx` を渡す。P2 自身は xmm2 を書かない (入口の xmm2 は slot 32 の先へ素通し)。
- P2 の直接呼出元 `0x17a2ac0`: `0x17a3151`・`0x17a3192` の 2 箇所とも `rcx` (= `this`) は `rdi` = `[rbp+0x68]` (関数内のローカル)。`rdx` は `[rbp+0xd0]`・`[rbp-0x28]` (出力先)。`rbp+0x68` を初期化する `0x181f40c37`・`0x181f40c7b` の出所は未確定。
- **結論**:
  - 受入 1 (呼出元の確定): **未達**。`0x17b460` は index 30 経由のみで、index 30 を呼ぶ 17 関数の `this` の出所が未追跡。P2 は `0x17a2ac0` の 2 箇所 (`this` の出所未確定)。P1・P3〜P6 は静的参照 0 件のまま。
  - 受入 2 (`rbx` の動的型): **未達だが候補は狭まった**。`rbx` が `vt_IInstrument` 系のオブジェクトなら、その vptr は `0x17a4b0` で書かれる。ただし `0x17a4b0` の呼出元が静的に無いため、実際に `0x17b460` へ来るオブジェクトの型は確定していない。
- 未了 (起票先: #5498 の次の run): `0x17a2ac0` の `this` (`rdi`) の出所を遡る / `0x17a4b0` の生成元を特定する (動的解析 or 初期化経路の追跡) / index 30 を呼ぶ 17 関数の `this` を個別に確定する。

### 3.6 追補 (MX-60 #5498・`scripts/mx60c_slot30.py`・測定 commit は本節の commit)

- 素材: `plugins-massivex` を `$RUNNER_TEMP/mx` に展開 → `parse_setup_headers.py` → `extract_massivex.py <exe> work key` で `Massive X.vst3` を取得。md5 `622993e7…` 一致 (exit 0)。展開 6 秒・抽出 11 秒。
- `mx60b_xrefs.py` の再実行 (exit 0・2 分 33 秒): 直接 E8/E9 の呼出元は 3 対象 (`0x17a4b0`・`0x17b460`・`0x17a2ac0`) とも 0 件。`vt_IInstrument` の vptr 書込みは `0x17a4b0` の 1 箇所のみ (§3.5 と同じ)。
- `mx60c_slot30.py` (exit 0・1 分 11 秒):
  - `call qword ptr [reg+0xf0]` (index 30) は .text 全体で **27 箇所**。本 script は呼出し箇所を列挙するだけで、呼出元の `this` の型による分類はしていない (分類は未測定)。出力は呼出し箇所ごとに `in fn` の行を持つが、本 run では出力を保存しておらず、関数数は未確認。§3.3 の「17 関数・27 サイト」は前回の `mx60_callers.py` の測定値。
  - `0x17b460` の関数ポインタを値として持つ非実行セクションの位置は **`.rdata` RVA `0x4183798` の 1 件のみ** (`vt_IInstrument` `0x41836a8` の index 30)。よって `0x17b460` への間接経路は、この vtable slot を経由するものに限られる。
  - `0x17b460` の入口: `rcx` → `rbx` (this)、`edx` → `edi`、`r9` → `rsi`。`xmm2` は入口で読まれない (§3.5 と同じ)。
- **結論**:
  - 受入 1 (呼出元の確定): **未達**。index 30 の呼出し 27 件の各 `this` の型・出所は未追跡。
  - 受入 2 (`rbx` の動的型): **未達**。`0x17b460` を指す vptr の書込み先は `vt_IInstrument` の 1 箇所だけという確認は取れたが、`rbx` のオブジェクトが実際にその型かは、呼出し 27 箇所のうち `rbx` を渡す側の型を追うまで確定しない。
- 未了 (起票先: #5498 の次の run): index 30 の 27 箇所を `this` の型で絞り込む (`vt_IInstrument` の vptr を `[rcx]` で比較する静的な手がかりを探す) / `0x17a4b0` の生成元。

### 3.7 追補 (MX-60 #5498・`scripts/mx60d_entry_xmm2.py`・測定 commit は本節の commit)

- 旧判定の撤回: 前 round の `mx60d_entry_xmm2.py` は capstone の `regs_read` だけで判定しており、`call` の暗黙の引数読みを見ていなかった。このため「確定 (渡さない)」は**撤回する**。前 round の出力 (判定 0 件) は無効。
- `0x17b460` の逆アセンブル (事実): 呼出元から受けるレジスタは `rcx`・`edx`・`r8`・`r9`。`xmm2` は `call 0x18038dfe8` の後の `movss xmm2` で載せられ、直後の `call [rax+0x100]` (index 32) に渡る。`movss` の前に `call 0x18038dfe8` がある。
- 判定ロジックの修正: `call` は xmm2 を読みうるものとして数え、xmm2 を書く前に到達する `call` で書込みによる遮断をしない (保守的扱い・修正案 (b))。呼出先 `0x18038dfe8` の解析は行わない。
- 受入 1 (呼出元が xmm2 に float を載せて渡すか): **未確定**。修正後の判定を素材で実測していないため、結論は出さない。
- 測定の状態: 修正後の判定は §3.8 で実測 (前版では未実測)。
- 素材 `plugins-massivex.tar.zst` の中身 (実測): `NI_Massive_X_1.7.1.dmg` (1.58 GB) と `Native Instruments Massive X v1.7.1.exe` (1.87 GB) の 2 件。`Massive X.vst3` は tar の直下には無い。
  - `.dmg`: `7z` で HFS として開けるが、中身は macOS 版 installer (`.app`・`osx-arm64`/`osx-x86_64`)。`.vst3` の文字列・ファイルは無い。
  - `.exe`: PE 本体 (約 1.15 MB) の後ろに約 1.7 GB のオーバーレイ。`7z` は開けない (オーバーレイ先頭の CAB の扱いは `extract_massivex.py` の手順とは別)。
  - **訂正 (§3.8 で実測)**: 前版の「`Massive X.vst3` は取り出せない」は誤り。`parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` で `Massive X.vst3` (95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca`) を抽出できた。`.exe` の `7z` 不可の事実と抽出の可否は別の話。
- 受入 1 の残り (`this` の出所・27 箇所の呼出元の確定) と受入 2 (`rbx` の動的型): **未達のまま** (§3.4・§3.6 の未了を継続)。
- 未了 (起票先: #5498 の次の run): `0x17a2ac0` の `this` は `[rbp+0xd8]` から来る (関数内で vtable 呼出しが多く、個別の遡りは本 run の範囲外)。index 30 の 27 箇所の `this` 型の分類。`0x17a4b0` の生成元。

### 3.8 追補 (MX-60 #5498・`scripts/mx60d_entry_xmm2.py`・実測)

- 測定 commit: `3745063f8` (`mx60d_entry_xmm2.py` の最後のコード変更。以降この script は変更していない)。
- 素材: `plugins-massivex.tar.zst` を `$RUNNER_TEMP/mx` に展開 (6.4 秒)。`parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` (10.7 秒・`md5-ok 0/125` は既知事象) で `Massive X.vst3` を取得。md5 `622993e76565f49c094063a2b717d6ca`・95,356,824 B (期待値と一致)。
- 測定条件: `python3 mx60d_entry_xmm2.py "<vst3>" <RVA>` (RVA は ImageBase `0x180000000` を引いた値)。load は runner 上の単発実行。

| 対象 (絶対 → RVA) | 関数範囲 | 命令数 | xmm2 を読みうる箇所 | 解析不能 | 判定 | exit・時間 |
|---|---|---|---|---|---|---|
| `0x17b460` (RVA `17b460`) | `0x17b460`-`0x17b4d9` | 37 | 3 件: `0x17b493` call `0x18038dfe8`・`0x17b4af` call `[rax+0x100]`・`0x17b4c8` call `0x181a529c0` | 0 件 | xmm2 を読む経路あり | 0・0.17 s |
| `0x18038dfe8` (RVA `38dfe8`) | `0x123920`-`0x443b65e8` | 7,413 | 14 件 | 1 件 (`0x24689c`) | xmm2 を読む経路あり | 0・0.24 s |
| `0x1807568e8` (RVA `7568e8`) | `0x754fb0`-`0x75694f` | 272 | 0 件 | 5 件 (`0x7554be`・`0x7554c0`×4) | 判定保留 | 0・0.17 s |
| `0x181a52850` (RVA `1a52850`) | `0x17cc790`-`0x4e7014e9` | 7,195 | 2 件 (`0x17cc7bd`・`0x17cc7d0`) | 0 件 | xmm2 を読む経路あり | 0・0.24 s |

- pdata 範囲の不正: `0x181a52850` の範囲 `0x17cc790`-`0x4e7014e9` は約 0.8 GB で明らかに不正。`0x18038dfe8` の範囲 (約 0.5 GB) も同様に不正の疑い。どちらも関数範囲の事実として記録し、この範囲に基づく結論は出さない。
- 結論: `0x17b460` は保守的判定で xmm2 を読みうる (call 経由を含む)。したがって**呼出元の xmm2 が使われうる**。「渡さないこと」は示せない。受入 1 の xmm2 判定は**確定不能**のまま (保守的判定で「使われない」とは言えない)。
- `0x1807568e8` は解析不能 5 件があるため「判定保留」。docstring の「保守的に読む扱い」と判定ロジックの食い違いは、このコミットで「判定保留」を出すよう直した。
- 未解決: `0x18038dfe8` 以降の解析不能箇所の詳細、pdata 不正範囲の修正、index 30 の 27 箇所の `this` 型。いずれも #5498 の次の run で行う。

### 3.9 追補 (MX-62 #5657・`scripts/mx62_vtable_slots.py`・測定 commit `5a4380377`)

- 素材: `plugins-massivex` を `$RUNNER_TEMP/mx62` に展開 (6.3 秒) → `parse_setup_headers.py` (0.3 秒) → `extract_massivex.py <exe> work key` (10.5 秒・`md5-ok 0/125` は既知事象 §8.1)。`Massive X.vst3` = 95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca` 一致。展開先は repo 外。
- 測定: `python3 tools/targets/massivex/dsp/scripts/mx62_vtable_slots.py "<vst3>"` (exit 0・0.25 s・load 0.35 → 0.60 の単発)。出力:
  - `vt_IInstrument` (VA `0x1841836a8`): slot 30 = RVA `0x17b460`、slot 32 = RVA `0x17b680`。
  - `vt_main` (VA `0x183976038`): slot 30 = RVA `0x106a0`、slot 32 = RVA `0x17b680`。
  - `0x17b460` を値として持つ 8 バイト位置: `.rdata` RVA `0x4183798` の 1 件のみ。`0x17a4b0`: 0 件。
- **受入 2 (`rbx` の動的型) の判定**: `rbx` = `this` の vptr は **`0x1841836a8` (`vt_IInstrument`)**。
  1. `0x17b460` は呼出元が `call [reg+0xf0]` (index 30) で呼ぶ (直接 E8/E9 は 0 件・§3.5)。`this` の vptr を `V` とすると `[V+0xf0] = 0x17b460` である必要がある。
  2. 静的データ内で `[V+0xf0] = 0x17b460` となる vtable は `vt_IInstrument` のみ (上記)。`vt_main` の slot 30 は `0x106a0` で一致しない。slot 30 だけが型を分ける。
  3. 注記: `0x17b460` 内の `call [rax+0x100]` (slot 32 = `0x17b680`) は両 vtable で同じ値のため、型の判定には使えない。
  - **前提と限界**: 判定は静的データ (.rdata/.data) の vtable に限る。実行時に作られる vtable (ヒープ上) に `0x17b460` が入る場合は対象外。`0x17a4b0` (vptr 書込み) の生成元は未確定だが、型の判定には不要。
- **受入 4 (確定できない箇所)**: `0x17b460` を呼ぶ 27 箇所の各 `this` が実際に `vt_IInstrument` 系のオブジェクトかの個別確認は未了。上の判定は「どの呼出でも、vptr が静的 vtable なら `vt_IInstrument`」の論理による。
- 測定 commit `5a4380377` から HEAD までのコード差分 (`git diff 5a4380377 HEAD -- tools/targets/massivex/dsp/scripts`) は 0 バイト (本節は文書のみの追記)。
