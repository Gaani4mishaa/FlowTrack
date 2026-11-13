from django import forms
from accounts.models import User

from .models import MaintenanceWorkOrder


class EngineerAssignmentForm(forms.ModelForm):
    class Meta:
        model = MaintenanceWorkOrder
        fields = ("engineer",)
        widgets = {"engineer": forms.Select(attrs={"class": "work-order-select"})}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["engineer"].queryset = User.objects.filter(
            role="engineer",
            organization=organization,
            is_active=True,
        ).order_by("first_name", "last_name", "username")


class WorkOrderProgressForm(forms.Form):
    status = forms.ChoiceField(widget=forms.Select(attrs={"class": "work-order-select"}))
    resolution_notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={"rows": 3, "maxlength": 2000, "placeholder": "Summarize the maintenance work completed."}
        ),
    )

    def __init__(self, *args, current_status, work_order_id, **kwargs):
        super().__init__(*args, **kwargs)
        next_status = {
            "assigned": ("in_progress", "In Progress"),
            "in_progress": ("resolved", "Resolved"),
        }.get(current_status)
        self.fields["status"].choices = [next_status] if next_status else []
        self.fields["status"].widget.attrs["id"] = f"next-status-{work_order_id}"
        self.fields["resolution_notes"].widget.attrs["id"] = f"resolution-notes-{work_order_id}"

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        notes = (cleaned_data.get("resolution_notes") or "").strip()
        if status == "resolved" and not notes:
            self.add_error("resolution_notes", "Add a resolution note before completing this work order.")
        return cleaned_data
