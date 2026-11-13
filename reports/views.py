from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from maintenance.models import MaintenanceWorkOrder
from .models import Report
from .forms import OrganizationTriageForm, ReportForm


def resident_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or request.user.role != "resident":
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)

    return login_required(wrapped, login_url="login")


def manager_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != "manager" or not request.user.is_active:
            return HttpResponseForbidden()
        if request.user.organization_id is None or not request.user.organization.is_active:
            return render(request, "reports/operations_access_denied.html", status=403)
        return view(request, *args, **kwargs)

    return login_required(wrapped, login_url="login")


@resident_required
@require_http_methods(["GET", "POST"])
def report_issue(request):
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.save()
            messages.success(request, "Your drainage report has been submitted successfully.")
            return redirect("report_detail", report_id=report.id)

    return render(request, "reports/report_issue.html", {"form": form, "is_edit": False})


@resident_required
@require_http_methods(["GET", "POST"])
def edit_report(request, report_id):
    report = get_object_or_404(Report, id=report_id, reporter=request.user)
    if report.status != "submitted" or MaintenanceWorkOrder.objects.filter(report=report).exists():
        messages.error(
            request,
            "Reports can only be edited before review begins and before maintenance work is assigned.",
        )
        return redirect("report_detail", report_id=report.id)

    form = ReportForm(request.POST or None, request.FILES or None, instance=report)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your report has been updated.")
        return redirect("report_detail", report_id=report.id)

    return render(request, "reports/report_issue.html", {"form": form, "report": report, "is_edit": True})


@resident_required
@require_http_methods(["GET", "POST"])
def delete_report(request, report_id):
    report = get_object_or_404(Report, id=report_id, reporter=request.user)
    if report.status != "submitted" or MaintenanceWorkOrder.objects.filter(report=report).exists():
        messages.error(
            request,
            "Reports can only be deleted before review begins and before maintenance work is assigned.",
        )
        return redirect("report_detail", report_id=report.id)

    if request.method == "POST":
        report.delete()
        messages.success(request, "Your report has been deleted.")
        return redirect("my_reports")

    return render(request, "reports/confirm_delete.html", {"report": report})

@resident_required
def my_reports(request):
    reports = Report.objects.filter(reporter=request.user).order_by("-created_at")
    page_obj = Paginator(reports, 10).get_page(request.GET.get("page"))

    return render(
        request,
        "reports/my_reports.html",
        {"reports": page_obj, "page_obj": page_obj},
    )

@resident_required
@require_GET
def report_detail(request, report_id):
    report = get_object_or_404(
        Report,
        id=report_id,
        reporter=request.user,
    )
    work_order = MaintenanceWorkOrder.objects.filter(report=report).first()
    status_stages = [
        {"value": value, "label": label, "current": report.status == value}
        for value, label in Report.STATUS_CHOICES
    ]

    return render(
        request,
        "reports/report_detail.html",
        {
            "report": report,
            "work_order": work_order,
            "status_stages": status_stages,
            "can_manage_report": report.status == "submitted" and work_order is None,
        },
    )


@manager_required
def manager_dashboard(request):
    organization = request.user.organization
    reports = Report.objects.filter(organization=organization)
    work_orders = MaintenanceWorkOrder.objects.filter(report__organization=organization)
    context = {
        "organization": organization,
        "assigned_reports_count": reports.count(),
        "pending_reviews_count": reports.filter(status__in=("submitted", "under_review")).count(),
        "active_work_orders_count": work_orders.filter(status__in=("assigned", "in_progress")).count(),
        "resolved_work_orders_count": work_orders.filter(status="resolved").count(),
        "recent_reports": reports.select_related(
            "reporter", "organization", "work_order__engineer"
        ).order_by("-created_at")[:6],
        "recent_work_orders": work_orders.select_related(
            "report", "engineer", "assigned_by"
        ).order_by("-assigned_at")[:5],
    }
    return render(request, "reports/manager_dashboard.html", context)


@manager_required
def manager_work_orders(request):
    organization = request.user.organization
    all_work_orders = MaintenanceWorkOrder.objects.filter(
        report__organization=organization
    ).select_related("report", "engineer", "assigned_by")
    work_orders = all_work_orders
    search = request.GET.get("search", "").strip()
    status_choices = MaintenanceWorkOrder._meta.get_field("status").choices
    valid_statuses = {value for value, _ in status_choices}
    selected_status = request.GET.get("status", "")
    if selected_status not in valid_statuses:
        selected_status = ""
    if search:
        query = Q(report__area__icontains=search) | Q(
            report__location_description__icontains=search
        ) | Q(report__issue_type__icontains=search) | Q(
            engineer__first_name__icontains=search
        ) | Q(engineer__last_name__icontains=search) | Q(
            engineer__username__icontains=search
        )
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
    return render(
        request,
        "reports/manager_work_orders.html",
        {
            "organization": organization,
            "page_obj": page_obj,
            "work_orders": page_obj,
            "search": search,
            "selected_status": selected_status,
            "status_choices": status_choices,
            "assigned_count": all_work_orders.filter(status="assigned").count(),
            "in_progress_count": all_work_orders.filter(status="in_progress").count(),
            "resolved_count": all_work_orders.filter(status="resolved").count(),
            "filter_query": urlencode(filter_params),
        },
    )


