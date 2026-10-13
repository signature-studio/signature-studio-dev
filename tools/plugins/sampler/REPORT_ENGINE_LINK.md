# sampler REPORT 付録: Fruity Slicer 2 殻と engine の結線 (#540 受入条件 4)

本書は `REPORT.md` §5 の付録。 測定は素材 `fl-win64` (block23663 殻 / block23664 engine、`$FL_WIN64_DIR/extracted`) の逆アセンブル (pefile + capstone) による。 実行は行っていない。

## 1. 結論

- 殻 (block 23663、ImageBase 0x400000) は `engine_x64.dll` を名前で読み、`DispatchToEngine` を名前で引く。 engine の selector 呼出し箇所は未特定。
- 受入条件 4 は **部分達成**。 ロード経路と export 取得は確定し、`DispatchToEngine` の呼出し規約 (選択子と引数の意味) は未解析。

## 2. 殻側の経路 (block 23663)

| 項目 | VA | 内容 |
|---|--:|---|
| export `CreatePlugInstance` | 0x842880 | |
| export `DecodeAudioFile` / `FinishAudioFile` | 0x842950 / 0x842fc0 | |
| 結線ラッパ | 0x843790 | 文字列 `engine_x64.dll` (UTF-16, file offset 0x442c94) を組み立て、0x83e200 で読み込み、0x421d60 で `DispatchToEngine` (UTF-16 0x442cb2) を引く。 結果を `obj+0x1c0` に保存 |
| ロード関数 | 0x83e200 | 名前から DLL を開く経路。 殻の IAT には `LoadLibraryW` / `LoadLibraryA` / `LoadLibraryExW` / `GetProcAddress` が import されている (kernel32 155 件の全件走査で確認)。 0x83e200 がそれを直接呼ぶかは未確認 |
| 名前解決 | 0x421d60 → 0x421d50 | `DispatchToEngine` の取得。 `GetProcAddress` 経由と推定 (呼出し先の IAT 照合は未実施) |

- 結線ラッパ 0x843790 が `lea r8, [rip+0xda]` (0x8437b3) と `lea rdx, [rip+0xa9]` (0x843802) で文字列を直接参照する。 参照先は `engine_x64.dll` (VA 0x843894、file off 0x442c94) と `DispatchToEngine` (VA 0x8438b2、file off 0x442cb2)。 根拠はラッパ 0x843790 の逆アセンブル (capstone、0x843790〜0x84386a)。 `.text` 全体の線形走査では同じ参照を拾えなかったため、走査結果は根拠にしない。
- `obj+0x1c0` に保存した関数ポインタの呼出し箇所を、殻 `.text` 全体のバイト列 `c0 01 00 00` (disp32 = 0x1c0) の 160 箇所から逆アセンブルして数えた (capstone、命令境界を 0x1c0 で終わるものに限定)。 `[reg+0x1c0]` を `call` するものは 24 件 (0x589137 / 0x590c92 / 0x591a16 / 0x594b6b / 0x594c0c / 0x59583e / 0x597510 / 0x5a7597 / 0x657aed / 0x6ea474 / 0x6ea494 / 0x73b356 / 0x73b386 / 0x73b644 / 0x778469 / 0x8439d1 / 0x846ab0 / 0x846af4 / 0x846b3c / 0x846b8f / 0x847220 / 0x8473c8 / 0x8474ad / 0x847547)。 そのうち `obj` (ラッパの `[rcx+0x1c0]` と同じ基底) かどうかは未確認。 selector の設定箇所は未特定 (間接参照の経路を要追跡)。

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

## 4. 殻の呼出し箇所と selector (受入条件 4 の残り・本 run で確定)

測定: `disasm_range.py` (capstone) で殻 23663 の `.text` を逆アセンブル。

