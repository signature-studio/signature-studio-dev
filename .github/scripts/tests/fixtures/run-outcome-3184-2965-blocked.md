## #2965 [WIN-15] 結果: 依存 #3077 未達のため停止 (コード変更・branch・PR なし)

**結論**: 本 issue の前提 (`CreateFruityInstance` が `EnterCriticalSection` で abort せず open まで進むこと) が未達です。この修復は open の子 issue #3077 [WIN-16] が持っています。受入 1〜3 は前提が満たされるまで測定できないため、停止します。

**確認したこと**
- 本文の依存欄 `#2880` は CLOSED です。#2880 は受入 1 (CS `0x12bd390` の特定と CS-MISS 出力) だけ達成して閉じ、残りの修復は #3077 に移管済みです (PR #3080 MERGED)。
- #3077 は OPEN です。その受入 6「`node tools/gui/flengine/cfi_probe.mjs` が `EnterCriticalSection` を越え、次の停止点 (または S22 到達) を記録すること」が未達です。最新の実測 (commit `ae963e28`) では `CreateFruityInstance` が 1 ms で Aborted しています (`[shim] CS-MISS key=0x12bd390`)。
- この状態で trace しても open 系の呼出しは 0 件のままです (#2905 の実測と同じ)。受入 1〜3 は測れません。
- branch `2965-*` の既存 PR はありません。
- 素材: `$ARTIFACTS_DIR` に `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-m11` が実在します。素材作業は、依存が解けてから行います。

**PM への依頼**
- 依存の表示が実態とずれています。#2880 は閉じているため「ブロックする open な issue が無い」と判定されましたが、実際のブロッカーは #3077 です。`blocked_by: #3077` の設定をお願いします。

**再開条件**
- #3077 が merge され、`cfi_probe.mjs` が `CreateFruityInstance` を abort せず通過することを確認できたら、本 issue を再投入してください (`oc_artifacts` は本文の行どおり)。

**起票**
- 子 issue は起票していません (依存による停止のため)。