def _manager_queue_url(request):
    queue_url = reverse("organization_report_queue")
    query_string = request.GET.urlencode()
    return f"{queue_url}?{query_string}" if query_string else queue_url


@manager_required
def organization_report_queue(request):
    organization = request.user.organization
    organization_reports = Report.objects.filter(organization=organization)
    reports = organization_reports.select_related(
        "reporter",
        "work_order__engineer",
    )
    search = request.GET.get("search", "").strip()
    selected_status = request.GET.get("status", "")
    selected_priority = request.GET.get("priority", "")
    selected_county = request.GET.get("county", "")
    selected_issue_type = request.GET.get("issue_type", "")
    valid_statuses = {value for value, _ in Report.STATUS_CHOICES}
    valid_priorities = {value for value, _ in Report.PRIORITY_CHOICES}
    valid_counties = {value for value, _ in Report.COUNTY_CHOICES}
    valid_issue_types = {value for value, _ in Report.ISSUE_TYPE_CHOICES}
    if selected_status not in valid_statuses:
        selected_status = ""
    if selected_priority not in valid_priorities:
        selected_priority = ""
    if selected_county not in valid_counties:
        selected_county = ""
    if selected_issue_type not in valid_issue_types:
        selected_issue_type = ""
    if search:
        query = Q(area__icontains=search) | Q(
            location_description__icontains=search
        ) | Q(issue_type__icontains=search) | Q(
            reporter__first_name__icontains=search
        ) | Q(reporter__last_name__icontains=search) | Q(
            reporter__username__icontains=search
        )
        matching_issue_types = [
            value
            for value, label in Report.ISSUE_TYPE_CHOICES
            if search.casefold() in label.casefold()
        ]
        if matching_issue_types:
            query |= Q(issue_type__in=matching_issue_types)
        if search.isdecimal():
            query |= Q(pk=int(search))
        reports = reports.filter(query)
    if selected_status:
        reports = reports.filter(status=selected_status)
    if selected_priority:
        reports = reports.filter(priority=selected_priority)
    if selected_county:
        reports = reports.filter(county=selected_county)
    if selected_issue_type:
        reports = reports.filter(issue_type=selected_issue_type)

    if request.method == "POST":
        try:
            report_id = int(request.POST.get("report_id", ""))
        except (TypeError, ValueError):
            messages.error(request, "Choose a report from your organization queue.")
            return redirect(_manager_queue_url(request))

        report = get_object_or_404(organization_reports, id=report_id)
        if report.status not in ("submitted", "under_review"):
            messages.error(request, "Only reports awaiting review can be triaged here.")
            return redirect(_manager_queue_url(request))

        form = OrganizationTriageForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save(commit=False)
            if report.status == "submitted":
                report.status = "under_review"
                success_message = "Report marked as under review and priority updated."
            else:
                success_message = "Report priority updated."
            report.save(update_fields=("priority", "status", "updated_at"))
            messages.success(request, success_message)
        else:
            messages.error(request, "Choose a valid priority and try again.")
        return redirect(_manager_queue_url(request))

    filter_params = {
        key: value
        for key, value in {
            "search": search,
            "status": selected_status,
            "priority": selected_priority,
            "county": selected_county,
            "issue_type": selected_issue_type,
        }.items()
        if value
    }
    page_obj = Paginator(reports.order_by("-created_at"), 10).get_page(
        request.GET.get("page")
    )
    context = {
        "reports": page_obj,
        "page_obj": page_obj,
        "search": search,
        "selected_status": selected_status,
        "selected_priority": selected_priority,
        "selected_county": selected_county,
        "selected_issue_type": selected_issue_type,
        "counties": Report.COUNTY_CHOICES,
        "issue_types": Report.ISSUE_TYPE_CHOICES,
        "statuses": Report.STATUS_CHOICES,
        "priorities": Report.PRIORITY_CHOICES,
        "filter_query": urlencode(filter_params),
        "priority_choices": Report.PRIORITY_CHOICES,
        "engineers": request.user.organization.users.filter(
            role="engineer",
            is_active=True,
        ).order_by("first_name", "last_name", "username"),
        "submitted_count": organization_reports.filter(status="submitted").count(),
        "under_review_count": organization_reports.filter(status="under_review").count(),
        "organization": organization,
    }
    return render(request, "reports/organization_queue.html", context)


@manager_required
@require_GET
def manager_report_detail(request, report_id):
    organization = request.user.organization
    report = get_object_or_404(
        Report.objects.filter(organization=organization).select_related(
            "reporter",
            "work_order__engineer",
            "work_order__assigned_by",
        ),
        pk=report_id,
    )
    engineers = organization.users.filter(
        role="engineer",
        is_active=True,
    ).order_by("first_name", "last_name", "username")

    return render(
        request,
        "reports/manager_report_detail.html",
        {
            "report": report,
            "organization": organization,
            "engineers": engineers,
            "priority_choices": Report.PRIORITY_CHOICES,
            "can_triage": report.status in ("submitted", "under_review"),
        },
    )
