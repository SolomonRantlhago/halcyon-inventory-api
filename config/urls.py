from django.contrib import admin
from django.urls import path

from core.views import HealthView

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
]
