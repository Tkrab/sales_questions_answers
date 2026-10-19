from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="用户",
    )
    display_name = models.CharField("姓名", max_length=50, blank=True)
    department = models.CharField("部门", max_length=100, blank=True)

    class Meta:
        verbose_name = "个人信息"
        verbose_name_plural = "个人信息"

    def __str__(self):
        return self.display_name or self.user.get_username()


class Question(models.Model):
    INDUSTRY_NONFERROUS = "nonferrous"
    INDUSTRY_STEEL = "steel"
    INDUSTRY_CHOICES = [
        (INDUSTRY_NONFERROUS, "有色行业"),
        (INDUSTRY_STEEL, "钢铁行业"),
    ]

    industry = models.CharField("行业", max_length=20, choices=INDUSTRY_CHOICES, db_index=True)
    code = models.CharField("题号", max_length=32)
    module = models.CharField("模块", max_length=120, blank=True)
    difficulty = models.CharField("难度", max_length=16, blank=True)
    qtype = models.CharField("题型", max_length=40, blank=True)
    scene = models.CharField("场景", max_length=80, blank=True)
    keywords = models.CharField("关键词", max_length=400, blank=True)
    question = models.TextField("题目")
    standard_answer = models.TextField("标准答案")
    scoring_points = models.TextField("评分要点", blank=True)
    source = models.CharField("来源", max_length=255, blank=True)
    notes = models.JSONField("补充信息", default=dict, blank=True)
    position = models.PositiveIntegerField("排序", default=0, db_index=True)
    active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "题目"
        verbose_name_plural = "题目"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["industry", "code"],
                name="uniq_question_industry_code",
            )
        ]
        indexes = [
            models.Index(fields=["active", "industry"]),
            models.Index(fields=["industry", "module"]),
        ]

    def __str__(self):
        return f"{self.code} {self.question[:28]}"


class AnswerRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="answer_records",
        verbose_name="用户",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name="题目",
    )
    user_answer = models.TextField("学员答案")
    similarity = models.FloatField("余弦相似度")
    similarity_score = models.FloatField("相似度得分")
    llm_score = models.FloatField("模型得分", null=True, blank=True)
    final_score = models.FloatField("综合得分")
    feedback = models.TextField("评语", blank=True)
    analysis = models.TextField("要点分析", blank=True)
    hit_points = models.JSONField("命中要点", default=list, blank=True)
    missed_points = models.JSONField("遗漏要点", default=list, blank=True)
    llm_error = models.CharField("评分说明", max_length=300, blank=True)
    grader_model = models.CharField("评分模型", max_length=120, blank=True)
    created_at = models.DateTimeField("作答时间", auto_now_add=True)

    class Meta:
        verbose_name = "作答记录"
        verbose_name_plural = "作答记录"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "question"]),
        ]

    def __str__(self):
        return f"{self.user} {self.question.code} {self.final_score}"
