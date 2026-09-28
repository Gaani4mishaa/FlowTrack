from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Report
from .forms import ReportForm


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
