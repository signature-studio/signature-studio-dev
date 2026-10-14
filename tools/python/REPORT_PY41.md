# PY-41 (#1514): channels 状態参照 18 関数の PE 解析 (ハンドラ位置・書式・引数)

親: #1343 (PY-33)。前段: #1336 (PY-32, 棚卸し)、#1527 (PY-39)、#1529 (PY-40)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 18 関数すべてについて、PyMethodDef 表の entry・ハンドラ先頭 VA・書式 (fmt)・kwlist を FLEngine PE から取得し、`flapi_kwargs.json` の `fn_va`・flags・fmt・kwlist と一致することを確認した。
- **戻り値・範囲外 code・状態の副作用は未確定**。ハンドラから下位関数への委譲先を追っていないため、`provider/fl_engine.c` への実装は今回行わない (推測実装の禁止)。
- コード変更は `provider/` `host/` `tests/` で 0 件。本 PR は解析の記録のみ。受入条件は部分達成 (`Refs #1514`)。

## 測定

- 解析対象: `$FL_WIN64_DIR/extracted/block00031_PE.bin` ([WIN64]・FL 26.1.7.5653 の FLEngine PE)。素材 `fl-win64.tar.zst` を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開 (実測 2.3 秒)。展開先は `$RUNNER_TEMP` 相当の作業領域 (repo 外・gitignore 対象外のため commit しない)。
- 解析補助: `tools/python/analysis/flapi/pe_handler_probe.py` (既存・未変更)。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <18 関数名>` → 終了 0。18 関数すべての表エントリを検出 (`selectAll` 等は PE 内に複数の同名表エントリがあり、channels 側は `flapi_kwargs.json` の `fn_va` で選んだ)。
- 測定 commit: 本 PR のコード commit (doc のみ)。差分 0 の証跡は PR 本文に記載。

## ハンドラ位置と書式 (PE 実測・flapi_kwargs と一致)

| 関数 | fn_va | flags | 書式 (fmt) | kwlist |
|---|---|---|---|---|
| channelNumber | 0xd58f80 | 3 | `\|ii` | canBeNone, offset |
| getActivityLevel | 0xd5d060 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelColor | 0xd594b0 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelIndex | 0xd5bd60 | 1 | `i` | なし |
| getChannelMidiInPort | 0xd5bcd0 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelPitch | 0xd5a600 | 3 | `i\|ii` | index, mode, useGlobalIndex |
| getChannelType | 0xd5abc0 | 3 | `i\|i` | index, useGlobalIndex |
| getCurrentStepParam | 0xd5bb30 | 3 | `iii\|i` | index, step, param, useGlobalIndex |
| getGridBit | 0xd5b420 | 3 | `i\|ii` | index, position, useGlobalIndex |
| getGridBitWithLoop | 0xd5bc10 | 3 | `ii\|i` | index, position, useGlobalIndex |
| getRecEventId | 0xd5c0f0 | 3 | `i\|i` | index, useGlobalIndex |
| getStepParam | 0xd5ba00 | 3 | `iiii\|i` | step, param, offset, startPos, padsStride |
| getSwing | 0xd5dbf0 | 4 (NOARGS) | なし | なし |
| isChannelMuted | 0xd59790 | 3 | `i\|i` | index, useGlobalIndex |
| isChannelSolo | 0xd59a80 | 3 | `i\|i` | index, useGlobalIndex |
| isGridBitAssigned | 0xd5b360 | 3 | `i\|i` | index, useGlobalIndex |
| isGraphEditorVisible | 0xd5c8f0 | 4 (NOARGS) | なし | なし |
| isHighLighted | 0xd5c7a0 | 4 (NOARGS) | なし | なし |

## 未確定 (次に決める事項)

1. **戻り値の型と意味**: 各ハンドラの末尾で返す値 (None / bool / int / float) は、下位関数の戻り規約を読んでいないため未確定。
2. **範囲外 code**: index・position・step が範囲外のときの code (`FL_E_RANGE` か別 code か) は未確定。PY-40 §3 未確定 1 と同じ参照関数 (`0x1005730` 系) の後半が未読。
3. **`channelNumber` の kwlist**: `canBeNone`・`offset` は実 FL の引数名として自然だが、`flapi_table.json` の `sig` との対応は未照合。
4. **`getChannelIndex` (flags 1)**: VARARGS のみで kwlist なし。引数 1 個 (`i`) の受け取りは確定。

## 次にやること (#1514 で継続)

1. 書式で受け取った引数の後段を読み、戻り値と範囲外 code を関数ごとに REPORT に追記する。
2. 確定した関数から順に `provider/fl_engine.c` に実装し、mock (`host/fl_mock.mjs`) に同じ意味論を足して diffs 0 を取る。
3. `tests/provider_check.mjs` の実装数を更新し、`FL_ENGINE=wasm node tests/all_tools.mjs` の 48/48 を再測定する。

---


検証起点 commit: `ecf6d6e5` (origin/main)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。
親: #1525 (PY-38 / #1515 の子)。前提の PY-38 報告: `tools/python/REPORT_PY38.md`。

## 結論

- 範囲縮小後の受入条件 (呼出し元 1 件と引数設定の確定) は**達成**。本 run では C 実装・mock 差分検査・`all_tools.mjs` は未実施。
- 汎用 helper `0x1046a30` の本体・引数の意味、`chan`・status 写像は未確定。残りは子 issue #1828 (PY-49)・#1829 (PY-50) に移管する。

## 測定条件

- 素材: `oc_artifacts: fl-win64` の `flstudio_win64_26.1.7.5653.exe/extracted/block00031_PE.bin` (22,227,016 B)。
  `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/py41 extracted/block00031_PE.bin` で `work/` に展開 (gitignore)。展開 2.5 秒 (実測)。
- 逆アセンブル: `python3 tools/python/analysis/py41_disasm.py tools/python/work/py41/extracted/block00031_PE.bin 0x1046a30` (capstone 5.0.7・pefile)。
- コード差分 0 の確認 (測定 commit = 本 commit、`provider/` は未変更): `git diff ecf6d6e5 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR で変更なし)。

