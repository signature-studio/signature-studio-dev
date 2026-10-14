# tools/plugins/f2 REPORT_APPENDIX_2574 — PLG-F3-31 (#2574): [0x8cd068] の初期化経路 (部分、測定 commit 914297eb、block19148)

- 測定 commit: **914297eb** (`table_refs.py` の修正。コードを変えた最後の commit)。鮮度: `git diff 914297eb HEAD -- tools/plugins/f2/*.py` は出力なし (§6)。
- 前提: #2468 の付録 `REPORT_APPENDIX_2468.md` (PR #2526, 2026-10-14 merge)。本件の受入 1 の結論 (0x5da070 の NULL this と `[0x8cd068]` = 0) はそこを引く。
- 既知類型との関係: (DEFECTS.md) 該当なし。NULL グローバルは合成 host の欠落で、lift の miscompile ではない。waiver は変更しない。
- 担当 dir: `tools/plugins/f2/` のみ。入力は `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`)。依存は `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 範囲: 静的走査と unicorn による実行。実 FL の host 値は得られないため、host は合成 (`-H`)。

## 0. 結論 (先出し)

1. **`[0x8cd068]` への直接の書込み (rip 相対・絶対) は 2 箇所のみ**: `0x5e01f4` (0 を格納、`0x5e01d0` の内側) と `0x5e0483` (`rax` を格納、`0x5e0340` の内側)。線形走査 (§2・§6) の結果。`0x8cd068` を格納する qword は `.data` の `0x8bd7f8` の 1 件だけ。そこから読んだポインタ経由の間接書込みは静的には未排除で、動的な確認 (M4/M5 の `-w`) は CreatePlugInstance と DllMain 前処理の経路に限る。
2. **関数表 `0x852d70` (36 要素 = 18 組の (初期化, 破棄) 対) を参照する命令・ポインタは PE 内に 1 件もない**。pdata 関数の逆アセンブルと `.text` 全体の線形走査で、表への rip 相対・絶対 disp (index 付きを含む)・即値はすべて 0 件。表の各要素の VA (`0x852d70+8k`) を指す qword も、RVA (`0x452d70+8k`) を指す dword も、ファイル全体の全オフセットで 0 件 (§2)。表は pdata 関数の外にあるデータである。
3. **動的にも表の要素は一度も実行されない**。合成 host (`-H`) の `CreatePlugInstance` 単独 (M4) と、DllMain 前処理 (`rdx=1`) を置いた `CreatePlugInstance` (M5) のどちらでも、`0x5e0340`・`0x5e01d0`・`0x5e0483` の到達は 0 件、`[0x8cd068]` の書込みは 0 件、停止点は `0x50138d06` (#2468 の A と同じ)。
4. 従って、`0x83efb0` 経路で `[0x8cd068]` が初期化される経路は、この表を経由しない (静的に見える範囲で)。**受入 2 (0x411a80 到達) は未達**。表の参照元の未特定は残件 (§5)。
5. DllMain 前処理 (`0x8525f0`、`rdx=1`) は `rax=0` で戻る (E-b)。`0x411930` 単独 (E-a) も `rax=0`。DllMain は `0x411930` の戻り値 0 の経路で `0x41c740` → `0x411a80` まで入るが、戻り値 (`[rbp+0x17c]`) が 0 になる理由は未特定。表は呼ばれない。

## 1. 測定 (測定 commit 914297eb、逐次、負荷 1 分値 0.48 → 0.52)

| 実行 (§6 の正本コマンド) | 結果 | wall |
|---|---|--:|
| T `table_refs.py PE 0x852d70 0x852e89 0x8cd068` | pdata 17,543 関数のうち途中停止 3 関数・未走査 24,932 B。参照: pdata 内 20 件・線形走査 20 件 (表 0、slot 20。直接書込みは slot の 2 件のみ)。線形走査の復号不能 44,478 B。表の各要素 36 個の qword 0・dword 0。陽性対照 (要素 0 の値 `0x5b7580` の qword = `0x852d70`、RVA の dword = `0x922d40` (.pdata)) | 27.95 / 28.13 s (n=2) |
| M4 `unicorn_trace.py PE 0x83efb0 -H -V -p 0x409090 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -t 0x411a80 -t 0x411bb8 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000` | `UC_ERR_INSN_INVALID rip=0x50138d06`。表の要素・`0x411a80`・`0x411bb8` の到達 0 件。書込み 0 件。`[0x8cd068]` 0 → 0 | 1.76 s (n=1) |
| M5 M4 に `-p 0x8525f0:rdx=1` を追加 (DllMain 前処理) | M4 と同じ停止点。DllMain 前処理は `rax=0` で戻る。前処理の中で `0x411a80` (rcx=`0xe2`) と `0x411bb8` (rcx=`0x8c3c80`) に 1 回ずつ入る。表の要素の到達 0 件、書込み 0 件 | 1.73 s (n=1) |
| E-b `unicorn_trace.py PE 0x8525f0 -H -V -p 0x409090 -r rdx=1 -t 0x41c740 -t 0x411a80 -t 0x5e0340 -t 0x5e01d0 -m 2000000` | `0x41c740` (rcx=`0x300ffcb8`) → `0x411a80` (rcx=`0xe2`) の順に入り、`rax=0x0` で戻る。表の要素 0 件 | 1.70 s (n=1) |
| 正の対照 `unicorn_trace.py PE 0x83efb0 -H -V -p 0x409090 -t 0x5da06d -m 2000000` | `0x5da06d` (rcx=`0x0`) の入場が 1 件出る (道具の `-t` は機能する)。停止点は M4 と同じ | 1.72 s (n=1) |

- 注: M4 の `-p 0x409090` で arena を構築し、`-V` で VirtualAlloc を pool へ返す。#2468 の A (`-H -V -p 0x409090`) と同じ条件。
- 注: M5 は M4 と同じ `-t`・`-q`・`-w` を付けた。`-t 0x411a80`・`0x411bb8` の入場は DllMain 前処理の中に出る (`0x83efb0` の経路ではない)。

## 2. 関数表 0x852d70 (36 要素)

- 表は pdata 関数の外 (`enclosing pdata fn = None`)。`.text` 内の 0x852d70〜0x852e88 に置かれたデータ。
- 要素は 18 組の対で、各要素の値はすべて pdata 関数の先頭 (例: `0x852d70 → 0x5b7580`、`0x852d78 → 0x5b7570`)。対の意味は、`0x852e30 → 0x5e0340` (初期化: `0x8cd068` に格納) と `0x852e38 → 0x5e01d0` (破棄: `0x8cd068` に 0) から、(初期化, 破棄) と読める。他の 16 組の書込み先は未確認。
- 参照の走査 (`table_refs.py`、§6 T): 逆アセンブル (pdata 関数単位と `.text` 全体の線形走査) で、表の範囲 `[0x852d70, 0x852e89)` を指す rip 相対・絶対 disp (index の有無を問わず)・即値は 0 件。表の各要素 (k=0..35) の VA `0x852d70+8k` を指す qword、RVA `0x452d70+8k` を指す dword を、ファイル全体の全オフセット (非整列を含む) で検索した結果は、いずれも 0 件 (`element hits: qword 0, dword 0`)。
- 陽性対照: 同じ検索で、要素 0 の値 `0x5b7580` の qword は表自身 (`0x852d70`) に、RVA `0x1b7580` の dword は .pdata の開始 RVA (`0x922d40`) に見つかる。検索は機能する。
- 以前の `fn_refs.py` (REPORT_APPENDIX_2468 §4) の「参照元 0 件」と一致する。今回は要素ごとの検索、絶対 disp の index 付き、dword RVA 格納、線形走査を加えた。
- slot `0x8cd068` (陽性の参照): rip 相対の参照は pdata 内・線形走査とも 20 件 (同一集合)。読取り 18 件 (`cmp`・`mov reg, [slot]`)、直接書込み 2 件 (`0x5e01f4`・`0x5e0483`)。`lea`・即値による slot のアドレス取得は 0 件。slot を格納する qword は `0x8bd7f8` の 1 件、dword RVA 格納は 0 件。

## 3. 初期化の意味 (既知の範囲)

- `0x5e0340` (初期化): `call 0x5d7df0` (割当てと推定。戻り値 `rax`) の後、`0x5e0483` で `[0x8cd068] = rax`。
- `0x5e01d0` (破棄): `0x5e01f4` で `[0x8cd068] = 0`。
- `0x83cbbe` の `this` は `[0x8cd068]` を読んだ値 (REPORT_APPENDIX_2468 §4)。よって、表の対が呼ばれない限り `this` は 0 のまま、`0x5d9f50` の NULL this 連鎖が起きる。
- 表の呼出し元が無いため、「誰がこの対を実行するか」は未特定。実 FL では、DllMain・TLS・host の別の呼出し・動的な関数テーブルのいずれかが該当し得るが、PE の静的情報からは確定できない。

## 4. 受入条件の判定

| 受入 (issue #2574 の本文) | 判定 |
|---|---|
| 1. `0x50138cf0`→`0x50138d06` へ至る原因を書込み元 rip で特定 | #2468 で確定済み (`0x40cffa`・`0x40ed36`、REPORT_APPENDIX_2468 §3)。本件では再測定していない。 |
| 2. `0x83efb0` (`-H -V -p 0x409090`) が `0x411a80` に届く | **未達**。M4 で停止点 `0x50138d06` のまま。`[0x8cd068]` の初期化経路が見つからない。 |
| 3. 届いた後、`0x411bb8` 呼出し時の `[0x8c3c80]`・`[[rcx]+0x28]` を記録 | **未達** (受入 2 が前提)。DllMain 前処理の中の `0x411bb8` (§1 M5) は別経路のため、受入の代わりにはしない。 |
| 4. 空き obj `[obj-8]` への書込み元 | **未達**。本件では未着手。 |

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数表 `0x852d70` を呼ぶ経路 (参照 0 件。計算によるアクセスの可能性) | `[0x8cd068]` の初期化が未確定。受入 2〜4 が未達 | #2574 |
| slot `0x8bd7f8` 経由の間接書込み (静的には未排除) | 静的な書込み元の網羅が未確定。M4/M5 の経路に限った動的確認 | #2574 |
| DllMain 前処理が `rax=0` で戻る原因 (`0x411930` の戻り値 0 の経路で `[rbp+0x17c]` が 0 になる理由) | DllMain 経路が本来どこまで進むかが未確定 | #2574 |
| 表の 16 組の書込み先 (初期化・破棄) | 他の `.bss` グローバルの初期化経路の有無 | #2574 |
| 空き obj `[obj-8]` の書込み元 (受入 4) | 空きリンクの書込み未観測 | #2574 |

## 6. 検証と鮮度

- 再現 (リポジトリ直下、`PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin`、`T=$RUNNER_TEMP/f2venv/bin/python`):
  - T: `$T tools/plugins/f2/table_refs.py $PE 0x852d70 0x852e89 0x8cd068`
  - M4: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -t 0x411a80 -t 0x411bb8 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000`
  - M5: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x8525f0:rdx=1 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -t 0x411a80 -t 0x411bb8 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000`
  - E-b: `$T tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -p 0x409090 -r rdx=1 -t 0x41c740 -t 0x411a80 -t 0x5e0340 -t 0x5e01d0 -m 2000000`
  - 正の対照: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x5da06d -m 2000000`
