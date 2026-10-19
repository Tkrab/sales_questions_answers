from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import AnswerForm, ProfileForm, RegisterForm
from .models import AnswerRecord, Question, UserProfile
from .services.scoring import ScoringError, score_attempt


INDUSTRY_COLORS = {
    "nonferrous": "#0e6b66",
    "steel": "#c56a32",
}


def _industry_charts(records, labels):
    covered = list(
        records.values("question__industry")
        .annotate(n=Count("question_id", distinct=True))
        .order_by("-n", "question__industry")
    )
    total = sum(row["n"] for row in covered) or 1
    slices = []
    start = 0.0
    for row in covered:
        industry = row["question__industry"]
        count = row["n"]
        share = count / total * 100
        end = start + share
        slices.append(
            {
                "industry": industry,
                "label": labels.get(industry, industry),
                "count": count,
                "percent": round(share, 1),
                "color": INDUSTRY_COLORS.get(industry, "#5c6b7a"),
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
        start = end
    if slices:
        slices[-1]["end"] = 100
    gradient = ", ".join(
        f"{item['color']} {item['start']}% {item['end']}%" for item in slices
    )

    ordered = list(records.order_by("created_at"))
    width, height = 640, 220
    left, right, top, bottom = 36, 16, 14, 28
    inner_w = width - left - right
    inner_h = height - top - bottom
    count = len(ordered)

    def x_at(index):
        if count <= 1:
            return left + inner_w / 2
        return left + inner_w * index / (count - 1)

    def y_at(score):
        score = max(0.0, min(100.0, float(score)))
        return top + inner_h * (100 - score) / 100

    grouped = {}
    for index, record in enumerate(ordered):
        industry = record.question.industry
        grouped.setdefault(industry, []).append(
            {
                "x": round(x_at(index), 1),
                "y": round(y_at(record.final_score), 1),
                "score": record.final_score,
            }
        )
    series = []
    for industry, points in grouped.items():
        path = " ".join(
            f"{'M' if index == 0 else 'L'}{point['x']},{point['y']}"
            for index, point in enumerate(points)
        )
        series.append(
            {
                "industry": industry,
                "label": labels.get(industry, industry),
                "color": INDUSTRY_COLORS.get(industry, "#5c6b7a"),
                "path": path,
                "points": points,
            }
        )
    series.sort(key=lambda item: 0 if item["industry"] == "nonferrous" else 1)
    grid = [{"y": round(y_at(value), 1), "label": str(value)} for value in (0, 50, 80, 100)]
    x_labels = []
    if ordered:
        marks = [0]
        if count > 2:
            marks.append(count // 2)
        if count > 1:
            marks.append(count - 1)
        seen = set()
        for index in marks:
            if index in seen:
                continue
            seen.add(index)
            when = timezone.localtime(ordered[index].created_at)
            x_labels.append({"x": round(x_at(index), 1), "text": when.strftime("%m-%d")})
    return {
        "gradient": gradient or "#efe7da 0% 100%",
        "slices": slices,
        "series": series,
        "grid": grid,
        "x_labels": x_labels,
        "width": width,
        "height": height,
        "plot_left": left,
        "plot_right": width - right,
    }


def _pager_suffix(request) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    encoded = query.urlencode()
    return f"&{encoded}" if encoded else ""


def _neighbors(question):
    siblings = Question.objects.filter(active=True, industry=question.industry)
    previous = siblings.filter(position__lt=question.position).order_by("-position").first()
    nxt = siblings.filter(position__gt=question.position).order_by("position").first()
    return previous, nxt


@login_required
@require_http_methods(["GET"])
def home(request):
    industry = request.GET.get("industry", "").strip()
    module = request.GET.get("module", "").strip()
    difficulty = request.GET.get("difficulty", "").strip()
    keyword = request.GET.get("q", "").strip()
    valid_industries = {key for key, _label in Question.INDUSTRY_CHOICES}

    qs = Question.objects.filter(active=True)
    if industry in valid_industries:
        qs = qs.filter(industry=industry)
    else:
        industry = ""

    facet = qs
    modules = list(
        facet.exclude(module="").values_list("module", flat=True).distinct().order_by("module")
    )
    difficulties = list(
        facet.exclude(difficulty="")
        .values_list("difficulty", flat=True)
        .distinct()
        .order_by("difficulty")
    )
    if module not in modules:
        module = ""
    if difficulty not in difficulties:
        difficulty = ""
    if module:
        qs = qs.filter(module=module)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if keyword:
        qs = qs.filter(
            Q(question__icontains=keyword)
            | Q(code__icontains=keyword)
            | Q(keywords__icontains=keyword)
            | Q(module__icontains=keyword)
        )

    best = AnswerRecord.objects.filter(
        user=request.user,
        question=OuterRef("pk"),
    ).order_by("-final_score")
    qs = qs.annotate(best_score=Subquery(best.values("final_score")[:1]))
    page_obj = Paginator(qs, 12).get_page(request.GET.get("page"))

    mine = AnswerRecord.objects.filter(user=request.user)
    agg = mine.aggregate(avg=Avg("final_score"), n=Count("id"))
    return render(
        request,
        "quiz/home.html",
        {
            "page_obj": page_obj,
            "industry": industry,
            "module": module,
            "difficulty": difficulty,
            "keyword": keyword,
            "modules": modules,
            "difficulties": difficulties,
            "industries": Question.INDUSTRY_CHOICES,
            "total": Question.objects.filter(active=True).count(),
            "covered": mine.values("question_id").distinct().count(),
            "average": agg["avg"],
            "pager_suffix": _pager_suffix(request),
        },
    )


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.display_name = form.cleaned_data["display_name"].strip()
        profile.department = form.cleaned_data["department"].strip()
        profile.save()
        login(request, user)
        messages.success(request, "账号已创建，可以开始练习。")
        return redirect("home")
    return render(request, "quiz/register.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def question_detail(request, pk):
    question = get_object_or_404(Question, pk=pk, active=True)
    if request.method == "POST":
        form = AnswerForm(request.POST)
        if form.is_valid():
            try:
                record = score_attempt(
                    request.user,
                    question,
                    form.cleaned_data["content"],
                )
            except ScoringError as exc:
                messages.error(request, str(exc))
            else:
                return redirect("record", record.pk)
    else:
        form = AnswerForm()
    previous, nxt = _neighbors(question)
    attempts = question.records.filter(user=request.user)[:5]
    return render(
        request,
        "quiz/question.html",
        {
            "question": question,
            "form": form,
            "attempts": attempts,
            "previous": previous,
            "next_question": nxt,
        },
    )


@login_required
@require_http_methods(["GET"])
def record_detail(request, pk):
    record = get_object_or_404(
        AnswerRecord.objects.select_related("question"),
        pk=pk,
    )
    if record.user_id != request.user.id and not request.user.is_staff:
        raise PermissionDenied
    previous, nxt = _neighbors(record.question)
    return render(
        request,
        "quiz/result.html",
        {
            "record": record,
            "previous": previous,
            "next_question": nxt,
            "sim_weight": round(settings.SCORE_SIMILARITY_WEIGHT * 100),
            "llm_weight": round(settings.SCORE_LLM_WEIGHT * 100),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "个人信息已更新。")
        return redirect("account")
    return render(
        request,
        "quiz/account.html",
        {"form": form, "profile_obj": profile_obj},
    )


@login_required
@require_http_methods(["GET"])
def profile(request):
    records = AnswerRecord.objects.filter(user=request.user).select_related("question")
    attempt_count = records.count()
    labels = dict(Question.INDUSTRY_CHOICES)
    industry_rows = []
    for row in records.values("question__industry").annotate(
        avg=Avg("final_score"),
        n=Count("id"),
    ):
        industry_rows.append(
            {
                "industry": row["question__industry"],
                "label": labels.get(row["question__industry"], row["question__industry"]),
                "avg": row["avg"] or 0,
                "n": row["n"],
            }
        )
    module_rows = []
    for row in (
        records.values("question__industry", "question__module")
        .annotate(avg=Avg("final_score"), n=Count("id"))
        .order_by("avg")
    ):
        module_rows.append(
            {
                "industry": row["question__industry"],
                "label": labels.get(row["question__industry"], ""),
                "module": row["question__module"] or "未分类",
                "avg": row["avg"] or 0,
                "n": row["n"],
            }
        )
    week_ago = timezone.now() - timedelta(days=7)
    page_obj = Paginator(records, 10).get_page(request.GET.get("page"))
    history_days = []
    for record in page_obj.object_list:
        day = timezone.localtime(record.created_at).strftime("%Y-%m-%d")
        if not history_days or history_days[-1]["day"] != day:
            history_days.append({"day": day, "items": []})
        history_days[-1]["items"].append(record)
    return render(
        request,
        "quiz/profile.html",
        {
            "attempt_count": attempt_count,
            "covered": records.values("question_id").distinct().count(),
            "week_count": records.filter(created_at__gte=week_ago).count(),
            "good_count": records.filter(final_score__gte=80).count(),
            "mid_count": records.filter(final_score__gte=50, final_score__lt=80).count(),
            "low_count": records.filter(final_score__lt=50).count(),
            "industry_rows": industry_rows,
            "industry_chart": _industry_charts(records, labels),
            "module_rows": module_rows,
            "page_obj": page_obj,
            "history_days": history_days,
            "pager_suffix": _pager_suffix(request),
        },
    )
