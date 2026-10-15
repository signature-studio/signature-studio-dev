# PY-188 (#3338): `0x8ed012` の Self (G1 = `0x8ecbc0`) の出所を 5 件の呼出し元から確定し、chan 判定

既知類型との関係: 該当なし (PE の機械語を直接読む静的解析。lift の IR・`kh_lower`・ldfix を使わないため `docs/DEFECTS.md` D1a〜D25 のどれにも当たらない)。

親: #2701 (`[PY-86]`)。前段: `REPORT_PY67_2159.md` §2 (G1 の 5 呼出し元の表。Self 未確定)。`REPORT_PY67.md`・`REPORT_PY71.md` の `py71_vmt.py` の読み方 (自己ポインタ・TypeInfo 名・親鎖) に従う。

## 結論

受入 1・2 の 5 件 (G1 の直接呼出し元 `0x8ecbc0` は 5 件、`py67_callers.py` と一致)。

| 呼出し元 (G1 への call) | 1 段上 (L1 関数の入口 rcx の保存 slot) | 2 段上 (L1 を呼ぶ箇所: rcx の出所・dl) | Self の VMT (大域 V = `[rip+d]` の値) | 受入 2 の判定 |
|---|---|---|---|---|
| `0xac4c8b` | L1 = `0xac4b50` (`[rbp+0x370]`) | `0xad028d` (関数 `0xad0260`): rcx = 大域 `0xac2640` → V = `0xac2708`、dl = 1 | `TVSTPlugin` (`0xac2708`) | **非 chan → 除外** |
| `0xb4b619` | L1 = `0xb4b5b0` (`[rbp+0x70]`) | `0xb648a4` (関数 `0xb64880`): rcx = 大域 `0xb448d8` → V = `0xb449a0`、dl = 1 | `TVST3Plugin` (`0xb449a0`) | **非 chan → 除外** |
| `0xb6655f` | L1 = `0xb664d0` (`[rbp+0x320]`) | `0xb69cc5` (関数 `0xb69c90`): rcx = `rax` = 大域 `0xb65500` → V = `0xb655c8`、dl = 1 (`mov r8b,1; mov edx,r8d`) | `TGenericPlugin` (`0xb655c8`) | **非 chan → 除外** |
| `0xb6db99` | L1 = `0xb6db00` (`[rbp+0x80]`) | `0xb75f64` (関数 `0xb75f40`): rcx = 大域 `0xb6a280` → V = `0xb6a348`、dl = 1 | `TCLAPPlugin` (`0xb6a348`) | **非 chan → 除外** |
| `0xc9e07c` | L1 = `0xc9dfd0` (`[rbp+0x90]`) | `0xca258a` (関数 `0xca24e0`・入口 rcx 保存 slot `[rbp+0x90]`、dl = 0) ← `0xca4713` (関数 `0xca43a0`): rcx = 大域 `0xca1508` → V = `0xca15d0`、dl = 1 | `TARPlugin` (`0xca15d0`) | **非 chan → 除外** |

- **受入 1 (Self の出所)**: 5 件すべて、Self は「呼出し元が dl = 1 で渡した大域の class ref (VMT) から `0x410320` (NewInstance 相当) が作ったインスタンス」まで確定した。5 件とも Self の型は大域 V のクラス。`0xc9e07c` だけ 3 段 (L1 → L2 `0xca24e0` の入口 rcx をそのまま渡す → L3 `0xca4713` の大域)。
- **受入 2 (VMT と chan 判定)**: VMT 5/5 確定 (`py71_vmt.py` で自己ポインタ・TypeInfo 名・クラス名の 3 者一致、§5)。5/5 とも親鎖は `TBaseAudioPlugin → TObject` (`0xca15d0` のみ `TBridgedPlugin → TBaseAudioPlugin → TObject`)。親鎖に `TChannel` は現れない。よって **5 件とも非 chan → 除外**。
- **受入 1・2 の判定**: 達成 (5/5)。ただし残る限界 (§7 未解決) は「この経路が実行時に到達するか」と「`NewInstance` が `[obj] = VMT` を書くか」。前者は L2 の直接呼出し元が 4 件無いため未確認。後者は `0x40fb40` を読んで確認済み (§1 末尾)。残るのは前者 (到達性) だけで、VMT の確定には不要な段。結論 (非 chan) を覆す根拠は見つかっていない。
- `REPORT_PY67_2159.md` §2 の「5 件とも Self 未確定」は本 REPORT で置き換える。

