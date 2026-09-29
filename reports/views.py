from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Report
from .forms import OrganizationTriageForm, ReportForm


@login_required(login_url="login")
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


@login_required(login_url="login")
def edit_report(request, report_id):
    report = get_object_or_404(Report, id=report_id, reporter=request.user)
    if report.status != "submitted":
        messages.error(request, "Reports can only be edited before review begins.")
        return redirect("report_detail", report_id=report.id)

    form = ReportForm(request.POST or None, request.FILES or None, instance=report)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your report has been updated.")
        return redirect("report_detail", report_id=report.id)

    return render(request, "reports/report_issue.html", {"form": form, "report": report, "is_edit": True})


@login_required(login_url="login")
def delete_report(request, report_id):
    report = get_object_or_404(Report, id=report_id, reporter=request.user)
    if report.status != "submitted":
        messages.error(request, "Reports can only be deleted before review begins.")
        return redirect("report_detail", report_id=report.id)

    if request.method == "POST":
        report.delete()
        messages.success(request, "Your report has been deleted.")
        return redirect("my_reports")

    return render(request, "reports/confirm_delete.html", {"report": report})

@login_required(login_url="login")
def my_reports(request):
    reports = Report.objects.filter(
        reporter=request.user
    ).order_by("-created_at")

    return render(
        request,
        "reports/my_reports.html",
        {"reports": reports},
    )
@login_required(login_url="login")

def report_detail(request, report_id):
    report = get_object_or_404(
        Report,
        id=report_id,
        reporter=request.user,
    )

    return render(
        request,
        "reports/report_detail.html",
        {"report": report, "can_manage_report": report.status == "submitted"},
    )


@login_required(login_url="login")
def organization_report_queue(request):
    if request.user.role != "manager":
        return HttpResponseForbidden()

    organization = request.user.organization
    if organization is None or not organization.is_active:
        return render(
            request,
            "reports/operations_access_denied.html",
            status=403,
        )

    reports = Report.objects.filter(organization=organization).select_related("reporter")

    if request.method == "POST":
        try:
            report_id = int(request.POST.get("report_id", ""))
        except (TypeError, ValueError):
            messages.error(request, "Choose a report from your organization queue.")
            return redirect(reverse("organization_report_queue"))

        report = get_object_or_404(reports, id=report_id)
        if report.status not in ("submitted", "under_review"):
            messages.error(request, "Only reports awaiting review can be triaged here.")
            return redirect(reverse("organization_report_queue"))

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
        return redirect(reverse("organization_report_queue"))

    context = {
        "reports": reports,
        "priority_choices": Report.PRIORITY_CHOICES,
        "submitted_count": reports.filter(status="submitted").count(),
        "under_review_count": reports.filter(status="under_review").count(),
        "organization": organization,
    }
    return render(request, "reports/organization_queue.html", context)
