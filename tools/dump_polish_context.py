"""
打印前台纠错会组装的 system / user（不调 LLM）。
用法（项目根目录）：python tools/dump_polish_context.py
可选：python tools/dump_polish_context.py "你的测试转写一句"
"""

from __future__ import annotations

import os
import sys

# 保证可从任意 cwd 运行
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from config import Config
from polish import PolishConfig, TextPolisher, USER_CORRECT_PREFIX
from term_bank import load_recent_final_texts


def main() -> int:
    cfg = Config.load()
    sample = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "测一下 action 和 release 还有 gemini 云代码 openclaw"
    )
    pc = PolishConfig(
        enabled=cfg.llm_enabled,
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        timeout=cfg.llm_timeout,
        dictionary_path=cfg.dictionary_path,
        llm_system_prompt=cfg.llm_system_prompt,
        suggest_domain_terms=cfg.suggest_domain_terms,
        domain_terms_path=cfg.domain_terms_path,
        review_history_path=cfg.review_history_path,
        domain_term_topic_window=cfg.domain_term_topic_window,
        domain_terms_prompt_cap=cfg.domain_terms_prompt_cap,
        domain_terms_max_store=cfg.domain_terms_max_store,
        learn_enabled=cfg.learn_enabled,
        learn_base_url=cfg.learn_base_url,
        learn_api_key=cfg.learn_api_key,
        learn_model=cfg.learn_model,
        learn_timeout=cfg.learn_timeout,
        learning_samples_path=cfg.learning_samples_path,
        learn_system_prompt=cfg.learn_system_prompt,
        learn_user_prompt=cfg.learn_user_prompt,
        dict_write_mode=cfg.dict_write_mode,
        dict_auto_min_confidence=cfg.dict_auto_min_confidence,
        dict_auto_max_pairs=cfg.dict_auto_max_pairs,
        dict_block_regexes=cfg.dict_block_regexes,
    )
    p = TextPolisher(pc, logger=None)

    window = max(1, int(cfg.domain_term_topic_window or 50))
    finals = load_recent_final_texts(cfg.review_history_path, window)
    system = p.build_foreground_system()
    user = USER_CORRECT_PREFIX + sample

    print("=== 配置摘要（无密钥）===")
    print(f"  suggest_domain_terms: {cfg.suggest_domain_terms}")
    print(f"  domain_term_topic_window: {window}")
    print(f"  domain_terms_prompt_cap: {cfg.domain_terms_prompt_cap}")
    print(f"  review_history 取到终稿条数: {len(finals)}")
    print(f"  term_bank 加载术语数: {len(p.term_bank)}")
    print(f"  system 总长度: {len(system)} 字符")
    print(f"  user 总长度: {len(user)} 字符")
    print()
    print("=== system（全文）===")
    print(system)
    print()
    print("=== user（全文）===")
    print(user)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
