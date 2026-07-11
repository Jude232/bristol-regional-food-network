from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CustomerProfile, ProducerProfile, User


class BaseRegistrationForm(UserCreationForm):
    """Shared fields and validation for marketplace registration."""

    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "name@example.com",
            }
        ),
    )

    first_name = forms.CharField(
        max_length=150,
        label="First name",
    )

    last_name = forms.CharField(
        max_length=150,
        label="Last name",
    )

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2",
        )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account already exists with this email address."
            )

        return email


class ProducerRegistrationForm(BaseRegistrationForm):
    """Registration form for local food producers."""

    business_name = forms.CharField(
        max_length=200,
        label="Business name",
    )

    phone = forms.CharField(
        max_length=30,
        label="Telephone number",
    )

    business_address = forms.CharField(
        label="Business address",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    postcode = forms.CharField(
        max_length=10,
        label="Postcode",
    )

    @transaction.atomic
    def save(self) -> User:
        user = super().save(commit=False)
        user.role = User.Role.PRODUCER
        user.email = self.cleaned_data["email"]
        user.save()

        ProducerProfile.objects.create(
            user=user,
            business_name=self.cleaned_data["business_name"].strip(),
            phone=self.cleaned_data["phone"].strip(),
            business_address=self.cleaned_data["business_address"].strip(),
            postcode=self.cleaned_data["postcode"].strip().upper(),
        )

        return user


class CustomerRegistrationForm(BaseRegistrationForm):
    """Registration form for customers."""

    phone = forms.CharField(
        max_length=30,
        label="Telephone number",
    )

    delivery_address = forms.CharField(
        label="Delivery address",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    postcode = forms.CharField(
        max_length=10,
        label="Postcode",
    )

    accepted_terms = forms.BooleanField(
        label="I accept the terms and conditions",
        required=True,
    )

    @transaction.atomic
    def save(self) -> User:
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER
        user.email = self.cleaned_data["email"]
        user.save()

        CustomerProfile.objects.create(
            user=user,
            phone=self.cleaned_data["phone"].strip(),
            delivery_address=self.cleaned_data["delivery_address"].strip(),
            postcode=self.cleaned_data["postcode"].strip().upper(),
            accepted_terms=self.cleaned_data["accepted_terms"],
        )

        return user
