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
  `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C tools/python/work/py41 extracted/block00031_PE.bin` で `work/` に展開 (gitignore)。展開 2.5 秒 (実測)。
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

- 測定: `tools/python/work/py41/extracted/block00031_PE.bin` (`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で展開・2.8 秒)。逆アセンブルは `analysis/py41_disasm.py` (capstone・pefile)。
- 呼出し元 `0x10473a5` (`call 0x1046a30`) を確認。直前の引数設定は `ecx = [rbp+0x5b0]`・`edx = 0`・`r8d = 2`。戻り値は `[rbp+0x580]` に格納 (0x10473aa)。呼出し元 `0x10473a5` は `.pdata` (RUNTIME_FUNCTION) で `0x1046a30`〜`0x104cccb` の関数に含まれ、呼出し先 `0x1046a30` と同一関数内 (自己呼出し)。`0x1046edf` は関数の先頭ではなく、`0x1046a30` 関数内の分岐先。
- 呼出しに至る経路: `0x104734a`〜`0x1047394` の走査ループ (`0x12df530` の戻り値判定) を抜けた後。ループ内で `0x1047382` の一致が見つかった場合は `je 0x1047424` で `0x1046a30` を呼ばずに抜ける。
- **未確認 (#1828 (PY-49) に移管)**: 呼出し元の全件。全 `.text` を走査する補助スクリプトの初回実行は 0 件を返したが、スクリプト側の誤りであり、呼出し元 0 件とは判定しない。
- **未確認 (#1828 (PY-49) に移管)**: `0x1046a30` の本体 (0x1046edf 以降の分岐先)、`ecx=0x40000001` の意味、`r8d=2` の意味。
- **未着手 (#1829 (PY-50) に移管)**: `chan` のフィールド・status 写像・`finish` のエラー文字列。

受入条件の達成状況 (範囲縮小後の受入条件を基準): **達成** (呼出し元 1 件・引数設定 `ecx`/`edx`/`r8d` の確定)。**子 issue へ移管**: `0x1046a30` の本体・引数の意味・呼出し元の全件 (#1828 (PY-49))、`chan` と status・エラー文字列 (#1829 (PY-50))、C 実装・mock 差分・all_tools 48/48 (#1828・#1829 の確定後)。

## PY-49 (#1828): 0x1046a30 の呼出し元 全件 と 戻り値 (実測)

- 呼出し元: `.text` 全体の E8 rel32 を走査 (`analysis/py49_callers.py`)。**160 件**。全件の一覧 (call 元 VA・ecx/edx/r8d の直前代入式) は `analysis/py49_callers_0x1046a30.tsv`。引数式は呼出し直前 12 命令の直線区間からの推定で、代入が分岐をまたぐ箇所は拾えない (表の `-` 4 件は未特定)。
- 引数の集計: `r8d=2` が 27 件 (getSwing 0xd5dbf0 を含む)。`ecx=0x40000001` が 3 件 (0xd5dc01・0xd5dcb5・0xfde5e7)。呼出し元 0x10473a5 は同関数内の自己呼出し (`ecx=[rbp+0x5b0]`・`edx=0`・`r8d=2`)。
- getSwing (0xd5dbf0) の直前: `mov ecx,0x40000001` (0xd5dbf4)・`xor edx,edx`・`mov r8d,2` → `call 0x1046a30` (0xd5dc01)。戻り値 `eax` は `cvtsi2sd` で使われる。
- **戻り値 (確定)**: 関数末尾の出口 `0x104ccba` は `[rbp+0x584]` を返す (`ret` は 0x104ccca の 1 箇所のみ)。`[rbp+0x584]` は入口で -1 (0x1046d79)、通常経路で `0x104cc6b` の `mov [rbp+0x584],eax` (`eax=[rbp+0x5b8]`) により置き換わる。`[rbp+0x5b8]` は入口で `edx` を受け (0x1046d6b)、途中の分岐で書き換えられる。早期 exit (0x1046d8d・0x10471f9・0x10474b9 の各 `jne`/`jmp`/`jge` → 0x104cc72) は -1 のまま返る。
- **未確定 (子 issue に移管)**: 関数本体の全分岐の意味 (0x1046edf 以降・`ecx` 0x40000001 の経路 0x104c4af の詳細)、`r8d` ビットの意味、`[rbp+0x5b8]` の各書換えの意味。

## PY-52 (#1875): `ecx=0x40000001`・`edx=0`・`r8d=2` 経路の確定 (実測・逆アセンブル)

- 測定: `analysis/py41_disasm.py` で `0x1046a30`〜`0x104ccca` (関数末尾の ret) を逆アセンブル (4,664 命令)。`ecx`/`edx`/`r8d` の引数は `[rbp+0x5b0]`・`[rbp+0x5b8]`・`[rbp+0x5c0]` に退避される (0x1046d65〜0x1046d71)。
- RIP 相対の参照先 VA は、命令長を含めて `ins.address + ins.size + disp` で解決した (手計算は 7 バイト命令の長さを誤ったため採用しない)。
- 対象は getSwing (0xd5dc01) と呼出し元 0x10473a5 のうち `ecx=0x40000001` の経路。getSwing の引数は `ecx=0x40000001`・`edx=0`・`r8d=2`。

### 経路 (r8d=2 で確定する部分)

| VA | 命令 | 判定 (r8d=2, ecx=0x40000001) |
|---|---|---|
| 0x1046d79 | `[rbp+0x584] = -1` | 戻り値の初期値 |
| 0x1046d8d | `[flag@0x15e1890]` が非 0 なら 0x104cc72 へ (戻り値 -1) | **実行時依存** (フラグの値は静的に決まらない) |
| 0x1046dc4 | `test r8d, 0x8a1` → 0 なら 0x1046e05 | 2 & 0x8a1 = 0 → 0x1046e05 へ (確定) |
| 0x1046e00 | `call 0xf82c20` | **通らない** (0x1046dc4 の `test r8d, 0x8a1` が 0 で 0x1046e05 へ飛ぶため) |
| 0x1046e23 | `test r8d, 0x240` → 0 なら 0x1047424 | 2 & 0x240 = 0 → **0x1047424 へ (確定)**。0x1046e2e〜0x1046edf (`ecx` の範囲判定・0x1046edf 以降の分岐) は**通らない** |
| 0x1047436 | `ecx == 0x40000001` なら 0x104c4af | 確定 |
| 0x104c4c7 / 0x104c520 | `test r8d, 0x20` / `test r8d, 1` | いずれも 0 → 分岐先へ (確定) |
| 0x104c557 | `test r8d, 2` が非 0 → 0x104c564 へ fall-through | 確定 |
| 0x104c564 | `eax = dword [*(0x15e3290)]`・`[rbp+0x5b8] = eax` | **edx=0 は捨てられ、この読み値が以降の戻り値になる** |
| 0x104c573〜0x104c5a6 | `test r8d, 0x10` / `test r8d, 4` | いずれも 0 → 0x104caae へ |
| 0x104caae〜0x104cb0a | `[rbp+0x52f]` (0x1046e05 で 0 に設定済み)・`test r8d, 0x100` | 0 → 0x104cc2e へ |
| 0x104cc34 | `test r8d, 0x80` が 0 → 0x104cc65 | 確定 |
| 0x104cc65〜0x104cc6b | `eax = [rbp+0x5b8]`・`[rbp+0x584] = eax` | 戻り値確定 |
| 0x104ccba | `eax = [rbp+0x584]`・`ret` | 戻り値 |

- **戻り値 (この経路)**: `dword [*(0x15e3290)]` (VA 0x15e3290 の qword を指すポインタの先の 32bit 値)。getSwing の `cvtsi2sd` はこの値を使う。
- **0x15e3290 の書込み元は未特定**: PE の `.data` 生データでの初期値は qword `0x0000000001 96ec34` で、実行時に書き換わる前提。書込み元 (初期化経路) の調査は子 issue に移管。よって getSwing の戻り値の数値は、現時点では静的に確定しない。
- `ecx=0x40000001` の意味: 0x1047436 で専用経路 (0x104c4af) に入る値。0x104c4af の経路は 0x104c5a6 等の条件で分岐するが、各ブロックの意味 (何の値を読み何を描画するか) は未確定。`r8d=2` の意味は未確定 (0x104c557 の `test r8d, 2` で 0x104c564 の読みを選ぶ分岐として確認したのみ)。

### 呼出し元 0x10473a5 (ecx ≠ 0x40000001 の経路)

- 呼出し元の `ecx = [rbp+0x5b0]` は `0x40000001` とは限らない。`ecx ≠ 0x40000001` の経路 (0x1047424 の後半・0x104746a〜0x104aa87・0x104c2a6 など) は本 run では未読。残りは子 issue に移管。

### 受入条件の達成状況

- `0x1046a30` の本体の分岐構造: **部分達成**。`ecx=0x40000001`・`r8d=2` の経路は確定 (上表)。他の `ecx`・`r8d` の組は未確定。
- 戻り値の経路別記録: **部分達成**。この経路の戻り値式は確定。値そのものは 0x15e3290 の書込み元に依存して未確定。
- 未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ecx ≠ 0x40000001` の経路 (0x1047424 後半〜0x104c2a6 など) と `r8d` の残りのビット (0x8a1・0x10000・0x2000・0x4000・0x1000・0x2800・0x200・0x40・0x80・0x100・0x800) の意味 | 呼出し元 160 件の大半の戻り値が決まらない | #1911 (PY-53) |
| 0x15e3290 (戻り値の読み先) の書込み元と初期化 | getSwing の数値が決まらない | #1912 (PY-54) |

## PY-53 (#1911): ecx 分岐表 (0x104742a〜0x104745f) の確定 (実測・逆アセンブル)

- 測定: `analysis/py53_dispatch.py work/py41/extracted/block00031_PE.bin work/py53` (0.1 秒・capstone 5.0.7・pefile)。関数 0x1046a30〜0x104ccca を 4,664 命令に逆アセンブル (PY-52 と同数)。素材 `fl-win64` は `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で展開 (2.8 秒)。
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
- 戻り値 `[rbp+0x584]` の書込みは 3 箇所のみ: 0x1046d79 (`= -1`)・0x104cc6b (`= eax`、直前 0x104cc65 の `eax = [rbp+0x5b8]`)・0x104ccba (読出し、ret 値)。
- `[rbp+0x5b8]` の書込みは **74 箇所** (`mov dword ptr [rbp+0x5b8], reg`)。個々の式は未確定 (子 issue)。
- 出口の入辺 (実測):
  - 0x104cc65 (`[rbp+0x5b8]` を読む): 0x104cc39 の `je` (r8d&0x80 = 0) と、0x104cc60 からの fall-through。
  - 0x104cc2e: 0x104cb0f の `je` (r8d&0x100 = 0) と、0x104cc29 からの fall-through。
  - 0x104cc72: 早期 exit の jcc/jmp 9 件 (0x1046d8d・0x10471f9・0x10474b9・0x104846a・0x104847b・0x10495f6・0x1049621・0x104a7ba・0x104a7d0) と、**通常経路の fall-through** (0x104cc6b → 0x104cc71 nop → 0x104cc72)。
  - 0x104cb04: 0x104cab5・0x104cac2 の `je` 2 件。
- **訂正**: 0x104cc72 は「-1 専用の早期 exit」ではなく、通常経路と共有する後始末ブロック。戻り値が -1 になるのは、早期 exit の経路で `[rbp+0x584]` が書かれないため。
- 受入条件の状況: 制御フローの照合 (検算 mismatch 0) と戻り値の書込み構造は**達成**。分岐先本体の値の式・`r8d` 各ビットの意味・`[rbp+0x5b8]` の各書込みの式は**未達** (子 issue へ移管)。