## 0x1046a30 の入口 (確認済み・実測)

- フレーム 0x590 バイト。引数は `ecx` → `[rbp+0x5b0]`、`edx` → `[rbp+0x5b8]`、`r8d` → `[rbp+0x5c0]` に退避。
- 入口で `[rbp+0x584] = -1` を入れ、`[rip+0x59ab06]` のフラグを `cmp byte ptr [rax], 0` / `jne 0x104cc72` (0x1046d8a〜0x1046d8d) で見る。フラグが立っていれば 0x104cc72 へ飛ぶ (`0xf82c20` は呼ばない)。
- フラグが立っていなければ `[rax+0xf30]+0x49e` と `[rax+0x10]` を見て (0x1046d93〜0x1046dbc)、条件を満たす経路で `r8d` のビット判定 (`0x8a1`・`0x20`・`0x10000`) を通過したときに `0xf82c20` を呼ぶ (`call` は 0x1046e00)。0xf82c20 の中身は未確認。
- `r8d` のビット判定:
  - `test r8d, 0x8a1` が 0 なら分岐 0x1046e05 へ飛ぶ。
  - `test r8d, 0x240` (0x1046e23) と `test r8d, 0x20` / `0x10000` / `0x8000` が分岐の条件に使われている。
- `ecx` の判定 (0x1046e7c〜): `test rax, rax` / `cmp rax, 0xfffffff` の 2 段で範囲を見て、`ecx >> 16` を `[rbp+0x55c]` に取り出す。
  - `0x40000001` は `0xfffffff` より大きいので、この範囲判定で `0x1046edf` へ飛ぶ経路になる。
  - **推定**: `ecx` の上位ビット (0x40000000) がカテゴリ、下位 16 bit が index ではなく別種の値。確定には 0x1046edf 以降の読解が必要。

## 未確定 (本 run で残したもの)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1046a30` の本体 (0x1046edf 以降) と `ecx=0x40000001`・`edx=0x3dd`・`r8d=2` の意味 | setSwing/getSwing の実装が書けない | #1828 (PY-49) |
| `chan` のフィールド `+0x739` / `+0x794` / `+0x79c` と `0xffa6d0` の戻り値 2 の意味 | rerollLoopStarter* の実装が書けない | #1829 (PY-50) |
| status 値 (-1〜-10) と `finish` のエラー文字列 10 件の対応 | エラー時の例外文字列が決まらない | #1829 (PY-50) |
| C 実装 (`provider/fl_engine.c` 4 関数 + getSwing)・mock 差分 0・`all_tools.mjs` 48/48 | 受入条件 3 件 | #1828・#1829 の確定後 |

