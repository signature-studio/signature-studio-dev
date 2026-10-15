# PY-336 (#4526): patterns 選択 setter 本体 (selectAll・deselectAll・selectPattern 経路) の PE 確定

親: #3538 (PY-282) / 前段: `REPORT_PY208.md` (未確定 2 の本体部分) / 委譲先: `REPORT_PY211.md`。既知類型との関係: 該当なし (PE の逆アセンブル読解のみ。lift 作業ではない)。起動・GUI に関わらないため製品 KPI は対象外。

## 0. 結論

- 受入条件の 6 関数 (`0xea6e50`・`0xea6a00`・`0xea7280`・`0xea7420`・`0xea6730`・`0xe4e7f0`) の本体を、PE 解析箇所 (VA) つきで確定した (§2)。検査スクリプト `analysis/flapi/pe_py336_probe.py` で再現できる (§4)。
- `0xea7420` は「内部 index が選択リストにあるか」の判定と確定した (真偽の返し方)。`REPORT_PY208.md` の「選択済みかは推定」はこれで解消。
- `0xea6e50` は `r8b` が 0 のとき (selectAll) は挿入と通知 (`[O]+0x178`) だけで終わる。`jumpToPattern` (`0x12d8af0`) を呼ぶのは `r8b≠0` (selectPattern の value=1) のときだけ。
- 本体の読解で、**`0xea7280` (単独解除) は要素の id (dword) だけを詰め、+4 の参照付きポインタは詰めない**ことを確認した。削除で空いた末尾要素のポインタの扱いは未読 (§5 の 3)。
- 本体の周辺 (vtable の呼出し先・モード byte の意味) は未読。§5 に残す。

## 1. 測定

- 測定 commit: `86fc25c8a` (probe の追加 commit。コードを変えた最後の commit)。base は `origin/main` の `26c2966e7`。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/py336" --wildcards '*block00031_PE.bin'` (実測 `real 0m2.906s`・展開先 `$RUNNER_TEMP/py336/extracted/block00031_PE.bin`・22,227,016 バイト)。
- 逆アセンブル: `python3 analysis/py41_disasm.py <PE> 0xea6e50 0xea6a00 0xea7280 0xea7420 0xea6730 0xe4e7f0` (`tools/python` で実行・rc 0)。呼出し元 `0xd66390 0xd66500 0xd660e0 0xd66230` と補助 `0xea66b0 0xbb1990 0x417fc0 0x4133f0 0x11e8720 0xff8a90 0xea75a0` も同じ方式 (rc 0)。
- 実行時の値 (グローバル変数の中身・要素数) は静的解析では得られない。以下の「O」「L」「item」は構造だけを書く。

## 2. 関数ごとの本体

記号: `O` = `[G]→[0]→[+0xd34]` (呼出し元と同じ対象)。`L` = `[O+0x6ac]` の選択リスト (要素 12 バイト: id = dword @+0、参照付きポインタ = @+4。件数は `[L-8]`、L が null なら 0)。`item(i)` = `[O+0x6c8]→[+8]→[i]` (8 バイトのポインタ。件数は `[O+0x6c8]→[+0x10]`)。`item(i).+0xc` = パターン番号 (dword)。`0xea66b0(O, i)` は `L[i].id` を範囲検査し、その item のパターン番号を返す (範囲外は -1)。

### 2.1 setSelected `0xea6e50` (rcx = O・edx = idx・r8b = flag)

1. `idx < 0` または `idx > 件数−1` なら何もせず終了 (`0xea6e8e`・`0xea6e97` → `0xea7248`)。
2. `L` に id == idx の要素が既にあれば何もせず終了 (`0xea6ed8`)。
3. `0x417fc0(&L, desc, 1, 件数+1)` で L を 1 つ伸ばす (`0xea6f1d`)。
4. 挿入 (`0xea6f3c`〜`0xea700a`): 末尾から、直前要素の id が idx より大きい間は要素を 1 つ後ろへ移す (id は dword 複写、+4 のポインタは `0x4133f0` で付け替え)。idx の位置に id を書く。結果は id 昇順。
5. 挿入位置の +4 に値を入れる (`0xea700d`〜`0xea704b`): `item(idx)` を材料に `0xbb1990(out, …)` で値を作り、`0x4133f0` で格納する。値の意味は未同定。
6. `[O]→[+0x178]` の仮想呼出し (`0xea7069`。通知と推定)。
7. `r8b == 0` ならここで終了 (`0xea7076` → `0xea7247`)。**selectAll はこの経路のみ**で、`jumpToPattern` は呼ばれない。
8. `r8b ≠ 0` (selectPattern の value=1):
   - `[O+0x6c4] == 0` (`0xea7080`) のとき: グローバル A の `+0x10f0→+0x49e` が 0 なら `0x12d8af0(item(idx).+0xc)` (`0xea711b`)。非 0 なら、グローバル byte を退避して 0 にし、`0x12d8af0`・`0xdce130` を呼び、退避値を戻す (`0xea70a7`〜`0xea70f7`)。いずれも最後に `[O+0x6f4] = 1` (`0xea7124`)。
   - `[O+0x6c4] ≠ 0` (`0xea7130`): `0xfe8bb0(グローバル B, item(idx).+0xc)` で記録 rdi を得る。グローバル byte (`0x68520c`) が 0 なら `0xffe410(rdi)` で終了 (`0xea723f`)。非 0 なら `0xffaf50(rdi)` の後、次の分岐に入る。
     - L の件数が 1 (`0xea7189`〜`0xea71b0`): `0xfe8bb0(グローバル, item(idx).+0xc)` の記録の `+0x32d == 0` なら `0x11e84a0(パターン番号)`、非 0 なら `0x11e8720()`。
     - 件数が 1 でない (`0xea71bf`〜`0xea723c`): `0x11e8720()` の後、L の全要素 i について `esi = 0xea66b0(O, i)` の記録の `+0x32d` が 0 なら `0xff8a90(記録, dl=1)` を呼ぶ。
     - 最後に `0xffe410(rdi)`。
