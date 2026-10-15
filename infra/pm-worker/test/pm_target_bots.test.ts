// oc-pm の対象の起票者: PM App (oc-pm-for-signature-studio[bot]) が起票した issue を、既定の設定で検出対象にする (#5462)。
// 許可外の bot・未取得の author は従来どおり拒否する (ネガコン)。
import { test } from "node:test";
import assert from "node:assert/strict";
import { authorAllowed } from "../src/pm.ts";
import { loadConfig } from "../src/config.ts";

const PM_APP = "oc-pm-for-signature-studio[bot]";

test("既定の pmTargetBots に PM App が入る (PM App 起票の issue が oc-pm の検出対象になる)", () => {
  const bots = loadConfig({}).pmTargetBots;
  assert.ok(bots.includes(PM_APP), `pmTargetBots に ${PM_APP} が無い: ${bots.join(",")}`);
  assert.equal(authorAllowed({ author: PM_APP, authorType: "Bot", assoc: "NONE" }, bots), true);
});

test("ネガコン: 許可外の bot・Bot 以外の型・author 未取得は拒否する", () => {
  const bots = loadConfig({}).pmTargetBots;
  assert.equal(authorAllowed({ author: "some-other-app[bot]", authorType: "Bot", assoc: "NONE" }, bots), false);
  assert.equal(authorAllowed({ author: PM_APP, authorType: "User", assoc: "NONE" }, bots), false);
  assert.equal(authorAllowed({ authorType: "Bot", assoc: "NONE" }, bots), false);
  assert.equal(authorAllowed({ author: "stranger", authorType: "User", assoc: "NONE" }, bots), false);
});
