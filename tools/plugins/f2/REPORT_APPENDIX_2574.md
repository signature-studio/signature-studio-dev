# tools/plugins/f2 REPORT_APPENDIX_2574 — PLG-F3-31 (#2574): [0x8cd068] の初期化経路 (部分、測定 commit 37d87300、block19148)

- 測定 commit: **37d87300** (`table_refs.py` の追加。コードを変えた最後の commit)。鮮度: `git diff 37d87300 HEAD -- tools/plugins/f2/` は本節を含む commit までの REPORT のみ (§6)。
- 前提: #2468 の付録 `REPORT_APPENDIX_2468.md` (PR #2526, 2026-10-14 merge)。本件の受入 1 の結論 (0x5da070 の NULL this と `[0x8cd068]` = 0) はそこを引く。
- 既知類型との関係: (DEFECTS.md) 該当なし。NULL グローバルは合成 host の欠落で、lift の miscompile ではない。waiver は変更しない。
- 担当 dir: `tools/plugins/f2/` のみ。入力は `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`)。依存は `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 範囲: 静的走査と unicorn による実行。実 FL の host 値は得られないため、host は合成 (`-H`)。

## 0. 結論 (先出し)

1. **`[0x8cd068]` の書込み元は、関数表 `0x852d70` (36 要素 = 18 組の (初期化, 破棄) 対) の 2 つの関数に限られる**。`0x852e30` の `0x5e0340` (初期化: `0x5e0483` で `rax` を格納) と `0x852e38` の `0x5e01d0` (破棄: `0x5e01f4` で 0 を格納)。これは PE 全体の qword 格納 (`fn_refs.py`) と一致する。
2. **表 `0x852d70` を参照する命令・ポインタは PE 内に 1 件も見つからない**。pdata 関数ごとの逆アセンブルで rip 相対・絶対 disp (index 付きを含む)・即値は 0 件、表の要素を指す qword は 0 件、表の RVA (`0x452d70`) を指す dword も 0 件 (§2)。表は `.text` 内の pdata 外にあるデータである。
3. **動的にも表の要素は一度も実行されない**。合成 host (`-H`) の `CreatePlugInstance` 単独 (M4) と、DllMain 前処理 (`rdx=1`) を置いた `CreatePlugInstance` (M5) のどちらでも、`0x5e0340`・`0x5e01d0`・`0x5e0483` の到達は 0 件、`[0x8cd068]` の書込みは 0 件、停止点は `0x50138d06` (#2468 の A と同じ)。
4. 従って、`0x83efb0` 経路で `[0x8cd068]` が初期化される経路は、この表を経由しない (静的に見える範囲で)。**受入 2 (0x411a80 到達) は未達**。表の参照元の未特定は残件 (§7)。
5. DllMain 前処理 (`0x8525f0`、`rdx=1`) は `rax=0` で戻る (E-b)。`0x411930` 単独 (E-a) も `rax=0`。DllMain は `0x411930` の戻り値 0 の経路で `0x41c740` → `0x411a80` まで入るが、戻り値 (`[rbp+0x17c]`) が 0 になる理由は未特定。表は呼ばれない。

## 1. 測定 (測定 commit 37d87300、逐次、負荷 1 分値 0.27 → 0.40)

| 実行 | 結果 | wall |
|---|---|--:|
| T `table_refs.py PE 0x852d70 0x852e89` | pairs 36 行、code refs 0、qword 0、dword 0 | 8.65 / 8.76 s (n=2) |
| M4 `unicorn_trace.py PE 0x83efb0 -H -V -p 0x409090 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -t 0x411a80 -t 0x411bb8 -q 0x8cd068 -w 0x8cd068:0x8cd070` | `UC_ERR_INSN_INVALID rip=0x50138d06`。表の要素・`0x411a80`・`0x411bb8` の到達 0 件。書込み 0 件。`[0x8cd068]` 0 → 0 | 1.79 s (n=1) |
| M5 M4 に `-p 0x8525f0:rdx=1` を追加 (DllMain 前処理) | M4 と同じ停止点。DllMain は `rax=0` で戻る。表の要素の到達 0 件、書込み 0 件 | 1.80 s (n=1) |
| E-a `unicorn_trace.py PE 0x411930 -H -V -p 0x409090 -t 0x41c740 -t 0x411a80` | `rax=0x0` で戻る。`0x41c740`・`0x411a80` の到達 0 件 (単独実行) | 未計測 (単発) |
| E-b `unicorn_trace.py PE 0x8525f0 -H -V -p 0x409090 -r rdx=1 -t 0x41c740 -t 0x411a80 -t 0x5e0340 -t 0x5e01d0` | `0x41c740` (rcx=`0x300ffcb8`) → `0x411a80` (rcx=`0xe2`) の順に入り、`rax=0x0` で戻る。表の要素 0 件 | 未計測 (単発) |

- 注: M4 の `-p 0x409090` で arena を構築し、`-V` で VirtualAlloc を pool へ返す。#2468 の A (`-H -V -p 0x409090`) と同じ条件。

## 2. 関数表 0x852d70 (36 要素)

- 表は pdata 関数の外 (`enclosing pdata fn = None`)。`.text` 内の 0x852d70〜0x852e88 に置かれたデータ。
- 要素は 18 組の対で、各要素の値はすべて pdata 関数の先頭 (例: `0x852d70 → 0x5b7580`、`0x852d78 → 0x5b7570`)。対の意味は、`0x852e30 → 0x5e0340` (初期化: `0x8cd068` に格納) と `0x852e38 → 0x5e01d0` (破棄: `0x8cd068` に 0) から、(初期化, 破棄) と読める。他の 16 組の書込み先は未確認。
- 参照の走査 (`table_refs.py`): pdata 関数ごとに逆アセンブルし、rip 相対 (表の範囲内を指す) 0 件、絶対 disp (index の有無を問わず) 0 件、即値 0 件。表の要素値 (`0x5b7580`〜`0x5e1d90`) を指す qword の走査は、表の先頭 `0x852d70` と表内の各要素に対しても、ファイル全体で 0 件 (8 バイト整列・4 バイト整列の両方)。
- 以前の `fn_refs.py` (REPORT_APPENDIX_2468 §4) の「参照元 0 件」と一致する。新たに、絶対 disp の index 付き・dword RVA 格納・関数単位の逆アセンブルでも 0 件であることを確認した。

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
| 3. 届いた後、`0x411bb8` 呼出し時の `[0x8c3c80]`・`[[rcx]+0x28]` を記録 | **未達** (受入 2 が前提)。DllMain 経路の `0x411bb8` (REPORT_APPENDIX_2468 §5) は別経路のため、受入の代わりにはしない。 |
| 4. 空き obj `[obj-8]` への書込み元 | **未達**。本件では未着手。 |

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数表 `0x852d70` を呼ぶ経路 (参照 0 件)。ポインタ・計算によるアクセスの可能性 | `[0x8cd068]` の初期化が未確定。受入 2〜4 が未達 | #2574 |
| DllMain 前処理が `rax=0` で戻る原因 (`0x411930` の戻り値 0 の経路で `[rbp+0x17c]` が 0 になる理由) | DllMain 経路が本来どこまで進むかが未確定 | #2574 |
| 表の 16 組の書込み先 (初期化・破棄) | 他の `.bss` グローバルの初期化経路の有無 | #2574 |
| 空き obj `[obj-8]` の書込み元 (受入 4) | 空きリンクの書込み未観測 | #2574 |

## 6. 検証と鮮度

- 再現 (リポジトリ直下、`PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin`、`T=$RUNNER_TEMP/f2venv/bin/python`):
  - T: `$T tools/plugins/f2/table_refs.py $PE 0x852d70 0x852e89`
  - M4: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -t 0x411a80 -t 0x411bb8 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000`
  - M5: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -p 0x8525f0:rdx=1 -t 0x5e0340 -t 0x5e01d0 -t 0x5e0483 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000`
  - E-b: `$T tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -p 0x409090 -r rdx=1 -t 0x41c740 -t 0x411a80 -t 0x5e0340 -t 0x5e01d0 -m 2000000`
- 陰性の対照: 表の要素を指す値の走査で 0 件 (`0x852d70` 自体の qword も 0 件)。表の RVA `0x452d70` を指す dword 検索 (4 バイト整列) も 0 件。
- 正の対照: `unicorn_trace.py -t 0x5da06d` (REPORT_APPENDIX_2468 §1 A) で `0x5da06d` の入場は出る (道具の `-t` は機能する)。
- 範囲の限界: 静的走査は pdata 関数の逆アセンブルに限る。pdata 外のコード・動的に計算したポインタは対象外。実 host の値は得られない。

## 7. 再現・次の一手

- 次の一手: (a) 表 `0x852d70` の 16 組を含む 18 組の書込み先を、各 pair を単独で `-t` と `-w` で実行して確認する (呼出し元とは別の作業)。(b) DllMain の `rax=0` の原因: `[0x300ffdec]` (= DllMain の `[rbp+0x17c]`) を `-w` で追う。(c) 表を実行する経路の候補 (DllMain の後続・host の別呼出し) を unicorn で順に試す。
