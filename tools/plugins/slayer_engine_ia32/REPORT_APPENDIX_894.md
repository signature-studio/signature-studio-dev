# tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_894.md — #894 events[] 探索の付録 (REPORT.md §9.5・§9.6 の全文)

本付録は 250 行上限 (`docs/DOC_MAP.md` §1) のため `REPORT.md` から分割移動した節の全文。内容は削除していない。 親: `REPORT.md` §9.5・§9.6。

### 9.5 events[] 読取の探索 (#894 受入 1 の追加調査・未達)

素材の検索範囲と結果 (`fl-win64` 展開・`extracted/` 配下):

再現: `python3 tools/plugins/slayer_engine_ia32/sweep_idx_mem.py --ctx 6` (素材は `$RUNNER_TEMP/fl-win64/extracted/block22434_PE.bin`、sha256 と capstone 5.0.7 を固定値で検証)。 スクリプトは decode 失敗時に 1 バイト飛ばし、`.text` 全 73,002 バイトを被覆する (最初の線形掃引は `.text` の約 51% で停止していた。旧記録の「0 件」はこの停止に基づく誤り)。

全域掃引の実測 (本 PR の HEAD で再現、capstone 5.0.7・CS_MODE_32):

| 項目 | 実測 |
|---|---|
| 被覆 | 命令 25,349 (72,998 B) + decode 失敗 4 B = **73,002 / 73,002 B** |
| 添字スケール 4 の memory operand | **304 件** (304 命令)。 うち x87 (`f*`) が 97 件 |
| 添字 *4 の上位 (base,index) 組 | `[edi+ecx*4]`=33・`[-+eax*4]`=30・`[ecx+eax*4]`=30・`[-+ecx*4]`=30・`[-+edx*4]`=28・`[esi+ecx*4]`=26・`[ebx+edx*4]`=21・`[ebx+eax*4]`=15 (`[-+X*4]` は disp のみの配列・jump table 形) |
| 変位 8 の添字 *4 | **8 件** (下表) |
| 素材内の他 PE | fl-win64 の PE は machine 0x14c (ia32) 55 件・0x8664 (x64) 258 件。 ia32 PE は block22434 以外にも多数 (例 block00000・00004・24830〜24863 など)。 `block22433` は machine 0x8664・ImageBase 0x400000 の x64 本体で、machine の値だけでは engine か断定できないため engine 候補から外すことはしない (x64 本体と推定するのみ)。 他の ia32 PE が engine か否かは未確認 |
| `slayer_x86/` の REPORT | 殻 ↔ engine の ILP32 marshal の必要性のみ記載 (読取箇所の記載なし) |

変位 8 の 8 件 (周辺命令から分類。 いずれも VstEvents 読取とは断定できない):

| VA | 命令 | 周辺から見た分類 |
|---|---|---|
| `0x1000a26c` | `mov eax,[esi+ecx*4+8]` | `+4`〜`+0x14` を連続で移す dword コピーループ (`lea eax,[ecx*4]` で ecx は dword 数)。 固定オフセットの一括コピーで、`events[i]` の単独読取ではない可能性が高い |
| `0x1000a270` | `mov [edi+ecx*4+8],eax` | 同上 (上の store) |
| `0x1000eb21` | `mov eax,[ebx+esi*4+8]` | `[ebx+esi*4]` の要素を `call` する直前。 関数ポインタ表の要素を読んで呼ぶ形 |
| `0x1000eb2a` | `call [ebx+esi*4+8]` | 間接 call。 **vtable・関数ポインタ表の呼出し**の可能性が高い (読取ではない) |
| `0x1000ec00` | `mov eax,[edi+ecx*4+8]` | 直前 `lea ecx,[esi+esi*2]` のため添字は 3·esi、実効 stride **12 B**。 `events[i]` (stride 4) とは一致しない |
| `0x1000ec0f` | `call [edi+ecx*4+8]` | 同上 (stride 12 の record 内の関数ポインタへの間接 call) |
| `0x10010e7c` | `mov eax,[esi+ecx*4+8]` | `0x1000a26c` と同一形の dword コピーループ (開始位置は未実測) |
| `0x10010e80` | `mov [edi+ecx*4+8],eax` | 同上 (store) |