9. 終了時 (`0xea7248`): `0x412d60` で一時値を解放 (推定)。

### 2.2 clearSelection `0xea6a00` (rcx = O・dl = flag)

1. `0x418190(&L, desc)` で L を空にする (`0xea6a1a`)。要素ごとの処理はしない。
2. `dl ≠ 0` なら `[O]→[+0x178]` の仮想呼出し (`0xea6a2a`)。
- deselectAll (`0xd66500` → `0xd6654f` で `dl=1`) から呼ばれる。

### 2.3 deselectOne `0xea7280` (rcx = O・edx = idx)

1. `idx < 0` または `idx > 件数−1` なら `edi = 0` で終了 (`0xea72ad`)。
2. `r13b` = (`[O+0x6c4] == 0` かつ `item(idx).+0xc == グローバル C の dword`) (`0xea72b5`〜`0xea72dc`)。モードが非 0 なら `r13b = 0`。
3. L を走査し、id == idx の要素を探す (`0xea72fa`〜`0xea7378`)。見つかったら `dil = 1`、その後ろの要素を id (dword) だけ 1 つ前へ詰める (`0xea7344`〜`0xea7368`)。**+4 のポインタは詰めない**。
4. `dil ≠ 0` なら `0x417fc0(&L, desc, 1, 件数−1)` で L を 1 つ縮める (`0xea73a6`)。
5. `[O]→[+0x178]` の仮想呼出し (`0xea73b1`)。
6. `0xea75a0(O)` で L が非空かを得る (`al`)。
7. `r13b && al` なら `0xea66b0(O, 0)` (残りの先頭のパターン番号) を `0x12d8af0` へ (`0xea73c5`〜`0xea73d1`)。
8. そうでなく `[O+0x6c4] ≠ 0` なら、`0xfe8bb0(グローバル, item(idx).+0xc)` の記録に `0xff8a90(記録, dl=0)` を呼ぶ (選択フラグの解除)。
9. `edi` を返す (`dil` が立っていれば 1 = リストから外した)。

### 2.4 isInSelection `0xea7420` (rcx = O・edx = id) → al

`L` の件数を走査し、`L[i].id == edx` となる要素があれば `al = 1` で返す。無ければ 0 (`0xea7422`〜`0xea746e`)。L が null なら 0。引数は id (内部 index)。
- 呼出し元 `selectPattern` (`0xd66161`〜`0xd66175`): `rcx = O`、`edx = rec.+0x18` (内部 index)。`al` が真なら value=0 (解除)、偽なら value=1 (選択) にする (`0xd6617a`〜`0xd66188`)。
- 呼出し元の分岐 (`REPORT_PY208.md` の表と一致): value=0 → `0xea7280`、value=1 → `0xea6e50(r8b=1)` と、preview (`rec.+0x28 > 0`) なら `0xea6730` と `0xe4e7f0`。

### 2.5 endPreview `0xea6730` (rcx = O)

1. `[O+0x6f5] == 0` なら何もせず終了 (`0xea6739`)。非 0 なら 0 にする (`0xea6746`)。
2. `[O+0x6c4] == 1` かつ `[グローバル D]+0xd58 ≠ 0` のとき (`0xea6754`〜`0xea6764`): `idx = [O+0x6fc]` が `0 ≤ idx ≤ 件数−1` なら `0xfe8bb0(グローバル E, item(idx).+0xc)` の記録の `[rsi+0x170]` を呼ぶ (`dl=1`、`0xea67b8`〜`0xea67bb`)。範囲外なら呼ばない。どちらの場合も最後に `[グローバル D]+0xd58 = 0` (`0xea67c1`〜`0xea67c8`。範囲外の飛び先もここ)。
3. `[グローバル F]` の dword が 1 で、`[O+0x6bc]` と異なれば、`0x11ca4e0(旧値, dl)` を呼び、`[O+0x6bc]` を書き換える (`0xea67d6`〜`0xea6808`)。
4. `[O+0x6c0]` と `[グローバル G]` の dword が異なれば、`0x11ca5f0(旧値, dl)` を呼び、`[O+0x6c0]` を書き換える (`0xea680e`〜`0xea6837`)。
- 3・4 は、beginPreview が退避した値を戻す処理と読める (推定)。

