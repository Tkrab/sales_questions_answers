import math
from datetime import timedelta

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


TREND_GRAINS = (
    ("day", "按天"),
    ("week", "按周"),
    ("month", "按月"),
)


def _trend_period(local_dt, grain):
    day = local_dt.date()
    if grain == "week":
        start = day - timedelta(days=day.weekday())
        return start, start.strftime("%m-%d") + "周"
    if grain == "month":
        start = day.replace(day=1)
        return start, start.strftime("%Y-%m")
    return day, day.strftime("%m-%d")


def _trend_chart(records, labels, grain, title):
    scores = {}
    period_text = {}
    industries = []
    seen = set()
    for record in records.order_by("created_at"):
        local = timezone.localtime(record.created_at)
        key, text = _trend_period(local, grain)
        industry = record.question.industry
        scores.setdefault((key, industry), []).append(float(record.final_score))
        period_text[key] = text
        if industry not in seen:
            seen.add(industry)
            industries.append(industry)
    industries.sort(key=lambda item: (item != "nonferrous", item != "steel", item))
    periods = sorted(period_text)

    width, height = 640, 240
    left, right, top, bottom = 42, 36, 16, 34
    inner_w = width - left - right
    inner_h = height - top - bottom

    def x_at(index):
        if len(periods) <= 1:
            return left + inner_w / 2
        return left + inner_w * index / (len(periods) - 1)

    def y_at(score):
        score = max(0.0, min(100.0, float(score)))
        return top + inner_h * (100 - score) / 100

    series = []
    for industry in industries:
        points = []
        for index, period in enumerate(periods):
            values = scores.get((period, industry))
            if not values:
                continue
            average = sum(values) / len(values)
            points.append(
                {
                    "x": round(x_at(index), 1),
                    "y": round(y_at(average), 1),
                    "score_text": _score_text(average),
                    "when": period_text[period],
                }
            )
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

    mark_count = len(periods)
    if mark_count <= 5:
        mark_indexes = list(range(mark_count))
    else:
        mark_indexes = sorted({0, mark_count - 1, *[round(step * (mark_count - 1) / 4) for step in range(1, 4)]})
    x_labels = []
    for index in mark_indexes:
        if mark_count > 1 and index == 0:
            anchor = "start"
        elif mark_count > 1 and index == mark_count - 1:
            anchor = "end"
        else:
            anchor = "middle"
        x_labels.append(
            {
                "x": round(x_at(index), 1),
                "text": period_text[periods[index]],
                "anchor": anchor,
            }
        )
    return {
        "grain": grain,
        "title": title,
        "series": series,
        "grid": [{"y": round(y_at(value), 1), "label": str(value)} for value in (0, 25, 50, 75, 100)],
        "x_labels": x_labels,
        "width": width,
        "height": height,
        "label_y": height - 12,
        "plot_left": left,
        "plot_right": width - right,
    }


def _trend_charts(records, labels):
    return [_trend_chart(records, labels, grain, title) for grain, title in TREND_GRAINS]


RADAR_AXES = (
    (Question.INDUSTRY_NONFERROUS, "有色行业", True),
    (Question.INDUSTRY_STEEL, "钢铁行业", True),
    ("xx-1", "xx行业", False),
    ("xx-2", "xx行业", False),
    ("xx-3", "xx行业", False),
)
MASTERY_HIGH = 80


def _score_text(value) -> str:
    if value is None:
        return "暂无"
    number = round(float(value), 1)
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}"