- 鮮度 (HEAD で実行、出力なし = 差分 0): `git diff 914297eb HEAD -- tools/plugins/f2/*.py` と `git diff 37d87300 HEAD -- tools/plugins/f2/unicorn_trace.py`。本節を含む REPORT の commit は `*.py` の pathspec の外にあるため、差分 0 の証跡になる。
- 範囲の限界:
  - pdata 逆アセンブルの途中停止: 3 関数・未走査 24,932 B (`0x4254f0..0x42b582` の 24,673 B、`0x55e9c0..0x55ff30` の 138 B、`0x561f00..0x564534` の 121 B)。この範囲は線形走査で検算した (§2)。
  - 線形走査 (`.text` 0x401000..0x866a4c): 復号できない 1 バイトごとに 1 バイト進めて再同期する。復号不能 44,478 件 (データ・埋込み表の可能性。未同定)。線形走査の参照集合は pdata 走査と同一 (表 0 件、slot 20 件)。
  - pdata 外の動的に計算したポインタ・slot 経由の間接書込みは静的には対象外。実 host の値は得られない。
- 陰性・陽性の対照: 表の要素の検索の陽性対照は §2 のとおり。`unicorn_trace.py -t 0x5da06d` の陽性対照は §1 のとおり。

## 7. 再現・次の一手

- 次の一手: (a) 表 `0x852d70` の 16 組の書込み先 (対の残り) を、各 pair を単独で `-t` と `-w` で実行して確認する (呼出し元とは別の作業)。(b) DllMain の `rax=0` の原因: `[0x300ffdec]` (= DllMain の `[rbp+0x17c]`) を `-w` で追う。(c) 表を実行する経路の候補 (DllMain の後続・host の別呼出し) を unicorn で順に試す。
