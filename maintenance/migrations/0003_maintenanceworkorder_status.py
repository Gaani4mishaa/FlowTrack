from django.db import migrations, models


WORK_ORDER_STATUSES = {"assigned", "in_progress", "resolved"}


def copy_report_status_to_work_orders(apps, schema_editor):
	WorkOrder = apps.get_model("maintenance", "MaintenanceWorkOrder")

	for work_order in WorkOrder.objects.select_related("report").iterator():
		report_status = work_order.report.status
		work_order.status = (
			report_status if report_status in WORK_ORDER_STATUSES else "assigned"
		)
		work_order.save(update_fields=["status"])


class Migration(migrations.Migration):

	dependencies = [
		("maintenance", "0002_remove_maintenanceworkorder_maintenance_work_order_valid_status_and_more"),
	]

	operations = [
		migrations.AddField(
			model_name="maintenanceworkorder",
			name="status",
			field=models.CharField(
				choices=[
					("assigned", "Assigned"),
					("in_progress", "In Progress"),
					("resolved", "Resolved"),
				],
				default="assigned",
				max_length=20,
			),
		),
		migrations.RunPython(
			copy_report_status_to_work_orders,
			migrations.RunPython.noop,
		),
	]
