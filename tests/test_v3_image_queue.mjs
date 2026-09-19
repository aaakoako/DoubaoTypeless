// Multi-select albums enqueue; only one editor is open; scene is kept for re-edit.
import assert from "node:assert/strict";

function enqueue(assets, files, cap = 6) {
  const editing = assets.some((a) => a.status === "editing");
  for (const name of files) {
    if (assets.length >= cap) break;
    assets.push({ id: name, status: "queued", scene: null, source: name });
  }
  return { openId: editing ? null : assets.find((a) => a.status === "queued")?.id || null };
}

function finish(assets, id, scene) {
  const item = assets.find((a) => a.id === id);
  item.status = "ready";
  item.scene = scene;
  return assets.find((a) => a.status === "queued")?.id || null;
}

function reopenUsesScene(asset) {
  return Boolean(asset.scene);
}

const assets = [];
const first = enqueue(assets, ["a.png", "b.png"]);
assert.equal(assets.length, 2);
assert.equal(first.openId, "a.png");
assert.equal(assets[1].status, "queued");
assets[0].status = "editing";
const second = enqueue(assets, ["c.png"]);
assert.equal(second.openId, null);
assert.equal(assets[2].status, "queued");
const next = finish(assets, "a.png", '{"ops":1}');
assert.equal(next, "b.png");
assert.equal(reopenUsesScene(assets[0]), true);
console.log("image queue ok");
