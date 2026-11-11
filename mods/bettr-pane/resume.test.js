import { test } from "node:test";
import assert from "node:assert/strict";
import { resume } from "./resume.js";

const SHELL = { shell: true, agent: false };
const label = (provider, sessionId, turns = []) => ({ "bettr.activity": JSON.stringify({ version: 4, provider, sessionId, turns }) });
const withContext = (labels, context) => ({ ...labels, "bettr.context": JSON.stringify(context) });

test("a shell with a session label gets the agent's resume command", () => {
  assert.deepEqual(resume(label("claude", "ff8f2341-79e6-44a6-b56c-099361f69786"), SHELL),
    { command: "claude --resume ff8f2341-79e6-44a6-b56c-099361f69786", title: "Resume: Claude Code", prompt: "" });
  assert.deepEqual(resume(label("codex", "0199a1b2-aaaa-7bbb-8ccc-123456789abc"), SHELL),
    { command: "codex resume 0199a1b2-aaaa-7bbb-8ccc-123456789abc", title: "Resume: Codex", prompt: "" });
});

test("the title names the model of the same session only", () => {
  const labels = label("claude", "abc");
  const title = (context) => resume(withContext(labels, context), SHELL).title;
  assert.equal(title({ provider: "claude", sessionId: "abc", model: "claude-opus-5-5-20260101" }), "Resume: Claude Code (opus-5-5)");
  assert.equal(title({ provider: "claude", sessionId: "other", model: "claude-opus-5-5" }), "Resume: Claude Code");
  assert.equal(title({ provider: "codex", sessionId: "abc", model: "gpt-5" }), "Resume: Claude Code");
  assert.equal(title({ provider: "claude", sessionId: "abc" }), "Resume: Claude Code");
  assert.equal(resume({ ...labels, "bettr.context": "{bad" }, SHELL).title, "Resume: Claude Code");
});

test("the prompt is the last one a person sent", () => {
  const turns = [{ id: 1, prompt: "fix the bug" }, { id: 2, prompt: " add a test " }, { id: 3, prompt: "Agent finished", source: "notice" }, { id: 4, prompt: "" }];
  assert.equal(resume(label("claude", "abc", turns), SHELL).prompt, "add a test");
  assert.equal(resume(label("claude", "abc", [null, { id: 1 }]), SHELL).prompt, "");
  assert.equal(resume({ "bettr.activity": JSON.stringify({ provider: "claude", sessionId: "abc", turns: "x" }) }, SHELL).prompt, "");
});

test("nothing while an agent or another program is in front", () => {
  assert.equal(resume(label("claude", "abc"), { shell: false, agent: true }), null);
  assert.equal(resume(label("claude", "abc"), { shell: false, agent: false }), null);
  assert.equal(resume(label("claude", "abc"), null), null);
});

test("nothing without a usable label", () => {
  assert.equal(resume({}, SHELL), null);
  assert.equal(resume(undefined, SHELL), null);
  assert.equal(resume({ "bettr.activity": "{not json" }, SHELL), null);
  assert.equal(resume({ "bettr.activity": "null" }, SHELL), null);
  assert.equal(resume(label("pi", "abc"), SHELL), null);
  assert.equal(resume(label("constructor", "abc"), SHELL), null);
  assert.equal(resume(label("claude", 7), SHELL), null);
});

test("an ID that a shell would read as code is refused", () => {
  for (const id of ["", "a b", "a;rm -rf ~", "$(id)", "-x", "a\nb", "`id`"]) {
    assert.equal(resume(label("claude", id), SHELL), null, JSON.stringify(id));
  }
});