## #1765 (PY-45) 追記: `0x1046a30` の呼出し元 (実測・1 件)

- 測定: `tools/python/work/py41/extracted/block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で展開・2.8 秒)。逆アセンブルは `analysis/py41_disasm.py` (capstone・pefile)。
- 呼出し元 `0x10473a5` (`call 0x1046a30`) を確認。直前の引数設定は `ecx = [rbp+0x5b0]`・`edx = 0`・`r8d = 2`。戻り値は `[rbp+0x580]` に格納 (0x10473aa)。呼出し元 `0x10473a5` は `.pdata` (RUNTIME_FUNCTION) で `0x1046a30`〜`0x104cccb` の関数に含まれ、呼出し先 `0x1046a30` と同一関数内 (自己呼出し)。`0x1046edf` は関数の先頭ではなく、`0x1046a30` 関数内の分岐先。
- 呼出しに至る経路: `0x104734a`〜`0x1047394` の走査ループ (`0x12df530` の戻り値判定) を抜けた後。ループ内で `0x1047382` の一致が見つかった場合は `je 0x1047424` で `0x1046a30` を呼ばずに抜ける。
- **未確認 (#1828 (PY-49) に移管)**: 呼出し元の全件。全 `.text` を走査する補助スクリプトの初回実行は 0 件を返したが、スクリプト側の誤りであり、呼出し元 0 件とは判定しない。
- **未確認 (#1828 (PY-49) に移管)**: `0x1046a30` の本体 (0x1046edf 以降の分岐先)、`ecx=0x40000001` の意味、`r8d=2` の意味。
- **未着手 (#1829 (PY-50) に移管)**: `chan` のフィールド・status 写像・`finish` のエラー文字列。

受入条件の達成状況 (範囲縮小後の受入条件を基準): **達成** (呼出し元 1 件・引数設定 `ecx`/`edx`/`r8d` の確定)。**子 issue へ移管**: `0x1046a30` の本体・引数の意味・呼出し元の全件 (#1828 (PY-49))、`chan` と status・エラー文字列 (#1829 (PY-50))、C 実装・mock 差分・all_tools 48/48 (#1828・#1829 の確定後)。

## PY-49 (#1828): 0x1046a30 の呼出し元 全件 と 戻り値 (要約)

- 結論: 呼出し元 160 件 (`analysis/py49_callers.py`)。戻り値 `[rbp+0x584]` の書込みは 2 箇所 (PY-60 で確定)。全文は `REPORT_PY41_APPENDIX.md` (250 行上限のため分割移動)。

## PY-52 (#1875): `ecx=0x40000001`・`edx=0`・`r8d=2` 経路の確定 (要約)

- 結論: getSwing 経路 (`ecx=0x40000001`・`r8d=2`) の分岐と戻り値式 `dword [*(0x15e3290)]` を確定。数値は 0x15e3290 の書込み元 (PY-54) に依存して静的には未確定。全文は `REPORT_PY41_APPENDIX.md` (250 行上限のため分割移動)。

## PY-53 (#1911): ecx 分岐表 (0x104742a〜0x104745f) の確定 (実測・逆アセンブル)

- 測定: `analysis/py53_dispatch.py work/py41/extracted/block00031_PE.bin work/py53` (0.1 秒・capstone 5.0.7・pefile)。関数 0x1046a30〜0x104ccca を 4,664 命令に逆アセンブル (PY-52 と同数)。素材 `fl-win64` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で展開 (2.8 秒)。
- 既知類型との関係: 該当なし (逆アセンブルの分岐読解のみ・lift/IR 変換は行っていない)。

### ecx の分岐表 (本 run で確定)

`0x1047424` で `mov eax,[rbp+0x5b0]` (ecx の退避値) を読み、以下の比較連鎖に入る (`0x104742a`〜`0x104745f`)。

| VA | 命令 | 分岐 |
|---|---|---|
| 0x104742a | `cmp eax, 0x40000001` / `jg 0x104746a` | ecx > 0x40000001 → 0x104746a |
| 0x1047436 | `cmp eax, 0x40000001` / `je 0x104c4af` | ecx == 0x40000001 → 0x104c4af (PY-52 の経路) |
| 0x104743c〜0x1047446 | `sub eax,0x80000000` / `cmp 0x70000000` / `jb 0x104aa87` | ecx ∈ [0x80000000, 0xf0000000) → 0x104aa87 |
| 0x104744c〜0x1047456 | `sub eax,0x80000000` / `cmp 0x10000000` / `jb 0x1047497` | ecx ∈ [0x00000000, 0x10000000) → 0x1047497 |
| 0x1047458〜0x104745f | `sub eax,0x40000000` / `test eax,eax` / `jne 0x104caae` / 以降 `jmp 0x104c2a6` | ecx == 0x40000000 → 0x104c2a6、他 → 0x104caae |
| 0x104746a〜0x1047492 | `sub eax,0x40000002` / `je 0x104c64f` / `sub 3` / `je 0x104c919` / `sub 0x2ffffffb` / `cmp 0x10000000` / `jae 0x104caae` / `jmp 0x104aa87` | ecx == 0x40000002 → 0x104c64f、ecx == 0x40000005 → 0x104c919、ecx ∈ [0x40000006, 0xf0000000) → 0x104aa87、他 → 0x104caae |

- 分岐表の検算 (別アルゴリズム): `analysis/py53_ecx_route.py` は 32bit 演算の if 文で分岐先を直接求める。`analysis/py53_ecx_check.py` は逆アセンブル命令 (`work/py53/fn.txt`) を実行して分岐先を求め、両者を境界値 20 件 (0・0xffff・0x10000000・0x40000000〜0x40000006・0x6fffffff・0x70000000・0x80000000・0xefffffff・0xf0000000・0xffffffff など) で比べる。
  - 結果: `cases=20 mismatch=0` (exit 0)。
  - ネガティブコントロール: `--mutate` で 0x104742a の比較値を 1 つ (0x40000001 → 0x40000002) 壊すと `MISMATCH ecx=0x40000002 asm=0x104caae table=0x104c64f` が 1 件出て exit 1。照合が比較値の変化を検出することを確認した。
- 戻り値への影響: 分岐先のうち `0x104c4af` (ecx=0x40000001) 以外の本体は未読。**分岐先ごとの戻り値は未確定** (子 issue へ)。

### r8d 判定箇所 (本 run で抽出・ビットの意味は未確定)

- `r8d` は入口の 0x1046d71 で `[rbp+0x5c0]` に退避される。`analysis/py53_dispatch.py` が `[rbp+0x5c0]` を `test eax, imm` で読む箇所を全件抽出: **174 件** (`work/py53/r8d_bits.txt` は gitignore 対象の生成物。再現はスクリプトで行う)。
- 判定マスクの件数 (実測): `0x1`×36・`0x20`×36・`0x2`×32・`0x4`×27・`0x10`×17・`0x10000`×7・`0x14`×3・`0x800`×2・`0x8a1`・`0x8000`・`0x80`・`0x4000`・`0x40`・`0x3c0`・`0x2800`・`0x240`・`0x2000`・`0x200`・`0x1000`・`0x100`・`0xffffffdd` 各 1。
- ビットの意味 (どの値を読むか・何を描画するか) は未確定。PY-52 の経路で確定したのは `0x20`・`0x1`・`0x2`・`0x10`・`0x4`・`0x80`・`0x100`・`0x8000` の判定の向きのみ。

### 受入条件の達成状況 (縮小後)

- ecx の分岐構造を PE 解析箇所 (VA) つきで確定: **達成** (上表・検算 mismatch 0)。
- `r8d` の各ビットの意味を判定箇所 (VA) つきで記録: **未達** → 子 issue。
- 戻り値 (`[rbp+0x584]`) の各経路の式を分岐ごとに記録: **未達** → 子 issue (分岐先本体の読解が前提)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 分岐先本体 (0x1047497・0x104aa87・0x104caae・0x104c2a6・0x104c64f・0x104c919) の読解と、`r8d` 各ビット (174 箇所) の意味・戻り値 `[rbp+0x584]` の分岐ごとの式 | 呼出し元 160 件の大半の戻り値が決まらない | #1982 (PY-60・親 #1911) |

## PY-60 (#1982): 戻り値の出口構造と制御フローの 2 手法照合 (実測)

- 測定: `analysis/py53_dispatch.py` (capstone・4,664 命令) と `analysis/py60_objdump_check.py` (objdump 2.42 で独立に取得)。素材 `fl-win64` は `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開 (2.5 秒)。
- 照合: jcc/jmp の辺 **614 件** を capstone と objdump で比べ、**一致 614・不一致 0** (exit 0)。
- 戻り値 `[rbp+0x584]` の書込みは 2 箇所のみ: 0x1046d79 (`= -1`)・0x104cc6b (`= eax`、直前 0x104cc65 の `eax = [rbp+0x5b8]`)。読出しは 0x104ccba (ret 値) の 1 箇所。
- `[rbp+0x5b8]` の書込みは **74 箇所** (`mov dword ptr [rbp+0x5b8], reg`)。個々の式は未確定 (子 issue)。
- 出口の入辺 (実測):
  - 0x104cc65 (`[rbp+0x5b8]` を読む): 0x104cc39 の `je` (r8d&0x80 = 0) と、0x104cc60 からの fall-through。
  - 0x104cc2e: 0x104cb0f の `je` (r8d&0x100 = 0) と、0x104cc29 からの fall-through。
  - 0x104cc72: 早期 exit の jcc/jmp 9 件 (0x1046d8d・0x10471f9・0x10474b9・0x104846a・0x104847b・0x10495f6・0x1049621・0x104a7ba・0x104a7d0) と、**通常経路の fall-through** (0x104cc6b → 0x104cc71 nop → 0x104cc72)。
  - 0x104cb04: 0x104cab5・0x104cac2 の `je` 2 件。
