import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { GENERATED, PANEL_FRAME, blocksDiffer, panelMod, withBlocks } from "./panel-mods.js";

const tree = (...extra) => ({ id: "root", type: "row", children: [
  { id: "panel-body", type: "row", children: [{ id: "files", type: "block", content: { mod: "files" } }, ...extra] },
] });
const body = t => t.children[0].children.map(node => node.id);
const tracker = panelMod("tracker", '{"title":"Tracker","panel":{"width":900}}');

test("only a mod that asks gets a panel", () => {
  assert.deepEqual(tracker, { name: "tracker", id: `${GENERATED}tracker`, title: "Tracker", width: 900 });
  assert.deepEqual(panelMod("x", '{"panel":true}'), { name: "x", id: `${GENERATED}x`, title: "x", width: null });
  for (const text of ['{"place":"none"}', '{"panel":false}', "{not json", null]) assert.equal(panelMod("x", text), null);
});

test("a missing block is added hidden, after the person's own", () => {
  const t = tree();
  assert.equal(blocksDiffer(t, [tracker]), true);
  withBlocks(t, [tracker]);
  assert.deepEqual(body(t), ["files", tracker.id]);
  assert.deepEqual(t.children[0].children[1],
    { id: tracker.id, type: "block", content: { mod: "tracker", props: { layoutFramed: true } }, size: { weight: 1 }, hidden: true, ...PANEL_FRAME });
  assert.equal(blocksDiffer(t, [tracker]), false);
});

test("a removed mod's block goes, and the person's own blocks and a kept block's fields stay", () => {
  const kept = { id: tracker.id, type: "block", content: { mod: "tracker" }, size: { px: 500 } };
  const gone = { id: `${GENERATED}gone`, type: "block", content: { mod: "gone" } };
  const mine = { id: "my-panel", type: "block", content: { mod: "mine" } };
  const t = tree(kept, mine, gone);
  assert.equal(blocksDiffer(t, [tracker]), true);
  withBlocks(t, [tracker]);
  assert.deepEqual(body(t), ["files", tracker.id, "my-panel"]);
  assert.deepEqual(t.children[0].children[1], kept);
});

test("a layout with no panel-body is left alone", () => {
  assert.equal(blocksDiffer({ id: "root", children: [] }, [tracker]), false);
});

test("the installer ignores the same prefix", () => {
  const script = readFileSync(new URL("../../scripts/install.py", import.meta.url), "utf8");
  assert.ok(script.includes(`GENERATED_PANEL = "${GENERATED}"`));
});


test("the same frame migrates built-in, nested and added panels without losing state", () => {
  const context = { id: "context", type: "column", hidden: true, size: { px: 540 }, children: [
    { id: "cache", type: "block", content: { mod: "context", props: { section: "cache", autoSize: "cache" } }, size: { px: 137 }, min: 37 },
  ] };
  const existing = { id: tracker.id, type: "block", content: { mod: "tracker", props: { trackers: "/my/trackers" } }, size: { px: 900 }, hidden: false };
  const t = tree(context, existing);
  withBlocks(t, [tracker]);
  const nodes = [t.children[0].children[0], context.children[0], existing];
  for (const node of nodes) {
    assert.equal(node.radius, PANEL_FRAME.radius);
    assert.equal(node.background, PANEL_FRAME.background);
    assert.deepEqual(node.border, PANEL_FRAME.border);
    assert.equal(node.content.props.layoutFramed, true);
  }
  assert.deepEqual(context.size, { px: 540 });
  assert.equal(context.hidden, true);
  assert.equal(context.border, undefined); // frame each leaf, not the group a second time
  assert.deepEqual(context.children[0].size, { px: 137 });
  assert.equal(context.children[0].min, 37);
  assert.equal(context.children[0].content.props.autoSize, "cache");
  assert.equal(existing.content.props.trackers, "/my/trackers");
  assert.deepEqual(existing.size, { px: 900 });
  assert.equal(existing.hidden, false);
  const once = JSON.stringify(t);
  assert.equal(blocksDiffer(t, [tracker]), false);
  withBlocks(t, [tracker]);
  assert.equal(JSON.stringify(t), once);
});

test("frame drift is repaired even when registered panels are unchanged", () => {
  const t = withBlocks(tree(), [tracker]);
  t.children[0].children[1].radius = 2;
  assert.equal(blocksDiffer(t, [tracker]), true);
  withBlocks(t, [tracker]);
  assert.equal(blocksDiffer(t, [tracker]), false);
  assert.equal(t.children[0].children[1].radius, PANEL_FRAME.radius);
});

test("normalizing a different layout changes nothing", () => {
  const t = { id: "root", type: "block", content: { mod: "tracker" }, radius: 3 };
  assert.equal(withBlocks(t, [tracker]), t);
  assert.equal(t.radius, 3);
  assert.equal(t.content.props, undefined);
});
