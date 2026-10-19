from ..models import AnswerRecord
from .grader import grade_with_llm


class ScoringError(Exception):
    pass


def score_attempt(user, question, user_answer: str) -> AnswerRecord:
    grade = grade_with_llm(question, user_answer)
    if grade.score is None:
        raise ScoringError(grade.error or "模型没有给出分数，这次没有记分。")
    final_score = round(max(0.0, min(100.0, float(grade.score))), 1)
    return AnswerRecord.objects.create(
        user=user,
        question=question,
        user_answer=user_answer.strip(),
        similarity=None,
        similarity_score=None,
        llm_score=final_score,
        final_score=final_score,
        feedback=grade.feedback,
        analysis=grade.analysis,
        hit_points=grade.hit_points,
        missed_points=grade.missed_points,
        llm_error="",
        grader_model=grade.model,
    )
