# REPORT 付録 — SR-97 (#5935) 収束後の未解決間接 call 6 箇所の分類

- 親: #5005 (残作業 1・3)。本付録は `REPORT_APPENDIX_5005.md` §5.5・§5.6 の未解決 6 箇所の分類。
- 日付: 2026-10-16 / 本付録の commit 系列: 初版 `d22c9e95a`・差し戻し対応 (本 commit 以降の `fix(serum2)` commit で `gui/xref_slot_writes.py` を修正)。
- 入力: `Serum2_win64.vst3` (sha256 `501e7bb3…4e5283` / 19,236,864 B)。Ghidra 12.1.4 (`[GHIDRA]`・sha256 `ddac49f9…d4db`)、JDK 21。
- 上限の root: `gui/xferonoff_upper_fns.tsv` (sha256 `c741878…26fb`・19 行)。
- **PE の取得状況**: 本 run の `ARTIFACTS_DIR` には `fl-win64` のみで、PE (`Serum2_win64.vst3`) の入力源 `plugins-serum2` は無い。このため PE を読む測定は本付録で行っていない (§5)。PE 依存の記述はすべて『未測定』とする。

## 1. 収束の再現 (受入 1 の前提)

`gui/iterate_sr85_upper.py` を実行し、`REPORT_APPENDIX_5005.md` §5.6.2 と一致した (初版 commit での実行。本 run では再実行していない)。

| 反復 | root | 閉包 関数数 | 本体合計 | 間接 call | 候補関数 | 新規候補 | 未解決 |
|---|---|---|---|---|---|---|---|
| 1 | 19 → 23 | 157 | 22,227 B | 100 | 20 | 4 | 0 |
| 2 | 23 → 24 | 161 | 23,180 B | 107 | 21 | 1 | 0 |
| 3 | 24 | 162 | 23,190 B | 107 | 21 | 0 (収束) | 0 |

- import (`ghidra_fn_size.java`) **1,111 秒** (real)。反復 3 回で **36.1 秒** (real)。

## 2. 未解決 6 箇所の分類 (分類の状態)

| 関数 | 命令 | 分類 | 状態 |
|---|---|---|---|
| `0x180136bf0` | `call R10` (`0x180136ca7`) | `.data` の slot `0x1817bf760` 由来 (前 run の逆アセンブル記録。直前 `mov r10, [rip+0x1688a99]`) | 本 run で未再検証 (PE 無し) |
| `0x180136bf0` | `call R10` (`0x180136ce8`) | 同上 (`test r10,r10; je` の null チェックの後) | 本 run で未再検証 (PE 無し) |
| `0x180136bf0` | `call RAX` (`0x180136d1d`) | 未確定 (供給元を未追跡) | 未確認 |
| `0x180138180` | `call RAX` (`0x1801381d8`) | 同 slot `0x1817bf760` (前 run の記録。`mov rax, [rip+0x16875a5]`) | 本 run で未再検証 (PE 無し) |
| `0x180142540` | `call RAX` (`0x1801425e3`) | 同 slot `0x1817bf760` (前 run の記録。`mov rax, [rip+0x167d19e]`) | 本 run で未再検証 (PE 無し) |
| `0x1809ca77c` | `call qword ptr [rip+0x616b38]` (`0x1809ca7b2`) | 間接 call の型は未確定。CFG 経由 (`__guard_dispatch_icall`) の可能性がある | Load Config 照合 (§5-3) 未実施。従来記録 (`REPORT_APPENDIX_5005.md` §5.6.2 の「IAT 形式・分類未確定」) は**本付録では訂正しない** |

- slot `0x1817bf760` 由来は 4 箇所 (`0x180136ca7`・`0x180136ce8`・`0x180138180`・`0x180142540`)。
- `0x180136d1d` (`call RAX`) の供給元は未確認のまま。

### 2.1 slot `0x1817bf760` の参照 (旧記録の取り下げ)

前版にあった「`.text` 内の store 0 件 (load 289 件)」「PE 上の初期値は 0 (`.data` の zero-fill)」は、**根拠の記録が無いため取り下げる**。根拠の再現は PE が要るため、本 run では測定していない。
- 旧 `xref_slot_writes.py` は `i == 0` の memory オペランドをすべて WRITE とし、`cmp`・`test`・`call` 等の読み出しを WRITE に数えていた。また `lea` で得たポインタ経由の store を検出できなかった。よって旧版の件数 (load 289・store 0) は、根拠として使えない。
- 修正版 (`gui/xref_slot_writes.py`) は capstone の `op.access` で WRITE / RW / READ を区別し、`lea reg,[rip+X]` で得たアドレスを reg が書き換わるまで追跡する。`--selftest` で分類と追跡を確認した (§5 の自己テスト結果)。PE 上の件数は §5-1 の手順で測定する。

## 3. 受入の判定

- 受入 2 (`call reg` の 2 段目以降の解決): **未達**。`0x1817bf760` の値の決定に必要な PE 上の情報 (store の有無・初期値) を、本 run で測定していない。
- 受入 1 (閉包の上限を真の値に閉じる): **未達**。slot 由来 4 箇所・`0x180136d1d` (未確認)・`0x1809ca77c` (型未確定) が残る。
- 閉包の値 (162 関数・23,190 B) は**下界**のまま。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1817bf760` の runtime 値 (PE 上の store 件数・初期値は未測定) | 閉包 4 箇所の呼出し先が未確定。閉包の上限が閉じない | #5935 (本 PR の `Refs`) |
| `0x180136bf0` の `call RAX` (`0x180136d1d`) の供給元 | 1 箇所の呼出し先が未確定 | #5935 |
| `0x1809ca77c` の間接 call (CFG 経由かの確認を含む) | 閉包 1 箇所 | #5935 |

## 5. 再測定の手順 (PE が要る・未実施)

PE は `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe`) から `tools/targets/serum2/host/ref_content.sh` で `work/Serum2_win64.vst3` に作る。PE を持つ run で以下を実行し、出力を本付録に貼る。

1. 修正版の WRITE/READ 件数: `python3 gui/xref_slot_writes.py work/Serum2_win64.vst3 0x1817bf760` (stderr の `total_refs`・`WRITE`・`RW`・`READ`)。
2. slot の PE 上の値: `pefile` で `.data` の section 名・`VirtualAddress`・`VirtualSize`・`SizeOfRawData` と、`0x1817bf760` の raw バイトを出力する。
3. `0x1809ca77c` の CFG 照合: `pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.GuardCFDispatchFunctionPointer` の値と、`0x1809ca7b2` の参照先 `0x180fe12f0` が一致するかを出力する。一致しなければ分類を直す。

### 5.1 自己テスト (PE 無し・本 commit で実行)

`python3 gui/xref_slot_writes.py --selftest` → `selftest OK: ['WRITE', 'READ', 'READ', 'WRITE', 'READ', 'RW']` (rip 相対の store/load/call・`lea` 経由の store/load・`add [rip+X]` の RW・rcx 書換え後の打ち切り)。