- 結線ラッパ 0x843790: `[obj+0x1a8]` に engine ローダ 0x83e200 の戻り値 (engine オブジェクト) を保存し、`[obj+0x1b0]` 系の名前引数で `DispatchToEngine` 0x421d60 を引いて `[obj+0x1c0]` に保存する。 その後 `[obj+0x1a8]` の vtable `+8` を 2 回呼ぶ (0x843831, 0x843858)。
- 殻が `DispatchToEngine` を呼ぶ形は `call qword ptr [reg+0x1c0]` で、`rcx = [obj+0x1b8]` (engine オブジェクト)、`rdx = selector` の直接呼出し。 この形の呼出しは 9 箇所 (以下、selector は `mov edx, imm` または `mov r9d, imm` → `mov edx, r9d` の直前代入から読んだ値)。

| 殻の呼出し箇所 | selector (rdx) | 引数の意味 (逆アセンブル上) |
|--|--:|---|
| 0x846ab0 (関数 0x846a80) | 2 | `r9` を第 4 引数、`xmm0` = 浮動小数点引数 |
| 0x846af4 (0x846ac0) | 4 | 第 5 引数 `[rsp+0x20]` = 0 |
| 0x846b3c (0x846b10) | 3 | `xmm3` を第 5 引数 |
| 0x846b8f (0x846b50) | 5 | 第 5 引数に `&local` (out ポインタ) |
| 0x8439d1 (0x8439a0) | 10 (0xa) | `r8 = &local` (out)、`xmm0` = 浮動小数点引数 |
| 0x847220 (0x8471f0) | 11 (0xb) | `r8 = &local` (out) |
| 0x8473c8 (0x847380) | 13 (0xd) | 戻り値 `rax` を直後に 0x41b670 の第 2 引数へ渡す (戻り値を使う) |
| 0x8474ad (0x847380 内) | 14 (0xe) | `r8 = &[rbp+0x57]` (直前の 0x55d0a0 で 0x200 バイトを埋めた領域を渡す) |
| 0x847547 (0x847510) | 12 (0xc) | `r10 = edx` 符号拡張、`r11 = r8d` 符号拡張 (範囲 2 引数) |

- 9 件の selector は engine 側 `DispatchToEngine` の case 表 (§3、有効 2..14) の内側に収まる。 case 6〜9 (no-op) は殻からは使われない。
- 残りの `call qword ptr [reg+0x1c0]` (0x589137 / 0x590c92 / 0x594b6b / 0x594c0c / 0x59583e / 0x597510 / 0x5a7597 など) は `rbx = [obj]` の vtable 呼出しで、`DispatchToEngine` とは別の仮想メソッド。 本 run の範囲では DispatchToEngine と結び付けない。
- 引数規約の残り: 戻り値は殻側で `rax` を読む箇所がある (0x8473c8) ため有効な結果を返す。 selector ごとの `r8`/`r9` の完全な意味は engine case ごとの読解が必要で、本 run では未完 (次の課題)。

## 5. 受入条件 3・5 の測定

### 3. RetDec の C バックエンド省略 (実測)

| 方式 | 対象 | 結果 (実測) |
|---|---|---|
| 既定 `lift_ranges.sh` 直行 (前 run 再掲、REPORT §5) | 23664 | 614 s 時点で RSS 8.15 GiB、"out of memory; trying to recover" 3 回。 未完で手動停止 |
| `--backend-no-opts` (本 run) | 23664 | **exit 0、441 s、Maximum RSS 3.52 GB**。 `.ll` 75 MB・`.c` 39.6 MB 出力まで完走 |

- 結論: `--backend-no-opts` で RSS は 8.15 GiB → 3.52 GB に下がり、C 出力まで完走する。 ただし 441 s は `lift_from_ll.sh` (.ll 出力後に停止、既定経路) より長い。 共有 `lift_ranges.sh` は変更せず、既定経路は `lift_from_ll.sh` のまま (判断: 変更しない)。
- 理由: `lift_from_ll.sh` は C 出力を使わず `.ll` の後段だけ使うため、`--backend-no-opts` を入れても時間の利点が無い。 `--no-memory-limit` は本 run では未測定 (RSS は 3.5 GB で上限に届かなかった)。

### 5. VEX helper の CPUID 分岐 (再測定、main f0d65f32)

`vex_guard.py` の実行結果 (同一値、前 run と一致):

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
