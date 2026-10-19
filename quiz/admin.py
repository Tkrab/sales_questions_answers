from django.contrib import admin

from .models import AnswerRecord, Question, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "department")
    search_fields = ("user__username", "display_name", "department")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "industry", "module", "difficulty", "active", "position")
    list_filter = ("industry", "difficulty", "active")
    search_fields = ("code", "question", "standard_answer", "keywords", "module")


@admin.register(AnswerRecord)
class AnswerRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "question",
        "final_score",
        "similarity_score",
        "llm_score",
        "created_at",
    )
    list_filter = ("question__industry",)
    search_fields = ("user__username", "question__code", "user_answer")
    readonly_fields = ("created_at",)
