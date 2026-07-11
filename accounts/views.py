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
