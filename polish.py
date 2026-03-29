"""
TextPolisher — 语音转写后的文本处理：前台兼容 OpenAI Chat Completions 的模型生成替换建议；
后台学习将审阅结果写入 JSONL 样本；可选将学习结果按规则追加至词典文件（带备份）。
"""

import asyncio
import json
import re
import shutil
import time

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from term_bank import TermBank, load_recent_final_texts


# 配置留空（自动）时使用的温度：略大于 0，避免过僵；MiniMax 仍须 ≤1
DEFAULT_CHAT_TEMPERATURE = 0.3


def _is_minimax_openai_base(url: str) -> bool:
    u = (url or "").lower()
    return "minimaxi.com" in u or "minimax.io" in u


def effective_chat_temperature(base_url: str, configured: float | None) -> float:
    """
    解析 chat/completions 使用的 temperature。
    configured 为 None 时用 DEFAULT_CHAT_TEMPERATURE（当前 0.3）；MiniMax 上 >1 压到 1。
    显式配置在 MiniMax 上若 <=0 会抬到 0.01（接口要求 (0,1]）。
    见 https://platform.minimaxi.com/docs/api-reference/text-openai-api
    """
    if configured is not None:
        t = float(configured)
        if _is_minimax_openai_base(base_url):
            if t <= 0:
                return 0.01
            return min(t, 1.0)
        return t
    t = DEFAULT_CHAT_TEMPERATURE
    if _is_minimax_openai_base(base_url):
        return min(t, 1.0)
    return t


def _normalize_openai_base_url(url: str) -> str:
    """MiniMax 文档要求 Base 为 https://api.minimaxi.com/v1（常漏写 /v1）。"""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if _is_minimax_openai_base(u) and not u.lower().endswith("/v1"):
        return u + "/v1"
    return u


def openai_compat_base_url(url: str) -> str:
    """与 TextPolisher 一致的 OpenAI 兼容 Base（含 MiniMax 补 /v1）。"""
    return _normalize_openai_base_url((url or "").strip())


def _reasoning_details_text(msg: dict) -> str:
    """MiniMax reasoning_split=True 时，思考在 message.reasoning_details[].text。"""
    rd = msg.get("reasoning_details")
    if not rd or not isinstance(rd, list):
        return ""
    parts: list[str] = []
    for item in rd:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or ""))
    return "".join(parts).strip()


def _strip_minimax_think_suffix(content: str) -> str:
    """未开 reasoning_split 时，M2 系可能在 content 内嵌思考块再跟正文；取最后一个闭合标记之后。"""
    s = (content or "").strip()
    if not s:
        return s
    for marker in ("`/think`",):
        if marker in s:
            s = s.split(marker)[-1].strip()
    return s


def _minimax_openai_extra_fields(base_url: str) -> dict:
    """MiniMax 文档：reasoning_split 将思考与正文分离，便于只取 content。"""
    if _is_minimax_openai_base(base_url):
        return {"reasoning_split": True}
    return {}


def _assistant_reply_text(data: dict, *, openai_base_url: str) -> str:
    """从 chat/completions 首条 choice 取助手可见正文（兼容 MiniMax / 智谱等）。"""
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    mm = _is_minimax_openai_base(openai_base_url)
    c_raw = _flatten_openai_message_content(msg.get("content"))
    if mm:
        c_raw = _strip_minimax_think_suffix(c_raw)
    r = (msg.get("reasoning_content") or "").strip()
    rd = _reasoning_details_text(msg)
    for part in (c_raw, r, rd):
        t = (part or "").strip()
        if t:
            return t
    return ""


class LearnJsonError(ValueError):
    """后台学习模型返回内容无法解析为合法 JSON 对象（不写入样本、不标记已处理）。"""



SYSTEM_PROMPT = """\
你是语音转写（ASR）的“专名与术语纠错器”，不是写作润色器。

你只允许做一件事：把被语音识别听错的专有名词、品牌/产品名、专业术语、外文专名等（听成近音字、错英文拼写、多字少字时），改成正确写法。与用户领域无关的普通词不要动。

严禁做的事（违反即视为错误输出）：
- 修改用户正常的中文口语、语气、句式、连接词、语序（不要为了“更通顺”“更书面”而改写）
- 把用户说得不够“标准”的表达改成你以为更好的说法
- 删句、并句、加解释、加标点“优化”、总结或扩写
- 把整段话改成关键词列表或提纲

输出要求：
- 输出必须是完整文本，长度与原文接近（不少于原文字符数约 60%），禁止摘要或大幅删减
- 除被纠正的专名/术语片段外，其余文字尽量与原文逐字相同
- 不确定某个词是否听错时，必须保留原文
- 不要输出任何说明，只输出纠正后的全文"""

