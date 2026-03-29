"""
读项目根目录 config.json，触发一次后台学习 API（无差异紧凑 payload）。
用于冒烟，不等同于手机桥接审阅流程。

用法（在项目根目录）:
  python tools/run_learn_once.py
  python tools/run_learn_once.py "自定义一段要学习的正文"
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from polish import PolishConfig, TextPolisher


DEFAULT_TEXT = (
    "你说已经 git push origin master 了，对，并且推送了 v0.1.0。"
    "让我到仓库的 Actions 里看 Release 是否跑绿，Releases 里是否出现 DoubaoTypeless 的 exe。"
)


def _polisher_from_config(cfg: Config) -> TextPolisher:
    return TextPolisher(
        PolishConfig(
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
        ),
        logger=lambda m: print(m, flush=True),
        redact_user_logs=False,
    )


async def _run(text: str) -> int:
    cfg = Config.load()
    if not cfg.learn_enabled:
        print("config 里 learn_enabled=false，跳过。", file=sys.stderr)
        return 2
    if not (cfg.learn_base_url and cfg.learn_api_key and cfg.learn_model):
        print("学习用 Base URL / Key / Model 未配齐。", file=sys.stderr)
        return 2
    t = (text or "").strip() or DEFAULT_TEXT
    p = _polisher_from_config(cfg)
    try:
        ok = await p.learn_from_review(
            raw_text=t,
            llm_text=t,
            final_text=t,
            accepted_suggestions=[],
        )
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        return 1
    finally:
        await p.close()
    print("learn_from_review:", "OK" if ok else "False")
    print("样本:", cfg.learning_samples_path)
    print("术语库:", cfg.domain_terms_path)
    return 0 if ok else 1


def main() -> None:
    arg = " ".join(sys.argv[1:]).strip()
    raise SystemExit(asyncio.run(_run(arg)))


if __name__ == "__main__":
    main()
