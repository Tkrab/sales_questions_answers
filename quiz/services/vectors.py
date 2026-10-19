import threading

import numpy as np
from django.conf import settings
from django.utils import timezone
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError


class VectorStoreError(Exception):
    pass


def cosine(left, right) -> float:
    a = np.asarray(left, dtype=np.float32)
    b = np.asarray(right, dtype=np.float32)
    if a.shape != b.shape or a.size == 0:
        return 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class VectorStore:
    def __init__(self):
        self.client = MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=4000,
        )
        self.collection = self.client[settings.MONGO_DB_NAME][settings.MONGO_COLLECTION]

    def ping(self):
        try:
            self.client.admin.command("ping")
        except PyMongoError as exc:
            raise VectorStoreError(
                "无法连接 MongoDB。请先在本机启动 27017 端口，或运行 start_mongo.ps1。"
            ) from exc

    def ensure_indexes(self):
        self.ping()
        self.collection.create_index(
            [("industry", 1), ("code", 1)],
            unique=True,
            name="industry_code",
        )

    def existing_hashes(self) -> dict[tuple[str, str], tuple]:
        self.ping()
        found = {}
        cursor = self.collection.find(
            {},
            {"industry": 1, "code": 1, "model": 1, "answer_hash": 1},
        )
        for doc in cursor:
            found[(doc.get("industry"), doc.get("code"))] = (
                doc.get("model"),
                doc.get("answer_hash"),
            )
        return found

    def upsert_many(self, docs: list[dict]):
        if not docs:
            return
        now = timezone.now()
        ops = [
            UpdateOne(
                {"industry": doc["industry"], "code": doc["code"]},
                {"$set": {**doc, "updated_at": now}},
                upsert=True,
            )
            for doc in docs
        ]
        self.collection.bulk_write(ops, ordered=False)

    def delete_except(self, keep: set[tuple[str, str]]):
        self.ping()
        if not keep:
            return
        self.collection.delete_many(
            {"$nor": [{"industry": industry, "code": code} for industry, code in keep]}
        )

    def get_embedding(self, industry: str, code: str):
        self.ping()
        return self.collection.find_one(
            {"industry": industry, "code": code},
            {"embedding": 1, "model": 1, "dim": 1},
        )


_store = None
_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = VectorStore()
    return _store
