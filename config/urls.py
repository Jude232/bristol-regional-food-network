from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),
    path(
        "api/",
        include("api.urls"),
    ),
    path(
        "",
        include("accounts.urls"),
    ),
    path(
        "marketplace/",
        include("marketplace.urls"),
    ),
    path(
        "cart/",
        include("orders.urls"),
    ),
    path(
        "reports/",
        include("orders.report_urls"),
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
