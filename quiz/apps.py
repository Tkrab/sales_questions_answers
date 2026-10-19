import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger("quiz")


class QuizConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "quiz"
    verbose_name = "知识问答"

    def ready(self):
        from . import signals  # noqa: F401

        argv = sys.argv
        running_server = "runserver" in argv
        is_server_process = os.environ.get("RUN_MAIN") == "true" or "--noreload" in argv
        if not (running_server and is_server_process):
            return
        if os.environ.get("SKIP_MODEL_PRELOAD") == "1":
            return
        try:
            from .services.embeddings import get_embedder

            get_embedder().load()
        except Exception:
            logger.exception("向量模型预加载失败，题库仍可浏览，提交答案时会再试一次。")