# 置于用户消息前，引导模型仅纠错专名术语，避免过度改写口语
USER_CORRECT_PREFIX = (
    "【任务】仅修正语音转写里的专有名词、品牌/产品名、专业术语、外文专名等同音或近形误识。"
    "禁止改写正常中文表述、语气、句式或润色。除必须替换的词外，其余与原文保持一致。\n\n"
    "【转写】\n"
)

LEARN_PROMPT = """\
【输出纪律】禁止思考链、禁止步骤说明、禁止复述题目。
除 JSON 外不要输出任何汉字、英文说明、markdown、``` 围栏或空行前缀。
有效输出只能是：一个 JSON 对象；第 1 个字符必须是 {，最后 1 个字符必须是 }；顶层必须含 notes、candidate_pairs、domain_terms。

输入为 JSON 对象，格式：{"items":[ 记录1, 记录2, ... ]}。可能只有一条。

每条记录为下列之一（优先紧凑形以省 token）：

1) 无差异或正文完全相同：ASR、前台纠错建议、用户终稿三者相同；若另有采纳列表可写 accepted_suggestions。
   {"mode":"no_diff","text":"…完整一段…"}  或  同上对象加 "accepted_suggestions":[…]
   （禁止把同一段正文重复写三遍。）

2) 有差异时的紧凑形：
   • 前台建议与 ASR 相同，仅终稿不同：
     {"raw_text":"…","llm_same_as_raw":true,"final_text":"…","accepted_suggestions":[]}
   • 终稿与 ASR 相同，前台曾给不同建议（用户改回）：
     {"raw_text":"…","llm_text":"…","final_same_as_raw":true,"accepted_suggestions":[]}
   • 终稿与前台建议一致，与 ASR 不同：
     {"raw_text":"…","llm_text":"…","final_same_as_llm":true,"accepted_suggestions":[]}
   • 三者两两不完全相同时用完整形：
     {"raw_text":"…","llm_text":"…","final_text":"…","accepted_suggestions":[]}

请提取「对今后纠错有参考价值」的观察，返回**严格 JSON 一份**（仅此对象，不要其它说明）。
**顶层必须包含**键名 `notes`、`candidate_pairs`、`domain_terms`（均可为空数组）；**禁止**把用户消息里的 `{"items":[...]}` 再抄一遍当作你的输出（那是输入格式，不是答案）。

{
  "notes": ["..."],
  "candidate_pairs": [{"wrong": "...", "correct": "..."}],
  "domain_terms": ["..."]
}

规则：
1. candidate_pairs 仅作参考样本；不要整句级替换；不确定则空数组
2. domain_terms：从各条 final/无差异时的 text 等提炼正确写法的专名术语，每条 2～24 字符；单条记录最多约 12 条，**多条 items 时合并去重**，总数建议不超过 24 条
3. 多条 items 时：notes / domain_terms / candidate_pairs 均合并去重，综合全文判断
4. mode=no_diff 时：candidate_pairs 一般为空；仅当有明确误听↔纠正对时可写，禁止臆造
"""

LEARN_SYSTEM_DEFAULT = "你是语音纠错学习分析器。禁止输出思考过程或自然语言说明，只输出一个 JSON 对象。"

# 追加在自定义 learn_system_prompt 之后，强化对推理模型的约束
LEARN_SYSTEM_SUFFIX = (
    "你是输出管道，不是讲解员。回复体=唯一一个 JSON 对象，不得含 JSON 之外的字符。"
    "禁止：「好的」「首先」「输入是」「记录详情」「用户希望」「我需要」等任何分析或过渡语。"
    "允许：直接从 { 开始到 } 结束，且含 notes、candidate_pairs、domain_terms 三个键（数组可为 []）。"
)


def build_compact_learn_item(
    raw_text: str,
    llm_text: str,
    final_text: str,
    accepted_suggestions: list,
) -> dict:
    """构造学习 API 用的单条紧凑 JSON，避免无差异时重复传三遍正文。"""
    raw = (raw_text or "").strip()
    llm = (llm_text or "").strip()
    fin = (final_text or "").strip()
    acc = accepted_suggestions if isinstance(accepted_suggestions, list) else []
    if raw == llm == fin:
        d: dict = {"mode": "no_diff", "text": raw}
        if acc:
            d["accepted_suggestions"] = acc
        return d
    out: dict = {"accepted_suggestions": acc}
    if raw == llm:
        out["raw_text"] = raw
        out["llm_same_as_raw"] = True
        out["final_text"] = fin
    elif fin == raw:
        out["raw_text"] = raw
        out["llm_text"] = llm
        out["final_same_as_raw"] = True
    elif fin == llm:
        out["raw_text"] = raw
        out["llm_text"] = llm
        out["final_same_as_llm"] = True
    else:
        out["raw_text"] = raw
        out["llm_text"] = llm
        out["final_text"] = fin
    return out


