from decimal import Decimal

from django import forms

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