## 1. 経路・根拠 (1 件ずつ)

共通の機構 (`0x410320` と `0x40f960`、いずれも逆アセ):

- `0x410320`: `mov rax, rcx; test dl, dl; jl ...; mov rcx, rax; call [rax-0x30]`。dl ≥ 0 のとき rcx の値 (VMT) で VMT-0x30 のスロットを呼ぶ。
- 5 件の VMT (と `TARPlugin`) は、すべて VMT-0x30 のスロットが `0x40f960` (`py71_vmt.py ... 0x30` で 5 件とも同値)。
- `0x40f960`: `mov rbx, rcx; movsxd rcx, [rbx-0x80] (インスタンスサイズ); call 0x409410 (GetMem 相当); mov rcx, rbx; mov rdx, rax; call 0x40fb40`。`rbx` に VMT が残るので、確保したインスタンスは VMT 由来のサイズで作られる。
- `0x40fb40` (`py59_func.py $P 0x40fb40 dump`): `0x40fb4b: mov rbx, rcx` (第 1 引数 = VMT)、`0x40fb4e: mov rsi, rdx` (第 2 引数 = obj)、`0x40fb66: mov [rsi], rdi` (rdi = rbx = VMT)。よって `[obj] = VMT` を書く。Self の型 = 大域 V のクラス、の前提はこれで確認した。

各 G1 呼出し元 (L1) の共通形: 入口で `mov [rbp+K], rcx` (K = 上表の slot)。dl != 0 なら `call 0x410320` の戻り値を K に格納。直後に `xor edx, edx` (dl = 0) で `call 0x8ecbc0` (G1)。G1 の Self = `mov rcx, [rbp+K]`。

1. **`0xac4c8b`** (L1 `0xac4b50`):
   - `0xac4c0b: mov [rbp+0x370], rcx` (入口)、`0xac4c4b..0xac4c5a`: dl != 0 なら `call 0x410320`。
   - `0xac4c68: mov rcx, [rbp+0x370]`、`0xac4c6f: xor edx, edx`、`0xac4c8b: call 0x8ecbc0`。
   - L1 の呼出し元 `0xad028d` (関数 `0xad0260`): `0xad0269: mov rcx, [rip-0xdc30]` → 大域 `0xac2640` (= 0xad0270 − 0xdc30)。値 `0xac2708` (VMT・.text 内)。`0xad0270: mov al, 1`、`0xad0288: mov edx, eax` → dl = 1。`0xad028d: call 0xac4b50`。
   - Self = NewInstance(`0xac2708`) = `TVSTPlugin` 系のインスタンス。
2. **`0xb4b619`** (L1 `0xb4b5b0`): 入口 `0xb4b5bd: mov [rbp+0x70], rcx`。G1 直前 `0xb4b5f9: mov rcx, [rbp+0x70]`、`0xb4b5fd: xor edx, edx`。上流 `0xb648a4` (関数 `0xb64880`): `0xb64889: mov rcx, [rip-0x1ffb8]` → 大域 `0xb448d8`、値 `0xb449a0`。`mov al,1`/`mov edx,eax` で dl = 1。Self = `TVST3Plugin`。
3. **`0xb6655f`** (L1 `0xb664d0`): 入口 `0xb664e0: mov [rbp+0x320], rcx`。上流 `0xb69cc5` (関数 `0xb69c90`): `0xb69c99: mov rax, [rip-0x47a0]` → 大域 `0xb65500`、値 `0xb655c8`。`0xb69cb9: mov rcx, rax`。dl は `0xb69ca0: mov r8b, 1` → `0xb69cbc: mov edx, r8d` で 1。Self = `TGenericPlugin`。
   - 注: `0xb69cb0: mov rcx, [rcx+0x20]` は後で rcx を上書きし、5 番目の引数 (スタック) を作るだけ。Self には効かない。
