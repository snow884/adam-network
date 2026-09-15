import test from "node:test";
import assert from "node:assert";
import * as crypto from "node:crypto";
import { solveChallenge } from "../src/client.ts";
import { adamPlugin, postMessageAction, replyThreadAction, readFeedAction } from "../src/index.ts";

test("solveChallenge computes correct SHA-1 preimage", () => {
  const secret = "a1b2c3";
  const targetHash = crypto.createHash("sha1").update(secret, "ascii").digest("hex");
  const solution = solveChallenge(targetHash);
  assert.strictEqual(solution, secret);
});

test("adamPlugin exports expected actions and structure", () => {
  assert.strictEqual(adamPlugin.name, "adam-network");
  assert.strictEqual(adamPlugin.actions.length, 3);
  assert.strictEqual(adamPlugin.providers.length, 1);

  const actionNames = adamPlugin.actions.map((a) => a.name);
  assert.ok(actionNames.includes("POST_MESSAGE"));
  assert.ok(actionNames.includes("REPLY_THREAD"));
  assert.ok(actionNames.includes("READ_FEED"));
});

test("postMessageAction validation", async () => {
  const validMsg = { content: { text: "Hello Adam" } };
  const invalidMsg = { content: {} };

  assert.strictEqual(await postMessageAction.validate({}, validMsg), true);
  assert.strictEqual(await postMessageAction.validate({}, invalidMsg), false);
});

test("replyThreadAction validation", async () => {
  const validReply = { content: { messageId: 42, text: "Great post" } };
  const invalidReply = { content: { text: "No ID" } };

  assert.strictEqual(await replyThreadAction.validate({}, validReply), true);
  assert.strictEqual(await replyThreadAction.validate({}, invalidReply), false);
});
