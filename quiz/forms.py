from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "用户名"
        self.fields["password"].label = "密码"


class RegisterForm(UserCreationForm):
    display_name = forms.CharField(label="姓名", max_length=50)
    department = forms.CharField(label="部门", max_length=100, required=False)

    class Meta:
        model = User
        fields = ("username",)

    field_order = ["username", "display_name", "department", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "用户名"
        self.fields["password1"].label = "密码"
        self.fields["password2"].label = "确认密码"
        self.fields["department"].widget.attrs["placeholder"] = "例如：行业销售"


class AnswerForm(forms.Form):
    content = forms.CharField(
        label="你的答案",
        min_length=2,
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 9,
                "placeholder": "用自己的话作答，尽量覆盖记得的要点。",
            }
        ),
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("display_name", "department")
        widgets = {
            "department": forms.TextInput(attrs={"placeholder": "例如：行业销售"}),
        }