4. **`0xb6db99`** (L1 `0xb6db00`): 入口 `0xb6db27: mov [rbp+0x80], rcx`。上流 `0xb75f64` (関数 `0xb75f40`): `0xb75f49: mov rcx, [rip-0xbcd0]` → 大域 `0xb6a280`、値 `0xb6a348`。dl = 1 (`mov al,1; mov edx,eax`)。Self = `TCLAPPlugin`。
5. **`0xc9e07c`** (L1 `0xc9dfd0`): 入口 `0xc9dffd: mov [rbp+0x90], rcx`。`0xc9e059: mov rcx, [rbp+0x90]`、`0xc9e060: xor edx, edx`。上流 L2 `0xca258a` (関数 `0xca24e0`): 入口 `0xca24ee: mov [rbp+0x90], rcx`、`0xca2550: mov rcx, [rbp+0x90]`、`0xca2557: xor edx, edx`、`0xca258a: call 0xc9dfd0`。L2 の dl (入口 `[rbp+0x98]`) が 1 のとき `0xca252f: call 0x410320` で作る。L2 の呼出し元 L3 `0xca4713` (関数 `0xca43a0`): `0xca46ef: mov rcx, [rip-0x31ee]` → 大域 `0xca1508`、値 `0xca15d0`。`0xca46f6: mov dl, 1`。Self = NewInstance(`0xca15d0`) = `TARPlugin`。

L2 の 4 件 (`0xad0260`・`0xb64880`・`0xb69c90`・`0xb75f40`) は直接呼出しが無い (`py67_callers.py` の直接呼出し 0 件。絶対 8 バイト参照のみ、§7)。大域 V は L2 のコード自身が読むので、VMT の確定には呼出し元が要らない。

## 2. 分類 (受入 1 の段の型)

- (a) 構築の VMT が確定: **5/5**。VMT は `[rip+d]` で読む大域 (= VMT 自己ポインタ slot、`qword(G) == G + 0xc8`) の値。py71 の自己ポインタ判定で確認 (§5)。
- (b) 上流の出所が特定できたが VMT の確定まで届かない: **0/5**。
- (c) 間接参照・ループ等で辿れない: **0/5** (ただし L2 の到達性は §7)。

## 3. 機械的な判定の流れ (`py188_self.py`)

1. `.text` を 1 回線形走査して直接 call の一覧を作る (`py67_callers.py` と同じ走査)。G1 の呼出し元 = 5。
2. 各呼出し元の関数を `.pdata` で求め、関数内で呼出しの直前の `mov rcx, ...` を読む:
   - `[rip+d]` → 大域 G (次命令 + d)、値 V = qword(G)。
   - `rax` → 直前の `mov rax, [rip+d]`。
   - `[rbp+K]` → 同じ関数の入口に `mov [rbp+K], rcx` があれば pass-through。呼出し元 (direct call) へ上がる (最大 3 段)。
3. dl の設定 (`mov dl,N` / `xor edx,edx` / `mov al,N; mov edx,eax` / `mov r8b,N; mov edx,r8d` / `movzx rdx, [rbp+K]`) を読む。
4. V について `V − 0xc8 == V` 相当 (自己ポインタ)、クラス名・インスタンスサイズ・親鎖 (親 VMT = 格納値 + 0xc8) を出し、親鎖に `TChannel` が有れば chan。

出力 (`py188_self.py $P`、§6):

```
# direct calls to G1 0x8ecbc0: 5
-- 呼出し 0xac4c8b (関数 0xac4b50..0xac5ec0)
   [0] call 0xac4c8b in 0xac4b50: rcx=slot 0x370  dl=imm 0
   [1] call 0xad028d in 0xad0260: rcx=global 11281984  dl=imm 1
       大域 0xac2640 の値 0xac2708: VMT OK 0xac2708 name=TVSTPlugin ... => 非 chan (除外)
(以下 4 件も同形。5 件目は [2] まで)
== ネガティブコントロール (非 VMT)
   0xebef68: VMT NG (V=0xebef68 の自己ポインタ不一致)
```

(注: `rcx=global 11281984` は 10 進表示。`0xac2640` と同じ。表示の改善は行わない。)

## 4. ネガティブコントロール

