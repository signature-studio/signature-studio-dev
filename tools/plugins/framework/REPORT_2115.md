# #2115 REPORT — 0x4181e0 の 0 引数呼出と `rcx` (前提の訂正。注釈の置換は付録 §12)

> **付録**: §10 の詳細は `REPORT_2115_APPENDIX.md` へ分割移動した (250 行上限のため。本文は改訂済み)。測定値の正本は付録 §10.3。

- 担当 issue: #2115 `[PLG-P0b-15]` (親 #2069 / 元 #2069 `[PLG-P0b-13]`)。
- 起点: `origin/main` 637b70de。branch `2115-plg-p0b-15-0x4181e0-rcx`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`extracted/block18983_PE.bin` を使用)、`work-fw-stage1` を worktree 直下の `tools/plugins/work/fw/` に展開。
- コード変更 (この時点の記録): 注釈は変更なし。`fw_hostfix.py` は 3b581236 と同一 (0x4181e0 注釈は `return 0` のまま)。以後、`0x4180d0`・`0x4181e0` の注釈は付録 §12 で置換済み。診断表示 (trace) のみ `fw_boot.c`・`fw_rt.c` に追加 (付録 §11)。TLS 0 埋めの stand-in は未採用の実験で、commit 91308efd に残す (戻した commit は 8858cc0f。§10)。

## 1. 結論

issue #2115 と REPORT_2069 §3.1 の前提「native `0x418190` が `rcx` を解放して返し、`0x4181e0` の戻り値はその `rcx`」は**成り立たない** (native 側 §2 で確認。lift 側の前 run の記録も同じ結論だが未検証)。
REPORT_2069 の解析は FW の PE (`block18983_PE.bin`) ではなく `block00031_PE.bin` に対して行われていた。

| 項目 | `block00031_PE.bin` (REPORT_2069 が解析した側) | `block18983_PE.bin` (FW PE・`fw_map.json` の対象) |
|---|---|---|
| `.pdata` で `0x418190` が関数先頭 | はい (`0x418190`〜`0x41820c`) | いいえ (`0x418190` は関数先頭でない) |
| `.pdata` で `0x4181e0` が関数先頭 | いいえ | はい (`0x4181e0`〜`0x418233`) |
| `fw_map.json` の `0x4181e0` 対応 | — | `0x7d8990` |

## 2. native `0x4181e0` (FW PE 側・確定)

逆アセンブル (capstone・`block18983_PE.bin`):

```
0x4181e0 sub rsp, 0x28
0x4181e4 cmp byte ptr [rip + 0x2fe0ed], 0
0x4181eb je 0x41821b
0x4181ed mov ecx, dword ptr [rip + 0x2bec7d]   ; ecx を上書き (rcx は入力でない)
0x4181f3 call 0x418030
0x4181f8 test rax, rax
0x4181fb jne 0x41822e
0x4181fd call 0x4180d0
0x418202 mov ecx, dword ptr [rip + 0x2bec68]
0x418208 call 0x418030
0x41820d test rax, rax
0x418210 jne 0x41822e
0x418212 mov rax, qword ptr [rip + 0x2fe0b7]
0x418219 jmp 0x41822e
0x41821b mov rax, qword ptr gs:[0x58]          ; TLS 配列
0x418224 mov ecx, dword ptr [rip + 0x2bec46]
0x41822a mov rax, qword ptr [rax + rcx*8]
0x41822e add rsp, 0x28
0x418232 ret
```

- 引数を取らない TLS getter。`rcx` は読まれる前に毎経路で上書きされるため、**入力の `rcx` は使われない**。
- 戻り値は TLS 値 (`gs:[0x58]` の配列要素) か、フォールバックのグローバル `[0x7162d0]` 系。
- 0 引数の呼出元が `rcx` を store しなくても、native の戻り値は変わらない。

## 3. lift 側 (前 run の記録・fix run では未検証)

`work-fw-stage1` は fix round 3・round 4 (2026-10-14) で展開し、件数だけ再確認した (IR の本体の読み書きは未再確認)。以下は REPORT_2069 §3.2 の前回 run の記録。

