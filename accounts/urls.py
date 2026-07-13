from django.urls import path

from . import views


app_name = "accounts"


urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),
    path(
        "register/producer/",
        views.producer_register,
        name="producer_register",
    ),
    path(
        "register/customer/",
        views.customer_register,
        name="customer_register",
    ),
    path(
        "login/",
        views.SecureLoginView.as_view(),
        name="login",
    ),
    path(
        "logout/",
        views.SecureLogoutView.as_view(),
        name="logout",
    ),
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),
]