- **訂正**: 0x104cc72 は「-1 専用の早期 exit」ではなく、通常経路と共有する後始末ブロック。戻り値が -1 になるのは、早期 exit の経路で `[rbp+0x584]` が書かれないため。
- 受入条件の状況: 制御フローの照合 (検算 mismatch 0) と戻り値の書込み構造は**達成**。分岐先本体の値の式・`r8d` 各ビットの意味・`[rbp+0x5b8]` の各書込みの式は**未達** (子 issue へ移管)。

## PY-54 (#1912): `0x15e3290` の書込み元 (実測・逆アセンブル)

- 測定: fl-win64 の `block00031_PE.bin` (`.text` 0x401000・size 0xfa3600、`.data` 0xfa5000)。解析は `analysis/py54_refs.py` (RIP 相対参照の全走査) と `analysis/py54_func.py` (`.pdata` による関数境界)。
- 参照の全件 (`0x15e3290` を RIP 相対で指す命令): **読み 6 件・書き 0 件**。0xd0c645・0xd0c6a4・0xf42a18・0xf4f88a・0xfde5b5・0x104c564 (`mov rax, [rip+...]` の後に `[rax]` を読む形)。`0x104c564` が getSwing の経路。
- `0x15e3290` の値 (qword): PE の生データは `0x000000000196ec34` (qword。`.bss` 内の `0x196ec34` を指すポインタ)。つまり `dword [*(0x15e3290)]` は `.bss` の cell `0x196ec34` の 32bit 値。
- `0x196ec34` への書込み: `0x1311030` の `mov [rip+...], ecx` (0x1311030) の 1 件だけ。これ以外に `.text` 内で `0x196ec34` を書く RIP 相対命令は無い。
- `0x196ec30` への書込み: `0x1311046` の `mov [0x196ec30], eax` (0x1311046) の 1 件。`0x1311030` の関数 (`.pdata` 上 0x1d バイト) の中の 2 命令。
- `0x1311030` の呼出し元 4 件: `0x104c53f` (getSwing 経路と同じ `0x1046a30` 内・`[rbp+0x5c0]` の bit0 が立つときのみ通る。getSwing の `r8d=2` では通らない)・`0xf4f9e5`・`0xf47726`・`0x13112a1`。
- **setter の役割 (実測の範囲)**: `0x1311030` は `ecx` を cell `0x196ec34` に格納し、(`[rip+0x2c7988]` の値 × cell) `>> 8` を `0x196ec30` に格納するだけの 0x1d バイト関数。何の値を表すかは、呼出し元の意味が未確定のため決められない。
- **結論 (getSwing の戻り値)**: 戻り値の式 (`dword [*(0x15e3290)]`) は確定。読み先の cell `0x196ec34` は `.text` 上で `0x1311030` の setter だけが書く。getSwing の数値はこの setter の入力 (呼出し元が渡す `ecx`) に依存し、**静的には決まらない**。`.bss` 初期値 (ゼロ初期化か否か) も実行時の値であり、静的解析では確定しない。
- **未解決**: setter `0x1311030` の入力を決める呼出し元 3 件 (`0xf4f9e5`・`0xf47726`・`0x13112a1`) の条件分岐の意味。`0x1310fb0` 付近は線形走査の同期が崩れるデータ領域のため、命令列の確認は `.pdata` 経由で行った。

