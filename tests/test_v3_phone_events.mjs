import assert from "node:assert/strict";
import { applyReady, applyRotated } from "../web/src/sync.js";

const cases = [];
function test(name, fn) {
  try {
    fn();
    cases.push({ name, status: "PASS" });
  } catch (e) {
    cases.push({ name, status: "FAIL", error: e.message });
  }
}

const base = () => ({ text: "", assets: [], draft_id: "D", epoch: "E1", revision: 10, conflict: null });

test("image_only_unknown_must_keep_attachment", () => {
  const s = { ...base(), assets: [{ asset_id: "PHOTO-A" }] };
  assert.equal(applyRotated(s, { archived: null, result: "UNKNOWN", draft_id: "D", epoch: "E1", revision: 10 }), "kept");
  assert.equal(s.assets.length, 1, "图片未知且未归档，不应清空手机附件");
});

test("new_attachment_same_text_must_survive_old_receipt", () => {
  const s = { ...base(), text: "说明", revision: 11, assets: [{ asset_id: "NEW-B" }] };
  assert.equal(
    applyRotated(s, {
      archived: { draft_id: "D", epoch: "E1", revision: 10, text: "说明", asset_refs: ["OLD-A"] },
      draft_id: "D",
      epoch: "E2",
      revision: 11,
    }),
    "kept"
  );
  assert.equal(s.assets[0]?.asset_id, "NEW-B", "相同文字不意味着同一份图文，不能删新附件");
});

test("confirmed_with_archived_clears_matching_draft", () => {
  const s = { ...base(), text: "已确认投递A" };
  assert.equal(
    applyRotated(s, {
      archived: { draft_id: "D", epoch: "E1", revision: 10, text: "已确认投递A", asset_refs: [] },
      result: "CONFIRMED",
      draft_id: "D",
      epoch: "E2",
      revision: 11,
    }),
    "cleared"
  );
  assert.equal(s.text, "");
  assert.equal(s.epoch, "E2");
});

test("session_ready_must_not_relabel_and_auto_resend_stale_epoch", () => {
  const s = { ...base(), text: "离线旧稿A" };
  assert.equal(applyReady(s, { draft_id: "D", epoch: "NEW-EPOCH", revision: 20, text: "服务器新稿" }), "conflict");
  assert.equal(s.epoch, "E1");
  assert.equal(s.text, "离线旧稿A");
  assert.equal(s.conflict?.epoch, "NEW-EPOCH");
});

test("control_matching_text_receipt_rotates", () => {
  const s = { ...base(), text: "A" };
  assert.equal(
    applyRotated(s, { archived: { draft_id: "D", epoch: "E1", revision: 10, text: "A", asset_refs: [] }, draft_id: "D", epoch: "E2", revision: 11 }),
    "cleared"
  );
  assert.equal(s.text, "");
  assert.equal(s.epoch, "E2");
});

if (cases.some((c) => c.status === "FAIL")) {
  console.error(JSON.stringify({ cases }, null, 2));
  process.exit(1);
}
console.log("ok " + cases.length);
