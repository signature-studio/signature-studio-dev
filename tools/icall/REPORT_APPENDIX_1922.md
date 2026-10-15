# 付録: icall #1922 (ICALL-52) — 実経路で必要な未実装 import の特定と実装

> 親: #1874 (ICALL-47)。前付録: `REPORT_APPENDIX_1921.md`・`REPORT_APPENDIX_3235.md`。

## 1. 結論

- 受入条件 1 (CRT 初期化後に crash を再計測し、未実装 import が原因のものを特定): **達成**。§2。
- 受入条件 2 (実経路で必要な import のみを IMPL 表に追加): **部分達成**。`KERNEL32!RtlPcToFileHeader` のみ追加した (§3)。
  `RtlCaptureContext`・`UnhandledExceptionFilter` は未実装のまま (§4)。
- 受入条件 3 (残りは fail-fast のまま列挙): **達成**。§4。
- 受入条件 4 (`fa_sweep.sh 8 60` の件数を更新): **達成**。§5。件数は変わらなかった (分類の中身は変わった)。

## 2. 特定 (crash 65 関数の stderr 分類)

測定 commit: `ee2883ab8` (main 取り込み後の HEAD・本 PR の基準。本 PR のコード変更は未 commit だった時点で測定)。
`fa_sweep.sh 8 60` の crash 65 関数を 1 関数 1 プロセスで再実行し、stderr の fail-fast 行を集計した。

| 変更前 (`MISSING IMPORT` で fail-fast) | 9 | `RtlPcToFileHeader` 6・`RtlCaptureContext` 2・`UnhandledExceptionFilter` 1 |
| 変更後 (`RtlPcToFileHeader` を追加) | 3 | `RtlCaptureContext` 2・`UnhandledExceptionFilter` 1。`RtlPcToFileHeader` 6 は C++ 例外 `RaiseException(0xe06d7363)` に進む |

`fa_sweep` の件数は main で `bit一致 56 / crash 65 / wasm のみ err 9 / 値の不一致 1` (合計 131)。
crash 65 のうち stderr で分類した 9 関数 (変更前) 以外の内訳 (SIGSEGV 等) は本付録では数えていない (未計数)。

## 3. 実装 (IMPL 追加)

- `RtlPcToFileHeader`: PC が画像 `[IMG_BASE, IMG_BASE+imgsize)` 内なら画像基底 (`g_img`) を返し、範囲外は NULL。
  6 関数 (`1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`・`18102f728`) が
  `MISSING IMPORT` から C++ 例外の `RaiseException(0xe06d7363)` に進むことを単独実行で確認した。
  この例外経路の後段は未確認 (§4)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `KERNEL32!RtlCaptureContext` (2 関数: `18100cc50`・`18103d218`) | fail-fast のまま。CONTEXT を正しく埋める実装が要る | #4338 (ICALL-100・子) |
| `UnhandledExceptionFilter` (1 関数: `18100ca28`) | fail-fast のまま。`SetUnhandledExceptionFilter` と意味が違うため別実装が要る | #4338 (ICALL-100・子) |
| `RtlPcToFileHeader` 追加後の C++ 例外経路 (6 関数) | `RaiseException 0xe06d7363` で fail-fast。`__CxxFrameHandler` 系の unwind が要る | #4362 (ICALL-103・子) |
| SIGSEGV (件数未計数) | encoded slot・ヒープ構造体の未初期化が候補。stderr 分類は本付録では未実施 | ICALL-55 (#2009) の既存範囲 |

## 5. fa_sweep 実測

`bash tools/icall/diff/fa_sweep.sh 8 60`。測定は未 commit の作業ツリーで行った (測定 tree は `ee2883ab8` + 本 PR の未 commit 変更)。両方とも `funcs 131` の集計が同一。
**注: コミット済み HEAD での再測定は未実施**。素材 (`plugins-freshair`・`work-icall`・`work-liftlib-targets`) が fix run (`pull_request_review`) に展開されておらず、`tools/icall/work/` と `tools/targets/freshair/work/` が存在しないため。`fa_sweep.sh` は `tools/icall/work/rt_freshair-core/map.json` を必要とする。次の run で素材を指定して再測定し、その測定値で本節の表を置き換える。

コード差分 (測定 commit `ee2883ab8` から HEAD まで。`git diff ee2883ab8 HEAD -- tools/ott/native tools/icall`):

```
 tools/icall/REPORT_APPENDIX_1922.md | 60 +++++++++++++++++++++++++++++++++++++
 tools/ott/native/ott_native.c       |  8 +++++
 2 files changed, 68 insertions(+)
```

| 項目 | 変更前 | 変更後 | 差分 |
|---|---|---|---|
| bit一致 | 56 | 56 | 0 |
| native crash/timeout | 65 | 65 | 0 |
| wasm のみ err | 9 | 9 | 0 |
| 値の不一致 | 1 | 1 | 0 |

件数は変わらない。`RtlPcToFileHeader` の追加で 6 関数の fail-fast 理由が `MISSING IMPORT` から例外経路に変わったが、分類は crash のまま。

## 6. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 1803b3fc0 --n 2   # RaiseException(0xe06d7363)
```
