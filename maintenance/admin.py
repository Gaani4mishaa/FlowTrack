from django.contrib import admin

from .models import MaintenanceWorkOrder


@admin.register(MaintenanceWorkOrder)
class MaintenanceWorkOrderAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"report",
		"engineer",
		"assigned_by",
		"status",
		"assigned_at",
		"started_at",
		"resolved_at",
	)
	list_filter = ("report__status", "engineer__organization")
	search_fields = (
		"report__area",
		"report__county",
		"engineer__username",
		"engineer__email",
	)
	readonly_fields = (
		"report",
		"engineer",
		"assigned_by",
		"status",
		"resolution_notes",
		"assigned_at",
		"started_at",
		"resolved_at",
		"updated_at",
	)

	def has_add_permission(self, request):
		return False

	def has_delete_permission(self, request, obj=None):
		return False
