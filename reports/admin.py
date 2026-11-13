from django.contrib import admin
from django import forms
from django.db.models import Q
from accounts.models import Organization

from .models import Report


class ReportAdminForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organizations = Organization.objects.filter(is_active=True)
        if self.instance.pk and self.instance.organization_id:
            organizations = Organization.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.organization_id)
            )
        self.fields["organization"].queryset = organizations.order_by("name")

    def clean_organization(self):
        organization = self.cleaned_data.get("organization")
        if (
            organization is not None
            and not organization.is_active
            and organization.pk != self.instance.organization_id
        ):
            raise forms.ValidationError(
                "Reports can only be assigned to active organizations."
            )
        return organization


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    form = ReportAdminForm
    list_display = (
        "id",
        "reporter",
        "organization",
        "issue_type",
        "county",
        "area",
        "status",
        "priority",
        "created_at",
    )

    list_filter = (
        "issue_type",
        "county",
        "organization",
        "status",
        "priority",
    )

    search_fields = (
        "area",
        "location_description",
        "description",
        "reporter__username",
        "reporter__email",
        "organization__name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )