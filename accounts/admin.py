from django.contrib import admin
from .models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization_type",
        "county",
        "is_active",
        "created_at",
    )
    list_filter = (
        "organization_type",
        "county",
        "is_active",
    )
    search_fields = (
        "name",
        "county",
        "email",
    )


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "role",
        "organization",
        "is_active",
    )
    list_filter = (
        "role",
        "organization",
        "is_active",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
    )
    actions = None
    exclude = ("password",)

    def has_delete_permission(self, request, obj=None):
        return False