from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path("", views.home, name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="quiz/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("questions/<int:pk>/", views.question_detail, name="question"),
    path("records/<int:pk>/", views.record_detail, name="record"),
    path("me/", views.profile, name="profile"),
    path("account/", views.account, name="account"),
]
