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

## 4. 受入条件 3・5 の扱い (前 run からの持ち越し)

- 受入条件 3 (RetDec C バックエンド省略): 既定経路は `sampler_engines.sh` → `engine_lift.sh` → `lift_from_ll.sh` (`.ll` 出力後に RetDec を止める) で、共有 `lift_ranges.sh` は変更していない。 判断は `REPORT.md` §5 と `REPORT_APPENDIX.md` §D の記録どおり。 `--backend-enabled-opts` / `--no-memory-limit` は未評価 (本 run では時間上限のため測定せず)。
- 受入条件 5 (VEX helper の CPUID 分岐): 前 run の静的確認 (VEX 関数 229 / 94 のうち caller 鎖深さ 3 に cpuid/xgetbv 関数を持つもの 0) を引き継ぐ。 本 run では未再測定。

## 5. 未解決 (起票先付き)

| 未解決 | 起票先 |
|---|---|
| 殻 `obj+0x1c0` の `DispatchToEngine` 呼出し箇所と selector 値 | 本 #540 (受入条件 4 の残り。 継続) |
| `DispatchToEngine` の引数規約 (rcx/rdx/r8/r9 の意味、戻り値) | 本 #540 |
| engine の `[rbx+0x30]` / `[rcx+0x1b0]` の構造体定義 | 本 #540 |
