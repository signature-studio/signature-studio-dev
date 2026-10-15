# Serum 2 SR-21: `.pdata` 外コード 20,467 ブロックの分類と cut 方針 (#1444 / 親 #71)

親: `REPORT.md` §11.3・§11.5 (`.pdata` 外ブロックの関数性)。
再現: `PY=python3 bash scripts/sr3_run.sh` → `bash scripts/sr21_run.sh` (`work/` 要・素材 `plugins-serum2` の Install exe 要)。
既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 前の静的分類。silent miscompile 類型は未触)。

## 0. 結論 (先出し)

- **前版 (PR #1604, 測定 commit `0959cd09`) の訂正**: 「未確定 19,115 ブロック / 217,141 B」は誤りだった。前版の `unref` 15,102 件のうち **15,061 ブロック / 130,736 B は NOP 命令だけのアラインメント・パディング**で、コードではない。原因は `sr3_gaps.py` のパディング定義が `0xCC`/`0x90`/`0x00` の単独バイトだけで、多バイト NOP (`0F 1F 44 00 00`・`66 2E 0F 1F 84 00 00 00 00 00` など) を拾えなかったこと。`REPORT.md` の「実コード約 318KB」も同じ理由で過大だった。
- 20,467 ブロック / 318,398 B を **8 区分**に分けた (§1)。gap 全体 463,748 B = ブロック間パディング 145,350 B (19,444 run) + ブロック 318,398 B で、assert で照合済み。
- **関数入口 (強)**: 直接 `call` の標的 844 ブロック (86,060 B)。全件に `.pdata` 内の参照元がある。
- **関数入口 (弱)**: `rip` 相対参照のみ 464 ブロック (11,800 B)。
- **分割 (strict 規則)**: 先頭への参照が `jmp`/`jcc` のみ 49 ブロック (3,562 B)。分割の確定ではなく、分割候補の判定規則 (§2)。
- **未確定 4,049 ブロック / 86,240 B**: `table_ptr` 3,928 / `ptr_single` 80 / `unref` 36 / `data` 5。lift 入口に使わない (§5)。
- **パディング 15,061 ブロック / 130,736 B** (NOP のみ) + ブロック間 19,444 run / 145,350 B。コードではないので lift 入力に含めない。
- cut 表 (`out/sr3_cut_table.tsv`) は変えない。gap ブロックと cut 関数の重なりは 0 件 (§3)。
- **SR-21b (RTTI vtable 照合, §7)**: `table_ptr` 3,928 件の 3,850 件 (98.0%) は MSVC x64 RTTI の vtable メンバー (関数入口)。未確定は 184 ブロック (vtable 外)。vtable メンバーは `.pdata` 外に 4,031 件 (先頭 3,936・途中 95)。OSS 名のメンバーは cut 窓の外に 17 件。

## 1. 分類 (`out/sr21_summary.txt`・`out/sr21_classify.tsv`)

判定は上から順に最初に当たったもの。区分は確度順。コードを含むブロックの両端にはパディング命令が無かった (`edge_padding_in_code_blocks` 0)。

| 区分 | ブロック | B | ret 含むブロック | 判定の根拠 | 確度 |
|---|---:|---:|---:|---|---|
| `entry_call` | 844 | 86,060 | 680 | 直接 `call` (E8) の標的 | 入口 (強) |
| `entry_rip` | 464 | 11,800 | 395 | `lea`/`mov` の rip 相対参照のみ | 入口? (弱) |
| `branch_only` | 49 | 3,562 | 39 | `jmp`/`jcc` の標的のみ (§2 の分割規則) | 分割候補 |
| `table_ptr` | 3,928 | 83,235 | 3,314 | 参照なし。`.rdata`/`.data` の 8 バイト連続値 (≥2 連続) がブロック先頭を指す | 未確定 |
| `ptr_single` | 80 | 1,267 | 10 | 参照なし。ポインタ 1 件のみ | 未確定 (弱) |
| `unref` | 36 | 1,597 | 18 | 参照なし・ポインタなし・clean decode | 未確定 |
| `data` | 5 | 141 | 1 | 参照なし・clean decode 失敗 | データ候補 |
| `padding` | 15,061 | 130,736 | 0 | 命令が全て `nop` / `int3` / `xchg ax,ax` | パディング |
| **合計 (ブロック)** | **20,467** | **318,398** | 4,457 | sr3 ブロックの B 数と一致 (assert) | |

- ブロック間パディング (`0xCC 0xCC` で切れた間の `0xCC`/`0x90`/`0x00` の run): **19,444 run / 145,350 B** (`sr3_gaps.py` の 145,350 と一致)。
- gap 全体: 29,354 区間 / 463,748 B = 145,350 + 318,398 (assert)。
- 非パディングのブロック: 318,398 − 130,736 = **187,662 B**。`REPORT.md` の「実コード約 318KB」は NOP を含む値だった。
- 参照の union: `.pdata` 側 index (`work/index.npz`) は `.pdata` chunk しか decode しないため、gap 内の参照元を欠く。gap ブロックの全命令を decode した参照を加えると、index に無い参照が 231 件増えた。分類の変化は、`unref` 15,102 件のうち 15,061 件が NOP のみでパディングへ、5 件が jmp 参照により `branch_only` へ。

## 2. 入口・分割の判定根拠

- `entry_call` 844 件の参照元 (call + rip) 数: 1 件 331 / 2 件 150 / 3 件 58 / 4 件 49 / 5 件以上 256。**844/844 に `.pdata` 内の参照元あり**、gap のみの参照元は 0 件。
- `entry_rip` 464 件: 参照元数 1 件 373 / 2 件 50 / 3 件 15 / 4 件 2 / 5 件以上 24。参照元が `.pdata` 内 461、gap のみ 3。rip 相対はデータ読みと区別できないため単独では入口と言えない。
- **分割 (strict 規則)**: 先頭への参照が 1 件以上の `jmp`/`jcc` で、`call`・rip 相対の参照が 0 件。対象 49 件。参照元は `.pdata` 内 12 件・gap 内のみ 37 件。末尾命令は `ret` 33 件・`jmp` 16 件。
  - 規則は分割の確定ではない (関数境界は静的に得られない)。ブロック境界が `0xCC 0xCC` のみのため、隣接からの連結も確認できない。
  - 5 件は `.rdata`/`.data` のポインタ一致も持つ。分類順で `branch_only` を優先した (`verify` の ptr_hit 5)。

## 3. 独立検算 (`scripts/sr21_verify.py`・`out/sr21_verify.txt`)

capstone を使わず、生バイト列の E8/E9/0F8x 走査と .rdata/.data のポインタで判定した (別アルゴリズム。命令境界に揃えていないため superset)。

| 区分 | blocks | E8 (call) 標的 | E9/0F8x (jmp/jcc) 標的 | 8B ポインタ 標的 |
|---|---:|---:|---:|---:|
| `entry_call` | 844 | 844 | 93 | 66 |
| `entry_rip` | 464 | 0 | 0 | 8 |
| `branch_only` | 49 | 1 | 49 | 5 |
| `unref` | 36 | 5 | 0 | 0 |
| `data` | 5 | 0 | 0 | 5 |
| 全体 | 20,467 | 851 | 142 | 4,092 |

- ネガティブコントロール (ブロック先頭 +1 バイト): call 1 件・ptr 0 件 (本来 851・4,092)。判定が偶然一致ではない。
- `unref` の生 E8 一致 5 件は命令境界の確認が未実施 (偽陽性か真の呼出か未確定)。
- **cut 表との重なり**: gap ブロックと cut 関数 (1,414 区間に統合) の重なりは **0 件**。cut 区間を +0x2000 ずらすと 469 件重なる (ネガティブコントロール)。
- cut 窓 (`out/sr3_cut_table.tsv` の library 窓): 217 ブロック / 2,280 B (sr3 ブロック単位)。内訳はパディング 164・`table_ptr` 30・`entry_call` 10・`entry_rip` 10・`ptr_single` 3。非パディング 53 件は cut 表に未登録 (§4)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未確定 184 ブロック (vtable 外。`table_ptr` 78・`ptr_single` 69・`unref` 36・`data` 1) の関数性。静的には到達未確認 | lift 入口として使えない。動的に到達した場合の扱いは §5 | #75 (動的トレース) |
| vtable メンバーの入口化 (§7)。cut 表・§5 の入口表は未改訂 | 強入口への反映は未実施 | #71 (次段) |
| vtable メンバー中の OSS 名 17 件 (ZL convolver 13・muParser 3・nlohmann 1) が cut 窓の外 (§7.4) | 除外漏れ (安全側: lift 側に残るだけ) | #71 (cut 表の窓拡張) |
| 分割 (strict) 49 件のうち 5 件はポインタ一致も持つ | 分割と表の根拠が重なる。分類順で `branch_only` 優先 | #71 |
| `unref` の生 E8 一致 5 件 (命令境界未確認) | 未確定の中に呼出されるものが残る可能性 | #75 |
| cut 窓内の非パディング隣接 53 ブロック (cut 表に未登録) | 除外漏れ (安全側: lift 側に残るだけ) | #71 (cut 表の窓拡張) |

## 5. lift 対象の方針 (本 issue の決定事項・提案)

1. **cut 表 (`out/sr3_cut_table.tsv`) は変更しない**。SR-21 の分類は cut 表の外側だけに適用し、重なりは 0 件。
2. **入口候補は 3 段で扱う** (lift 入口の追加は動的トレース #75 の到達確認後):
   - 強: `entry_call` 844 件 (86,060 B) → lift 入口候補に加える。
   - 弱: `entry_rip` 464 件 (11,800 B)・分割 (strict) `branch_only` 49 件 (3,562 B) → 候補。到達確認が無い限り入口にしない。
   - 未確定: `table_ptr` 3,928 件・`ptr_single` 80 件・`unref` 36 件・`data` 5 件 (計 4,049 件 / 86,240 B) → **lift 入口に使わない**。
3. **未確定ブロックが動的に到達した場合は fail-closed** (未知の入口に入ったら trap として止める)。この挙動は lift 側の実装 (#75 の範囲) で確認する。
4. **パディング** (15,061 件 / 130,736 B・ブロック間 145,350 B) はコードではないため、lift 入力に含めない。
5. 「入口候補 (強)」の 844 件は `.pdata` 33,791 件とは別の追加入口。wasm 再ビルドの除外範囲は変えない (`out/sr3_cut_table.tsv` のまま)。

## 6. 検証 (実測)

- 測定 commit: **`a327e9bd1`** (分類コード `scripts/sr21_classify.py`・`scripts/sr21_verify.py` と生成物 `out/sr21_*` を含む最後のコード変更。assert の追加と verify ラベルの修正。`sr21_classify.tsv`・`sr21_summary.txt` は前版と同一、`sr21_verify.txt` は label 行のみ変更)。前版の測定 commit `0959cd09` は訂正前。
- 素材: `plugins-serum2` から `Install_Xfer_Serum2_2.1.5.exe` を `tar --zstd -x` で単独展開 (1,313,084,056 B)。VST3 `Serum2_win64.vst3` の sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` (前版と同一)。
- **e2e 再現 (コミット済み HEAD で実行。コード・生成物は測定 commit と同一。測定 commit 以降のコード差分は下記 git diff で 0 行)**:
  - `PY=python3 bash scripts/sr3_run.sh`: 31.1 秒 (開始時 load 0.67)。VST3 sha256 一致。`out/` 差分 0。
  - `bash scripts/sr21_run.sh`: 7.8 秒 (開始時 load 1.47)。`out/sr21_*` 差分 0。
  - 検算 `sr21_verify.py` は sr21_run に含まれ、§3 の値を再現 (ラベルのみ `table_ptr blocks hit by data pointer: 3928`)。
  - 追加した assert `padding block is referenced` は通過 (パディング 15,061 件への参照 0)。
- 測定 commit 以降のコード差分 (`git diff a327e9bd1 HEAD -- tools/targets/serum2/scripts tools/targets/serum2/out`) は 0 行 (REPORT のみ変更)。

```
git diff a327e9bd1 HEAD -- tools/targets/serum2/scripts tools/targets/serum2/out
(出力 0 行)
```

## 7. RTTI vtable 照合 (SR-21b / `table_ptr` の由来)

測定 commit: **`58af49731`** (`scripts/sr21_vtable.py`・`scripts/sr21_run.sh`・`out/sr21_vtable*`)。入力は §3 と同じ `Serum2_win64.vst3` (sha256 `501e7bb3…5283`) と `out/sr21_classify.tsv`。

方式 (MSVC x64 RTTI): 8 バイト境界で、直前のスロット (vtable[-1]) が Complete Object Locator (COL) を指し、COL の signature == 1 かつ pSelf (COL+0x14、RVA) が COL 自身の RVA と一致するものを vtable とする。メンバーは、その後に続く `.text` を指す 8 バイト値の連続。クラス名は COL の pTypeDescriptor (COL+0x0C) → TypeDescriptor の名前 (+0x10) を分解したもの。

### 7.1 結果 (実測。`out/sr21_vtable_summary.txt`)

| 項目 | 値 |
|---|---:|
| COL signature == 1 の候補 (スロット -1 が `.rdata`/`.data` の COL を指す) | 3,633 (全件で pSelf 一致) |
| vtable | 3,633 |
| メンバー (異なる VA) | 9,504 |

メンバーの所在:

| 所在 | メンバー |
|---|---:|
| `.pdata` 関数入口 | 5,473 |
| gap ブロックの先頭 | 3,936 |
| gap ブロックの途中 | 95 |
| `.pdata` 内部 (入口でない) | 0 |
| その他 | 0 |

gap ブロック (非パディング 5,406) の区分別。「vt 先頭」は先頭がメンバーのブロック:

| 区分 (§1) | ブロック | vt 先頭 |
|---|---:|---:|
| `entry_call` | 844 | 59 |
| `entry_rip` | 464 | 7 |
| `branch_only` | 49 | 5 |
| `table_ptr` | 3,928 | 3,850 |
| `ptr_single` | 80 | 11 |
| `unref` | 36 | 0 |
| `data` | 5 | 4 |

### 7.2 対照

- ブロック先頭 +8 がメンバーに当たった数: **5**。期待値 (ランダム一致) は 5,406 × 9,504 / `.text` 10,593,792 B = **4.85**。対照は偶然一致の水準。
- vt 先頭でない未確定: `table_ptr` 78・`ptr_single` 69・`unref` 36・`data` 1 = **184 ブロック**。

### 7.3 解釈 (推定を含む)

- vtable メンバーは vtable 経由で呼ばれる関数入口である (定義上)。gap 上の入口は **4,031** (先頭 3,936 + 途中 95)。いずれも `.pdata` に無い。SR-21 §5 の「強」入口に加える根拠になる (cut 表は変えない。§7.5)。
- 途中の 95 件は、直前の 1 バイトが単独の `0xCC` (51)・`ret` (28)・その他 (16) で、2 連続 `0xCC` の区切り規則では分割されない。lift 単位をブロックにするなら、この 95 件で分割が要る。
- `data` 区分の 4 件は vtable メンバー。デコード失敗で `data` と判定したものは関数であり、区分が誤判定している。
- 名前の粗い分類 (正規表現。4,031 件): VSTGUI 497・Steinberg::Vst 等 108・`std::` (`_Func_impl_no_alloc` のラムダ) 290・Serum 本体のクラス (`SerumController`・`ProxyParameter` 等) 672・OSS 名 18・その他 2,446。VSTGUI と Steinberg の SDK は SR-3 の OSS 一覧に無い。framework 判定 (§3) の範囲で未整理。

### 7.4 OSS 名のメンバー (cut 窓の外)

OSS 名のメンバーは 18 件。うち 17 件が cut 窓の外。

- ZL convolver (`ZLFIRConvolve`・`ZLSingleFDLConvolve`・`ZLDualFDLConvolve`): 13 件 (窓外)
- muParser (`mu::ParserBase::D::change_dec_sep`): 3 件 (窓外)
- nlohmann (`nlohmann::json_abi_v3_12_0::detail::type_error`): 1 件 (窓外)

窓内の 1 件は `ZLSingleFDLConvolve` (タグ `zl_convolver`)。

### 7.5 判定と #71 への影響

- §4 の「`table_ptr` 3,928 件が vtable 由来か未照合」は、98.0% (3,850 件) が vtable メンバーと確定。残り 78 件は未確定のまま。
- cut 表 (`out/sr3_cut_table.tsv`、1,510 関数) は変えていない (§5-1 のまま)。vtable 由来の入口と窓外の OSS 17 件を cut と lift 入口に反映するのは次段 (#71)。

### 7.6 再現・検証

- 手順: 素材展開 (`tar --zstd -xf $ARTIFACTS_DIR/plugins-serum2.tar.zst Install_Xfer_Serum2_2.1.5.exe` → `$RUNNER_TEMP/serum2/`) → `PY=python3 bash scripts/sr3_run.sh` → `PY=python3 bash scripts/sr21_run.sh` (SR-21b は同スクリプトに組込み)。
- 実測 (測定 commit `58af49731`、worktree `ws-71`): `sr3_run.sh` 33.4 秒・rc 0・cut 1,510 関数 / 1,464,181 B を再現。`sr21_run.sh` rc 0・`sr21_vtable.py` 単体 1.3 秒 (real)。
- 既存の `out/sr21_*` は差分 0。新規は `sr21_vtable.tsv` (3,633 行)・`sr21_vtable_hits.tsv` (4,031 行)・`sr21_vtable_summary.txt` の 3 件。
- 測定 commit からの差分: `git diff 58af49731 HEAD -- tools/targets/serum2/scripts tools/targets/serum2/out` の出力は 0 行 (本節は REPORT のみの commit)。

```
git diff 58af49731 HEAD -- tools/targets/serum2/scripts tools/targets/serum2/out
(出力 0 行)
```
