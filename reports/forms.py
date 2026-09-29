from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_image_file_extension

from .models import Report


class ReportForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issue_type"].choices = [("", "Select an issue"), *Report.ISSUE_TYPE_CHOICES]
        self.fields["county"].choices = [("", "Select county"), *Report.COUNTY_CHOICES]

    class Meta:
        model = Report
        fields = (
            "issue_type",
            "county",
            "area",
            "location_description",
            "latitude",
            "longitude",
            "photo",
            "description",
        )
        widgets = {
            "issue_type": forms.Select(attrs={"id": "issue_type"}),
            "county": forms.Select(attrs={"id": "county"}),
            "area": forms.TextInput(attrs={"id": "area", "maxlength": 150, "placeholder": "e.g. South B"}),
            "location_description": forms.TextInput(attrs={"id": "location_description", "maxlength": 255, "placeholder": "e.g. Near the main gate, next to the bus stop"}),
            "latitude": forms.HiddenInput(attrs={"id": "latitude"}),
            "longitude": forms.HiddenInput(attrs={"id": "longitude"}),
            "photo": forms.ClearableFileInput(attrs={"id": "photo", "accept": "image/jpeg,image/png,image/webp"}),
            "description": forms.Textarea(attrs={"id": "description", "rows": 5, "maxlength": 1000, "placeholder": "Describe what you observed and anything else people responding should know."}),
        }

    def clean_area(self):
        area = self.cleaned_data["area"].strip()
        if not area:
            raise ValidationError("Enter the area or estate where you saw the issue.")
        return area

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if (latitude is None) != (longitude is None):
            raise ValidationError("Enter both location coordinates or leave both blank.")
        if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
            self.add_error("latitude", "Latitude must be between -90 and 90.")
        if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
            self.add_error("longitude", "Longitude must be between -180 and 180.")

        photo = cleaned_data.get("photo")
        if photo:
            if photo.size > 5 * 1024 * 1024:
                self.add_error("photo", "Choose an image smaller than 5 MB.")
            else:
                try:
                    validate_image_file_extension(photo)
                    from PIL import Image

                    image = Image.open(photo)
                    image.verify()
                except (ValidationError, OSError, ValueError):
                    self.add_error("photo", "Upload a valid JPG, PNG or WEBP image.")
                finally:
                    if hasattr(photo, "seek"):
                        photo.seek(0)

        return cleaned_data


class OrganizationTriageForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ("priority",)