- 非 VMT の `0xebef68` (`REPORT_PY67_2159.md` の VMT `0xebef58` + 0x10 相当の番地): `py71_vmt.py $P 0xebef68 0x30` で `[-0xc8] self = 0x0 (NG)`、`[-0x88] classname = 0x6f3290` (名前 NG)、`[-0x80] instsize = 0x40fcd0` (不正)。自己ポインタ NG 1/1、名前 NG 1/1。`py188_self.py` の NC も `VMT NG` (1/1)。
- 大域 slot 自体を VMT とみなす誤り (`py71_vmt.py $P 0xac2640`): `[-0xc8] self = 0x100b97bf4058390 (NG)`。大域は VMT ではなく VMT-0xc8 の slot で、VMT 判定で弾かれる (期待どおり NG)。
- 手計算の誤り (§8) で一度読み間違えた番地 `0xca3508` (値 `0x097ec13b48c96348`) は、自己ポインタ NG。正しい `0xca1508` (値 `0xca15d0`、自己 OK) と区別できた。

## 5. 検算 (別アルゴリズム)

人手の逆アセ読み (`py59_func.py ... dump` の行を目で読む) と `py188_self.py` の出力を突き合わせた:

| 呼出し元 | 人手 (dump 行) | script | 一致 |
|---|---|---|---|
| `0xac4c8b` | `0xac4c68: mov rcx,[rbp+0x370]`・`0xac4c6f: xor edx,edx` | rcx=slot 0x370、dl=0 | 一致 |
| `0xb4b619` | `0xb4b5f9: mov rcx,[rbp+0x70]`・`0xb4b5fd: xor edx,edx` | slot 0x70、dl=0 | 一致 |
| `0xb6655f` | `0xb6653c: mov rcx,[rbp+0x320]`・`0xb66543: xor edx,edx` | slot 0x320、dl=0 | 一致 |
| `0xb6db99` | `0xb6db76: mov rcx,[rbp+0x80]`・`0xb6db7d: xor edx,edx` | slot 0x80、dl=0 | 一致 |
| `0xc9e07c` | `0xc9e059: mov rcx,[rbp+0x90]` | slot 0x90、dl=0 | 一致 |
| `0xad028d` | `0xad0269: mov rcx,[rip-0xdc30]`・`0xad0288: mov edx,eax` (al=1) | global・dl=1 | 一致 |
| `0xb648a4` | `0xb64889: mov rcx,[rip-0x1ffb8]`・dl=1 | global・dl=1 | 一致 |
| `0xb69cc5` | `0xb69cb9: mov rcx,rax` (rax=`0xb69c99` の大域)・`0xb69cbc: mov edx,r8d` (r8b=1) | global・dl=1 | 一致 |
| `0xb75f64` | `0xb75f49: mov rcx,[rip-0xbcd0]`・dl=1 | global・dl=1 | 一致 |
| `0xca4713` | `0xca46ef: mov rcx,[rip-0x31ee]`・`0xca46f6: mov dl,1` | global・dl=1 | 一致 (番地は下記) |

- 大域の番地の算術 (人手と Python): `0xca46f6 − 0x31ee = 0xca1508`。人手の一度目の計算は `0xca3508` と誤り (差 0x2000)。`py67_qword.py` で `0xca3508` を読んで非 VMT と見えた。訂正後 `0xca1508` は VMT 自己 OK (`0xca15d0`)。script の出力は訂正後と一致。
- 他 3 個の大域番地 (`0xac2640`・`0xb448d8`・`0xb6a280`) は script と一致し、`py67_qword.py` で値 `0xac2708`・`0xb449a0`・`0xb6a348` を確認。`0xb65500` は `0xb655c8` (script と一致)。

## 6. 測定

- 測定 commit: `e42e9fae` (`feat(python): add py188_self for PY-188 (#3338)`。解析コードを変えた最後の commit)。作業枝の基点 HEAD `e7b2f170` (main 由来)。
- 差分 0 の証跡 (測定 commit から本節を書いた HEAD まで):

  ```
  $ git diff e42e9fae HEAD -- tools/python/analysis tools/python/src | wc -l
  0
  ```

