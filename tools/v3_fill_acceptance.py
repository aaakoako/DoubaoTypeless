"""Fill fixtures/acceptance.json from executed evidence. Never self-PASS native gaps."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AC_PATH = ROOT / "docs" / "pocket-composer-v3" / "fixtures" / "acceptance.json"

# status, evidence, optional note. Keep old evidence when downgrading; note the scope.
MAP = {
    "AC3-001": ("PASS", ["docs/evidence/baseline/AC3-001/result.json"]),
    "AC3-002": ("BLOCKED_NATIVE", ["docs/evidence/baseline/AC3-002/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-003": ("PASS", ["docs/evidence/baseline/AC3-003/result.json"]),
    "AC3-004": ("PASS", ["docs/evidence/baseline/AC3-004/result.json"]),
    "AC3-005": (
        "NOT_RUN",
        ["docs/evidence/v3-product/result.json", "tests/test_v3_runtime.py"],
        "旧证据为产品窗空闲隐藏与插入，未测外部编辑器焦点保持与 360×88 实窗",
    ),
    "AC3-006": ("BLOCKED_NATIVE", ["docs/evidence/v3-cursor/result.json", "docs/evidence/v3-product/ACCEPTANCE.md"]),
    "AC3-007": (
        "NOT_RUN",
        ["tests/test_v3_core_services.py::test_code_focus_does_not_inject_images"],
        "旧证据仅为 classify_focus 单测，未在 Cursor 代码区/终端切焦点",
    ),
    "AC3-008": ("BLOCKED_NATIVE", ["docs/evidence/v3-cursor/result.json"]),
    "AC3-009": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-010": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-011": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-012": (
        "NOT_RUN",
        ["src/doubao_typeless/static/composer.html", "web/src/app.ts"],
        "旧证据仅为源码存在，未锁定依赖并生成可启动样板包",
    ),
    "AC3-013": ("PASS", ["tests/test_v3_runtime.py::test_frozen_bundle_ignores_later_draft_edits"]),
    "AC3-014": (
        "NOT_RUN",
        ["tests/test_v3_bridge.py"],
        "旧证据为协议配对/ACK，未发送同 revision 不同 hash 冲突",
    ),
    "AC3-015": (
        "NOT_RUN",
        ["tests/test_v3_runtime.py::test_frozen_bundle_ignores_later_draft_edits"],
        "旧证据为冻结快照，不是前导空格/emoji 往返",
    ),
    "AC3-016": (
        "NOT_RUN",
        ["tests/test_v3_core_services.py"],
        "旧证据为授权/投递单测，未覆盖 r3 归档回执与 r4 保留",
    ),
    "AC3-017": (
        "PASS",
        [
            "tests/test_v3_core_services.py::test_pairing_mismatch_and_insert_grant",
            "tests/test_v3_auth_isolation.py",
            "docs/evidence/v3-review/counterexamples.json",
            "docs/evidence/v3-auth/result.json",
        ],
        "旧证据仅 AuthService mismatch；本批补未鉴权 WS 改稿/资源下载与非环回挑战隔离",
    ),
    "AC3-018": (
        "NOT_RUN",
        ["tests/test_v3_core_services.py::test_pairing_mismatch_and_insert_grant"],
        "旧证据覆盖 mismatch 与 nonce 一次性，未测过期 token/撤销设备后继续发消息",
    ),
    "AC3-019": (
        "PASS",
        [
            "tests/test_v3_runtime.py::test_capture_requires_grant",
            "tests/test_v3_auth_isolation.py::test_lan_pair_post_cannot_self_grant_insert_or_capture",
            "docs/evidence/v3-review/counterexamples.json",
        ],
        "旧证据仅授权表；本批禁止非环回 POST 自授 insert/capture，默认不再 True",
    ),
    "AC3-020": (
        "PASS",
        [
            "tests/test_v3_bridge.py",
            "tests/test_v3_auth_isolation.py::test_forged_host_and_origin_are_rejected",
            "tests/test_v3_auth_isolation.py::test_lan_api_without_origin_is_rejected",
            "tests/test_v3_auth_isolation.py::test_ws_burst_is_rate_limited",
        ],
        "旧证据只拒绝 keys；本批补伪造 Origin/Host、空 Origin 非环回、WS 突发限流。HTTPS 不在本轮。",
    ),
    "AC3-021": ("PASS", ["tests/test_v3_assets.py::test_chunked_resume_completes_once", "tests/test_v3_chunk_http.py"]),
    "AC3-022": ("PASS", ["tests/test_v3_assets.py::test_bad_magic_and_path_traversal_leave_no_tmp"]),
    "AC3-023": ("PASS", ["tests/test_v3_assets.py::test_complete_failure_is_not_durable"]),
    "AC3-024": ("PASS", ["tests/test_v3_assets.py::test_gc_skips_attempt_referenced_assets"]),
    "AC3-025": (
        "NOT_RUN",
        ["tests/test_v3_bridge.py"],
        "旧证据 ACK 恒为 durable=True，未阻断落地仍让 WS send 成功",
    ),
    "AC3-026": (
        "NOT_RUN",
        ["tests/test_v3_bridge.py"],
        "旧证据无断线重连与乱序重放",
    ),
    "AC3-027": ("PASS", ["tests/test_v3_remaining.py::test_tail_flush_on_commit_keeps_last_character"]),
    "AC3-028": (
        "NOT_RUN",
        ["src/doubao_typeless/ui/tokens.py"],
        "旧证据为 should_wake 源码，未混合心跳/重播/editor.activity",
    ),
    "AC3-029": (
        "NOT_RUN",
        ["docs/evidence/v3-product/result.json", "tests/test_v3_runtime.py::test_hud_idle_is_hidden"],
        "旧证据为空闲隐藏单测/产品截图，10 分钟连接静置见 AC3-081 BLOCKED_NATIVE",
    ),
    "AC3-030": (
        "NOT_RUN",
        ["docs/evidence/v3-product/result.json"],
        "旧证据有插入后 HUD，未测 6 秒静置隐藏与 900ms 结果窗",
    ),
    "AC3-031": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_hotkeys_do_not_bind_escape"],
        "旧证据为源码不含 Esc 绑定，未在 HUD 显示时把 Esc 交给外部编辑器",
    ),
    "AC3-032": (
        "NOT_RUN",
        ["docs/evidence/v3-capture/result.json"],
        "旧证据为区域截图像素/DPR，不是 HUD 在 100/150/200% 与全屏下的位置",
    ),
    "AC3-033": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_hotkey_repeat_fires_once_until_release"],
        "旧证据为 HotkeyGate 注入时钟，不是系统 Alt+I repeat",
    ),
    "AC3-034": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_wait_modifiers_true_when_none_held"],
        "旧证据为 get_async 桩，不是真实按住 Alt/Shift 再 Ctrl+V",
    ),
    "AC3-035": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_lock_and_elevated_do_not_drop_bundle"],
        "旧证据为 is_locked/is_elevated 回调桩，不是真实锁屏或提权窗口",
    ),
    "AC3-036": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_clipboard_interference_stops_without_paste"],
        "旧证据为剪贴板读回桩，不是其他程序中途改剪贴板",
    ),
    "AC3-037": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-038": ("BLOCKED_NATIVE", ["docs/evidence/v3-web/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-039": (
        "NOT_RUN",
        ["web/src/app.ts", "tests/test_v3_web_source.py"],
        "旧证据为源码关键字，未测空内容/失联/上传中按钮态",
    ),
    "AC3-040": ("BLOCKED_NATIVE", ["docs/evidence/v3-web/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-041": ("BLOCKED_NATIVE", ["docs/evidence/v3-capture/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-042": (
        "NOT_RUN",
        ["docs/evidence/v3-capture/result.json", "tests/test_v3_capture.py::test_region_cancel_does_not_grab"],
        "旧证据为编程 bbox/取消不 grab，不是热键叠加层取消后再完成",
    ),
    "AC3-043": (
        "NOT_RUN",
        ["docs/evidence/v3-capture/result.json"],
        "旧证据为单屏 DPR=2 色块，无负坐标显示器跨边界",
    ),
    "AC3-044": (
        "PASS",
        ["tests/test_v3_capture.py", "docs/evidence/v3-capture/result.json"],
        "适用范围：过期 request/取消/限流单测；锁屏与 HWND 拒绝未在真实会话验证",
    ),
    "AC3-045": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-046": ("BLOCKED_NATIVE", ["docs/evidence/v3-web/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-047": (
        "NOT_RUN",
        ["web/src/editor/canvas.ts"],
        "旧证据为画布源码，未执行裁剪→撤销→恢复像素链",
    ),
    "AC3-048": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-049": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-050": ("BLOCKED_NATIVE", ["docs/evidence/v3-web/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-051": ("BLOCKED_NATIVE", ["web/src/editor/canvas.ts", "docs/evidence/v3-ime/result.json"]),
    "AC3-052": (
        "NOT_RUN",
        ["web/src/editor/canvas.ts"],
        "旧证据为源码，未跑 50 步混合撤销重做",
    ),
    "AC3-053": ("BLOCKED_NATIVE", ["docs/evidence/v3-web/whiteboard-number.png", "docs/evidence/v3-ime/result.json"]),
    "AC3-054": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-055": (
        "NOT_RUN",
        ["web/src/editor/canvas.ts"],
        "旧证据为源码，未测网格开关/导出不含网格/旋转不改画布",
    ),
    "AC3-056": ("BLOCKED_NATIVE", ["docs/evidence/v3-product/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-057": (
        "NOT_RUN",
        ["web/src/editor/canvas.ts", "src/doubao_typeless/storage/asset_store.py"],
        "旧证据为源码，未解码导出文件检查遮挡像素与 EXIF",
    ),
    "AC3-058": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-059": (
        "NOT_RUN",
        ["docs/evidence/v3-web/whiteboard-number.png"],
        "旧证据为桌面编号截图，未测两图重排后说明引用",
    ),
    "AC3-060": (
        "NOT_RUN",
        ["web/src/app.ts"],
        "旧证据为源码，层级含真机，未测导出失败保稿",
    ),
    "AC3-061": (
        "NOT_RUN",
        ["docs/evidence/v3-product/result.json", "docs/evidence/v3-soak/result.json"],
        "旧证据为 V3ComposerTarget 产品窗先图后文与协议浸泡，不是已验证 Cursor Composer",
    ),
    "AC3-062": ("PASS", ["tests/test_v3_core_services.py::test_delivery_unknown_image_does_not_paste_text_or_enter"]),
    "AC3-063": ("PASS", ["tests/test_v3_runtime.py::test_delivery_stops_remaining_when_target_changes"]),
    "AC3-064": ("PASS", ["tests/test_v3_runtime.py::test_frozen_bundle_ignores_later_draft_edits"]),
    "AC3-065": (
        "NOT_RUN",
        ["src/doubao_typeless/app.py", "src/doubao_typeless/ui/recovery.py"],
        "旧证据为源码路径，未在代码区失败后点 Composer 按 Alt+Shift+I",
    ),
    "AC3-066": (
        "NOT_RUN",
        ["src/doubao_typeless/core/policy.py"],
        "旧证据为 policy 函数，未在真实目标做只补文字召回",
    ),
    "AC3-067": ("PASS", ["tests/test_v3_remaining.py::test_unknown_recovery_never_ctrl_a_delete"]),
    "AC3-068": ("PASS", ["tests/test_v3_core_services.py"]),
    "AC3-069": ("PASS", ["tests/test_v3_runtime.py::test_history_last_is_not_current_draft", "tests/test_v3_sqlite_history.py"]),
    "AC3-070": ("PASS", ["tests/test_v3_sqlite_history.py"]),
    "AC3-071": ("PASS", ["tests/test_v3_runtime.py::test_history_gc_keeps_protected_and_caps"]),
    "AC3-072": (
        "NOT_RUN",
        ["src/doubao_typeless/services/byok.py"],
        "旧证据为源码，未模拟凭据库不可用并导出无 key 诊断包",
    ),
    "AC3-073": ("BLOCKED_NATIVE", ["docs/evidence/v3-product/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-074": ("PASS", ["tests/test_v3_runtime.py::test_byok_skips_without_key_and_rejects_images"]),
    "AC3-075": ("PASS", ["tests/test_v3_runtime.py::test_terms_hint_never_auto_replaces"]),
    "AC3-076": ("PASS", ["tests/test_v3_runtime.py::test_byok_stale_revision_does_not_overwrite"]),
    "AC3-077": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-078": (
        "NOT_RUN",
        ["docs/evidence/baseline/AC3-003/hotkey-migration.md"],
        "旧证据为迁移说明文档，未导入自定义旧快捷键跑 Windows 注册",
    ),
    "AC3-079": (
        "NOT_RUN",
        ["src/doubao_typeless/platform/windows/hotkeys.py"],
        "旧证据为源码，未在外部占用热键时观察失败提示",
    ),
    "AC3-080": (
        "NOT_RUN",
        ["tests/test_v3_runtime.py::test_capture_requires_grant"],
        "旧证据为授权表单测，层级含真机，未在拒绝截图后继续文字同步",
    ),
    "AC3-081": ("BLOCKED_NATIVE", ["docs/evidence/v3-idle/result.json"]),
    "AC3-082": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-083": ("BLOCKED_NATIVE", ["docs/evidence/v3-soak/result.json", "docs/evidence/v3-ime/result.json"]),
    "AC3-084": (
        "PASS",
        ["docs/evidence/v3-pack/result.json", "web/dist/index.html"],
        "适用范围：本地 onedir 统计；不是 GitHub Release 产物",
    ),
    "AC3-085": (
        "NOT_RUN",
        [".github/workflows/preview-v3.yml", "docs/evidence/v3-ci/result.json"],
        "workflow 已补 Pillow；本 SHA 的 GitHub Actions 尚未跑绿",
    ),
    "AC3-086": (
        "NOT_RUN",
        ["tests/test_v3_remaining.py::test_migration_invalid_json_does_not_write"],
        "旧证据仅 invalid JSON 不写回，不是脱敏迁移失败后重跑再回退",
    ),
    "AC3-087": (
        "PASS",
        [
            "tests/test_v3_remaining.py::test_instance_lock_does_not_kill_other",
            "tests/test_v3_auth_isolation.py::test_start_stops_without_writers_when_lock_held",
            "docs/evidence/v3-review/counterexamples.json",
        ],
        "旧证据仅锁文件互斥；本批补 start() 失败即停且不写 pair.txt。不是稳定版 exe 与候选 exe 同机对打",
    ),
    "AC3-088": ("NOT_RUN", []),
    "AC3-089": ("BLOCKED_NATIVE", ["docs/evidence/v3-cursor/result.json"]),
    "AC3-090": ("BLOCKED_NATIVE", ["docs/evidence/v3-ime/result.json"]),
    "AC3-091": ("BLOCKED_NATIVE", ["docs/evidence/v3-review/INDEPENDENT_REVIEW.md"]),
    "AC3-092": (
        "NOT_RUN",
        ["tests/test_v3_core_services.py", "tests/test_v3_bridge.py"],
        "旧证据不是乱序断线/过期 intent/插入中退出红队矩阵",
    ),
    "AC3-093": ("NOT_RUN", ["docs/evidence/v3-review/INDEPENDENT_REVIEW.md"]),
    "AC3-094": (
        "NOT_RUN",
        ["docs/release/preview-notes.md"],
        "旧证据为预览说明，不是 R01–R11 逐项追溯表",
    ),
    "AC3-095": (
        "PASS",
        [
            "docs/release/preview-notes.md",
            "docs/evidence/v3-runtime/BLOCKED_NATIVE.md",
            "docs/evidence/v3-review/counterexamples.json",
            "docs/pocket-composer-v3/fixtures/acceptance.json",
        ],
        "本批已把缺少步骤证据或与代码矛盾的 PASS 降级并保留旧证据范围说明",
    ),
    "AC3-096": ("PASS", ["docs/release/daily-use-switch.md"]),
}


def _unpack(entry):
    if len(entry) == 2:
        return entry[0], entry[1], None
    return entry[0], entry[1], entry[2]


def main() -> int:
    cases = json.loads(AC_PATH.read_text(encoding="utf-8"))
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED_NATIVE": 0, "NOT_RUN": 0, "DEFERRED": 0}
    for case in cases:
        raw = MAP.get(case["id"])
        if raw is None:
            status, evidence, note = case["status"], case.get("evidence") or [], case.get("note")
        else:
            status, evidence, note = _unpack(raw)
        case["status"] = status
        case["evidence"] = evidence
        if note:
            case["note"] = note
        elif "note" in case:
            del case["note"]
        counts[status] = counts.get(status, 0) + 1
    AC_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