- 前回の記録: 0 引数版 `@function_4181e0()` (`fw0.restored.ll:7185`) は `[BLK+0x20..0x40]` と `[BLK+0x88]` を読み、`[BLK+8]` (= 9048072) を読まない。`9048072` を使う IR は 0 件。(再確認: `grep -c 'i64 9048072'` は 12 ファイル全て 0 件。本体の読み書きは未再確認)
- 前回の記録では、0 引数版の本体は `rcx` 非依存で、戻り値は `spec.select(TLS 経由の値, @global_var_7162d0)` の形を取る。(未再確認)
- 0 引数呼出元 (`grep -n 'call i64 @function_4181e0()' tools/plugins/work/fw/*.restored.ll` で IR 行を列挙。下表): work-fw-stage1 の 10 ファイルで計 75 件 (fw0 14・fw1 10・fw2 7・fw3 2・fw4 6・fw5 12・fw6 8・fw7 8・r2 8・r3 0)。REPORT_2069 §3.2 の 142 件は、この 75 に結合 IR `fw_all` の 67 件を加えた**二重計上の誤り** (`fw_all` は fw0〜fw7 の結合で archive に無い。67 は fw0〜fw7 の合計と一致)。

| ファイル (件数) | 行番号 (`call i64 @function_4181e0()` の行) |
|---|---|
| fw0 (14) | 2360 4335 4406 4432 4547 70151 70170 70189 70208 70227 70246 70265 70284 70303 |
| fw1 (10) | 2448 2506 2525 4978 6805 6829 6858 6877 49459 92020 |
| fw2 (7) | 3833 6586 6784 7001 7058 44779 200852 |
| fw3 (2) | 6196 6245 |
| fw4 (6) | 4446 44674 44718 44750 44805 163636 |
| fw5 (12) | 24860 24885 24994 25015 25034 25062 25109 39458 52055 52074 169839 169894 |
| fw6 (8) | 2228 2270 2331 2406 38743 38778 38838 38894 |
| fw7 (8) | 2480 2501 2524 2573 4468 50936 50997 51027 |
| r2 (8) | 7927 7949 7968 111403 111407 199141 297088 297100 |
- 引数付き呼出は r3 のみ 8 件 (r3 7054・7078・7100・82308・82312・144053・192518・192530)。0 引数定義との不一致は残る (受入 1 の付随確認・今回未検証)。

## 4. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | 0 引数呼出元で `rcx` が失われる経路を確定し、REPORT に呼出元の IR 行を列挙 | **達成**。(a) native の getter は `rcx` を読まない (§2: 全経路で上書きされてから読まれる)。よって 0 引数呼出で `rcx` が失われても戻り値は変わらず、`[BLK+8]` の復元や呼出の版の統一は不要 (注釈版も `rcx` を読まない)。(b) lift 側の 0 引数呼出元 75 件の IR 行を §3 の表に列挙。native 呼出元 68 件は §5 |
| 2 | 正しい戻り値を確定し `fw_hostfix.py` の 0x4181e0 注釈を修正 | **達成** (付録 §12・eeb6babf)。戻り値は per-thread block (0x288 byte) と確定 (§2・付録 §11.2)。注釈を native の TLS getter 意味に置換し、`fw_stage2` SMOKE PASS・Phase A `dispatch=38 ff=0` を維持。Phase B の変化 (失敗位置の target `0 → 0x1712`) を実測。Phase B の OOB 解消 (E2E PASS) は本 issue の受入ではなく #2911 へ移管 |
| 3 | 実測 (所要・load・PASS/FAIL) とネガティブコントロール | **達成 (n=1)**。§8 (注釈あり・注釈削除) と付録 §12.3 (ネガティブコントロールは「対照: 現注釈 (`0x4181e0` `return 0`)」行。HEAD 行と同じ表で所要・load・PASS/FAIL を記録)。n≥3 の min–max は未実施で #2911 (受入 3) |

## 5. native 呼出元 (`block18983`・`call 0x4181e0` の直接 rel32)