結論: `events[i]` (+8 から stride 4 で並ぶ) と**同じ添字形の単独読取は確認できない**。 stride 4 の候補 (`0xa26c` 系・`0xeb21`) は、前者が一括コピー、後者が関数ポインタ呼出しと読め、 VstEvents 読取とは断定できない。 `0xec00` 系は stride 12 で `events[i]` と異なる。 #894 受入 1 は**未達のまま**。

- この探索は「添字 `*4+8` の形」に限定した静的検索であり、**読取の不在を証明しない**。 `numEvents` (+0) は `[reg]`・`events[]` 要素は `[reg+4]` や `[reg+idx*4+4]` (ptr 内の値) で読まれる可能性がある (未確認)。
- 次の一手 (未着手): effProcessEvents(25) の**呼出し元**を辿る方向 (dispatcher の外から opcode 25 を受ける経路・vtable 初期化) か、`events` を受ける関数の探索を、`[reg+4]` を含む形へ広げて行う。 いずれも #894 の継続。

### 9.6 `mov r,[X+8]` → `[r+idx*4]` の形による events[] 候補の列挙 (#894 受入 1 の追加調査・未達)

再現: `python3 tools/plugins/slayer_engine_ia32/scan_events.py` (素材 sha256 `84b64c43…` を検証、capstone 5.0.7・CS_MODE_32、線形掃引)。 base を `[X+8]` から読み、直後 6 命令以内に `[base+idx*4]` を読む形を列挙する。

所要と鮮度 (scan_events.py・測定 commit `ee01b1c2`・n=3 の順次実行、並列数 1、cpu 4):

| 項目 | 実測 |
|---|---|
| wall (`date +%s%N` 差分) | 480 / 492 / 512 ms → min–max 480–512 ms |
| load average (1 分、各 run 前) | 0.45 / 0.45 / 0.45 |
| 出力 | 3 回とも `[events-cand] count=5` で同一 (`diff` 0 行) |
| `git diff ee01b1c2 HEAD -- 'tools/plugins/slayer_engine_ia32/*.py'` の出力 (`6eaff222` 時点) | 0 行 (`*.py` 差分 0。 再測定は不要) |
| `git diff --stat ee01b1c2 HEAD -- tools/plugins/slayer_engine_ia32` (`6eaff222` 時点・文書のみの差分) | `REPORT.md` 45 行削除・`REPORT_APPENDIX_894.md` 62 行追加 (2 files, +64/-43。 `*.py` は含まない) |

| VA | 候補の読込み | 直後の添字読み | 判定 |
|---|---|---|---|
| `0x1000ebbc` | `mov edi,[ebx+8]` | `cmp [edi+ecx*4+4],0`・`call [edi+ecx*4+4]` | stride 12 (`lea ecx,[esi+esi*2]`) のレコード。 関数ポインタ呼出し。 events[] ではない |
| `0x1000ec13` | `mov edi,[ebx+8]` | `mov esi,[edi+ecx*4]` (stride 12) | 同上 |
| `0x1000f737` | `mov eax,[esp+8]` | `test [eax+esi*4],edx` | 32bit ビット集合の操作。 逆アセンブル実測 (0x1000f720〜0x1000f744): `pop ecx` で ecx=0x20 → `idiv ecx` (÷32、商を esi)、`push 0x1f`・`pop ecx` で ecx=0x1f → 2 回目の `idiv ecx` (÷31、剰余を edx)、`sub ecx,edx` 後 `or edx,-1`・`shl edx,cl`・`not edx` でマスクを作り `test [eax+esi*4],edx` |
| `0x1000f7e8` | `mov eax,[ebp+8]` | `lea eax,[eax+ecx*4]` | ビット集合の添字計算。 読取ではない |
| `0x1000f837` | `mov edx,[ebp+8]` | `lea edi,[edx+eax*4]`・`rep stosd` | ビット集合の 0 埋め。 読取ではない |

結論: この形の候補 5 件はいずれも VstEvents の `events[i]` 読取と判定できない。 `events[i]` (ポインタ 4 B, stride 4) と一致する読取は、この探索の範囲では見つからない。 **読取の不在は証明できていない** (base を `[X+8]` 以外から得る経路、`numEvents` の `[reg]` 読取は未探索)。 受入 1 は未達のまま。