def _radar_chart(records):
    now = timezone.now()
    this_start = now - timedelta(days=7)
    last_start = now - timedelta(days=14)
    count = len(RADAR_AXES)
    cx, cy, radius = 220, 168, 102
    label_radius = 138

    def average_between(industry, start, end):
        matched = records.filter(question__industry=industry, created_at__gte=start)
        if end is not None:
            matched = matched.filter(created_at__lt=end)
        return matched.aggregate(avg=Avg("final_score"))["avg"]

    def point_at(index, score):
        angle = -math.pi / 2 + index * 2 * math.pi / count
        distance = radius * max(0.0, min(100.0, float(score or 0))) / 100
        return (
            round(cx + distance * math.cos(angle), 1),
            round(cy + distance * math.sin(angle), 1),
        )

    axes = []
    high = []
    low = []
    for index, (key, label, real) in enumerate(RADAR_AXES):
        this_avg = last_avg = overall = None
        if real:
            this_avg = average_between(key, this_start, None)
            last_avg = average_between(key, last_start, this_start)
            overall = records.filter(question__industry=key).aggregate(avg=Avg("final_score"))["avg"]
            current = next(
                (value for value in (this_avg, last_avg, overall) if value is not None),
                None,
            )
            if current is not None:
                (high if current >= MASTERY_HIGH else low).append(label)
        angle = -math.pi / 2 + index * 2 * math.pi / count
        cosine = math.cos(angle)
        if cosine > 0.35:
            anchor = "start"
        elif cosine < -0.35:
            anchor = "end"
        else:
            anchor = "middle"
        axes.append(
            {
                "label": label,
                "this_week": this_avg,
                "last_week": last_avg,
                "this_text": _score_text(this_avg),
                "last_text": _score_text(last_avg),
                "this_point": point_at(index, this_avg),
                "last_point": point_at(index, last_avg),
                "label_x": round(cx + label_radius * cosine, 1),
                "label_y": round(cy + label_radius * math.sin(angle), 1),
                "anchor": anchor,
            }
        )

    def pack(attr):
        return " ".join(f"{axis[attr][0]},{axis[attr][1]}" for axis in axes)

    return {
        "cx": cx,
        "cy": cy,
        "rings": [radius * step / 4 for step in (1, 2, 3, 4)],
        "spoke_ends": [
            {"x": point_at(index, 100)[0], "y": point_at(index, 100)[1]}
            for index in range(count)
        ],
        "this_points": pack("this_point"),
        "last_points": pack("last_point"),
        "axes": axes,
        "high": high,
        "low": low,
    }


def _history_page(records, page_number):
    grouped = {}
    order = []
    for record in records.order_by("-created_at"):
        key = record.question_id
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(record)
    groups = []
    for key in order:
        attempts = grouped[key]
        latest = attempts[0]
        groups.append(
            {
                "question": latest.question,
                "attempts": attempts,
                "day": timezone.localtime(latest.created_at).strftime("%Y-%m-%d"),
            }
        )
    page_obj = Paginator(groups, 8).get_page(page_number)
    history_days = []
    for item in page_obj.object_list:
        if not history_days or history_days[-1]["day"] != item["day"]:
            history_days.append({"day": item["day"], "items": []})
        history_days[-1]["items"].append(item)
    return page_obj, history_days


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
    difficulty = request.GET.get("difficulty", "").strip()
    keyword = request.GET.get("q", "").strip()
    valid_industries = {key for key, _label in Question.INDUSTRY_CHOICES}

    qs = Question.objects.filter(active=True)
    if industry in valid_industries:
        qs = qs.filter(industry=industry)
    else:
        industry = ""

    difficulties = list(
        qs.exclude(difficulty="")
        .values_list("difficulty", flat=True)
        .distinct()
        .order_by("difficulty")
    )
    if difficulty not in difficulties:
        difficulty = ""
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
    return render(
        request,
        "quiz/home.html",
        {
            "page_obj": page_obj,
            "industry": industry,
            "difficulty": difficulty,
            "keyword": keyword,
            "difficulties": difficulties,
            "industries": Question.INDUSTRY_CHOICES,
            "total": Question.objects.filter(active=True).count(),
            "covered": mine.values("question_id").distinct().count(),
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
    page_obj, history_days = _history_page(records, request.GET.get("page"))
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
            "trend_charts": _trend_charts(records, labels),
            "radar": _radar_chart(records),
            "module_rows": module_rows,
            "page_obj": page_obj,
            "history_days": history_days,
            "pager_suffix": _pager_suffix(request),
        },
    )
