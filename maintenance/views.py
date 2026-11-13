from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from reports.models import Report

from .forms import EngineerAssignmentForm, WorkOrderProgressForm
from .models import MaintenanceWorkOrder
from .services import assign_report_to_engineer, update_work_order_status


def _has_active_engineer_organization(user):
	return (
		user.role == "engineer"
		and user.is_active
		and user.organization_id is not None
		and user.organization.is_active
	)


def _has_active_manager_organization(user):
	return (
		user.role == "manager"
		and user.is_active
		and user.organization_id is not None
		and user.organization.is_active
	)


@login_required(login_url="login")
@require_POST
def assign_engineer(request, report_id):
	if not _has_active_manager_organization(request.user):
		return HttpResponseForbidden()

	report = get_object_or_404(
		Report.objects.filter(
			organization=request.user.organization,
			status="under_review",
			work_order__isnull=True,
		),
		id=report_id,
	)
	form = EngineerAssignmentForm(request.POST, organization=request.user.organization)

	if not form.is_valid():
		messages.error(request, "Choose an active engineer from your organization.")
		return redirect(_manager_queue_url(request))

	try:
		assign_report_to_engineer(
			report_id=report.id,
			manager=request.user,
			engineer=form.cleaned_data["engineer"],
		)
	except ValidationError as error:
		messages.error(request, error.messages[0])
	else:
		messages.success(request, "The report has been assigned to a maintenance engineer.")

	return redirect(_manager_queue_url(request))


def _manager_queue_url(request):
	queue_url = reverse("organization_report_queue")
	query_string = request.GET.urlencode()
	return f"{queue_url}?{query_string}" if query_string else queue_url


@login_required(login_url="login")
def engineer_work_orders(request):
	if request.user.role != "engineer":
		return HttpResponseForbidden()
	if not _has_active_engineer_organization(request.user):
		return render(request, "maintenance/access_denied.html", status=403)

	work_orders = MaintenanceWorkOrder.objects.filter(
		engineer=request.user,
		report__organization=request.user.organization,
	).select_related("report", "report__reporter", "assigned_by")

	if request.method == "POST":
		try:
			work_order_id = int(request.POST.get("work_order_id", ""))
		except (TypeError, ValueError):
			messages.error(request, "Choose a work order from your list.")
			return redirect(reverse("engineer_work_orders"))

		work_order = get_object_or_404(work_orders, id=work_order_id)
		form = WorkOrderProgressForm(
			request.POST,
			current_status=work_order.status,
			work_order_id=work_order.id,
		)
		if not form.is_valid():
			messages.error(request, "Check the status and resolution details, then try again.")
			return redirect(reverse("engineer_work_orders"))

		try:
			update_work_order_status(
				work_order_id=work_order.id,
				engineer=request.user,
				status=form.cleaned_data["status"],
				resolution_notes=form.cleaned_data["resolution_notes"],
			)
		except ValidationError as error:
			messages.error(request, error.messages[0])
		else:
			messages.success(request, "Work order updated.")
		return redirect(reverse("engineer_work_orders"))

	all_work_orders = work_orders
	counts = all_work_orders.aggregate(
		total=Count("id"),
		assigned=Count("id", filter=Q(status="assigned")),
		in_progress=Count("id", filter=Q(status="in_progress")),
		resolved=Count("id", filter=Q(status="resolved")),
	)
	search = request.GET.get("search", "").strip()
	status_choices = MaintenanceWorkOrder._meta.get_field("status").choices
	valid_statuses = {value for value, _ in status_choices}
	selected_status = request.GET.get("status", "")
	if selected_status not in valid_statuses:
		selected_status = ""
	if search:
		query = Q(report__area__icontains=search) | Q(
			report__location_description__icontains=search
		) | Q(report__issue_type__icontains=search)
		matching_issue_types = [
			value
			for value, label in Report.ISSUE_TYPE_CHOICES
			if search.casefold() in label.casefold()
		]
		if matching_issue_types:
			query |= Q(report__issue_type__in=matching_issue_types)
		if search.isdecimal():
			query |= Q(pk=int(search)) | Q(report_id=int(search))
		work_orders = work_orders.filter(query)
	if selected_status:
		work_orders = work_orders.filter(status=selected_status)

	filter_params = {
		key: value
		for key, value in {"search": search, "status": selected_status}.items()
		if value
	}
	page_obj = Paginator(work_orders.order_by("-assigned_at"), 10).get_page(
		request.GET.get("page")
	)
	work_orders = list(page_obj)
	for work_order in work_orders:
		work_order.progress_form = WorkOrderProgressForm(
			current_status=work_order.status,
			work_order_id=work_order.id,
		)

	context = {
		"work_orders": work_orders,
		"page_obj": page_obj,
		"total_count": counts["total"],
		"assigned_count": counts["assigned"],
		"in_progress_count": counts["in_progress"],
		"resolved_count": counts["resolved"],
		"search": search,
		"selected_status": selected_status,
		"status_choices": status_choices,
		"filter_query": urlencode(filter_params),
		"organization": request.user.organization,
	}
	return render(request, "maintenance/work_orders.html", context)


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def engineer_work_order_detail(request, work_order_id):
	if request.user.role != "engineer":
		return HttpResponseForbidden()
	if not _has_active_engineer_organization(request.user):
		return render(request, "maintenance/access_denied.html", status=403)

	work_order = get_object_or_404(
		MaintenanceWorkOrder.objects.filter(
			engineer=request.user,
			report__organization=request.user.organization,
		).select_related(
			"report",
			"report__reporter",
			"report__organization",
			"assigned_by",
			"engineer",
		),
		pk=work_order_id,
	)
	if request.method == "POST":
		form = WorkOrderProgressForm(
			request.POST,
			current_status=work_order.status,
			work_order_id=work_order.id,
		)
		if not form.is_valid():
			messages.error(request, "Check the status and resolution details, then try again.")
			return redirect("engineer_work_order_detail", work_order_id=work_order.id)
		try:
			update_work_order_status(
				work_order_id=work_order.id,
				engineer=request.user,
				status=form.cleaned_data["status"],
				resolution_notes=form.cleaned_data["resolution_notes"],
			)
		except ValidationError as error:
			messages.error(request, error.messages[0])
		else:
			messages.success(request, "Work order updated.")
		return redirect("engineer_work_order_detail", work_order_id=work_order.id)

	work_order.progress_form = WorkOrderProgressForm(
		current_status=work_order.status,
		work_order_id=work_order.id,
	)

	return render(
		request,
		"maintenance/work_order_detail.html",
		{
			"work_order": work_order,
			"organization": request.user.organization,
		},
	)
