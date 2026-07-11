from django.urls import path

from . import report_views


app_name = "reports"


urlpatterns = [
    path(
        "producer/settlements/",
        report_views.producer_settlement_view,
        name="producer_settlement",
    ),
    path(
        "producer/settlements/export/",
        report_views.producer_settlement_csv,
        name="producer_settlement_csv",
    ),
    path(
        "admin/commission/",
        report_views.commission_report_view,
        name="commission_report",
    ),
    path(
        "admin/commission/export/",
        report_views.commission_report_csv,
        name="commission_report_csv",
    ),
]
