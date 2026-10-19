from datetime import timedelta

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from quiz.models import AnswerRecord, Question
from quiz.services.corpus import load_corpus
from quiz.services.grader import _parse_grade
from quiz.templatetags.quiz_extras import score_level
from quiz.services.vectors import cosine


class CorpusTests(SimpleTestCase):
    def test_both_industries_load(self):
        rows = load_corpus()
        nonferrous = [row for row in rows if row["industry"] == "nonferrous"]
        steel = [row for row in rows if row["industry"] == "steel"]
        self.assertGreaterEqual(len(nonferrous), 250)
        self.assertGreaterEqual(len(steel), 270)
        self.assertTrue(all(row["question"] and row["standard_answer"] for row in rows))
        self.assertTrue(
            all(row["code"].startswith(("M", "ST-")) for row in rows)
        )


class ScoreMathTests(SimpleTestCase):
    def test_cosine(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0, places=6)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0, places=6)
        self.assertEqual(cosine([0, 0], [1, 0]), 0.0)

    def test_score_bands(self):
        self.assertEqual(score_level(80), "good")
        self.assertEqual(score_level(79.9), "mid")
        self.assertEqual(score_level(50), "mid")
        self.assertEqual(score_level(49.9), "low")

    def test_parse_grade_keeps_analysis(self):
        grade = _parse_grade(
            '{"score": 88, "feedback": "覆盖了主要要点", '
            '"hit_points": ["电耗"], "missed_points": ["恢复周期"], '
            '"analysis": "学员提到了电耗，但没有说明停电后的恢复周期。"}'
        )
        self.assertEqual(grade.score, 88)
        self.assertIn("恢复周期", grade.analysis)


class PageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("learner", password="Learn-qa-2026")
        self.client.login(username="learner", password="Learn-qa-2026")
        self.question = Question.objects.create(
            industry=Question.INDUSTRY_STEEL,
            code="ST-TEST",
            module="测试",
            question="钢和生铁如何区分？",
            standard_answer="以含碳量约 2.11% 为界。",
            position=1,
            active=True,
        )

    def test_home_requires_login(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)

    def test_home_lists_question(self):
        response = self.client.get("/")
        self.assertContains(response, "钢和生铁如何区分")
        self.assertNotContains(response, "平均分")
        self.assertNotContains(response, 'name="module"')

    def test_question_hides_standard_answer(self):
        response = self.client.get(f"/questions/{self.question.pk}/")
        self.assertContains(response, "钢和生铁如何区分")
        self.assertNotContains(response, "2.11%")

    def test_profile_page(self):
        response = self.client.get("/me/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的学习")
        self.assertNotContains(response, "平均分")
        self.assertNotContains(response, "最高分")
        self.assertNotContains(response, "个人信息")
        AnswerRecord.objects.create(
            user=self.user,
            question=self.question,
            user_answer="含碳量更高的是生铁。",
            similarity=0.62,
            similarity_score=62,
            final_score=62,
        )
        AnswerRecord.objects.create(
            user=self.user,
            question=self.question,
            user_answer="含碳量大约 2% 是分界。",
            similarity=0.4,
            similarity_score=40,
            final_score=40,
        )
        again = self.client.get("/me/")
        self.assertContains(again, "学习历史")
        self.assertContains(again, "钢和生铁如何区分", count=1)
        self.assertContains(again, "2 次")
        self.assertContains(again, "history-board")
        self.assertContains(again, "行业掌握")
        self.assertNotContains(again, "行业占比")
        self.assertContains(again, "本周均分")
        self.assertContains(again, "上周均分")
        self.assertContains(again, "掌握程度高")
        self.assertContains(again, "掌握程度低")
        self.assertContains(again, "xx行业")
        self.assertContains(again, "成绩走势")
        self.assertContains(again, "按天")
        self.assertContains(again, "按周")
        self.assertContains(again, "按月")
        older = AnswerRecord.objects.filter(user=self.user, final_score=80)
        if not older.exists():
            past = AnswerRecord.objects.create(
                user=self.user,
                question=self.question,
                user_answer="八天前的答案。",
                similarity=0.8,
                similarity_score=80,
                final_score=80,
            )
            AnswerRecord.objects.filter(pk=past.pk).update(
                created_at=timezone.now() - timedelta(days=8)
            )
            again = self.client.get("/me/")
        charts = {chart["grain"]: chart for chart in again.context["trend_charts"]}
        self.assertEqual([point["score_text"] for point in charts["day"]["series"][0]["points"]], ["80", "51"])
        self.assertEqual(len(charts["week"]["series"][0]["points"]), 2)
        self.assertEqual(charts["month"]["series"][0]["points"][0]["score_text"], "60.7")
        self.assertEqual(charts["day"]["series"][0]["color"], "#c56a32")
        self.assertContains(again, "钢铁行业")
        radar = again.context["radar"]
        self.assertEqual([axis["label"] for axis in radar["axes"]], ["有色行业", "钢铁行业", "xx行业", "xx行业", "xx行业"])
        self.assertEqual(radar["axes"][1]["this_text"], "51")
        self.assertEqual(radar["axes"][1]["last_text"], "80")
        self.assertEqual(radar["low"], ["钢铁行业"])
        self.assertEqual(radar["high"], [])
        self.assertContains(again, "50 到 80")

    def test_account_page_has_profile_form(self):
        response = self.client.get("/account/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "个人中心")
        self.assertContains(response, "个人信息")