def _flatten_openai_message_content(content) -> str:
    """部分网关把 message.content 做成字符串或 [{type,text}] 片段列表。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if (p.get("type") or "") == "text" or "text" in p:
                    parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts).strip()
    return str(content).strip()


def _extract_balanced_json_object(s: str, start: int) -> str | None:
    """从 s[start]=='{' 起截取第一个花括号平衡的子串。"""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _learn_output_shape_ok(d: dict) -> bool:
    """
    学习模型应返回含 notes / domain_terms / candidate_pairs 的对象。
    勿把用户消息里的 {\"items\":[...]} 请求体回显当成结果（会导致术语库零增量）。
    """
    return any(k in d for k in ("notes", "domain_terms", "candidate_pairs"))


def parse_learn_model_json(raw: str, log, *, quiet_failure: bool = False) -> dict:
    """
    将学习模型返回的正文解析为 JSON 对象（容忍 markdown 代码块、前后说明、推理前缀）。
    若正文中出现多段 JSON，优先采用「含 notes/domain_terms/candidate_pairs」的段落，通常取最后一段（模型常在回显输入后再写答案）。
    quiet_failure：为 True 时不打「无法解析」类日志（供多段候选依次尝试时避免误报；仅最后一次尝试应传 False）。
    """
    s = (raw or "").replace("\ufeff", "").strip()
    if not s:
        raise LearnJsonError("empty learn model content")

    def try_load(candidate: str) -> dict | None:
        c = (candidate or "").strip()
        if not c:
            return None
        try:
            v = json.loads(c)
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            return None

    def accept(d: dict | None) -> dict | None:
        if d and _learn_output_shape_ok(d):
            return d
        return None

    if r := accept(try_load(s)):
        return r

    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE):
        if r := accept(try_load(m.group(1))):
            return r

    found: list[dict] = []
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        blob = _extract_balanced_json_object(s, i)
        if not blob:
            continue
        d = try_load(blob)
        if accept(d):
            found.append(d)
    if found:
        chosen = found[-1]
        if len(found) > 1:
            log(
                f"[learn] 从回复中解析出 {len(found)} 段「学习结果形」JSON，采用最后一段（避免误用 items 回显）"
            )
        return chosen

    # 模型先写长分析再在文末写 JSON（或被截断）：从最后一个 "notes" 锚点向前找 {
    search_end = len(s)
    while search_end > 0:
        ni = s.rfind('"notes"', 0, search_end)
        if ni < 0:
            break
        brace = s.rfind("{", 0, ni)
        if brace >= 0:
            blob = _extract_balanced_json_object(s, brace)
            if blob and (d := accept(try_load(blob))):
                log("[learn] 已通过 \"notes\" 锚点从长文中提取学习结果 JSON")
                return d
        search_end = ni

    sloppy = try_load(s)
    if (
        sloppy is not None
        and not _learn_output_shape_ok(sloppy)
        and not quiet_failure
    ):
        log(
            "[learn] 顶层 JSON 缺少 notes/domain_terms/candidate_pairs "
            "（常见：模型回显了用户消息里的 items）；已扫描全文仍无合法学习结果"
        )

    if not quiet_failure:
        preview = s[:160].replace("\n", " ")
        if len(s) > 160:
            preview += "…"
        log(f"[learn] JSON 无法解析为学习结果，正文预览: {preview!r}")
    raise LearnJsonError("invalid json: could not extract learn result object")


@dataclass
class PolishConfig:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 5.0
    dictionary_path: str = "./data/dictionary.txt"
    llm_system_prompt: str = ""

    learn_enabled: bool = False
    learn_base_url: str = ""
    learn_api_key: str = ""
    learn_model: str = ""
    learn_timeout: float = 8.0
    learning_samples_path: str = "./data/learning_samples.jsonl"
    learn_system_prompt: str = ""
    learn_user_prompt: str = ""
    # None = 由 effective_chat_temperature 使用 DEFAULT_CHAT_TEMPERATURE（0.3）
    llm_temperature: float | None = None
    learn_temperature: float | None = None

    dict_write_mode: str = "off"
    dict_auto_min_confidence: float = 0.0
    dict_auto_max_pairs: int = 8
    dict_block_regexes: str = ""

    # 专业术语采集：近窗审阅话题注入前台纠错（与 dictionary 错题集分离）
    suggest_domain_terms: bool = True
    domain_terms_path: str = "./data/domain_terms.json"
    review_history_path: str = "./data/review_history.json"
    domain_term_topic_window: int = 50
    domain_terms_prompt_cap: int = 80
    domain_terms_max_store: int = 300


@dataclass
class Suggestion:
    id: str
    source: str
    target: str
    start: int
    end: int
    reason: str = "llm"
    confidence: float = 0.5


@dataclass
class SuggestionBatch:
    raw_text: str
    llm_text: str
    suggestions: list[Suggestion]
    # 前台 API 未经校验回退的原始文本；后台学习用其判断模型是否曾提出与转写不同的文本
    api_llm_text: str = ""
    # 是否实际发起了 chat 请求；api_ok 仅在 api_called 时有效
    api_called: bool = False
    api_ok: bool = False
    # api_ok 为 False 时给界面用的短说明（如超时调大「前台超时」）
    api_fail_hint: str = ""


class Dictionary:
    """误听/误写 → 正确写法 对照表（文本行 wrong=correct），供前台 prompt 参考。"""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._mappings: list[tuple[str, str]] = []
        self.reload()

    def reload(self):
        self._mappings = []
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                wrong, correct = line.split("=", 1)
                wrong, correct = wrong.strip(), correct.strip()
                if wrong and correct:
                    self._mappings.append((wrong, correct))

    def as_prompt_hint(self) -> str:
        if not self._mappings:
            return ""
        lines = [f"{w} → {c}" for w, c in self._mappings]
        return (
            "下列为常见误听→正确专名/术语（仅当转写里出现左侧误听形式时，将对应片段替换为右侧；"
            "不要用于改写普通中文句子）：\n"
            + "\n".join(lines)
        )


class TextPolisher:
    def __init__(self, config: PolishConfig, logger=None, *, redact_user_logs: bool = False):
        self.config = config
        self._logger = logger
        self._redact_user_logs = redact_user_logs
        self.dictionary = Dictionary(config.dictionary_path)
        self.term_bank = TermBank(
            config.domain_terms_path,
            max_store=config.domain_terms_max_store,
            log=self._log if logger else None,
        )
        self.term_bank.load()
        self._client: httpx.AsyncClient | None = None
        self._learn_client: httpx.AsyncClient | None = None

    def _log(self, msg: str):
        if self._logger:
            self._logger(msg)

    def _effective_llm_system(self) -> str:
        s = (self.config.llm_system_prompt or "").strip()
        return s if s else SYSTEM_PROMPT

    def _effective_learn_system(self) -> str:
        s = (self.config.learn_system_prompt or "").strip()
        base = s if s else LEARN_SYSTEM_DEFAULT
        return f"{base.rstrip()}\n\n{LEARN_SYSTEM_SUFFIX}"

    def _effective_learn_user_task(self) -> str:
        s = (self.config.learn_user_prompt or "").strip()
        return s if s else LEARN_PROMPT

    def _compile_block_patterns(self) -> list[re.Pattern]:
        patterns: list[re.Pattern] = []
        for line in (self.config.dict_block_regexes or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line))
            except re.error as e:
                self._log(f"[dict.auto] 跳过无效正则: {line!r} err={e}")
        return patterns

    @staticmethod
    def _pair_passes_block_regexes(
        wrong: str, correct: str, patterns: list[re.Pattern]
    ) -> bool:
        for pat in patterns:
            if pat.search(wrong) or pat.search(correct):
                return False
        return True

    def _pair_ok_for_dictionary(self, wrong: str, correct: str, conf: float | None) -> bool:
        if not wrong or not correct or wrong == correct:
            return False
        if len(wrong) < 2 or len(correct) < 2:
            return False
        if len(wrong) > 24 or len(correct) > 24:
            return False
        if "\n" in wrong or "\n" in correct or "=" in wrong or "=" in correct:
            return False
        if any(ch in wrong + correct for ch in "。！？；;"):
            return False
        if self._is_style_only_change(wrong, correct):
            return False
        min_c = float(self.config.dict_auto_min_confidence or 0.0)
        if min_c > 0.0 and conf is None:
            return False
        if conf is not None and conf < min_c:
            return False
        if wrong in correct and len(correct) - len(wrong) > 6:
            return False
        if correct in wrong and len(wrong) - len(correct) > 6:
            return False
        return True

    def _auto_append_dictionary_from_learn(self, parsed: dict) -> None:
        mode = (self.config.dict_write_mode or "off").strip().lower()
        if mode != "auto":
            return
        raw_pairs = parsed.get("candidate_pairs") or []
        if not isinstance(raw_pairs, list):
            return
        max_n = max(1, min(50, int(self.config.dict_auto_max_pairs or 8)))
        patterns = self._compile_block_patterns()
        dict_path = Path(self.config.dictionary_path)
        existing_wrong = {w for w, _ in self.dictionary._mappings}
        to_add: list[tuple[str, str]] = []
        for item in raw_pairs:
            if len(to_add) >= max_n:
                break
            if not isinstance(item, dict):
                continue
            wrong = str(item.get("wrong", "")).strip()
            correct = str(item.get("correct", "")).strip()
            conf = item.get("confidence")
            conf_f = float(conf) if isinstance(conf, (int, float)) else None
            if not self._pair_ok_for_dictionary(wrong, correct, conf_f):
                continue
            if not self._pair_passes_block_regexes(wrong, correct, patterns):
                continue
            if wrong in existing_wrong:
                continue
            to_add.append((wrong, correct))
            existing_wrong.add(wrong)
        if not to_add:
            return
        dict_path.parent.mkdir(parents=True, exist_ok=True)
        backup = dict_path.with_name(dict_path.name + ".bak")
        try:
            if dict_path.exists():
                shutil.copy2(dict_path, backup)
        except Exception as e:
            self._log(f"[dict.auto] 备份失败，取消写入: {e}")
            return
        try:
            with open(dict_path, "a", encoding="utf-8") as f:
                for w, c in to_add:
                    f.write(f"{w}={c}\n")
        except Exception as e:
            self._log(f"[dict.auto] 写入失败: {e}")
            return
        self.dictionary.reload()
        self._log(
            "[dict.auto] "
            f"对照表追加 appended={len(to_add)} path='{dict_path}' backup='{backup.name}'"
        )

    @staticmethod
    def _preview(text: str, limit: int = 80) -> str:
        text = text.replace("\n", "\\n")
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    @staticmethod
    def _is_useful_fragment(text: str) -> bool:
        if not text.strip():
            return False
        if len(text.strip()) < 2:
            return False
        return True

    def _ensure_client(self, *, learning: bool = False) -> httpx.AsyncClient:
        if learning:
            if self._learn_client is None or self._learn_client.is_closed:
                raw = (self.config.learn_base_url or "").strip()
                norm = _normalize_openai_base_url(raw)
                base_url = norm.rstrip("/") + "/" if norm else ""
                self._learn_client = httpx.AsyncClient(
                    base_url=base_url,
                    headers={
                        "Authorization": f"Bearer {self.config.learn_api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=httpx.Timeout(self.config.learn_timeout, connect=5.0),
                )
            return self._learn_client

        if self._client is None or self._client.is_closed:
            raw = (self.config.base_url or "").strip()
            norm = _normalize_openai_base_url(raw)
            base_url = norm.rstrip("/") + "/" if norm else ""
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout, connect=5.0),
            )
        return self._client

    def _suggest_timeout_for(self, text: str) -> float:
        base = max(self.config.timeout, 5.0)
        extra = len(text) / 80.0
        return min(12.0, max(base, 3.0 + extra))

    async def build_suggestions(self, raw_text: str) -> SuggestionBatch:
        if not self.config.enabled or not self.config.base_url or not self.config.api_key or not self.config.model:
            return SuggestionBatch(raw_text=raw_text, llm_text=raw_text, suggestions=[], api_llm_text="")
        if len(raw_text) < 3:
            return SuggestionBatch(raw_text=raw_text, llm_text=raw_text, suggestions=[], api_llm_text="")

        try:
            api_llm, elapsed_ms, status_code = await self._llm_correct(raw_text)
            llm_text = api_llm
            if not self._is_valid_llm_output(raw_text, llm_text):
                llm_text = raw_text
            suggestions = self._build_diff_suggestions(raw_text, llm_text)
            if not suggestions and llm_text != raw_text:
                llm_text = raw_text
            if suggestions or llm_text != raw_text or elapsed_ms >= 4000:
                if self._redact_user_logs:
                    self._log(
                        "[suggest.result] "
                        f"http_status={status_code} elapsed_ms={elapsed_ms} "
                        f"suggestions={len(suggestions)} "
                        f"raw_len={len(raw_text)} llm_len={len(llm_text)} "
                        "(正文已默认脱敏，设 DT_VERBOSE_LOG=1 可记录片段)"
                    )
                else:
                    self._log(
                        "[suggest.result] "
                        f"http_status={status_code} elapsed_ms={elapsed_ms} "
                        f"suggestions={len(suggestions)} "
                        f"before='{self._preview(raw_text)}' "
                        f"after='{self._preview(llm_text)}'"
                    )
            return SuggestionBatch(
                raw_text=raw_text,
                llm_text=llm_text,
                suggestions=suggestions,
                api_llm_text=api_llm or "",
                api_called=True,
                api_ok=True,
            )
        except Exception as e:
            self._log(f"[suggest.error] {type(e).__name__}: {e}")
            hint = ""
            if isinstance(e, httpx.TimeoutException):
                hint = (
                    "纠错请求超时（慢模型常见）。请到「设置 → 高级」调大「前台超时(s)」后再试。"
                )
            return SuggestionBatch(
                raw_text=raw_text,
                llm_text=raw_text,
                suggestions=[],
                api_llm_text="",
                api_called=True,
                api_ok=False,
                api_fail_hint=hint,
            )

    def _is_style_only_change(self, raw_text: str, llm_text: str) -> bool:
        left = raw_text
        right = llm_text
        for old, new in (("你", "#"), ("您", "#"), ("妳", "#")):
            left = left.replace(old, "#")
            right = right.replace(old, "#")
        return left == right

    def _is_valid_llm_output(self, raw_text: str, llm_text: str) -> bool:
        if not llm_text or llm_text == raw_text:
            return True
        if "\n" in llm_text and "\n" not in raw_text:
            return False
        if len(llm_text) < len(raw_text) * 0.6:
            self._log(
                f"[suggest.error] LLM 输出过短，疑似摘要/截断 "
                f"raw_len={len(raw_text)} llm_len={len(llm_text)}"
            )
            return False
        if len(llm_text) - len(raw_text) > max(24, int(len(raw_text) * 0.2)):
            return False
        if self._is_style_only_change(raw_text, llm_text):
            return False
        return True

    def _build_diff_suggestions(self, raw_text: str, llm_text: str) -> list[Suggestion]:
        if llm_text == raw_text:
            return []
        raw_tokens = self._tokenize_with_spans(raw_text)
        llm_tokens = self._tokenize_with_spans(llm_text)
        if raw_tokens and llm_tokens:
            token_suggestions = self._build_token_suggestions(raw_text, llm_text, raw_tokens, llm_tokens)
            if token_suggestions:
                return token_suggestions
        matcher = SequenceMatcher(a=raw_text, b=llm_text)
        suggestions: list[Suggestion] = []
        idx = 1
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            source = raw_text[i1:i2]
            target = llm_text[j1:j2]
            if not self._is_useful_fragment(source) and not self._is_useful_fragment(target):
                continue
            if len(source) > 24 or len(target) > 24:
                split_items = self._split_large_block(source, target, base_start=i1)
                if split_items:
                    for item in split_items:
                        item.id = f"s{idx}"
                        suggestions.append(item)
                        idx += 1
                continue
            suggestions.append(
                Suggestion(
                    id=f"s{idx}",
                    source=source,
                    target=target,
                    start=i1,
                    end=i2,
                    confidence=0.6,
                )
            )
            idx += 1
        return suggestions

    def _tokenize_with_spans(self, text: str) -> list[tuple[str, int, int]]:
        tokens: list[tuple[str, int, int]] = []
        pattern = r"[A-Za-z]+(?:[\s_-][A-Za-z]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]+|[^\s]"
        for match in re.finditer(pattern, text):
            token = match.group(0)
            if token.strip():
                tokens.append((token, match.start(), match.end()))
        return tokens

    def _build_token_suggestions(
        self,
        raw_text: str,
        llm_text: str,
        raw_tokens: list[tuple[str, int, int]],
        llm_tokens: list[tuple[str, int, int]],
    ) -> list[Suggestion]:
        matcher = SequenceMatcher(a=[t[0] for t in raw_tokens], b=[t[0] for t in llm_tokens])
        suggestions: list[Suggestion] = []
        idx = 1
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            source = raw_text[raw_tokens[i1][1]:raw_tokens[i2 - 1][2]] if i1 < i2 else ""
            target = llm_text[llm_tokens[j1][1]:llm_tokens[j2 - 1][2]] if j1 < j2 else ""
            if not self._is_useful_fragment(source) and not self._is_useful_fragment(target):
                continue
            if len(source) > 40 or len(target) > 40:
                continue
            start = raw_tokens[i1][1] if i1 < i2 else (raw_tokens[i1 - 1][2] if raw_tokens and i1 > 0 else 0)
            end = raw_tokens[i2 - 1][2] if i1 < i2 else start
            suggestions.append(
                Suggestion(
                    id=f"t{idx}",
                    source=source,
                    target=target,
                    start=start,
                    end=end,
                    confidence=0.72,
                )
            )
            idx += 1
        return suggestions

    def _split_large_block(self, source: str, target: str, *, base_start: int) -> list[Suggestion]:
        matcher = SequenceMatcher(a=source, b=target)
        items: list[Suggestion] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            sub_source = source[i1:i2]
            sub_target = target[j1:j2]
            if not self._is_useful_fragment(sub_source) and not self._is_useful_fragment(sub_target):
                continue
            if len(sub_source) > 24 or len(sub_target) > 24:
                continue
            items.append(
                Suggestion(
                    id="",
                    source=sub_source,
                    target=sub_target,
                    start=base_start + i1,
                    end=base_start + i2,
                    confidence=0.55,
                )
            )
        return items

    def build_foreground_system(self) -> str:
        """前台纠错请求里的 system 全文（词典 + 近窗术语）；不调 API，供排查上下文。"""
        system = self._effective_llm_system()
        dict_hint = self.dictionary.as_prompt_hint()
        if dict_hint:
            system += "\n\n" + dict_hint
        if getattr(self.config, "suggest_domain_terms", True):
            finals = load_recent_final_texts(
                self.config.review_history_path,
                max(1, int(self.config.domain_term_topic_window or 50)),
            )
            term_hint = self.term_bank.as_suggest_hint(
                finals,
                int(self.config.domain_terms_prompt_cap or 80),
            )
            if term_hint:
                system += "\n\n" + term_hint
        return system

    async def _llm_correct(self, text: str) -> tuple[str, int, int]:
        client = self._ensure_client()
        system = self.build_foreground_system()

        user_content = USER_CORRECT_PREFIX + text
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": effective_chat_temperature(
                self.config.base_url, self.config.llm_temperature
            ),
            "max_tokens": max(len(text) * 3, 256),
        }
        payload.update(_minimax_openai_extra_fields(self.config.base_url))
        started = time.perf_counter()
        resp = await client.post(
            "chat/completions",
            json=payload,
            timeout=httpx.Timeout(self._suggest_timeout_for(text), connect=5.0),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        resp.raise_for_status()
        data = resp.json()
        result = _assistant_reply_text(data, openai_base_url=self.config.base_url).strip()
        return (result or text), elapsed_ms, resp.status_code

    @staticmethod
    def _learn_response_candidates(data: dict, *, openai_base_url: str = "") -> list[str]:
        """OpenAI 形响应：reasoning_details / reasoning_content / content 等分别尝试解析。"""
        choices = data.get("choices") or []
        if not choices:
            return []
        msg = choices[0].get("message") or {}
        c = _flatten_openai_message_content(msg.get("content"))
        if _is_minimax_openai_base(openai_base_url):
            c = _strip_minimax_think_suffix(c)
        r = (msg.get("reasoning_content") or "").strip()
        rd = _reasoning_details_text(msg)
        # 智谱等推理模型常把最终 JSON 放在 reasoning_content；MiniMax 可能在 reasoning_details
        out: list[str] = []
        if rd:
            out.append(rd)
        if r:
            out.append(r)
        if c:
            out.append(c)
        for a, b in ((rd, r), (rd, c), (r, c)):
            if a and b and a != b:
                out.append(f"{a}\n{b}")
                out.append(f"{b}\n{a}")
        return out

    async def learn_from_review(
        self,
        *,
        raw_text: str,
        llm_text: str,
        final_text: str,
        accepted_suggestions: list[dict],
    ) -> bool:
        """单条学习：一次 API，payload 为紧凑 items（无差异时不重复传三遍正文）。"""
        return await self.learn_from_review_batch(
            [
                {
                    "raw_text": raw_text,
                    "llm_text": llm_text,
                    "final_text": final_text,
                    "accepted_suggestions": accepted_suggestions,
                }
            ]
        )

    async def learn_from_review_batch(self, records: list[dict]) -> bool:
        """多条合并为一次 API（items 数组）；成功返回 True，可逐条标记审阅历史已处理。"""
        if not records:
            return False
        if not self.config.learn_enabled or not self.config.learn_base_url or not self.config.learn_api_key or not self.config.learn_model:
            return False

        norm: list[dict] = []
        for r in records:
            norm.append(
                {
                    "raw_text": r.get("raw_text") or "",
                    "llm_text": r.get("llm_text") or "",
                    "final_text": r.get("final_text") or "",
                    "accepted_suggestions": r.get("accepted_suggestions") or [],
                }
            )

        compact_items = [
            build_compact_learn_item(
                x["raw_text"],
                x["llm_text"],
                x["final_text"],
                x["accepted_suggestions"],
            )
            for x in norm
        ]
        user_body = {"items": compact_items}
        user_json = json.dumps(user_body, ensure_ascii=False)
        user_content = (
            self._effective_learn_user_task()
            + "\n\n"
            + user_json
            + "\n\n【最终输出】"
            "只输出上述任务对应的 JSON 结果；不要分析过程。"
            "从本回复第 1 个可见字符起必须是 {，最后一字符必须是 }；"
            "不要复述 items，不要写 notes 以外的开场白。"
        )
        n_items = len(norm)
        # 推理模型会先写长分析再写 JSON，过小易截断导致无法解析
        max_tokens = min(8192, max(2500, 900 + 700 * n_items))

        client = self._ensure_client(learning=True)
        payload = {
            "model": self.config.learn_model,
            "messages": [
                {"role": "system", "content": self._effective_learn_system()},
                {"role": "user", "content": user_content},
            ],
            "temperature": effective_chat_temperature(
                self.config.learn_base_url, self.config.learn_temperature
            ),
            "max_tokens": max_tokens,
        }
        payload.update(_minimax_openai_extra_fields(self.config.learn_base_url))
        # MiniMax 兼容层未必支持 OpenAI 的 json_object；其它网关仍尽量约束 JSON
        if not _is_minimax_openai_base(self.config.learn_base_url):
            payload["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        resp = await asyncio.wait_for(
            client.post(
                "chat/completions",
                content=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
            ),
            timeout=self.config.learn_timeout,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        resp.raise_for_status()
        data = resp.json()
        ch0 = (data.get("choices") or [{}])[0]
        finish_reason = (ch0.get("finish_reason") or "").strip()
        usage = data.get("usage")
        candidates = self._learn_response_candidates(
            data, openai_base_url=self.config.learn_base_url
        )
        parsed: dict | None = None
        last_learn_err: LearnJsonError | None = None
        usable = [t for t in candidates if (t or "").strip()]
        n_u = len(usable)
        for idx, text in enumerate(usable):
            try:
                parsed = parse_learn_model_json(
                    text,
                    self._log,
                    quiet_failure=n_u > 1 and idx < n_u - 1,
                )
                if n_u > 1 and idx > 0:
                    self._log(
                        f"[learn] 第 {idx + 1}/{n_u} 段候选解析成功"
                        f"（前几段多为推理过程，非学习结果 JSON）"
                    )
                break
            except LearnJsonError as e:
                last_learn_err = e
        if parsed is None:
            if finish_reason == "length":
                self._log(
                    f"[learn] finish_reason=length（可能截断） usage={usage} "
                    f"max_tokens={max_tokens}；可换非推理模型或稍后重试"
                )
            if last_learn_err:
                self._log(
                    "[learn] JSON 解析失败，不写入样本、不标记已处理 "
                    f"elapsed_ms={elapsed_ms} err={last_learn_err}"
                )
                raise last_learn_err
            self._log("[learn] 模型返回空 content，不写入样本、不标记已处理")
            raise LearnJsonError("empty learn model content")

        ts = datetime.now().isoformat(timespec="seconds")
        if n_items == 1:
            r0 = norm[0]
            self._append_learning_sample(
                {
                    "ts": ts,
                    "raw_text": r0["raw_text"],
                    "llm_text": r0["llm_text"],
                    "final_text": r0["final_text"],
                    "accepted_suggestions": r0["accepted_suggestions"],
                    "learn_result": parsed,
                }
            )
        else:
            self._append_learning_sample(
                {
                    "ts": ts,
                    "batch": True,
                    "item_count": n_items,
                    "items": norm,
                    "learn_result": parsed,
                }
            )
        self._log(
            "[learn.sample_saved] "
            f"path='{self.config.learning_samples_path}' "
            f"http_status={resp.status_code} elapsed_ms={elapsed_ms} "
            f"items={n_items} user_chars={len(user_json)} "
            f"candidate_pairs={len(parsed.get('candidate_pairs', []))}"
        )
        self._auto_append_dictionary_from_learn(parsed)
        self.term_bank.merge_from_learn_parsed(parsed)
        return True

    def _append_learning_sample(self, sample: dict):
        path = Path(self.config.learning_samples_path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._learn_client and not self._learn_client.is_closed:
            await self._learn_client.aclose()
