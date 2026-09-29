from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
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