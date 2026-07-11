from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    """Form used by producers to create and update products."""

    class Meta:
        model = Product

        fields = (
            "category",
            "name",
            "description",
            "price",
            "unit",
            "stock_quantity",
            "low_stock_threshold",
            "availability_status",
            "available_from",
            "available_until",
            "harvest_date",
            "best_before_date",
            "allergen_information",
            "organic_certified",
            "organic_certification_details",
            "is_active",
        )

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
            "allergen_information": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "For example: Contains milk and eggs, "
                        "or No common allergens"
                    ),
                }
            ),
            "available_from": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "available_until": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "harvest_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "best_before_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        organic_certified = cleaned_data.get(
            "organic_certified"
        )

        certification_details = cleaned_data.get(
            "organic_certification_details",
            "",
        ).strip()

        if organic_certified and not certification_details:
            self.add_error(
                "organic_certification_details",
                (
                    "Enter certification details for a product "
                    "marked as certified organic."
                ),
            )

        return cleaned_data
