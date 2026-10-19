import logging

from django.conf import settings

from ..models import AnswerRecord
from .embeddings import get_embedder
from .grader import grade_with_llm
from .vectors import VectorStoreError, cosine, get_store

logger = logging.getLogger("quiz")


class ScoringError(Exception):
    pass


def similarity_to_score(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))) * 100, 1)


def blend_score(similarity_score, llm_score, sim_weight=None, llm_weight=None) -> float:
    sim_weight = settings.SCORE_SIMILARITY_WEIGHT if sim_weight is None else sim_weight
    llm_weight = settings.SCORE_LLM_WEIGHT if llm_weight is None else llm_weight
    semantic = max(0.0, min(100.0, float(similarity_score)))
    if llm_score is None:
        return round(semantic, 1)
    language = max(0.0, min(100.0, float(llm_score)))
    final = semantic * float(sim_weight) + language * float(llm_weight)
    return round(max(0.0, min(100.0, final)), 1)


def score_attempt(user, question, user_answer: str) -> AnswerRecord:
    try:
        user_vector = get_embedder().embed_one(user_answer)
    except Exception as exc:
        logger.exception("用户答案向量化失败")
        raise ScoringError("向量模型暂时不可用，请稍后再试。") from exc

    try:
        stored = get_store().get_embedding(question.industry, question.code)
    except VectorStoreError as exc:
        raise ScoringError(str(exc)) from exc

    if not stored or not stored.get("embedding"):
        raise ScoringError("这道题还没有向量。请先执行 python manage.py ingest_knowledge。")
    if stored.get("model") and stored.get("model") != settings.EMBEDDING_MODEL:
        raise ScoringError("题库向量与当前模型不一致，请重新导入知识库。")
    if len(stored["embedding"]) != len(user_vector):
        raise ScoringError("向量维度不一致，请重新导入知识库。")

    similarity = cosine(user_vector, stored["embedding"])
    similarity_score = similarity_to_score(similarity)
    grade = grade_with_llm(question, user_answer, similarity)
    final_score = blend_score(similarity_score, grade.score)
    return AnswerRecord.objects.create(
        user=user,
        question=question,
        user_answer=user_answer.strip(),
        similarity=round(similarity, 6),
        similarity_score=similarity_score,
        llm_score=grade.score,
        final_score=final_score,
        feedback=grade.feedback,
        analysis=grade.analysis,
        hit_points=grade.hit_points,
        missed_points=grade.missed_points,
        llm_error=grade.error[:300],
        grader_model=grade.model,
    )