### 2.6 beginPreview `0xe4e7f0` (rcx = O・edx = idx)

1. `[O+0x6f5] = 1` (preview 中)・`[O+0x6fc] = idx` (`0xe4e7f9`〜`0xe4e800`)。
2. `[O+0x6c4] == 0` のとき (`0xe4e813`〜`0xe4e915`):
   - `[O+0x6c0]` にグローバル G1 の dword を退避し、`[O+0x680]` にグローバル byte A を退避したうえで、別のグローバル byte B を 0 にする (`0xe4e81c`〜`0xe4e830`)。A と B は別のアドレス。
   - `[グローバル H→+0x7a8]` のオブジェクトの vtable `+0x1f0` を、`rdx = item(idx).+0xc`・`r8 = 1` で呼ぶ (`0xe4e86b`)。jumpToPattern (`REPORT_PY211.md`) と同じスロットの呼出し。
   - 直後に退避した byte を戻す (`0xe4e879`)。その後 `0x12d14e0`・`0x4232e0`・`0x737640`・`0x11e79d0`・`0x11caab0` (条件付き)・`0x11ca4e0`・`0x423980` を呼ぶ。`[O+0x6bc]` にグローバルの dword を書く (`0xe4e8f1`)。
3. `[O+0x6c4] ≠ 0` のとき (`0xe4e917`〜`0xe4e95a`): `[O+0x680]` にグローバル byte を退避し、`0xfe8bb0(グローバル, item(idx).+0xc)` の記録を `0xff5120` へ渡す。最後にグローバル D の `+0xd58 = 1` (`0xe4e95a`)。これが endPreview §2 の条件になる。

## 3. 確認した呼出し元 (`REPORT_PY208.md` との照合)

| 呼出し元 | 本 REPORT の確定 | 結果 |
|---|---|---|
| selectAll (`0xd66390`: `0xd6640a` で `r8 = 0`・`0xd6640d` で `0xea6e50`) | 0..件数−1 の各 i で `0xea6e50(O, i, r8b=0)` | 挿入のみ・`jumpToPattern` は呼ばれない (§2.1 の 7) |
| deselectAll (`0xd66500`: `0xd6654f` で `dl=1`) | `0xea6a00(O, dl=1)` | 全解除 (§2.2) |
| selectPattern (`0xd660e0`) | value=−1 → `0xea7420` で反転、value=0 → `0xea7280`、value=1 → `0xea6e50(r8b=1)` と preview | `REPORT_PY208.md` の分岐表と一致 |

## 4. 検証

| 検証 | コマンド | 結果 (測定 commit `86fc25c8a`) |
|---|---|---|
| 本体の命令列 | `FL_WIN64_DIR=$RUNNER_TEMP/py336 python3 analysis/flapi/pe_py336_probe.py` | rc 0・6 関数すべて OK・所要 0.089 秒 (real) |
| negative control | `... pe_py336_probe.py --negctl` (選択 flag の書込みを `0` に変えた期待で検査) | rc 1・`setSelected` が `NG missing=['mov byte ptr [rax + 0x6f4], 0']`。検査が効いている |
| 測定時の load | `uptime` | 0.01 / 0.05 / 0.06 |

## 5. 未確定 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| vtable 呼出し先の意味: `[O]+0x178` (通知。`0xea6e50`・`0xea6a00`・`0xea7280` が使う)・`+0x170` (`0xea6730`)・`+0x1f0` (`0xe4e7f0`・`0xea70d2` の jumpToPattern と同じスロット) | 通知の内容と、preview 中の再描画・保存の挙動 | #3538 (PY-282 の親) |
| モード byte `[O+0x6c4]` の意味 (0/1 以外の値の有無を含む) と、グローバル A・B・C・D・F・G・H の役割 | 選択の 2 分岐 (§2.1 の 8・§2.3 の 2・§2.5 の 2) の意味づけ | #3538 |
| `0xea7280` の詰めが id (dword) だけで、+4 のポインタを詰めない件。`0x417fc0` (縮小) が末尾要素の +4 ポインタを解放するかは未読 | 参照の残存・解放漏れの有無 (実機の挙動は未確認) | #3538 (要確認。実装時に前提にしない) |
| 補助関数の本体: `0xbb1990` (out の値の意味)・`0xdce130`・`0x12d14e0`・`0x4232e0`・`0x737640`・`0x11e79d0`・`0x11caab0`・`0x11ca4e0`・`0x11ca5f0`・`0x423980`・`0xffaf50`・`0xff5120`・`0xffe410`・`0x11e84a0`・`0x11e8720`・`0x418190`・`0x417fc0`・`0x412d60` | 各分岐の副作用の細部 | #3538 |
