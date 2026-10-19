import json
import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger("quiz")

SYSTEM_PROMPT = (
    "你是有色金属与钢铁行业的培训阅卷老师。"
    "请对照题目、标准答案和评分要点给学员打分。"
    "语义相近即可给分，不要要求措辞一致；漏掉关键要点要扣分；答非所问或明显错误给低分。"
    "只输出一个 JSON 对象，不要 Markdown。格式："
    '{"score": 0到100的整数, "feedback": "不超过100字的评语", '
    '"hit_points": ["已覆盖要点"], "missed_points": ["遗漏要点"], '
    '"analysis": "对照评分要点写150到350字，说明答对了什么、漏了什么、和标准答案差在哪里"}'
)


@dataclass
class LLMGrade:
    score: int | None = None
    feedback: str = ""
    hit_points: list[str] = field(default_factory=list)
    missed_points: list[str] = field(default_factory=list)
    analysis: str = ""
    error: str = ""
    model: str = ""


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text[:80])
    return items[:8]


def _message_text(message) -> str:
    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(getattr(part, "text", "") or ""))
        content = "\n".join(part for part in parts if part)
    text = str(content).strip()
    if not text:
        text = str(getattr(message, "reasoning_content", "") or "").strip()
    return text


def _parse_grade(text: str) -> LLMGrade:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no json")
    data = json.loads(raw[start : end + 1])
    score = int(round(float(data["score"])))
    if not 0 <= score <= 100:
        raise ValueError("score out of range")
    feedback = str(data.get("feedback") or "").strip()[:500]
    analysis = str(data.get("analysis") or "").strip()[:2000]
    return LLMGrade(
        score=score,
        feedback=feedback,
        analysis=analysis,
        hit_points=_as_str_list(data.get("hit_points")),
        missed_points=_as_str_list(data.get("missed_points")),
        model=settings.DEEPSEEK_MODEL,
    )


def grade_with_llm(question, user_answer: str, similarity: float) -> LLMGrade:
    if not settings.DEEPSEEK_API_KEY:
        return LLMGrade(error="未配置 DeepSeek API Key，本次只按相似度记分。")

    points = question.scoring_points.strip() or "（没有单独要点，请对照标准答案）"
    user_prompt = (
        f"行业：{question.get_industry_display()}\n"
        f"模块：{question.module or '未标注'}\n"
        f"难度：{question.difficulty or '未标注'}\n"
        f"题目：{question.question}\n\n"
        f"标准答案：{question.standard_answer}\n\n"
        f"评分要点：{points}\n\n"
        f"学员答案：{user_answer}\n\n"
        f"向量余弦相似度仅供参考：{similarity:.3f}。分数必须依据要点，不要直接照搬相似度。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        from openai import BadRequestError, OpenAI

        client = OpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            timeout=90,
        )
        payloads = [
            {
                "response_format": {"type": "json_object"},
                "extra_body": {"enable_thinking": False},
            },
            {"extra_body": {"enable_thinking": False}},
            {},
        ]
        response = None
        for index, extra in enumerate(payloads):
            try:
                response = client.chat.completions.create(
                    model=settings.DEEPSEEK_MODEL,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1200,
                    **extra,
                )
                break
            except BadRequestError as exc:
                if "no provider supported" in str(exc) or index == len(payloads) - 1:
                    raise
        text = _message_text(response.choices[0].message)
        if not text:
            return LLMGrade(error="DeepSeek 没有返回评语，已按相似度记分。")
        return _parse_grade(text)
    except Exception as exc:
        logger.exception("DeepSeek 评分失败")
        detail = str(exc)
        if "no provider supported" in detail:
            return LLMGrade(
                error=f"模型 {settings.DEEPSEEK_MODEL} 当前没有可用服务，已按相似度记分。"
            )
        return LLMGrade(error="DeepSeek 评分暂时失败，已按相似度记分。")
