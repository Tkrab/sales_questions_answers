import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Question
from quiz.services.corpus import load_corpus
from quiz.services.embeddings import answer_digest, get_embedder
from quiz.services.vectors import VectorStoreError, get_store


class Command(BaseCommand):
    help = "把 CSV 题库写入 SQLite，并把标准答案向量写入 MongoDB。"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="只导入前 N 题，便于试跑。")
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="忽略已有向量，全部重新计算。",
        )

    def handle(self, *args, **options):
        started = time.perf_counter()
        try:
            rows = load_corpus()
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        limit = options["limit"]
        if limit:
            rows = rows[:limit]
        if not rows:
            raise CommandError("没有读到题目。")

        try:
            store = get_store()
            store.ensure_indexes()
            existing = {} if options["rebuild"] else store.existing_hashes()
        except VectorStoreError as exc:
            raise CommandError(str(exc)) from exc

        embedder = get_embedder()
        embedder.load()
        self.stdout.write(f"向量模型 {settings.EMBEDDING_MODEL}，设备 {embedder.device}")

        pending = []
        skipped = 0
        with transaction.atomic():
            for index, row in enumerate(rows, start=1):
                Question.objects.update_or_create(
                    industry=row["industry"],
                    code=row["code"],
                    defaults={
                        "module": row["module"],
                        "difficulty": row["difficulty"],
                        "qtype": row["qtype"],
                        "scene": row["scene"],
                        "keywords": row["keywords"],
                        "question": row["question"],
                        "standard_answer": row["standard_answer"],
                        "scoring_points": row["scoring_points"],
                        "source": row["source"],
                        "notes": row["notes"],
                        "position": index,
                        "active": True,
                    },
                )
                digest = answer_digest(settings.EMBEDDING_MODEL, row["standard_answer"])
                previous = existing.get((row["industry"], row["code"]))
                if previous == (settings.EMBEDDING_MODEL, digest):
                    skipped += 1
                    continue
                pending.append((row, digest))

        written = 0
        batch_size = 32
        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            vectors = embedder.embed(
                [row["standard_answer"] for row, _digest in chunk],
                progress=False,
            )
            docs = []
            for (row, digest), vector in zip(chunk, vectors):
                docs.append(
                    {
                        "industry": row["industry"],
                        "code": row["code"],
                        "model": settings.EMBEDDING_MODEL,
                        "answer_hash": digest,
                        "dim": len(vector),
                        "embedding": vector,
                    }
                )
            store.upsert_many(docs)
            written += len(docs)
            self.stdout.write(f"已写入向量 {written}/{len(pending)}")

        deactivated = 0
        if not limit:
            keep = {(row["industry"], row["code"]) for row in rows}
            current = set(Question.objects.values_list("industry", "code"))
            for industry, code in current - keep:
                deactivated += Question.objects.filter(
                    industry=industry,
                    code=code,
                    active=True,
                ).update(active=False)
            store.delete_except(keep)

        elapsed = time.perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"完成：题目 {len(rows)}，新向量 {written}，跳过 {skipped}，"
                f"停用 {deactivated}，耗时 {elapsed:.1f}s。"
            )
        )