## 追補 (#1514・実装): 公開 stub の戻り型で決めた 5 関数

- 結論: 18 関数のうち **5 関数** (`isChannelMuted`・`isChannelSolo`・`getChannelColor`・`getGridBit`・`channelNumber`) を `provider/fl_engine.c` と `host/fl_mock.mjs` に実装した。残り 13 関数は未実装 (PR 本文の未解決表。#1514 に残す)。
- 意味論の根拠: 公開 API stub (IL-Group/FL-Studio-API-Stubs・commit `9b4c7fa`・`tools/python/work/fl-stubs` に `git clone --depth 1`)。`src/midi_controller_scripting/channels/__properties.py` (`channelNumber` :59・`getChannelColor` :157・`isChannelMuted` :209・`isChannelSolo` :258) と `__sequencer.py` (`getGridBit` :41) の `## Returns` と説明に従う。fn_va は前節の表のとおり。**PE による意味論の確認は本追補では行っていない。**

| 関数 | fn_va | 戻り型 (stub) | 実装 (C と mock 同一) |
|---|---|---|---|
| isChannelMuted | 0xd59790 | bool | `mute` を返す |
| isChannelSolo | 0xd59a80 | bool | `solo` を返す |
| getChannelColor | 0xd594b0 | int | `color` をそのまま返す (stub: 0x--BBGGRR) |
| getGridBit | 0xd5b420 | bool | `steps[position]` を返す (0..63 外は code 4) |
| channelNumber | 0xd58f80 | int | 選択の並びで offset 番目 (0 = 先頭)、超えたら最後の選択。無選択は canBeNone で -1 / 0 |

- 範囲外 code: 4 関数 (isChannelMuted・isChannelSolo・getChannelColor・getGridBit) は channels 共通の `CH` 検査 (code 4 "Index out of range")。PE で `-4` を確認したのは `selectOneChannel` のみ (REPORT_PY69)。この 4 関数は PE 未確認。`channelNumber` は index 引数が無いため範囲外 code を持たず、offset 超過は最後の選択を返す。
- 仮置き (stub に記述なし): `getGridBit` の position 範囲は `setGridBit` と同じ 0..63。`channelNumber` の負の offset は先頭扱い。useGlobalIndex は未モデル (グループ無し・既存関数と同じ扱い)。
- PM agent の判断待ち: getGridBit の position は必須か (PE fmt `i|ii` は任意、stub と生成表は必須)・既定案: stub 準拠 (現実装)。

### 測定 (測定 commit `fde09f94`・コード変更の最後の commit)

| 検査 | コマンド | 結果 |
|---|---|---|
| C provider の build | `bash tools/python/provider/build.sh` (emsdk) | 成功・1.3 s。`FL_H` 76 |
| 件数・ABI | `node tests/provider_check.mjs` (wasm) | PASS (functions 435・implemented 76・unimplemented 359・mcp_static 60)、0.30 s |
| mock と C の差分 | `node tests/channels_diff.mjs` | PASS (calls 98・diffs 0)、0.04 s |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0)、1.33 s |

