# sampler REPORT 付録: Fruity Slicer 2 殻と engine の結線 (#540 受入条件 4)

本書は `REPORT.md` §5 の付録。 記録している作業は次のとおり: 素材 `fl-win64` (block23663 殻 / block23664 engine、`$FL_WIN64_DIR/extracted`) の逆アセンブル (pefile + capstone)、素材展開 (§7)、`sampler_engines.sh` の 900 s 打ち切り実行 (exit 124、§7)。 結果の出典と HEAD は §7 に分けて書く。

## 1. 結論

- 殻 (block 23663、ImageBase 0x400000) は `engine_x64.dll` を名前で読み、`DispatchToEngine` を名前で引く。 殻から `DispatchToEngine` を呼ぶ箇所は 9 件 (§4)。
- 受入条件 4 は **部分達成**。 ロード経路・export 取得・呼出し箇所 9 件・各 selector 値は確定。 `DispatchToEngine` の引数規約 (`r8`/`r9` の意味・戻り値) は未解析。
- 受入条件 1・2 は `PLUG_NO_STATIC_DETECT=0` 相当の経路 (RetDec argv が `5880a9f6` と同じ) では PASS (§7): `sampler_engines.sh` exit 0・`PASS 2/2`、`sampler_e2e.sh` exit 0・`PASS 7/7`。 ただし表の測定 commit は未確定 (`5880a9f6` / `cb3a89a6`) のため、現 HEAD では未確認 (#540)。 既定経路 (HEAD、`PLUG_NO_STATIC_DETECT` 未設定 = 1) では `sampler_engines.sh` のみ PASS 2/2 を実測。 `sampler_e2e.sh` の既定経路は未測定 (起票先: #540)。 既定経路での受入条件 1・2 の達成は、`sampler_e2e.sh` 既定経路の実測が揃うまで未確認。

## 2. 殻側の経路 (block 23663)

| 項目 | VA | 内容 |
|---|--:|---|
| export `CreatePlugInstance` | 0x842880 | |
| export `DecodeAudioFile` / `FinishAudioFile` | 0x842950 / 0x842fc0 | |
| 結線ラッパ | 0x843790 | 文字列 `engine_x64.dll` (UTF-16, file offset 0x442c94) を組み立て、0x83e200 で読み込み、0x421d60 で `DispatchToEngine` (UTF-16 0x442cb2) を引く。 結果を `obj+0x1c0` に保存 |
| ロード関数 | 0x83e200 | 名前から DLL を開く経路。 殻の IAT には `LoadLibraryW` / `LoadLibraryA` / `LoadLibraryExW` / `GetProcAddress` が import されている (kernel32 155 件の全件走査で確認)。 0x83e200 がそれを直接呼ぶかは未確認 |
| 名前解決 | 0x421d60 → 0x421d50 | `DispatchToEngine` の取得。 `GetProcAddress` 経由と推定 (呼出し先の IAT 照合は未実施) |

- 結線ラッパ 0x843790 が `lea r8, [rip+0xda]` (0x8437b3) と `lea rdx, [rip+0xa9]` (0x843802) で文字列を直接参照する。 参照先は `engine_x64.dll` (VA 0x843894、file off 0x442c94) と `DispatchToEngine` (VA 0x8438b2、file off 0x442cb2)。 根拠はラッパ 0x843790 の逆アセンブル (capstone、0x843790〜0x84386a)。 `.text` 全体の線形走査では同じ参照を拾えなかったため、走査結果は根拠にしない。
- `[reg+0x1c0]` を `call` する箇所は、殻 `.text` の `ff /2` (mod=10, disp32=0x1c0) 候補 24 件を逆アセンブルして確定 (capstone、`call` 命令の終端が候補の終端と一致するもののみ)。 件数は REPORT 外の再走査でも 24 件で一致。
- 24 件の内訳 (基底・分類は下表 §2a)。 `obj` は `DispatchToEngine` の受け手 (殻の `[obj+0x1c0]`) と同じ基底を指す。 engine 呼出しと確定できたのは `[X+0x1b8]` を第 1 引数に、`edx = selector` を直前に置く 9 件 (§4)。 残り 15 件は vtable の `+0x1c0` スロット (`mov rbx,[obj]` の直後に `call [rbx+0x1c0]`) か、`rbx`/`rsi`/`rdi` に別オブジェクトを取る仮想呼出しで、`DispatchToEngine` ではない。

### 2a. 24 件の基底と分類

| 呼出し箇所 | 基底 | 分類 |
|--|--|--|
| 0x589137 | rbx (`mov rbx,[rax]`) | vtable 呼出し (ラッパ外) |
| 0x590c92 | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x591a16 | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x594b6b | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x594c0c | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x59583e | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x597510 | rdi (`mov rdi,[rax]`) | vtable 呼出し |
| 0x5a7597 | rbx (`mov rbx,[rax]`) | vtable 呼出し |
| 0x657aed | rsi (`mov rsi,[rax]`) | vtable 呼出し |
| 0x6ea474 | rbx (`mov rbx,[rcx]`) | vtable 呼出し |
| 0x6ea494 | rbx (`mov rbx,[rcx]`、関数 0x6ea480 の末尾) | vtable 呼出し |
| 0x73b356 | rbx (`mov rbx,[rbx]`) | vtable 呼出し |
| 0x73b386 | rbx (`mov rbx,[rbx]`) | vtable 呼出し |
| 0x73b644 | rbx (`mov rbx,[rbx]`) | vtable 呼出し |
| 0x778469 | rbx (`mov rbx,rcx` = this、`cmp [rbx+0x1c0],0` の直後) | 自オブジェクトの `+0x1c0` 関数ポインタ。 `rdx` は selector ではなくポインタ (`lea rdx,[rbp+0x28]`) |
| 0x8439d1 | rbx (`mov rbx,[rbp+0x30]` = obj) | **obj** の `+0x1c0`。 `rcx = [obj+0x1b8]` (engine)、`edx = 0xa` (§4 の selector 10) |
| 0x846ab0 | rax (`mov rax,rcx`、rcx = obj) | **obj**。 `edx = 2` (§4) |
| 0x846af4 | rax (同上) | **obj**。 `edx = 4` (§4) |
| 0x846b3c | rax (同上) | **obj**。 `edx = 3` (§4) |
| 0x846b8f | rax (同上) | **obj**。 `edx = 5` (§4) |
| 0x847220 | rax (`mov rax,[rbp+0x40]`、関数引数由来) | **obj**。 `edx = 0xb` (§4) |
| 0x8473c8 | rax (`mov rax,[rbp+0x38]` = obj) | **obj**。 `edx = 0xd` (§4) |
| 0x8474ad | rax (`mov rax,[rbp+0x38]` = obj) | **obj**。 `edx = 0xe` (§4) |
| 0x847547 | rax (`mov rax,rcx`、rcx = obj) | **obj**。 `edx = 0xc` (§4) |

- 「obj」の 9 件は全て `rcx = [base+0x1b8]` (engine) を第 1 引数にしている。 `rbx`/`rax` の由来は、呼出し直前の代入 (`mov rax,rcx` または `mov rax,[rbp+0x..]` で obj を受け、`[obj+0x1c0]` を読む) で確定。
- 0x8439d1 の `rbx` は `[rbp+0x30]` (関数 0x843930 の先頭で `mov [rbp+0x30],rcx`、rcx = 関数の第 1 引数 = obj)。 他 8 件 (`rax`) と基底レジスタは違うが、同じ obj を指す。
- 0x847220 の `rax` は `mov rax,[rbp+0x40]` (関数 0x8471d0 の `mov [rbp+0x40],rcx`、rcx = obj)。 関数先頭の確認で obj と判定。

## 3. engine 側 `DispatchToEngine` (block 23664、VA 0x180147bc0)

- 関数は `rdx` を選択子として `lea eax, [rdx-2]; cmp eax, 0xc` の境界を持つ (有効な選択子は 2..14)。 ジャンプテーブル (base 0x18014831c) の 13 エントリを読んだ結果:

| 選択子 (rdx) | case VA | 先頭命令 (要約) |
|--:|--:|---|
| 2 | 0x180147d38 | `[rcx+0x1b0]` を取り `call [rip+...]` (外部呼出し) |
| 3 | 0x180148082 | `[rcx+0x1b0]` を取り `call [rip+...]`、`r12-0x3e8` で分岐 |
| 4 | 0x180147f6d | `r12d` (0x0e 以下) で別テーブル 0x14838c を引く |
| 5 | 0x180148183 | `r9-0x3e8` で分岐、`xmm0` を 0 初期化 |
| 6, 7, 8, 9 | 0x180147d02 | `xor eax, eax` して返す (no-op) |
| 10 | 0x180148270 | `[rcx]` の vtable `+0xd0` を呼ぶ |
| 11 | 0x180147d28 | `[r8]=0x80` を書き、`rbx+0x3468` を返す |
| 12 | 0x180147cd2 | `[rcx+0x1b0]` を取り `call [rip+...]` |
| 13 | 0x180147c2b | `[rbx+0x30]` の長さ (`>=0x10`) で分岐 |
| 14 | 0x180147c42 | `[rcx]` の vtable `+0xd0` を呼ぶ |

- 選択子 6〜9 は同一 case (no-op)。 engine の `CreatePlugInstance` (VA 0x180147980) は `call 0x1801cc570` (サイズ 0x12310 の確保) の後、0x180145560 へ tail-jump する。
- 殻の selector 値 (rdx) は未解析。 case 表だけでは `DispatchToEngine` の引数規約 (`rcx` の意味・`r8`/`r9` の意味) は確定しない。

## 4. 殻の呼出し箇所と selector (受入条件 4 の残り・本 HEAD で確定)

測定: `disasm_range.py` (capstone) で殻 23663 の `.text` を逆アセンブル。

- 結線ラッパ 0x843790: `[obj+0x1a8]` に engine ローダ 0x83e200 の戻り値 (engine オブジェクト) を保存し、`[obj+0x1b0]` 系の名前引数で `DispatchToEngine` 0x421d60 を引いて `[obj+0x1c0]` に保存する。 その後 `[obj+0x1a8]` の vtable `+8` を 2 回呼ぶ (0x843831, 0x843858)。
- 殻が `DispatchToEngine` を呼ぶ形は `call qword ptr [reg+0x1c0]` で、`rcx = [obj+0x1b8]` (engine オブジェクト)、`rdx = selector` の直接呼出し。 この形の呼出しは 9 箇所 (以下、selector は `mov edx, imm` または `mov r9d, imm` → `mov edx, r9d` の直前代入から読んだ値)。

| 殻の呼出し箇所 | selector (rdx) | 引数の意味 (逆アセンブル上) |
|--|--:|---|
| 0x846ab0 (関数 0x846a80) | 2 | 元の `rdx` (ラッパの第 2 引数) を `mov r11, rdx`→`mov r9, r11` で DispatchToEngine の第 4 引数 r9 に移す。 `xmm0` = 浮動小数点引数 |
| 0x846af4 (0x846ac0) | 4 | 第 5 引数 `[rsp+0x20]` = 0 |
| 0x846b3c (0x846b10) | 3 | `xmm3` を第 5 引数 |
| 0x846b8f (0x846b50) | 5 | 第 5 引数に `&local` (out ポインタ) |
| 0x8439d1 (0x8439a0) | 10 (0xa) | `r8 = &local` (out)、`xmm0` = 浮動小数点引数 |
| 0x847220 (0x8471f0) | 11 (0xb) | `r8 = &local` (out) |
| 0x8473c8 (0x847380) | 13 (0xd) | 戻り値 `rax` を直後に 0x41b670 の第 2 引数へ渡す (戻り値を使う) |
| 0x8474ad (0x847380 内) | 14 (0xe) | `r8 = &[rbp+0x57]` (直前の 0x55d0a0 で 0x200 バイトを埋めた領域を渡す) |
| 0x847547 (0x847510) | 12 (0xc) | `r10 = edx` 符号拡張、`r11 = r8d` 符号拡張 (範囲 2 引数) |

- 9 件の selector は engine 側 `DispatchToEngine` の case 表 (§3、有効 2..14) の内側に収まる。 case 6〜9 (no-op) は殻からは使われない。
- 残りの 15 件 (§2a の vtable 呼出し 14 件 + 0x778469) は `DispatchToEngine` とは別の仮想メソッド / 自オブジェクトの関数ポインタで、本 HEAD の範囲では DispatchToEngine と結び付けない。
- 9 件が完全である根拠: 殻 `.text` の `ff /2` disp32=0x1c0 候補を全件 (24 件) 逆アセンブルし、基底レジスタと引数の由来を §2a で確認した。 走査範囲は殻の実行可能セクション全体、判定基準は「第 1 引数 `rcx` が `[X+0x1b8]` (engine)、`edx` が即値 selector」。 0x778469 は `rcx = [rbx+0x1c8]`・`rdx = &local` で、selector 形ではないため除外。 残り 14 件は vtable の `+0x1c0` で、`rcx` が vtable 元オブジェクトのため除外。
- 引数規約の残り: 戻り値は殻側で `rax` を読む箇所がある (0x8473c8) ため有効な結果を返す。 selector ごとの `r8`/`r9` の完全な意味は engine case ごとの読解が必要で、本 HEAD では未完 (次の課題)。

## 5. 受入条件 3・5 の測定

### 3. RetDec の C バックエンド省略 (前 run #810 の引用)

| 方式 | 対象 | 結果 (実測) |
|---|---|---|
| 既定 `lift_ranges.sh` 直行 (前 run #810 の実測、本 HEAD では未再測定) | 23664 | 614 s 時点で RSS 8.15 GiB、"out of memory; trying to recover" 3 回。 未完で手動停止。 run id 未確認 |
| `--backend-no-opts` (前 run #810 の実測、本 HEAD では未再測定) | 23664 | **exit 0、441 s、Maximum RSS 3.52 GB**。 `.ll` 75 MB・`.c` 39.6 MB 出力まで完走。 run id 未確認 |

- 結論: 前 run の値では `--backend-no-opts` で RSS が 8.15 GiB から下がり、C 出力まで完走した (上表)。 共有 `lift_ranges.sh` は変更せず、既定経路は `lift_from_ll.sh` のまま (判断: 変更しない)。
- 理由: `lift_from_ll.sh` は C 出力を使わず `.ll` の後段だけ使う。 `.ll` 出力までの秒数は本書で未記録のため、既定経路との時間比較は行わない。
- 本 HEAD (main dc7c11df・fl-win64 展開 `$RUNNER_TEMP/fl-win64`、23664 の ranges 5,160 関数) での測定。 **n=1 の単発測定**。 環境は 4 vCPU・RAM 15 GiB (`nproc`・`free -g`)。 run id・load average・並列数は未記録 (レビュー run `38459725194` (head 3f80a201、`pull_request` の review job) のログと #540 のコメントに該当出力が無いことを確認済み)。 min–max レンジは未取得。 したがって下表の秒数・RSS は **出所不明の参考値** として扱い、判断の根拠は exit 137・C 出力未完・完走の有無という観測事実に限る:

| 方式 | 結果 (n=1 実測) |
|---|---|
| `--no-memory-limit` (既定 `--backend-*` のまま) | exit 137、`--timeout 1100` で打ち切り (経過 18:20.34)、Maximum RSS 11.19 GB。 "out of memory" 0 件。 "emission of the target code [c]" に 922.76 s で入り、C 出力の途中で打ち切り。 C 出力は未完 |
| `--backend-no-opts` | exit 0、8:18.90 (498.90 s)、Maximum RSS 3.52 GB。 `.ll` 75 MB・`.c` 39.6 MB 出力まで完走 |

- 結論 (受入条件 3・n=1 の範囲): 上表の n=1 測定では `--no-memory-limit` は C 出力を完了できなかった。 `--backend-no-opts` は完走した。 共有 `lift_ranges.sh` には入れない (判断: 変更しない)。 RetDec の既定経路は本 HEAD でも `lift_from_ll.sh` を使う。 n≥3 の min–max は未取得のため、受入条件 3 は「判断まで完了 (測定は n=1、再測定は未実施)」。
- 鮮度 (WORKFLOW §6): 測定 commit は dc7c11df。 検証 HEAD 77b85cec までの sampler コード差分は 0 行。 出力:

  ```
  $ git diff dc7c11df 77b85cec -- tools/plugins/sampler ':!*.md' | wc -l
  0
  $ git diff --stat dc7c11df 77b85cec -- tools/plugins/sampler
   tools/plugins/sampler/REPORT_ENGINE_LINK.md | 25 ++++++++++++++++++++++---
   1 file changed, 22 insertions(+), 3 deletions(-)
  ```

  差分は本 REPORT (md) のみ。 本 REPORT の更新 commit も md のみのため、dc7c11df の測定結果は現 HEAD でも同じ sampler コードに対するものとして扱う。 再測定は要求しない。

### 5. VEX helper の CPUID 分岐 (前 run の引用、main f0d65f32。本 HEAD では未再測定)

`vex_guard.py` の数値 (前 run の記録の引用。本 HEAD の capstone 不在のため再現していない):

| block | pdata | VEX 関数 | cpuid 関数 | xgetbv 関数 | VEX 関数のうち caller 深さ 3 に cpuid/xgetbv を持つもの |
|--:|--:|--:|--:|--:|--:|
| 23664 | 5,160 | 229 | 29 | 4 | 0 |
| 23677 | 2,355 | 94 | 28 | 3 | 0 |

- 結論: `vex_guard.py` の深さ 3 の直接 call 鎖 (即値の `call`/`jmp` のみ追跡) では、VEX 関数の caller に cpuid 関数が届かなかった。間接 call (`call [rip+...]`・関数ポインタ・vtable) は未追跡のため、「静的に不成立」とは言わない。SSE 固定の可否は未確定で、動的な分岐の実測は未実施。

## 6. 未解決 (起票先付き)

| 未解決 | 起票先 |
|---|---|
| 殻の selector 9 件の `r8`/`r9` 引数の完全な意味・戻り値の型 (§8 で 7 件の意味を確定。sel 2・4 の内側 id の値と、sel 10 の `r8` 入力バッファの書込み元は未確定) | 本 #540 (継続) |
| `--no-memory-limit` の n=1 測定の扱い (§5 参照) | 本 #540 (継続、受入条件 3 は判断まで完了) |
| VEX helper の SSE 固定の動的確認 (直接 call 鎖では guard 無し。間接 call は未追跡) | #527 にコメント予定 (既存・重複起票せず) |

## 7. 検証 (測定 commit 5880a9f6)

鮮度の証跡 (WORKFLOW §6):

- 測定 commit: **`5880a9f6`** (下表の実測はこの commit のコードで行った。 `6769c2c7` の時点で記録された系列)。
- 解析 HEAD (§9 の逆アセンブル・参照走査): `ba4babca`。 `git diff --stat ba4babca HEAD -- tools/plugins/sampler ':!*.md'` は空 (0 行)。
- 測定 commit `5880a9f6` から HEAD までの測定経路の差分 (`git diff --stat 5880a9f6 HEAD -- tools/plugins/lift tools/plugins/sampler ':!*.md'` = 16 files / 1072 insertions / 30 deletions。 既定経路の測定 HEAD `f73bcab0` からの測定経路の差分は 0 行 (`git diff f73bcab0 HEAD -- tools/plugins/lift tools/plugins/sampler ':!*.md'`)。 内訳の要点):
  - `tools/plugins/lift/lift_ranges.sh` (31 行追加・2 行削除) は測定経路に入る (上の訂正参照)。 RetDec 呼出の既定が変わるため、表は HEAD の既定では未測定 (`sampler_engines.sh` の既定経路は下の行で実測済み)。
  - `tools/plugins/sampler/` の 6 ファイルは別経路 (下の訂正参照)。 sampler 側の stat:

```
 closure_unreached.py | 65 +++++++++++++++++----
 f80_split.py         | 67 ++++++++++++++++++++++
 lea_lift.sh          | 23 ++++----
 nc2_imm_synth.py     | 92 ++++++++++++++++++++++++++++++
 unr_nega.sh          | 10 +++-
 x87_check.py         | 29 ++++++++++
 6 files changed, 258 insertions(+), 28 deletions(-)
```

  全文の patch は 250 行上限 (`docs/DOC_MAP.md` §1) を超えるため載せない。 上の stat と同じ範囲で `git diff 5880a9f6 HEAD -- tools/plugins/sampler ':!*.md'` を実行すれば再現できる。

- **訂正 (測定経路に `lift/lift_ranges.sh` の差分が入る)**: `sampler_engines.sh` (受入条件 1) は `engine_lift.sh` → `lift_from_ll.sh` (`lift_ranges.sh` の RetDec 行を切り出して実行) 経由、`sampler_e2e.sh` (受入条件 2) は `lift/batch_lift.sh` → `lift_ranges.sh` 経由で RetDec を呼ぶ。 この `lift_ranges.sh` は `5880a9f6`..HEAD で変わっている (`git diff 5880a9f6 HEAD -- tools/plugins/lift/lift_ranges.sh`: 31 行追加・2 行削除)。
- 変更の要点: `5880a9f6` の RetDec 呼出は `--select-decode-only --timeout` のみで、静的検出の無効化を渡さない。 `8ea7a78b` で opt-in の `${PLUG_NO_STATIC_DETECT:+--disable-static-code-detection}` が入り、HEAD (`8a7f32ba`) で既定 1 になった。
- argv の実測 (`lift_ranges.sh` を実行し、`/opt/retdec/bin/retdec-decompiler` を記録用の偽実行ファイルに差し替えて、渡った引数を比べた。 RetDec 本体は走らせていない):
  - `5880a9f6` (env 未設定): `--select-decode-only --timeout 60` (静的検出の無効化なし)
  - HEAD `8a7f32ba` (env 未設定): `--select-decode-only --disable-static-code-detection --timeout 60`
  - HEAD `8a7f32ba` (`PLUG_NO_STATIC_DETECT=0`): `--select-decode-only --timeout 60` (`5880a9f6` と同一)
- よって表の実測 (`5880a9f6`) は、HEAD で `PLUG_NO_STATIC_DETECT=0` を立てた経路と RetDec argv が一致する。 HEAD の既定 (静的検出なし) での `sampler_engines.sh` は実測済み (下の「既定経路」行)、`sampler_e2e.sh` の既定経路は未測定。
- 上の 6 ファイル (`closure_unreached.py`・`f80_split.py`・`lea_lift.sh`・`nc2_imm_synth.py`・`unr_nega.sh`・`x87_check.py`) を呼ぶのは `lea_e2e.sh` / `unr_e2e.sh` / `unr_nega.sh` / `unr_lift.sh` (別経路) だけ。 この点はレビュー側の `git grep` 確認と一致する。
- **既定経路 (HEAD `PLUG_NO_STATIC_DETECT` 未設定 = 1) の実測**: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` で RetDec (`/opt/retdec`) と emsdk (`/opt/emsdk`) を展開して実行。 `sampler_engines.sh` を 1 回のみ実行 (`sampler_e2e.sh` は未実行)。 結果は下の「既定経路」行。 本 HEAD の表は表と別に読むこと。
- 既定経路の実行条件: 測定 HEAD `f73bcab0` (本節のみ変更、コード差分 0 で測定経路は `8a7f32ba` と同じ)。 env 未設定。 `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、PATH に `/opt/emsdk/upstream/emscripten`。
- 上の 6 ファイルの変更 (f80 計数・U6・NC2a/b) は別経路の検証の範囲で、本 REPORT の測定対象外。

以下の表は **`PLUG_NO_STATIC_DETECT=0` 相当 (RetDec argv が `5880a9f6` と同じ経路) の実測** である。 測定 commit は `5880a9f6` と `cb3a89a6` のどちらか未確定で、`5880a9f6`..HEAD の測定経路にはコード差分がある (上の stat)。 そのため **表の値は現 HEAD に対する鮮度を確認していない** (記録として扱う、#540)。 HEAD の既定経路 (`PLUG_NO_STATIC_DETECT` 未設定 = 1、`--disable-static-code-detection` あり) の `sampler_engines.sh` は下の「既定経路」行に実測を置く (`sampler_e2e.sh` の既定経路は未測定)。

| 項目 | 結果 (実測・`PLUG_NO_STATIC_DETECT=0` 相当) |
|---|---|
| 素材展開 `fl-win64.tar.zst` → `$RUNNER_TEMP/fl-win64` | 8.0 s、`block23663_PE.bin` / `block23664_PE.bin` 存在を確認 |
| 殻の `ff /2` disp32=0x1c0 候補 (block23663) | 24 件 (§2a)。 9 件の selector (2,3,4,5,10,11,12,13,14) は §4 のとおり |
| 殻の結線 0x843790〜0x84386a | 逆アセンブル成功 (`disasm_range.py`)、`[obj+0x1c0]` 保存・`[obj+0x1b8]` engine 保存を確認 |
| 検証 HEAD (記録) | `cb3a89a6` と記載 (§7 冒頭の `5880a9f6` との不整合は下の注記)。 コード変更なし |
| `sampler_engines.sh` (受入条件 1) | **exit 0・4:59.15 (299 s)**・Maximum RSS 3.52 GB (`/usr/bin/time -v`、2 engine 並列)・終了直後の load average 1.18 (1 分平均)。 `judge engines: PASS 2/2`。 23664: pdata 5,160 / lift_rc 0 / define 5,993 / `emcc_c_rc_after_f80` 0 / missing_ref 0。 23677: pdata 2,355 / lift_rc 0 / define 2,525 / `emcc_c_rc_after_f80` 0 / missing_ref 0。 (23677 は `emcc_c_rc` = 1、`emcc_c_rc_after_fixcmp` = 1、f80 処理後の `emcc_c_rc_after_f80` = 0 で判定を通る。 23664 は `emcc_c_rc` = 0。) ログに `do not know how to soften fp_extend` (final.ll / fixcmp.ll、計 2 件) が出るが、判定は PASS。 原因は未調査 |
| `sampler_engines.sh` 既定経路 (`PLUG_NO_STATIC_DETECT` 未設定) | **rc 0・4:56.02 (296 s)**・Maximum RSS 3.52 GB・開始時 load 0.70 / 終了直後 load 1.15 (1 分平均)。 `judge engines: PASS 2/2`。 23664: pdata 5,160 / lift_rc 0 / define 5,993 / `emcc_c_rc_after_f80` 0 / missing_ref 0 / missing_define 3。 23677: pdata 2,355 / lift_rc 0 / define 2,525 / `emcc_c_rc_after_f80` 0 / missing_ref 0 / missing_define 1。 (上の `PLUG_NO_STATIC_DETECT=0` 相当の表と比べ、pdata・lift_rc・define・`emcc_c_rc_after_f80`・missing_ref は両 block で一致。 `--disable-static-code-detection` の有無による差は、この 2 block の上の列では観測されなかった) |
| `sampler_e2e.sh` (受入条件 2、既存 T0/T1 の emcc 退行確認) | **exit 0・14:13.43 (853 s)**・load average 4.80 (5 分平均、run 中盤)。 `judge shells: PASS 7/7` (lift_rc / emcc_c_rc / f80 全 0)。 batch 7 本すべて `rc=0 emcc_c=0 f80=0`。 `ids_crosscheck: 7/7` |

- 注記: 上の表の数値は `cb3a89a6` 記録の実測 (n=1)。 `/usr/bin/time` と `uptime` で取った値で、run 内の他プロセスの負荷は記録していない。
- 前 run #643 の記録 (main f0d65f32、exit 0・321 s) と上の表の値は同じ判定結果 (PASS 2/2)。 表の測定 commit は上の記録のとおり (`cb3a89a6` または `5880a9f6`、未確定)。 前 run との比較は判定結果の一致のみで、同一 commit での再現とは書かない。
- **測定 commit の記録の不整合 (未解決)**: 本書は測定 commit を §7 冒頭・表の見出しでは `5880a9f6`、上の表の行と §1 では `cb3a89a6` と記す。 どちらが表の実測を行った commit かは、本書の記録からは確定できない。 両 commit とも既定 (`PLUG_NO_STATIC_DETECT` 未設定) の RetDec argv に `--disable-static-code-detection` を含まない (`cb3a89a6` は `${PLUG_NO_STATIC_DETECT:+...}` で未設定時は空、`5880a9f6` は該当行なし) ため、表の argv 条件は両方に当てはまる。 確定には実測 commit の記録を正す再実行が要る (起票先: #540)。

## 8. selector ごとの引数の意味 (受入条件 4 の続き)

測定: `disasm_range.py` (capstone) で engine 23664 の `DispatchToEngine` 0x180147bc0〜、殻 23663 の呼出し wrapper を逆アセンブル。 jump table は `.text` 上の rip 相対 int32 表を直接読んで解いた (case VA は §3 と一致)。

関数の共通形: `rcx` = engine (殻の `[obj+0x1b8]`)、`rdx` = selector、`r8`/`r9` = 第 3・第 4 引数、`[rsp+0x20]` = 第 5 引数 (殻は `&local` の out ポインタ、または 0)、`xmm3`/`[rsp+0x28]` = 第 6 引数 (float)。 engine 側は `r12` = `r9`、`rdi` = `r8`、`rsi` = 第 5 引数 (`[rbp+0x60]`)。

| sel | engine case の動作 (逆アセンブル) | 殻の呼出し (引数) | 確定した意味 |
|--:|---|---|---|
| 2 | `[rcx+0x1b0]` の関数を呼んだ後、`r9` (= `r12`) を第 2 段 switch (0..14) の添字に使う | wrapper 0x846a80 が `r9` = 自身の第 2 引数 (`rdx`) を渡す | 二段ディスパッチ。 内側 id は `r9` |
| 3 | 第 2 段 switch: `r9-0x3e8` (0..8)、float を engine obj のフィールドへ格納 (`[rbp+0x68]` = xmm3 を書く) | wrapper 0x846b10 が `r9` = 第 2 引数、`xmm3` = 値 | float setter と読める (第 2 段の各 case が obj のフィールドへ `movss` する形。 xmm3 の `[rbp+0x68]` への退避は未確認)。 id = `r9-1000` |
| 4 | sel 2 と同型の第 2 段 switch (表 0x14838c) | wrapper 0x846ac0 が `r9` = 第 2 引数 | 二段ディスパッチ (sel 2 と同じ) |
| 5 | 第 2 段 switch: `r9-0x3e8` (0..8)、obj のフィールドを読み `[rsi]` (= 第 5 引数) へ格納 | wrapper 0x846b50 が `r9` = 第 2 引数、第 5 引数 = `&local` | float getter。 出力は第 5 引数の out ポインタ |
| 10 (0xa) | `[rcx]` vtable `+0xd0` を呼び、`r8` を C 文字列として `strlen` し、`std::string` を組む | 0x8439a0 が `r8` = `&[rbp+0x4f]` | `r8` は入力の C 文字列。 ただし 0x8439a0 の範囲内には `[rbp+0x4f]` への書込みが無く、書込み元は未確定 |
| 11 (0xb) | `*r8 = 0x80` を書き、`rbx+0x3468` を返す | 0x8471f0 が `r8` = `&[rbp+0x58]` (out)、戻り値 `rax` を使う | バッファ容量 (0x80) を `*r8` に返し、バッファ先頭を戻り値で返す。 殻は長さを `[rbp+0x58]-1` を `0x7f` で頭打ちにして使う |
| 12 (0xc) | `r8` (= `edi`) を index、`r9 != 0` を bool として、`xmm3` を値に第 2 関数 0x18014fdf0 へ渡す | 0x847510 が `r8` = `sext(edx)` (index)、`r9` = `sext(r8d)` (flag)、`xmm3` = 値、かつ `edx > -1` のときのみ呼ぶ | 範囲付き index 設定。 `r9` は 0/非 0 の flag |
| 13 (0xd) | `[rbx+0x30]` の std::string の `c_str` 相当 (SSO 判定 `>= 0x10` 込み) を返す | 0x8473c8 が戻り値 `rax` を使う (`r8`・`r9` = 0 で未使用) | 文字列の `c_str()` 取得 |
| 14 (0xe) | `[rcx]` vtable `+0xd0`、`r8` を C 文字列として `strlen` して `std::string` を組む | 0x8474ad が `r8` = `&[rbp+0x57]` (直前に 0x55d0a0 で 0x200 バイトを埋めた入力) | `r8` は入力の C 文字列 (sel 10 と同じ形) |

- 結論 (本 HEAD、逆アセンブルの範囲): 9 件の selector のうち 7 件 (3・5・11・12・13・14、および 2・4 の二段ディスパッチの形) は引数の意味を確定した。 sel 10 は `r8` が入力文字列であることまでを確定し、書込み元は未確定。
- 未確定 (本 HEAD): (a) sel 2・4 の wrapper 呼出し元 (`[obj+0x1c0]` を経由しない間接経由の呼出し元) の inner id の値。 `E8 rel32` と絶対ポインタの走査 (wrapper 8 関数) は 0 件で終わった。 走査方法の正しさは未検証のため、呼出し元は本 HEAD では確定しない。 (b) sel 10 の `[rbp+0x4f]` の書込み元。 (c) 戻り値の型の完全な一覧 (sel 2・4 の戻り値は未確認)。
- 受入条件 4 の残り: (a)〜(c) を次の run で確定する。

## 9. 未確定 3 点の追跡 (受入条件 4 の続き、main ba4babca)

測定: `disasm_range.py` (capstone) と、直接参照の走査 (call/jmp の即値、RIP 相対 lea、絶対 8 バイト、4 バイト RVA) を殻 23663 全体に対して実施。

- **(a) sel 2・4 の wrapper 呼出し元**: wrapper 0x846a80 (sel 2)・0x846ac0 (sel 4) の VA を、殻の `.text` 全体で `call`/`jmp` 即値・RIP 相対 `lea`・即値 VA の形で走査 → 0 件。 4 バイト RVA (0x446a80・0x446ac0) は `.pdata` の unwind 項目 (0x52a3fc・0x52a408) のみ。 よって呼出し元は直接参照では見つからず、間接呼出し (関数ポインタ・vtable) と推定されるが未確認。 inner id の値は**未確定**。
- **(b) sel 10 の `[rbp+0x4f]` の書込み元**: wrapper 0x8439a0 は関数 0x843930 (`.pdata` 上の関数範囲は 0x843930〜0x843a20。 §4 の 0x8439a0 は関数途中の位置) の内部。 0x84398c〜0x84399a で `[rbp+0x4f]` に `0x55d0a0(rcx=&[rbp+0x4f], rdx=[rbp+0x38], r8=0x200)` の結果を書く。 `[rbp+0x38]` は `0x41b450(rcx=&[rbp+0x38], rdx=[rbp+0x278])` で作られ、 `[rbp+0x278]` は関数 0x843930 の第 2 引数。 `0x55d010` は入力の c_str を最大 0x200 バイトまでコピーして末尾に NUL を置く。 **確定した入力**: sel 10 の `r8` は、関数 0x843930 の第 2 引数 (C 文字列) のコピー。 0x843930 の呼出し元は (a) と同じく直接参照 0 件のため未確定。
- **(c) 戻り値**: sel 2・4 の wrapper は `DispatchToEngine` の戻り値 `rax` をそのまま返す (`call [rax+0x1c0]` の後に `add rsp`・`ret`、 rax 加工なし)。 よって戻り値型は engine 側 `DispatchToEngine` の case 依存で、 sel 2 は `[rcx+0x1b0]` の外部呼出し結果、 sel 4 は表 0x14838c の結果。 いずれも case 内の戻り値型は未読解。
- 結論: 受入条件 4 の残り (a)(b)(c) は、(b) の入力源 (第 2 引数) まで確定。 (a) と (c) は未確定。


## 10. 残り (a)(b)(c) の再解析 (受入条件 4 の続き)

- 詳細 (呼出し元 17 件の内側 id 表・(b) の入力源・(c) 未着手) は `REPORT_ENGINE_LINK_APPENDIX_540.md` (付録) に分割移動。
- **§9 (a) の訂正**: §9 の「呼出し元 0 件」は誤り。 命令境界で検証すると、sel 2 の wrapper 0x846a80 の呼出し元は 9 件、sel 4 の 0x846ac0 は 8 件。
- **(a) の結論**: 呼出し元 17 件のうち 16 件で内側 id が確定。 未確定は 0x84bd8f (sel 2) の `esi` 由来 1 件のみ。
- **(b)**: §9 の確定 (sel 10 の `r8` = 関数 0x843930 の第 2 引数の C 文字列コピー) は据え置き。 第 2 引数の文字列内容は未確定。
- **(c)**: 未確定 (本 run では未着手)。
- 受入条件 5 (VEX の SSE 固定の動的確認): 本 run では未着手。 runner に Windows 実行環境 (wine 等) は無い。