`.text` の `E8` rel32 走査で call site 68 件 (capstone の線形走査と一致)。含む関数は 28 個。表の 1 行 = 1 call site。

| 関数 VA | call site VA |
|---|---|
| 0x4070f0 | 0x4070ff |
| 0x4070f0 | 0x407121 |
| 0x4070f0 | 0x40715c |
| 0x4071a0 | 0x4071ac |
| 0x4071a0 | 0x4071c2 |
| 0x4071a0 | 0x4071e0 |
| 0x407200 | 0x407204 |
| 0x407230 | 0x407234 |
| 0x407260 | 0x407265 |
| 0x4072d0 | 0x4072f7 |
| 0x407350 | 0x407358 |
| 0x407380 | 0x407387 |
| 0x4073c0 | 0x4073c5 |
| 0x4073c0 | 0x4073d0 |
| 0x40cc80 | 0x40cff9 |
| 0x40cc80 | 0x40d1b8 |
| 0x40cc80 | 0x40d36a |
| 0x40cc80 | 0x40d3c4 |
| 0x40d5d0 | 0x40d5e7 |
| 0x40d5d0 | 0x40d641 |
| 0x40d860 | 0x40d866 |
| 0x40d8b0 | 0x40d8b9 |
| 0x40d8b0 | 0x40d8f7 |
| 0x40d8b0 | 0x40d90b |
| 0x40d8b0 | 0x40d95c |
| 0x40d980 | 0x40d98a |
| 0x412f60 | 0x412f69 |
| 0x412f60 | 0x412f77 |
| 0x412f60 | 0x412f91 |
| 0x412f60 | 0x412f9d |
| 0x463730 | 0x463737 |
| 0x463730 | 0x463746 |
| 0x463730 | 0x46377c |
| 0x463730 | 0x4637a0 |
| 0x463730 | 0x4637ac |
| 0x463730 | 0x4637bb |
| 0x463730 | 0x4637d9 |
| 0x4e5ed0 | 0x4e5eda |
| 0x4e5ed0 | 0x4e5efc |
| 0x4e5ed0 | 0x4e5f08 |
| 0x4e5ed0 | 0x4e5f38 |
| 0x4e5f50 | 0x4e5f59 |
| 0x4e5fc0 | 0x4e5fc6 |
| 0x4e5fc0 | 0x4e5fd7 |
| 0x4e5fc0 | 0x4e5fff |
| 0x4e5fc0 | 0x4e6031 |
| 0x4f4f90 | 0x4f51b5 |
| 0x4ff2f0 | 0x4ff301 |
| 0x4ff9f0 | 0x4ff9f5 |
| 0x4ff9f0 | 0x4ffa24 |
| 0x4ff9f0 | 0x4ffa30 |
| 0x506230 | 0x506296 |
| 0x506230 | 0x5062a2 |
| 0x5567e0 | 0x5567f8 |
| 0x5567e0 | 0x556807 |
| 0x5567e0 | 0x556816 |
| 0x5567e0 | 0x556825 |
| 0x5567e0 | 0x556834 |
| 0x5567e0 | 0x556843 |
| 0x5567e0 | 0x556852 |
| 0x5567e0 | 0x556861 |
| 0x5567e0 | 0x556870 |
| 0x5ae990 | 0x5ae9a9 |
| 0x6b8e80 | 0x6b90a8 |
| 0x6b92f0 | 0x6b9383 |
| 0x6b92f0 | 0x6b93ab |
| 0x6b9e70 | 0x6b9eea |
| 0x6b9e70 | 0x6b9f26 |

- 「呼出元で `rcx` が書き換えられるか」の分類は**本 REPORT では未実施**。線形走査で試算したが、分類の定義 (基本ブロック・分岐をまたぐか) を確定できず、数値を採用しない。
- 関数単位の件数 (例: `0x5567e0` 9 件・`0x463730` 7 件) は一覧から数えられる。ただし `rcx` 書換えの有無は §2 の通り戻り値に影響しない。

## 6. 実測

