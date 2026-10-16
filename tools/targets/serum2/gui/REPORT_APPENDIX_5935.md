# REPORT 付録 — SR-97 (#5935) 収束後の未解決間接 call 6 箇所の分類

- 親: #5005 (残作業 1・3)。本付録は `REPORT_APPENDIX_5005.md` §5.5・§5.6 の未解決 6 箇所の分類。
- 日付: 2026-10-16 / 測定 commit (コードを変えた最後の commit): `41d95d39c`。PE 測定は同 commit の `gui/xref_slot_writes.py` で行った。
- 入力: `Serum2_win64.vst3` (sha256 `501e7bb3…4e5283` / 19,236,864 B)。Ghidra 12.1.4 (`[GHIDRA]`・sha256 `ddac49f9…d4db`)、JDK 21。PE は `plugins-serum2` から `host/ref_content.sh` で展開 (本 run で実施)。
- 上限の root: `gui/xferonoff_upper_fns.tsv` (sha256 `c741878…26fb`・19 行)。

## 1. 収束の再現 (受入 1 の前提)

`gui/iterate_sr85_upper.py` の結果は初版 commit `d22c9e95a` のもの。本 run では再実行していない。

| 反復 | root | 閉包 関数数 | 本体合計 | 間接 call | 候補関数 | 新規候補 | 未解決 |
|---|---|---|---|---|---|---|---|
| 1 | 19 → 23 | 157 | 22,227 B | 100 | 20 | 4 | 0 |
| 2 | 23 → 24 | 161 | 23,180 B | 107 | 21 | 1 | 0 |
| 3 | 24 | 162 | 23,190 B | 107 | 21 | 0 (収束) | 0 |

- import (`ghidra_fn_size.java`) **1,111 秒** (real)。反復 3 回で **36.1 秒** (real)。

## 2. 未解決 6 箇所の分類 (PE 実測後)

| 関数 | 命令 | 分類 | 根拠 |
|---|---|---|---|
| `0x180136bf0` | `call R10` (`0x180136ca7`) | slot `0x1817bf760` 由来 | `0x180136c7f` で `mov r10,[rip+…]` → slot。直前 `test r10,r10; je` の null チェックあり |
| `0x180136bf0` | `call R10` (`0x180136ce8`) | slot `0x1817bf760` 由来 | `0x180136cc0` で `mov r10,[rip+…]` → slot。`test r10,r10; je` あり |
| `0x180136bf0` | `call RAX` (`0x180136d1d`) | slot `0x1817bf760` 由来 (**前版の「供給元未確認」を訂正**) | `0x180136cf5` で `mov rax,[rip+…]` → slot。`test rax,rax; je` あり |
| `0x180138180` | `call RAX` (`0x1801381d8`) | slot `0x1817bf760` 由来 | `0x1801381b4` で `mov rax,[rip+…]` → slot (計算で一致)。`test rax,rax; je` あり |
| `0x180142540` | `call RAX` (`0x1801425e3`) | slot `0x1817bf760` 由来 (前版の記録。本 run で再確認していない) | `0x1801425c5` に `test rax,rax; je` あり |
| `0x1809ca77c` | `call qword ptr [rip+0x616b38]` (`0x1809ca7b2`) | **CFG 経由の vtable 呼出し** (slot ではない) | `[rip+0x616b38]` = `0x180fe12f0` = Load Config の `GuardCFDispatchFunctionPointer` (一致)。呼出し先 `rax` は `[[rcx]-8]+0x40` (オブジェクトの vtable) から来る |

- slot 由来は **5 箇所** (前版は 4 箇所 + 「未確認」1 箇所だった。`0x180136d1d` が slot 由来と確定したため 5 箇所)。
- 「IAT 形式」の記録 (`REPORT_APPENDIX_5005.md` §5.6.2) は、Load Config 照合により **CFG dispatch 経由の vtable 呼出し** に訂正する。`0x180fe12f0` は IAT ではなく `__guard_dispatch_icall` のポインタ。

### 2.1 slot `0x1817bf760` の PE 上の値 (実測)

- `.data`: VirtualAddress `0x1121000`・VirtualSize `0xf85804`・SizeOfRawData `0x9b400`。slot の section 内オフセットは `0x69e760` で、SizeOfRawData より外側。**zero-fill 領域**で、PE 上の初期値は 0。
- `.text` 内の参照 (`xref_slot_writes.py`・rip 相対と `lea` 経由): `total_refs=289 WRITE=0 RW=0 READ=289`。
- `lea reg,[rip+X]` で slot の絶対アドレスを作る命令: 0 件。全 section の 8 バイト列を走査し、slot の絶対ポインタ: 0 件。
- 判定: **PE の中には slot へ書き込む命令も、slot を指すポインタも見つからない**。よって slot は静的には 0 のまま。各 call は null チェックで飛ばされる。ただし、これは `.text` の rip 相対・`lea` 経由の走査による下界の証拠。PE 外や、計算で作った絶対アドレスからの store は除外できていない (`xref_slot_writes.py` の限界)。

## 3. 受入の判定

- 受入 2 (`call reg` の 2 段目以降の解決): **未達**。slot の runtime 値 (store の有無) は PE だけでは決まらない。PE 上の初期値は 0 で、store は見つからなかった。
- 受入 1 (閉包の上限を真の値に閉じる): **未達**。slot 由来 5 箇所は「値が 0 なら呼ばれない」、CFG 1 箇所はオブジェクトの vtable に依存するため、閉包の値は**下界**のまま (162 関数・23,190 B)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot `0x1817bf760` の runtime 値 (PE 外・計算アドレスからの store の有無) | slot 由来 5 箇所の呼出し先が未確定。閉包の上限が閉じない | #5935 |
| `0x1809ca77c` の CFG 経由 vtable 呼出し先 (オブジェクトの型) | 閉包 1 箇所。runtime 型に依存 | #5935 |

## 5. 測定手順と結果

PE は `plugins-serum2` から `tools/targets/serum2/host/ref_content.sh` で `work/Serum2_win64.vst3` に作る (sha256 一致を確認)。

1. 修正版の WRITE/READ 件数: `python3 gui/xref_slot_writes.py work/Serum2_win64.vst3 0x1817bf760` → `total_refs=289 WRITE=0 RW=0 READ=289` (実測)。
2. slot の PE 上の値: §2.1 (実測)。
3. `0x1809ca77c` の CFG 照合: `GuardCFDispatchFunctionPointer=0x180fe12f0` と `0x1809ca7b2` の参照先が一致 (実測)。

### 5.1 自己テスト (PE 無し)

`python3 gui/xref_slot_writes.py --selftest` → `selftest OK: ['WRITE', 'READ', 'READ', 'WRITE', 'READ', 'RW']` (rip 相対の store/load/call・`lea` 経由の store/load・`add [rip+X]` の RW・rcx 書換え後の打ち切り)。
