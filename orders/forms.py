from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from marketplace.models import Product


class CartQuantityForm(forms.Form):
    """Validate a quantity against a product's current stock."""

    quantity = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        initial=Decimal("1.00"),
        label="Quantity",
    )

    def __init__(
        self,
        *args,
        product: Product,
        existing_quantity: Decimal = Decimal("0.00"),
        add_to_existing: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.product = product
        self.existing_quantity = existing_quantity
        self.add_to_existing = add_to_existing

    def clean_quantity(self) -> Decimal:
        quantity = self.cleaned_data["quantity"]

        if not self.product.is_available_now:
            raise forms.ValidationError(
                "This product is not currently available."
            )

        final_quantity = quantity

        if self.add_to_existing:
            final_quantity += self.existing_quantity

        if final_quantity > self.product.stock_quantity:
            raise forms.ValidationError(
                (
                    "Only "
                    f"{self.product.stock_quantity:g} "
                    f"{self.product.get_unit_display().lower()} "
                    "is currently available."
                )
            )

        return quantity


class CheckoutForm(forms.Form):
    """Collect delivery details and simulated payment information."""

    delivery_address = forms.CharField(
        label="Delivery address",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    delivery_postcode = forms.CharField(
        label="Delivery postcode",
        max_length=10,
    )

    delivery_at = forms.DateTimeField(
        label="Delivery or collection date and time",
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={
                "type": "datetime-local",
            },
        ),
        help_text=(
            "The selected time must be at least 48 hours "
            "after checkout."
        ),
    )

    special_instructions = forms.CharField(
        label="Special delivery instructions",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "For example: deliver to the side entrance."
                ),
            }
        ),
    )

    payment_token = forms.ChoiceField(
        label="Mock payment result",
        choices=[
            (
                "tok_success",
                "MockPay test payment — approve",
            ),
            (
                "tok_declined",
                "MockPay test payment — decline",
            ),
        ],
        help_text=(
            "This project uses simulated payments only. "
            "No real card details are processed."
        ),
    )

    card_last_four = forms.CharField(
        label="Test card last four digits",
        min_length=4,
        max_length=4,
        initial="4242",
        help_text="Use four test digits such as 4242.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        minimum_delivery = timezone.localtime(
            timezone.now() + timedelta(hours=48, minutes=5)
        ).replace(
            second=0,
            microsecond=0,
        )

        default_delivery = timezone.localtime(
            timezone.now() + timedelta(hours=72)
        ).replace(
            second=0,
            microsecond=0,
        )

        self.fields["delivery_at"].widget.attrs["min"] = (
            minimum_delivery.strftime("%Y-%m-%dT%H:%M")
        )

        if not self.is_bound and not self.initial.get("delivery_at"):
            self.initial["delivery_at"] = default_delivery

    def clean_delivery_at(self):
        delivery_at = self.cleaned_data["delivery_at"]

        minimum_delivery = (
            timezone.now() + timedelta(hours=48)
        )

        if delivery_at < minimum_delivery:
            raise forms.ValidationError(
                "Delivery must be scheduled at least 48 hours "
                "after checkout."
            )

        return delivery_at

    def clean_delivery_postcode(self) -> str:
        return (
            self.cleaned_data["delivery_postcode"]
            .strip()
            .upper()
        )

    def clean_card_last_four(self) -> str:
        last_four = self.cleaned_data["card_last_four"].strip()

        if not last_four.isdigit():
            raise forms.ValidationError(
                "Enter exactly four numerical test digits."
            )

        return last_four