e2e の実測値の正本は 2 つに分ける: 注釈版の負のコントロールは §8 (c2f67568)、stand-in 版 (未採用) と対照は付録 `REPORT_2115_APPENDIX.md` §10.3 (stand-in 版の測定 commit 91308efd・対照 3b581236)。本節には測定値を書かない。

- 前 run (起点 637b70de) で行った素材展開 (`work-fw-stage1`・`fl-win64`) は、fix round 3 では `work-fw-stage1` のみ展開した (`fw_stage2.sh` と `hs_e2e.sh` は `fl-win64` を読まない)。round 3 の実測は付録 §10.3。
- REPORT_2069 の基準値 (Phase A `dispatch=38 ff=0`・Phase B OOB) は前回測定 (commit 0d9b5385) の記録で、本 REPORT は再掲しない。

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst            # repo ルートで展開 (§3 用・tools/plugins/work/fw/ に 12 ファイル)
# block18983_PE.bin の .pdata で 0x4181e0 が関数先頭 (0x418233 まで) / 0x418190 は先頭でないことを確認
# (pefile で DIRECTORY_ENTRY_EXCEPTION の BeginAddress を比較)
grep -c 'call i64 @function_4181e0()' tools/plugins/work/fw/*.restored.ll   # 10 ファイルで計 75 件 (IR 行は §3 の表)。REPORT_2069 の 142 件は fw_all (67 件) を加えた二重計上
grep -c 'i64 9048072' tools/plugins/work/fw/*.restored.ll                    # 0 件が期待値
```

native 側 68 件 (§5) の確認 (`pefile` で `.text` の raw bytes を読む。入力は `block18983_PE.bin` のみ):

```python
# 送り先 = 命令末尾 (E8 の位置 + 5) + rel32 が 0x4181e0 (VA) なら call site
# 関数 VA は DIRECTORY_ENTRY_EXCEPTION の BeginAddress (+ ImageBase) で範囲判定
import re, pefile
pe = pefile.PE("block18983_PE.bin"); b = pe.OPTIONAL_HEADER.ImageBase
t = next(s for s in pe.sections if s.Name.startswith(b".text"))
d = t.get_data()[: t.Misc_VirtualSize]; tb = b + t.VirtualAddress
for m in re.finditer(b"\xe8", d):
    o = m.start()
    if o + 5 <= len(d) and tb + o + 5 + int.from_bytes(d[o+1:o+5], "little", signed=True) == 0x4181E0:
        print(hex(tb + o))   # 68 行 (call site)
```

- 生の `E8` 走査 (上記) と capstone の線形逆アセンブル (`skipdata=True`) で call site が一致することを確認済み (68 件)。
- 関数 VA への写像は、上記の `pe.DIRECTORY_ENTRY_EXCEPTION` の範囲判定で行う (§5 の表の関数 VA 列)。

## 8. 実測 (測定 commit c2f67568 = origin/main・コード差分 0)

測定は 637b70de ではなく現行 main (c2f67568) で行った (REPORT_2069 の基準 0d9b5385 とは commit が異なる)。以下は PR 作成時点の測定 run の記録で、後続の fix run では再実行していない。

| 手順 | 結果 | 所要 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh --fresh` | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 ff=0) | 13 分 54.6 秒 (834.6 秒) | 0.64 / 0.39 / 0.16 (10:46:17) → 2.35 / 2.26 / 1.23 (11:00:12) |
| `hs_e2e.sh --fresh` (baseline・注釈あり) | rc 1 / Phase A `dispatch=38 ff=0` / Phase B `memory access out of bounds` / `status=0xffffffff plug=0x0 rec=8` / `E2E FAIL: 3 項目` | 2 分 26.7 秒 | 2.35 / 2.26 / 1.23 (11:00:12・stage2 終了時) → 1.11 / 1.76 / 1.18 (11:02:42) |
| `hs_e2e.sh --fresh` (変種: 0x4181e0 注釈を削除) | rc 1 / Phase A `dispatch=38 ff=0` / Phase B 同一 OOB / `rec=8` / `E2E FAIL: 3 項目` (同一文言) | 2 分 28.5 秒 | 0.67 / 1.59 / 1.14 (11:03:09) → 0.97 / 1.36 / 1.12 (11:05:38) |

- 測定 commit は c2f67568。本 PR のコード変更 (`tools/plugins/framework/fw_hostfix.py`) は変種実験後に元へ戻した (差分 0)。残るのは本節の追加のみ。
- 1 回測定 (n=1)。変動レンジは未取得。
- **負のコントロール**: 注釈 (`return 0`) を外しても Phase B の失敗は同一。よって、この注釈が Phase B OOB の原因ではない。REPORT_2069 の `rec=7` (1 項目) と異なり、現 main では `rec=8` / 3 項目で失敗している (注釈・Phase B 以外の変更で変化した可能性。原因は未確定)。
- 注釈の戻り値の正しい値は、この測定では確定しなかった。lift 本体の挙動 (`fw0.restored.ll:7185` は `rax` を返すだけで `[BLK+0x80]` に store しない、`[BLK+0x80]` を読むのは呼出元) は**前 run の記録であり、未再確認**。正しい戻り値は未確定のため、§8 の時点では `fw_hostfix.py` を変更していない (REPORT_2069 §4 の理由と同じ)。
- 検証 HEAD での再確認 (コード差分): `git diff c2f67568 HEAD -- tools/plugins/framework ':!*.md'` の出力は 0 行 (実行コードの変更なし)。

## 9. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fw_hostfix.py` の 0x4181e0 注釈 (`return 0`) の妥当性。正しい TLS 値 (`gs:[0x58]` 配列と `[0x7162d0]`) の確定 | 解消 (付録 §12 で native の TLS getter 意味に置換)。注釈の置換では Phase B OOB は解消せず (付録 §12.3) | — (解消) |
| lift 側 0 引数呼出元の IR 行 (ファイル名・行番号) の列挙: work-fw-stage1 の 75 件 (`fw_all` の 67 件は fw0〜fw7 の結合で加算しない) | 解消 (§3 の表) | — (解消) |
| `rcx` 書換えの有無による呼出元の分類 | 本 REPORT では採用せず (戻り値に影響しないため判断は不要) | 未実施のまま (定義を決めてから再測定) |
| REPORT_2069 §3.1 の解析対象の誤り (`block00031` を使用) | 前提の誤伝播 | 本 PR で §1 に訂正を記載 |
| r3 系の引数付き呼出 (8 件) と 0 引数定義の不一致 | 引数規約の不整合 | #2911 (受入 4) |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B OOB | #2534 (`[PLG-P0b-19]`・OPEN。#1890 → #1935 → #2008 → #2426 → #2534 の移管先) |
| 対照 (既定と同一コード) と stand-in 版 (未採用) の各 n=1 (`--fresh`・load 記録済み。付録 §10.3)。n≥3 の min–max は未実施 | 失敗位置 (`0x4e5fa6` の target 0 / `0x1712`) の解釈。stand-in 版を採用する判断の前提 | #2911 (受入 3 の n≥3。stand-in 版を採用する場合も同じ) |
| 同一の実行コードで §8 と付録 §10.3 の結果が食い違う。失敗位置の変化は n=1 で変動未評価 | Phase B 結果の解釈 | #2911 (注意) |
| `hostshim/hs_e2e.sh` の増分判定 (49 行目) が `fw_hostfix.py` の変更を見ない (`--fresh` の測定には影響しない) | plain 実行で古い `hs_flat3.ll` が混入する余地 | #2911 (注意。測定ハーネスの修正は再測定を伴うため未変更) |
| 基点 `9f403c97` (PR の merge-base) から `origin/main` (fix round 5 の取得時点 `064af0d8`) までに framework の 5 ファイルが変わった: `fw_smoke_check.py` (+42/-10)・`hostshim/hs_irfix.py` (+64)・`hostshim/hs_plug.c` (+17・`hs_fw_init_tls`・#2571)・`fw_269_verify.sh`・`fw_pack_stage1.sh` (各 1 行のコメント)。（fix round 5 時点の記述。現基点 `bbb07d80` は `origin/main` と framework 同一のため取り込み済み・付録 §12.3） | `fw_smoke_check.py` の判定は付録 §12.3 で測定済み (`runerr=1`・`init_reach=16` で FAIL。基準は `runerr=0 ff=0 init_reach=288`)。`dispatch=38` の PASS は完走の証拠にしない。main では既に FAIL (`REPORT_2571.md` §3・#2510) | #2510 (OPEN) |
| 基点 `9f403c97` の `hs_e2e_run` は framework 初期化 (TLS 初期化) を通らない。TLS 値を正しくしても OOB は残る (付録 §11.5 E3。E3 は n=1・所要と load は未記録 (ログも未保存))。main では #2571 (PR #2595・`9b352bd7`) が `hs_fw_init_tls()` で TLS 初期化を入れた。main の `REPORT_2571.md` §3 では初期化ありでも OOB が残る (本 PR では未測定) | 受入 2 (Phase B の変化) | #2911 (注意) |
| `0x418120` の実行経路の訂正: `_InitLib` の hooks 表 (`0x6d6ef8`・reason=1 → `[+8]`) からの間接 call で実行される (§10.1 の「呼ばれない」は誤り) | 前提の訂正 | 付録 §11.1 で訂正済み |
| lift の fold 欠陥: `function_4180a0` の引数 `ecx` が `ptrtoint @683` に化け、`function_4180d0` の戻り値が 1 になる | TLS block が正しく作られない | #2510 (`[PLG-P0b-18]`・OPEN。同じ類型の別インスタンスとしてコメントで追記)・付録 §11.3 |
| `fw_rt.c` 表示カウンタ分離 (commit `058c2049`) の再測定 | 解消。付録 §11.4.1 で再測定済み (Phase A `dispatch=38 ff=0`・Phase B は 4c00ec24 と同じ OOB・`rec=7`・1 項目)。基準との差は表示行の heap アドレス 3 件のみ | — (解消) |
| smoke 終端の `Aborted(Runtime error: The application has corrupted its heap memory area (address zero)!)` (smoke.log 47 行目。基準 4c00ec24 にも同一行。trace 由来ではない) | SMOKE PASS の判定には影響しない。address zero への書込みの有無は未調査 | #2911 (注意・原因は未調査) |

## 10. TLS index 未設定の確認と stand-in 版の実験 (未採用・測定 commit 91308efd)

- 確認事実 (TLS index は `0x418120` でしか設定されず、`0x6d6e70` は `.data` で `0xFFFFFFFF`) と stand-in 版 (`fw_hostfix.py` 0x4181e0: `TlsAlloc` + 0 埋めブロック) の定義・実測は付録 `REPORT_2115_APPENDIX.md` §10.1〜§10.3。
- **stand-in 版は未採用**。既定の注釈は 3b581236 の `return 0` のまま (戻した commit は 8858cc0f)。stand-in 版のコードは commit 91308efd を参照する。
- 実測 (付録 §10.3・全て n=1): 対照 (既定と同一コード) と stand-in 版はどちらも Phase B が OOB。§8 との食い違い・失敗位置の変動は付録 §10.3 を参照。**受入 2 は未達。効果は未確認。**
- 差分確認: 既定の注釈 (`fw_hostfix.py`) は対照 3b581236 と同一。framework 全体は 3b581236 から HEAD で 3 ファイル (`fw_boot.c`・`fw_rt.c`・`hostshim/hs_preinit.mjs`) が違う。実行コードの基準は測定 commit `058c2049` (`git diff 058c2049 HEAD -- tools/plugins/framework ':!*.md'` は 0 行)。
- HEAD の実行コードは測定 commit `058c2049` と同一のため、HEAD の実測は付録 §11.4.1 を引用する (WORKFLOW §6)。対照 3b581236 は既定の注釈 `fw_hostfix.py` の対照 (stand-in 版との比較) にだけ使う。
