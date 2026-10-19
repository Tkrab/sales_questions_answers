from .models import UserProfile


def quiz_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"profile_name": "", "user_profile": None}
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {
        "profile_name": profile.display_name or user.get_username(),
        "user_profile": profile,
    }
