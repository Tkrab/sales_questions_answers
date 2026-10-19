import csv
from pathlib import Path

from django.conf import settings


FILES = (
    ("有色行业问答题库_255题.csv", "nonferrous"),
    ("钢铁行业知识库_问答.csv", "steel"),
)

LIMITS = {
    "code": 32,
    "module": 120,
    "difficulty": 16,
    "qtype": 40,
    "scene": 80,
    "keywords": 400,
    "source": 255,
}


def _clean(value) -> str:
    return (value or "").strip()


def _clip(value, field: str) -> str:
    return _clean(value)[: LIMITS[field]]


def _normalize(row: dict) -> dict:
    return {(_clean(key)): value for key, value in row.items() if key}


def _base_row(industry: str, code: str, question: str, answer: str) -> dict:
    return {
        "industry": industry,
        "code": _clip(code, "code"),
        "module": "",
        "difficulty": "",
        "qtype": "",
        "scene": "",
        "keywords": "",
        "question": question.strip(),
        "standard_answer": answer.strip(),
        "scoring_points": "",
        "source": "",
        "notes": {},
    }


def load_nonferrous(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = _normalize(raw)
            code = _clean(row.get("题号"))
            question = _clean(row.get("题目"))
            answer = _clean(row.get("标准答案"))
            if not code or not question or not answer:
                continue
            item = _base_row("nonferrous", code, question, answer)
            item.update(
                {
                    "module": _clip(row.get("模块"), "module"),
                    "difficulty": _clip(row.get("难度"), "difficulty"),
                    "qtype": _clip(row.get("题型"), "qtype"),
                    "scene": _clip(row.get("场景标签"), "scene"),
                    "scoring_points": _clean(row.get("评分要点")),
                    "source": _clip(row.get("来源资料"), "source"),
                }
            )
            yield item


def load_steel(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = _normalize(raw)
            code = _clean(row.get("编号"))
            question = _clean(row.get("问题"))
            answer = _clean(row.get("答案"))
            if not code or not question or not answer:
                continue
            item = _base_row("steel", code, question, answer)
            item.update(
                {
                    "module": _clip(row.get("主题"), "module"),
                    "qtype": "问答题",
                    "keywords": _clip(row.get("关键词"), "keywords"),
                    "source": _clip(row.get("来源文件"), "source"),
                    "notes": {
                        "来源页码": _clean(row.get("来源页码")),
                        "内容性质": _clean(row.get("内容性质")),
                        "适用说明": _clean(row.get("适用说明")),
                    },
                }
            )
            yield item


def load_corpus(data_dir: Path | None = None) -> list[dict]:
    root = Path(data_dir or settings.DATA_DIR)
    rows = []
    seen = set()
    for filename, industry in FILES:
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(path)
        parser = load_nonferrous if industry == "nonferrous" else load_steel
        for row in parser(path):
            key = (row["industry"], row["code"])
            if key in seen:
                raise ValueError(f"重复题目：{key[0]} {key[1]}")
            seen.add(key)
            rows.append(row)
    return rows
