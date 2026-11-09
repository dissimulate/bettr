import { test } from "node:test";
import assert from "node:assert/strict";
import { numstatTotals, parseWorktrees, sizeLabel } from "./worktrees.js";

const HASH = "36d8f8e48c70d2a9179395d51550af7f87419dcf";

test("each worktree gets its folder name and branch", () => {
  const text = `worktree /r/main\nHEAD ${HASH}\nbranch refs/heads/main\n\nworktree /r/.claude/worktrees/fix\nHEAD ${HASH}\nbranch refs/heads/feature/a b\nlocked why\n\n`;
  assert.deepEqual(parseWorktrees(text), [
    { path: "/r/main", name: "main", branch: "main", unborn: false },
    { path: "/r/.claude/worktrees/fix", name: "fix", branch: "feature/a b", unborn: false },
  ]);
});

test("a detached worktree shows its short commit, and a new branch has no commit", () => {
  const [detached, unborn] = parseWorktrees(`worktree /a\nHEAD ${HASH}\ndetached\n\nworktree /b\nHEAD ${"0".repeat(40)}\nbranch refs/heads/new\n`);
  assert.equal(detached.branch, "detached 36d8f8e");
  assert.equal(unborn.unborn, true);
});

test("bare and prunable entries are left out", () => {
  const text = `worktree /bare\nbare\n\nworktree /gone\nHEAD ${HASH}\nbranch refs/heads/x\nprunable gitdir file points to non-existent location\n\nworktree /ok\nHEAD ${HASH}\nbranch refs/heads/y\n`;
  assert.deepEqual(parseWorktrees(text).map((tree) => tree.name), ["ok"]);
});

test("no output is no worktrees", () => assert.deepEqual(parseWorktrees(""), []));

test("du output becomes whole megabytes, rounded up", () => {
  assert.equal(sizeLabel("1\t/a\n"), "1 MB");
  assert.equal(sizeLabel("2048\t/a\n"), "2 MB");
  assert.equal(sizeLabel("2049\t/a b\n"), "3 MB");
  assert.equal(sizeLabel("2097152\t/a\n"), "2,048 MB");
  assert.equal(sizeLabel(""), null);
});

test("numstat adds up lines", () => {
  assert.deepEqual(numstatTotals("3\t1\ta.js\x002\t0\tb c.js\0"), { add: 5, del: 1, dirty: true });
});

test("a binary change is dirty with no lines, and a touched file is clean", () => {
  assert.deepEqual(numstatTotals("-\t-\timage.png\0"), { add: 0, del: 0, dirty: true });
  assert.deepEqual(numstatTotals("0\t0\ttouched.js\0"), { add: 0, del: 0, dirty: false });
  assert.deepEqual(numstatTotals(""), { add: 0, del: 0, dirty: false });
});
