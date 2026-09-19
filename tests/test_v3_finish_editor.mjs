// Production finishEditor policy: failed re-upload must drop the old asset id.
import assert from "node:assert/strict";

function beginReprocess(item) {
  item.asset_id = undefined;
  return item;
}

function finishReprocess(item, uploadedId) {
  if (!uploadedId) {
    item.asset_id = undefined;
    return false;
  }
  item.asset_id = uploadedId;
  return true;
}

const existing = { asset_id: "ORIGINAL-SCREEN-ID", preview: "raw" };
beginReprocess(existing);
existing.preview = "blob:PROCESSED-PREVIEW";
assert.equal(finishReprocess(existing, undefined), false);
assert.equal(existing.asset_id, undefined);

const fresh = {};
beginReprocess(fresh);
assert.equal(finishReprocess(fresh, undefined), false);
assert.equal(fresh.asset_id, undefined);

console.log("finishEditor policy ok");
