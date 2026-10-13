# sampler REPORT 付録: Fruity Slicer 2 殻と engine の結線 (#540 受入条件 4)

本書は `REPORT.md` §5 の付録。 測定は素材 `fl-win64` (block23663 殻 / block23664 engine、`$FL_WIN64_DIR/extracted`) の逆アセンブル (pefile + capstone) による。 実行は行っていない。

## 1. 結論

- 殻 (block 23663、ImageBase 0x400000) は `engine_x64.dll` を名前で読み、`DispatchToEngine` を名前で引く。 殻から `DispatchToEngine` を呼ぶ箇所は 9 件 (§4)。
- 受入条件 4 は **部分達成**。 ロード経路・export 取得・呼出し箇所 9 件・各 selector 値は確定。 `DispatchToEngine` の引数規約 (`r8`/`r9` の意味・戻り値) は未解析。
- 受入条件 1・2 は本 HEAD で **未再現** (§7)。 RetDec が runner に無く `sampler_engines.sh` が 900 s で打ち切られた。

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

### 3. RetDec の C バックエンド省略 (実測)

| 方式 | 対象 | 結果 (実測) |
|---|---|---|
| 既定 `lift_ranges.sh` 直行 (前 run #810 の実測、本 HEAD では未再測定) | 23664 | 614 s 時点で RSS 8.15 GiB、"out of memory; trying to recover" 3 回。 未完で手動停止。 run id 未確認 |
| `--backend-no-opts` (前 run #810 の実測、本 HEAD では未再測定) | 23664 | **exit 0、441 s、Maximum RSS 3.52 GB**。 `.ll` 75 MB・`.c` 39.6 MB 出力まで完走。 run id 未確認 |

- 結論: `--backend-no-opts` で RSS は 8.15 GiB → 3.52 GB に下がり、C 出力まで完走する。 ただし 441 s は `lift_from_ll.sh` (.ll 出力後に停止、既定経路) より長い。 共有 `lift_ranges.sh` は変更せず、既定経路は `lift_from_ll.sh` のまま (判断: 変更しない)。
- 理由: `lift_from_ll.sh` は C 出力を使わず `.ll` の後段だけ使うため、`--backend-no-opts` を入れても時間の利点が無い。 `--no-memory-limit` は本 HEAD では未測定 (RSS は 3.5 GB で上限に届かなかった)。

### 5. VEX helper の CPUID 分岐 (前 run の引用、main f0d65f32。本 HEAD では未再測定)

`vex_guard.py` の数値 (前 run の記録の引用。本 HEAD の capstone 不在のため再現していない):

| block | pdata | VEX 関数 | cpuid 関数 | xgetbv 関数 | VEX 関数のうち caller 深さ 3 に cpuid/xgetbv を持つもの |
|--:|--:|--:|--:|--:|--:|
| 23664 | 5,160 | 229 | 29 | 4 | 0 |
| 23677 | 2,355 | 94 | 28 | 3 | 0 |

- 結論: 静的には CPUID 分岐で SSE 路に固定する経路が見えない (VEX 関数の caller 鎖に cpuid 関数が無い)。 SSE 固定は成立しない見込みで、判断は「静的に不成立」。 動的な分岐の実測は未実施。

## 6. 未解決 (起票先付き)

| 未解決 | 起票先 |
|---|---|
| 殻の selector 9 件の `r8`/`r9` 引数の完全な意味・戻り値の型 (engine 側 case ごとの読解) | 本 #540 (継続) |
| `--no-memory-limit` の実測 (今回 RSS 3.5 GB で未到達) | 本 #540 (継続) |
| VEX helper の SSE 固定の動的確認 (静的には不成立) | #527 にコメント予定 (既存・重複起票せず) |
| 受入条件 1・2 の再測定 (`sampler_engines.sh`) | 本 HEAD の検証 run は runner に [RETDEC] が無く未再現。 RetDec 環境のある run で再測定 (#540 継続) |

## 7. 本 HEAD (5880a9f6) での再測定

| 項目 | 結果 (実測) |
|---|---|
| 素材展開 `fl-win64.tar.zst` → `$RUNNER_TEMP/fl-win64` | 8.0 s、`block23663_PE.bin` / `block23664_PE.bin` 存在を確認 |
| 殻の `ff /2` disp32=0x1c0 候補 (block23663) | 24 件 (§2a)。 9 件の selector (2,3,4,5,10,11,12,13,14) は §4 のとおり |
| 殻の結線 0x843790〜0x84386a | 逆アセンブル成功 (`disasm_range.py`)、`[obj+0x1c0]` 保存・`[obj+0x1b8]` engine 保存を確認 |
| `sampler_engines.sh` (受入条件 1・2) | **未再現**。 exit 124 (900 s 打ち切り)。 [RETDEC] の `retdec-decompiler` 不在 (`No such file or directory`)、`.ll` が出ず後段に進めない。 [EMSDK] も無し。 負荷 (load) は 0.02 前後で待機のみ |

- 参照のみ (本 HEAD の実測ではない): 前 run #643 の記録では `sampler_engines.sh` が main f0d65f32 で exit 0・321 s・`judge engines: PASS 2/2`。 run id は未確認。 受入条件 1・2 は、本 HEAD で再測定できるまで「未再現 (前 run #643 の値のみ)」として扱う。