- 作業用ビルド (`dist/`・`work/` は gitignore): `build_cpython_wasm.sh` 3 分 41 秒 (4 core)、`FLPY_SKIP_TABLE=1 build_flpy.sh` 5.2 s。load average は測定時 1.4〜1.5。
- コード差分: `git diff fde09f94 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (測定後の commit は本 REPORT のみ)。

## PY-64 (#2033): 分岐先 6 件の読む値・書く値・`[rbp+0x5b8]` 式 (実測・逆アセンブル)

親: #1911 (PY-53)。前段: #1982 (PY-60)。既知類型との関係: 該当なし (逆アセンブルの読解のみ)。

## 結論 (部分達成)

- 分岐先 4 件 (0x104caae・0x104c2a6・0x104c64f・0x104c919) は、共通後半 0x104caae の手前の読む値・書く値・`[rbp+0x5b8]` の式を VA つきで確定。
- 残り 2 件 (0x1047497・0x104aa87) は `[rbp+0x5b8]` 書込み箇所 (55 件・15 件) の列挙まで。式は未読 (PY-88 に移管)。
- 検算: jcc/jmp 614 辺の制御フロー照合 (objdump 対 capstone) は mismatch 0。式の別算法照合は未実施。

## 測定

- 素材を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で `work/py64/` に展開 (2.3 秒)。
- `analysis/py53_dispatch.py` → 4,664 命令。`analysis/py60_objdump_check.py` → 614 辺 一致 614・不一致 0 (exit 0)。
- `analysis/py64_branch_regions.py work/py53/fn.txt` → 固有部分の命令数と書込み 76 件 (0x1047497 55・0x104aa87 15・他 3 件は各 2)。

## 分岐先ごとの式 (入口 `[rbp+0x5b8]` = edx、0x1046d6b)

- 共通: r8d は `[rbp+0x5c0]`。F = `P.0x3b8 + rint(K · [rbp+0x5b8] · (P.0x3bc − P.0x3b8))`。`rint` は `call 0x40c660` (`cvtsd2si`・最近接偶数)、K = 2^-30 (VA 0x104ccd8)。F は r8d&0x20 のときだけ適用する。
- 0x104c2a6 (ecx=0x40000000): P = `*(*(0x15e2eb8)+0x9e0)`。(a) F (0x104c311)。(b) r8d&1=0 かつ r8d&2≠0 で `[rbp+0x5b8] = dword[*(0x15e36d8)]` (0x104c3f0)。r8d&1 では `dword[*(0x15e36d8)] = [rbp+0x5b8]` (0x104c335) と `dword[*(0x15e2110)] = [rbp+0x2cc]` (0x104c3ca) を書く。
- 0x104c64f (ecx=0x40000002): P = `*(*(0x15e2eb8)+0xb28)`。(a) F (0x104c6ba)。(b) r8d&1=0 かつ r8d&2≠0 で `[rbp+0x5b8] = dword[*(0x15e2c50)]` (0x104c769)。r8d&1 では `dword[*(0x15e2c50)] = [rbp+0x5b8]` (0x104c6ea) と `[*(0x15e2218)]` の各要素の `vtbl[0x128]` 呼出し。
- 0x104c919 (ecx=0x40000005): P = `*(*(0x15e2eb8)+0x778)`。(a) F (0x104c984)。(b) r8d&1=0 または `byte[0x15e3500]≠0` で r8d&2≠0 なら `[rbp+0x5b8] = dword[*(0x15e28c8)]` (0x104c9e6)。r8d&1 かつ `byte[0x15e3500]=0` かつ `byte[*(0x15e2900)+0x3c]=0` なら `dword[*(0x15e28c8)] = [rbp+0x5b8]` (0x104c9c0)。
- 0x104caae (ecx の既定値): `[rbp+0x5b8]` は書かない。共通後半で `[rbp+0x5b8]` を読んで `call 0x12df2a0` の引数 (r9d) にする (条件: `[rbp+0x52f]≠0` かつ r8d&0x40)。
- 共通の出口: `[rbp+0x584] = [rbp+0x5b8]` (0x104cc6b)。早期 exit は `[rbp+0x584] = -1` のまま 0x104cc72 へ飛ぶ。

## 未了 (2 件)

| 分岐先 | 入る ecx | 固有命令数 | `[rbp+0x5b8]` 書込み | -1 exit への分岐元 |
|---|---|---|---|---|
| 0x1047497 | [0, 0x10000000) | 2556 | 55 件 | 0x10474b9・0x104846a・0x104847b・0x10495f6・0x1049621・0x104a7ba・0x104a7d0 |
| 0x104aa87 | [0x80000000, 0xf0000000) と [0x40000006, 0xf0000000) | 1284 | 15 件 | 0x104a7ba・0x104a7d0 |

書込み箇所の VA と直前命令は `analysis/py64_branch_regions.py` の出力が正本。各式の読む値・書く値は未読。

## 受入条件・未解決

- (1) 6 件の読む値・書く値・式の VA つき確定: 部分達成 (4/6)。(2) mismatch 0 の検算: 部分達成 (制御フローのみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1047497 (55 件) と 0x104aa87 (15 件) の書込み式・読む値・書く値 | ecx ∈ [0, 0x10000000) と [0x80000000, 0xf0000000) 経路の戻り値 | PY-88 (子) |
| 4 件の式の別算法照合 | 式の確定の検算 | PY-88 (子) |