- 実測 (wall・逐次・n=1。`nproc` = 4。load average は実行後の `/proc/loadavg` = `0.36 0.40 0.30`):
  - `py188_self.py $P`: 37.2 秒 (`.text` 線形走査が支配的)。
  - `py59_func.py` 6 関数の範囲: 15.3 秒 (1 関数あたり約 2.5 秒)。
  - `py67_callers.py $P 0xac4b50,0xb4b5b0,0xb664d0,0xb6db00,0xc9dfd0`: 37.0 秒。`py67_callers.py $P 0xad0260,...,0xca24e0`: 37.2 秒。
  - `py67_qword.py` (find 含む): 1 秒未満。`py71_vmt.py`: 1 秒未満。
- 再現コマンド (`tools/python` で実行。`P` は `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` で展開):

  ```
  P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
  python3 analysis/py188_self.py "$P"
  python3 analysis/py71_vmt.py "$P" 0xac2708,0xb449a0,0xb655c8,0xb6a348,0xca15d0 0x30
  python3 analysis/py71_vmt.py "$P" 0xebef68 0x30
  python3 analysis/py67_qword.py "$P" 0xac2640,0xb448d8,0xb65500,0xb6a280,0xca1508
  python3 analysis/py67_callers.py "$P" 0xac4b50,0xb4b5b0,0xb664d0,0xb6db00,0xc9dfd0
  python3 analysis/py59_func.py "$P" 0x40fb40 dump
  ```

- `py71_vmt.py` の 5 件 (測定値): `0xac2708` TVSTPlugin (instsize `0x9e0`)・`0xb449a0` TVST3Plugin (`0x980`)・`0xb655c8` TGenericPlugin (`0x7c0`)・`0xb6a348` TCLAPPlugin (`0x9c8`)・`0xca15d0` TARPlugin (`0x808`)。5 件とも自己 OK・名前 OK。VMT-0x30 は 5 件とも `0x40f960`。親鎖: 4 件は `0x8ec050` (TBaseAudioPlugin)、`0xca15d0` は `0xc9d290` (TBridgedPlugin → TBaseAudioPlugin → TObject)。
- 大域の値 (`py67_qword.py`): `0xac2640`→`0xac2708`・`0xb448d8`→`0xb449a0`・`0xb65500`→`0xb655c8`・`0xb6a280`→`0xb6a348`・`0xca1508`→`0xca15d0`。いずれも `.text` 内 (VMT 自己ポインタ slot = VMT-0xc8)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| L2 の 4 件 (`0xad0260`・`0xb64880`・`0xb69c90`・`0xb75f40`) に直接呼出し元が無い。絶対 8 バイト参照だけあり (ファイル offset `0x6ce858`・`0x7627c8`・`0x7682e8`・`0x7717a0`、`py67_qword.py ... find`)。参照の種類 (VMT スロット・関数ポインタ表) は未確認 | VMT 確定には影響しない。この経路が実行時に `0x8ed012` まで届くか (到達性) は未確定 | #2701 |
| | L3 `0xca4713` (関数 `0xca43a0`) の呼出し元は未追跡 | `0xc9e07c` の 3 段目より上 (この経路の到達性) | #2701 |
| 大域 (VMT 自己ポインタ slot、`0xac2640` 等) への書込み参照の有無は未確認 (`py66_riprefs.py` の全走査が必要。約 60 秒) | 大域の値が実行時に変わらない前提 (`.text` 配置から推定) | #2701 |

- 本 REPORT は Self の VMT と chan 判定 (受入 1・2) を達成した。上表の 3 件は、結論 (非 chan) の根拠ではなく、経路の実行到達性と大域の不変性に関する残り。子 issue は起票しない (実装作業ではなく検証の残り)。
- 受入 4 (`#2701` の本文) の判定: 達成 (5/5 の VMT 確定と非 chan 判定)。ただし上の残りを「達成の条件」にするかは親の判断。

## 8. 作業の注記

- 手計算の誤り: 一度 `0xca3508` と誤って読み、`py67_qword.py` でその値を「非 VMT」と見た。script と人手の再計算で `0xca1508` に訂正した。訂正前の読みは結論に使っていない。
- 限界: 呼出し元の探索は direct call のみ (`call imm`)。`call [reg+slot]`・`jmp` による間接経路は見ない (§7 の L2)。G1 への間接呼出しは `py67_callers.py` の対象外。
