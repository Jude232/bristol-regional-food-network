from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import CustomerRegistrationForm, ProducerRegistrationForm
from .models import User


def home(request):
    """Display the marketplace landing page."""

    return render(request, "accounts/home.html")


def producer_register(request):
    """Register a new producer and associated business profile."""

    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = ProducerRegistrationForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Producer account created successfully. You can now log in.",
            )

            return redirect("accounts:login")
    else:
        form = ProducerRegistrationForm()

    return render(
        request,
        "accounts/producer_register.html",
        {
            "form": form,
        },
    )


def customer_register(request):
    """Register a new customer and delivery profile."""

    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Customer account created successfully. You can now log in.",
            )

            return redirect("accounts:login")
    else:
        form = CustomerRegistrationForm()

    return render(
        request,
        "accounts/customer_register.html",
        {
            "form": form,
        },
    )


@login_required
def dashboard(request):
    """Display role-specific account information."""

    profile = None

    if request.user.role == User.Role.PRODUCER:
        profile = getattr(request.user, "producer_profile", None)

    elif request.user.role == User.Role.CUSTOMER:
        profile = getattr(request.user, "customer_profile", None)

    return render(
        request,
        "accounts/dashboard.html",
        {
            "profile": profile,
        },
    )


from django.contrib.auth.views import (
    LoginView as DjangoLoginView,
    LogoutView as DjangoLogoutView,
)
from django.shortcuts import render as security_render
from django.urls import reverse_lazy

from .forms import SecureAuthenticationForm
from .models import AuthenticationEvent
from .security import (
    get_client_ip,
    is_login_blocked,
    normalise_email,
    record_authentication_event,
)


class SecureLoginView(DjangoLoginView):
    """Login with auditing, throttling and session choice."""

    template_name = "accounts/login.html"
    authentication_form = SecureAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        self.login_email = normalise_email(
            request.POST.get(
                "username",
                "",
            )
        )

        self.login_ip = get_client_ip(request)

        if is_login_blocked(
            email=self.login_email,
            ip_address=self.login_ip,
        ):
            record_authentication_event(
                request=request,
                event_type=(
                    AuthenticationEvent.EventType.LOGIN_BLOCKED
                ),
                email=self.login_email,
            )

            form = self.get_form_class()(
                request=request
            )

            return security_render(
                request,
                self.template_name,
                {
                    "form": form,
                    "blocked_message": (
                        "Too many unsuccessful login attempts. "
                        "Wait 15 minutes before trying again."
                    ),
                },
                status=429,
            )

        return super().post(
            request,
            *args,
            **kwargs,
        )

    def form_valid(self, form):
        response = super().form_valid(form)

        user = form.get_user()

        record_authentication_event(
            request=self.request,
            event_type=(
                AuthenticationEvent.EventType.LOGIN_SUCCESS
            ),
            email=user.email,
            user=user,
        )

        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(
                60 * 60 * 24 * 14
            )
        else:
            self.request.session.set_expiry(0)

        return response

    def form_invalid(self, form):
        email = getattr(
            self,
            "login_email",
            "",
        )

        if email:
            record_authentication_event(
                request=self.request,
                event_type=(
                    AuthenticationEvent.EventType.LOGIN_FAILURE
                ),
                email=email,
            )

        return super().form_invalid(form)


class SecureLogoutView(DjangoLogoutView):
    """Record explicit logout before terminating the session."""

    next_page = reverse_lazy("accounts:home")

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            record_authentication_event(
                request=request,
                event_type=(
                    AuthenticationEvent.EventType.LOGOUT
                ),
                email=request.user.email,
                user=request.user,
            )

        return super().post(
            request,
            *args,
            **kwargs,
        )
