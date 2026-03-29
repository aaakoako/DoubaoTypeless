import json
from pathlib import Path
from dataclasses import dataclass, asdict

from paths import app_root

CONFIG_DIR = app_root()
CONFIG_PATH = CONFIG_DIR / "config.json"

# dict_write_mode: "off" | "auto"
DICT_WRITE_MODES = frozenset({"off", "auto"})


@dataclass
class Config:
    clipboard_protection: bool = True
    bridge_port: int = 8765
    # Windows：写入 HKCU\...\Run，随用户登录启动（源码用 pythonw 优先）
    start_with_windows: bool = False

    # Global hotkeys (pynput GlobalHotKeys format; empty = disabled)
    hotkey_toggle_review: str = "<ctrl>+<shift>+u"
    hotkey_insert: str = "<alt>+i"

    # Foreground suggestion model
    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: float = 8.0
    # None = 自动（默认 0.3，见 polish.DEFAULT_CHAT_TEMPERATURE）
    llm_temperature: float | None = None
    # Empty = use built-in default in polish.py
    llm_system_prompt: str = ""
    # 近窗审阅话题中的专业术语注入前台纠错（词库由后台学习写入，与 dictionary 错题集分离）
    suggest_domain_terms: bool = True
    domain_terms_path: str = "./data/domain_terms.json"
    domain_term_topic_window: int = 50
    domain_terms_prompt_cap: int = 80
    domain_terms_max_store: int = 300

    # Background learning model
    learn_enabled: bool = False
    learn_base_url: str = ""
    learn_api_key: str = ""
    learn_model: str = ""
    learn_timeout: float = 45.0
    learn_temperature: float | None = None
    learn_system_prompt: str = ""
    learn_user_prompt: str = ""

    # 纠错对照表（误听→正确，非纯名词库）；配置项名仍为 dictionary 以兼容旧版
    dictionary_path: str = "./data/dictionary.txt"
    learning_samples_path: str = "./data/learning_samples.jsonl"
    # 审阅历史（插入记录）持久化；关闭程序后仍可恢复
    review_history_path: str = "./data/review_history.json"
    # 批量自动学习：未满 N 条时的待处理队列（仅新插入产生，不会扫历史文件）
    learn_pending_path: str = "./data/learn_pending.json"
    # 0 = 每条可学习插入立即 1 次学习 API（单条 items，无差异时正文不重复传三遍）
    # N>=1 = 每累计 N 条合并为 1 次 API（同一请求内 items 数组）；历史菜单批量学习按同一 N 分块
    learn_batch_interval: int = 0
    # True：无「纠错差异」仍学习；与插入自动学习、历史菜单批量学习筛选一致；不会在启动时自动重学全部旧历史
    learn_when_no_diff: bool = False
    dict_write_mode: str = "auto"
    dict_auto_min_confidence: float = 0.6
    dict_auto_max_pairs: int = 8
    # One regex per line; empty lines ignored; invalid lines skipped at runtime with log
    dict_block_regexes: str = ""

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        config = cls()
        config.save()
        return config

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
