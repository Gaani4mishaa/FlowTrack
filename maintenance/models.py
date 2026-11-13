from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MaintenanceWorkOrder(models.Model):
	report = models.OneToOneField(
		"reports.Report",
		on_delete=models.CASCADE,
		related_name="work_order",
	)
	engineer = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="maintenance_work_orders",
	)
	status = models.CharField(
		max_length=20,
		choices=[
			("assigned", "Assigned"),
			("in_progress", "In Progress"),
			("resolved", "Resolved"),
		],
		default="assigned",
	)
	assigned_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="created_work_orders",
	)
	resolution_notes = models.TextField(blank=True, max_length=2000)
	assigned_at = models.DateTimeField(auto_now_add=True)
	started_at = models.DateTimeField(null=True, blank=True)
	resolved_at = models.DateTimeField(null=True, blank=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-assigned_at"]

	def clean(self):
		errors = {}

		if self.report_id and self.engineer_id:
			if self.report.organization_id is None:
				errors["report"] = "Assign the report to an organization before creating a work order."
			elif self.engineer.organization_id != self.report.organization_id:
				errors["engineer"] = "The engineer must belong to the report's organization."
			elif self.engineer.role != "engineer" or not self.engineer.is_active:
				errors["engineer"] = "Select an active maintenance engineer."

		if self.report_id and self.assigned_by_id:
			if (
				self.assigned_by.role != "manager"
				or self.assigned_by.organization_id != self.report.organization_id
				or not self.assigned_by.is_active
			):
				errors["assigned_by"] = "The assigning user must be an active manager in the report's organization."

		if self.resolved_at is not None and not self.resolution_notes.strip():
			errors["resolution_notes"] = "Add a resolution note before completing the work order."

		if errors:
			raise ValidationError(errors)

	def __str__(self):
		return f"Work order for report #{self.report_id}"
