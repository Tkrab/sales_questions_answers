from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "行业知识问答"
admin.site.site_title = "知识问答"
admin.site.index_title = "管理"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("quiz.urls")),
]
