from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from reports.models import Report

from .models import MaintenanceWorkOrder


@transaction.atomic
def assign_report_to_engineer(*, report_id, manager, engineer):
    if (
        manager.role != "manager"
        or not manager.is_active
        or manager.organization_id is None
        or not manager.organization.is_active
    ):
        raise ValidationError("An active organization manager is required.")

    if (
        engineer.role != "engineer"
        or not engineer.is_active
        or engineer.organization_id != manager.organization_id
    ):
        raise ValidationError("Choose an active engineer in your organization.")

    try:
        report = Report.objects.select_for_update().get(
            pk=report_id,
            organization_id=manager.organization_id,
            status="under_review",
        )
    except Report.DoesNotExist as error:
        raise ValidationError("This report is no longer available for assignment.") from error

    if MaintenanceWorkOrder.objects.filter(report=report).exists():
        raise ValidationError("This report already has a work order.")

    work_order = MaintenanceWorkOrder(
        report=report,
        engineer=engineer,
        assigned_by=manager,
        status="assigned",
    )
    work_order.full_clean()
    work_order.save()

    report.status = "assigned"
    report.save(update_fields=("status", "updated_at"))
    return work_order


@transaction.atomic
def update_work_order_status(*, work_order_id, engineer, status, resolution_notes=""):
    if (
        engineer.role != "engineer"
        or not engineer.is_active
        or engineer.organization_id is None
        or not engineer.organization.is_active
    ):
        raise ValidationError("An active organization engineer is required.")

    try:
        work_order = MaintenanceWorkOrder.objects.select_for_update().select_related("report").get(
            pk=work_order_id,
            engineer=engineer,
            report__organization_id=engineer.organization_id,
        )
    except MaintenanceWorkOrder.DoesNotExist as error:
        raise ValidationError("This work order is not assigned to your account.") from error

    allowed_transitions = {
        "assigned": "in_progress",
        "in_progress": "resolved",
    }
    if allowed_transitions.get(work_order.status) != status:
        raise ValidationError("The requested work-order status transition is not allowed.")

    notes = resolution_notes.strip()
    if status == "resolved" and not notes:
        raise ValidationError("Add a resolution note before completing this work order.")

    now = timezone.now()
    work_order.status = status
    work_order.resolution_notes = notes
    if status == "in_progress":
        work_order.started_at = now
    else:
        work_order.resolved_at = now

    work_order.full_clean()
    work_order.save(
        update_fields=("status", "resolution_notes", "started_at", "resolved_at", "updated_at")
    )

    report = Report.objects.select_for_update().get(pk=work_order.report_id)
    report.status = status
    report.save(update_fields=("status", "updated_at"))
    return work_order
