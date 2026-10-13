# REPORT_419 — #419 の合流前・旧 ON 構成の測定 (REPORT.md §8 から無変更で分割移動)

REPORT.md は 250 行上限 (`docs/DOC_MAP.md` §1) のため、合流前 (`fa918df`・`c7061c6` 基準) の調査と旧 ON 構成 (410360 + 8cbda0/8cbce0、#503 前の main) の測定を本ファイルへ移した。内容は削除していない。現 HEAD の実測は `REPORT.md` §8.2。

## A. 旧 §8.2 `8cc190` 系の原因 (合流前)
`8cc190` 内の OOB 地点は `8cbcb0` の `[[rcx+8]-8]` (wasm offset 0x271497)。`rcx` は `8c7a10` が
`[g+0x410]` (= `8cbfa0` が作った TDictionary 様オブジェクト) から取り出した値。unit 53 で実測すると
`g+0x410 = 0x4c70c0` は **インスタンスではなくコードバイト列** (`[+0]=0x68ec834853565800` は機械語) だった。
`8cbfa0 → 40f9e0 (TObject.Create) → 410320 (ClassCreate stub) / 410360 (AfterConstruction stub)` で、
RetDec は 410320 / 410360 の **VMT 間接 call (`call [rax-0x30]` NewInstance / `call [rbx-0x50]`) を落とし `ret arg1` だけの関数**にしていた
(DEFECTS D15 型。call site は IR 上 410320 が 493、410360 が 492)。このため TObject.Create は確保せず VMT/コード領域を `this` として扱う。

## B. 合流前の修正試行とネガコン (旧)
**修正の試行 (合流前, #414 HEAD `fa918df`)** (`m11_ov.c` に `M11_OV_CLASSCREATE=1` で有効化する形で保存、既定 OFF):
`410320`/`410360` を C に転記し、NewInstance 実体 `40f960`(GetMem→InitInstance) と `40fb40`/`40fac0` (InitInstance・管理フィールド初期化) を
逆アセンブル (`disasm_img.py`) から C で再実装。加えて `8cbda0`/`8cbce0` (TDictionary の comparer 間接 call 脱落) も転記。

| 構成 (合流前) | ok | oob | halt0 | miss | 備考 |
|---|--:|--:|--:|--:|---|
| ベースライン (既定 OFF) | 830 | 44 | 20 | 46 | |
| 410320/410360 のみ | 830 | 30 | 31 | 49 | unit 114 が**ハング** (abort→hang、`5c00e0`→`439670` の探索ループ) |
| + 8cbda0/8cbce0 | 830 | 41 | 20 | 49 | 8cc190 系 11 unit は**全て OOB のまま** |

unit 遷移 (+8cbda0/8cbce0): oob→ok 4 / ok→miss 3 (42 45 415) / ok→oob 2 (85 719) / abort→hang 1 / oob→halt0 1 / halt0→ok 1。
合流前は **trap 総数が減っていない (ok 830 のまま、退行 5 件が改善 4 件を相殺)** 結果だった (現 tree での判定は下の「合流後の再測定」)。
退行 5 件は 410320 転記が実際にオブジェクトを確保するようになった副作用で、確保後に別の欠陥 (85: `409470` 経由, 719: `409410` 内 `407a50`) が顕在化した。
8cc190 系 11 unit が OOB のままなのは、確保後もなお `8c7a10` の入力 (`rcx` 先) が不正なため (unit 53 でも `8cbcb0` で OOB)。
次の調査対象は NewInstance 後の `[g+0x410]` の中身と `8cbfa0` の `cls` 引数 (VA 0x4bd878→LVA 同値) の VMT 内容。

**ネガコン**: 既定 OFF で build し直した survey は ベースラインと unit 単位で完全一致 (差 0、ok 830 / oob 44 / halt0 20 / abort 1 / miss 46)。
OFF のまま e2e 入口 (`m11_run.mjs`) は不変、units_run 17/942。

## C. 合流後の再測定 (旧ブロック、#503 前の main)
#### 合流後の再測定 (#503 より前の main `021fd75` 系 + 旧 ON ブロック = 410360 + 8cbda0/8cbce0。コード HEAD `cf327ba`)

**この節の表は #503 マージ前の測定で、ON の内容も旧ブロック (410360 + 8cbda0/8cbce0) のもの。現 main (#503 で 8cbce0 / 8cc190 / 8cbde0 / ov_dict_hash が既定 ON) の
「ON = 410360 のみ」には当てはまらない。現 main での再測定は未実施** (最後の merge 解消 run は素材 `fl-win64` のみで `work-m11` / emsdk が無く build / survey 不可。
`oc_artifacts: toolchain-emsdk work-m11` で再測定する)。以下の手順の `function_8cbda0` 確認は現ブロックでは `function_410360` のみに読み替える。

手順: `bash m11_build.sh` (既定 OFF) / `M11_OV_CLASSCREATE=1 bash m11_build.sh` (ON) → `node trap_triage/survey_units.mjs out.json` → `survey_diff.py off.json on.json`。
`m11_build.sh` が `M11_OV_CLASSCREATE` を `-D` で `m11_ov.c` に渡し、`work/ov_classcreate.stamp` で `work/obj/ov.o` を無効化する (ON/OFF の切替で古い ov.o を再リンクしない。
ON ビルドで `cc m11_ov.c` が走り `ov.o` に `function_410360`/`function_8cbda0` が入ることを `llvm-nm` で確認)。マクロは値で判定 (`=0` は OFF)。
build 8.0 s / survey 8.7 s (load average 0.4〜0.6、PE 無し・work-m11 スナップショット、942 unit)。

| 構成 | ok | oob | halt0 | miss | trap (oob+halt0) | 備考 |
|---|--:|--:|--:|--:|--:|---|
| 既定 OFF | 816 | 14 | 65 | 46 | 79 | main の `m11_ov.c` を build した対照と 942 unit 全て一致 (kind 差 0、icall 差 0)。`=0` 明示も同一 |
| ON | **847** | 36 | 8 | 50 | **44** | `SV_SKIP` 不要 (unit 114 は halt0。`SV_SKIP=114` 付きだと 114 が hang 扱いで trap 43)。同じ ON を作り直して 2 回測り unit 単位で一致 |

遷移 (OFF → ON): halt0→ok 36 / halt0→oob 23 / oob→halt0 2 / halt0→halt0 6 / **ok 退行 5** (15 42 45 415 → miss、138 → oob)。
`SV_SKIP=114` を付けた旧手順では unit 114 が skip マーカー (`hang`) になるだけで、付けなくても ON は 60 s 以内に完走する。
`8cc190` 系 11 unit (53 54 56 58 59 60 61 62 63 307 311) は現 main の OFF では halt0 だが、ON では **11/11 が oob** (ok にはならない)。

**受入条件 2 の再判定 (旧ブロックでの値): 部分達成**。trap 総数は 79→44 (ok +31) と減ったが、減った分は最多分類 (`8cc190` 系) の修復ではない (11 unit は oob のまま)。
旧ブロックでは 8cbda0/8cbce0 を足す前後の寄与の分離は測っていない。ok 退行 5 件が残るため既定 ON への昇格はしない。
(参考: 先行 review の独立再実行では 410360 単独でも ok 847 / trap 43 で、ok の増加は 410360 によるもの・8cbda0/8cbce0 のみでは ok 不変と報告されている。本 run の実測ではない。)
**現 main (410360 のみ) での判定は再測定待ち**。ネガコン (既定 OFF) の対照差 0 は旧 tree での実測で、現 main では未再確認。
ネガコン (既定 OFF で対照と差 0) は成立。ICALL_AT 経由にしたため、ON の `0x41037d` (410360 の `call [rbx-0x50]`) は site 計測に ok 888 / miss 22 で乗る (410070 直処理は ok 計上)。
