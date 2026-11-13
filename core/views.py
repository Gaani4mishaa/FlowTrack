from functools import wraps

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from urllib.parse import urlencode

from accounts.models import Organization, User
from maintenance.models import MaintenanceWorkOrder
from reports.models import Report

from .forms import (
    AdminOrganizationForm,
    AdminReportManagementForm,
    AdminUserCreationForm,
    AdminUserForm,
    AdminUserPasswordResetForm,
)


def administrator_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or request.user.role != "admin":
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)

    return login_required(wrapped, login_url="login")


def resident_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or request.user.role != "resident":
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)

    return login_required(wrapped, login_url="login")


def home(request):
    return render(request, 'core/home.html')


def login_page(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        matching_users = User.objects.filter(
            email__iexact=email,
            is_active=True
        )

        authenticated_users = []

        for account in matching_users:
            user = authenticate(
                request,
                username=account.username,
                password=password
            )

            if user is not None:
                authenticated_users.append(user)

        if len(authenticated_users) == 1:
            user = authenticated_users[0]
            login(request, user)

            if user.role == "admin":
                return redirect("admin_dashboard")

            if user.role == "manager":
                return redirect("manager_dashboard")

            if user.role == "engineer":
                return redirect("engineer_dashboard")

            return redirect("resident_dashboard")

        if len(authenticated_users) > 1:
            messages.error(
                request,
                'Multiple accounts match these credentials. '
                'Please contact the administrator.'
            )
        else:
            messages.error(
                request,
                'The email or password you entered is incorrect.'
            )

    return render(request, 'core/login.html')

@resident_required
def resident_dashboard(request):
    reports = Report.objects.filter(
        reporter=request.user
    ).order_by("-created_at")
    report_counts = reports.aggregate(
        total=Count("id"),
        awaiting_review=Count("id", filter=Q(status__in=("submitted", "under_review"))),
        in_progress=Count("id", filter=Q(status="in_progress")),
        resolved=Count("id", filter=Q(status="resolved")),
    )
    recent_reports = reports[:5]

    return render(
        request,
        "core/resident_dashboard.html",
        {
            "total_reports": report_counts["total"],
            "awaiting_review_reports": report_counts["awaiting_review"],
            "in_progress_reports": report_counts["in_progress"],
            "resolved_reports": report_counts["resolved"],
            "recent_reports": recent_reports,
        },
    )

@administrator_required
def admin_dashboard(request):
    reports = Report.objects.all()
    work_orders = MaintenanceWorkOrder.objects.all()
    user_stats = User.objects.aggregate(
        total=Count("id"),
        residents=Count("id", filter=Q(role="resident")),
        managers=Count("id", filter=Q(role="manager")),
        engineers=Count("id", filter=Q(role="engineer")),
        active=Count("id", filter=Q(is_active=True)),
        inactive=Count("id", filter=Q(is_active=False)),
    )
    report_stats = reports.aggregate(
        total=Count("id"),
        pending=Count("id", filter=~Q(status__in=("resolved", "closed"))),
        resolved=Count("id", filter=Q(status="resolved")),
        awaiting_organization=Count(
            "id",
            filter=Q(organization__isnull=True)
            & ~Q(status__in=("resolved", "closed")),
        ),
        high_priority=Count("id", filter=Q(priority="high")),
        critical_priority=Count("id", filter=Q(priority="critical")),
    )
    report_counts_by_status = {
        row["status"]: row["count"]
        for row in reports.values("status").annotate(count=Count("id"))
    }
    report_statuses = [
        {
            "value": value,
            "label": label,
            "count": report_counts_by_status.get(value, 0),
        }
        for value, label in Report.STATUS_CHOICES
    ]
    work_order_counts_by_status = {
        row["status"]: row["count"]
        for row in work_orders.values("status").annotate(count=Count("id"))
    }
    work_order_statuses = [
        {
            "value": value,
            "label": label,
            "count": work_order_counts_by_status.get(value, 0),
        }
        for value, label in MaintenanceWorkOrder._meta.get_field("status").choices
    ]
    return render(
        request,
        "core/admin_dashboard.html",
        {
            "total_users": user_stats["total"],
            "user_stats": user_stats,
            "total_reports": report_stats["total"],
            "pending_reports": report_stats["pending"],
            "resolved_reports": report_stats["resolved"],
            "total_organizations": Organization.objects.count(),
            "awaiting_organization_reports": report_stats["awaiting_organization"],
            "report_statuses": report_statuses,
            "high_priority_reports": report_stats["high_priority"],
            "critical_priority_reports": report_stats["critical_priority"],
            "total_work_orders": work_orders.count(),
            "work_order_statuses": work_order_statuses,
            "recent_reports": Report.objects.select_related(
                "reporter", "organization"
            )[:6],
            "work_orders": MaintenanceWorkOrder.objects.select_related(
                "report", "engineer", "report__organization"
            )[:5],
            "activity": {
                "submitted_reports": reports.filter(status="submitted").count(),
                "under_review_reports": reports.filter(status="under_review").count(),
                "active_work_orders": work_orders.filter(
                    status__in=("assigned", "in_progress")
                ).count(),
                "active_organizations": Organization.objects.filter(
                    is_active=True
                ).count(),
            },
        },
    )


@administrator_required
def admin_users(request):
    users = User.objects.select_related("organization").order_by(
        "first_name", "last_name", "username"
    )
    search = request.GET.get("search", "").strip()
    selected_role = request.GET.get("role", "")
    selected_organization = request.GET.get("organization", "")
    selected_status = request.GET.get("status", "")
    invalid_filter = False

    if search:
        users = users.annotate(
            full_name=Concat("first_name", Value(" "), "last_name")
        ).filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(full_name__icontains=search)
            | Q(email__icontains=search)
        )

    valid_roles = {value for value, _ in User.ROLE_CHOICES}
    if selected_role:
        if selected_role in valid_roles:
            users = users.filter(role=selected_role)
        else:
            invalid_filter = True
            selected_role = ""

    organizations = Organization.objects.order_by("name")
    if selected_organization:
        try:
            organization_id = int(selected_organization)
        except ValueError:
            invalid_filter = True
            selected_organization = ""
        else:
            if organizations.filter(pk=organization_id).exists():
                users = users.filter(organization_id=organization_id)
            else:
                invalid_filter = True
                selected_organization = ""

    if selected_status:
        if selected_status == "active":
            users = users.filter(is_active=True)
        elif selected_status == "inactive":
            users = users.filter(is_active=False)
        else:
            invalid_filter = True
            selected_status = ""

    if invalid_filter:
        users = users.none()

    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_params = {
        key: value
        for key, value in {
            "search": search,
            "role": selected_role,
            "organization": selected_organization,
            "status": selected_status,
        }.items()
        if value
    }

    def page_url(page_number):
        params = {**filter_params, "page": page_number}
        return f"?{urlencode(params)}"

    return render(
        request,
        "core/admin_users.html",
        {
            "page_obj": page_obj,
            "search": search,
            "selected_role": selected_role,
            "selected_organization": selected_organization,
            "selected_status": selected_status,
            "role_choices": User.ROLE_CHOICES,
            "organizations": organizations,
            "invalid_filter": invalid_filter,
            "previous_page_url": page_url(page_obj.previous_page_number())
            if page_obj.has_previous()
            else "",
            "next_page_url": page_url(page_obj.next_page_number())
            if page_obj.has_next()
            else "",
        },
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def admin_user_create(request):
    form = AdminUserCreationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f"User account for {user.email} was created successfully.",
            )
            return redirect("admin_users")
        messages.error(request, "Review the highlighted fields and try again.")

    return render(
        request,
        "core/admin_user_create.html",
        {
            "form": form,
            "page_title": "Create user",
            "page_description": (
                "Create a Resident, Organization Manager, or Maintenance Engineer account."
            ),
        },
        status=400 if request.method == "POST" and not form.is_valid() else 200,
    )


@administrator_required
def admin_user_detail(request, user_id):
    managed_user = get_object_or_404(
        User.objects.select_related("organization"),
        pk=user_id,
    )
    if managed_user.is_staff or managed_user.is_superuser:
        return HttpResponseForbidden()

    return render(
        request,
        "core/admin_user_detail.html",
        {"managed_user": managed_user},
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def admin_user_edit(request, user_id):
    managed_user = get_object_or_404(
        User.objects.select_related("organization"),
        pk=user_id,
    )
    if managed_user.is_staff or managed_user.is_superuser:
        return HttpResponseForbidden()

    form = AdminUserForm(
        request.POST or None,
        instance=managed_user,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "User account updated.")
            return redirect("admin_user_detail", user_id=managed_user.pk)
        messages.error(request, "Review the highlighted fields and try again.")

    return render(
        request,
        "core/admin_form.html",
        {
            "form": form,
            "page_title": "Edit user",
            "page_description": "Update this user's FlowTrack role, organization, and access.",
            "record_label": managed_user.get_full_name() or "Unnamed account",
            "record_meta": f"Account ID #{managed_user.pk}",
            "account_summary": {
                "email": managed_user.email or "Not provided",
                "phone_number": managed_user.phone_number or "Not provided",
                "role": managed_user.get_role_display(),
                "organization": managed_user.organization.name
                if managed_user.organization
                else "Not assigned",
            },
            "form_sections": (
                {
                    "title": "Personal information",
                    "description": "Update the user's identity and contact details.",
                    "fields": [
                        form["first_name"],
                        form["last_name"],
                        form["email"],
                        form["phone_number"],
                    ],
                },
                {
                    "title": "Account access",
                    "description": "Set the user's FlowTrack role, organization, and access status.",
                    "fields": [
                        form["role"],
                        form["organization"],
                        form["is_active"],
                    ],
                },
            ),
            "back_url": "admin_user_detail",
            "back_user_id": managed_user.pk,
            "active_section": "users",
            "submit_label": "Save user",
        },
        status=400 if request.method == "POST" and not form.is_valid() else 200,
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def admin_user_password_reset(request, user_id):
    managed_user = get_object_or_404(
        User.objects.select_related("organization"),
        pk=user_id,
    )
    if managed_user.is_staff or managed_user.is_superuser:
        return HttpResponseForbidden()

    form = AdminUserPasswordResetForm(
        request.POST or None,
        user=managed_user,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Password reset successfully for {managed_user.get_full_name() or managed_user.email}.",
            )
            return redirect("admin_user_detail", user_id=managed_user.pk)
        messages.error(request, "Review the password requirements and try again.")

    return render(
        request,
        "core/admin_user_password_reset.html",
        {
            "form": form,
            "managed_user": managed_user,
        },
        status=400 if request.method == "POST" and not form.is_valid() else 200,
    )


@administrator_required
def admin_organizations(request):
    organizations = Organization.objects.annotate(
        user_count=Count("users", distinct=True),
        report_count=Count("reports", distinct=True),
    ).order_by("name")
    search = request.GET.get("search", "").strip()
    selected_status = request.GET.get("status", "")
    selected_type = request.GET.get("type", "")
    selected_county = request.GET.get("county", "")
    invalid_filter = False

    if search:
        organizations = organizations.filter(name__icontains=search)

    if selected_status:
        if selected_status == "active":
            organizations = organizations.filter(is_active=True)
        elif selected_status == "inactive":
            organizations = organizations.filter(is_active=False)
        else:
            invalid_filter = True
            selected_status = ""

    organization_types = Organization.ORGANIZATION_TYPES
    valid_types = {value for value, _ in organization_types}
    if selected_type:
        if selected_type in valid_types:
            organizations = organizations.filter(organization_type=selected_type)
        else:
            invalid_filter = True
            selected_type = ""

    counties = list(
        Organization.objects.order_by("county")
        .values_list("county", flat=True)
        .distinct()
    )
    if selected_county:
        if selected_county in counties:
            organizations = organizations.filter(county=selected_county)
        else:
            invalid_filter = True
            selected_county = ""

    if invalid_filter:
        organizations = organizations.none()

    page_obj = Paginator(organizations, 25).get_page(request.GET.get("page"))
    filter_params = {
        key: value
        for key, value in {
            "search": search,
            "status": selected_status,
            "type": selected_type,
            "county": selected_county,
        }.items()
        if value
    }

    def page_url(page_number):
        params = {**filter_params, "page": page_number}
        return f"?{urlencode(params)}"

    return render(
        request,
        "core/admin_organizations.html",
        {
            "page_obj": page_obj,
            "search": search,
            "selected_status": selected_status,
            "selected_type": selected_type,
            "selected_county": selected_county,
            "organization_types": organization_types,
            "counties": counties,
            "invalid_filter": invalid_filter,
            "previous_page_url": page_url(page_obj.previous_page_number())
            if page_obj.has_previous()
            else "",
            "next_page_url": page_url(page_obj.next_page_number())
            if page_obj.has_next()
            else "",
        },
    )


@administrator_required
def admin_organization_detail(request, organization_id):
    organization = get_object_or_404(Organization, pk=organization_id)
    users = organization.users.select_related("organization").order_by(
        "first_name", "last_name", "username"
    )
    managers = users.filter(role="manager")
    engineers = users.filter(role="engineer")
    reports = organization.reports.select_related("reporter").order_by("-created_at")
    work_orders = MaintenanceWorkOrder.objects.filter(
        report__organization=organization
    ).select_related(
        "report",
        "engineer",
        "assigned_by",
    ).order_by("-assigned_at")
    report_statuses = [
        {
            "value": value,
            "label": label,
            "count": reports.filter(status=value).count(),
        }
        for value, label in Report.STATUS_CHOICES
    ]

    return render(
        request,
        "core/admin_organization_detail.html",
        {
            "organization": organization,
            "total_users": users.count(),
            "manager_count": managers.count(),
            "engineer_count": engineers.count(),
            "managers": managers[:5],
            "engineers": engineers[:5],
            "total_reports": reports.count(),
            "report_statuses": report_statuses,
            "recent_reports": reports[:5],
            "total_work_orders": work_orders.count(),
            "open_work_orders": work_orders.filter(
                status__in=("assigned", "in_progress")
            ).count(),
            "work_order_statuses": [
                {
                    "value": value,
                    "label": label,
                    "count": work_orders.filter(status=value).count(),
                }
                for value, label in MaintenanceWorkOrder._meta.get_field(
                    "status"
                ).choices
            ],
            "recent_work_orders": work_orders[:5],
        },
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def admin_organization_form(request, organization_id=None):
    organization = (
        get_object_or_404(Organization, pk=organization_id)
        if organization_id is not None
        else None
    )
    organization_was_active = organization.is_active if organization else False
    was_edit = organization is not None
    form = AdminOrganizationForm(
        request.POST or None,
        instance=organization,
    )
    if request.method == "POST":
        if form.is_valid():
            saved_organization = form.save()
            messages.success(request, "Organization saved.")
            return redirect(
                "admin_organization_detail",
                organization_id=saved_organization.pk,
            )
        messages.error(request, "Review the highlighted fields and try again.")

    return render(
        request,
        "core/admin_form.html",
        {
                "form": form,
                "page_title": "Edit organization" if was_edit else "Add organization",
                "page_description": (
                    "Update organization details and operational status."
                    if was_edit
                    else "Register an organization for drainage reporting and maintenance."
                ),
                "record_label": organization.name if was_edit else "",
                "record_meta": organization.county if was_edit else "",
                "deactivation_warning": (
                    {
                        "users": organization.users.count(),
                    "reports": organization.reports.count(),
                    "open_work_orders": MaintenanceWorkOrder.objects.filter(
                        report__organization=organization,
                        status__in=("assigned", "in_progress"),
                    ).count(),
                }
                if was_edit and organization_was_active
                else None
            ),
            "back_url": "admin_organization_detail" if was_edit else "admin_organizations",
            "back_record_id": organization.pk if was_edit else None,
            "active_section": "organizations",
            "submit_label": "Save organization",
        },
        status=400 if request.method == "POST" and not form.is_valid() else 200,
    )


@administrator_required
def admin_reports(request):
    reports = Report.objects.select_related("reporter", "organization").order_by(
        "-created_at"
    )
    search = request.GET.get("search", "").strip()
    selected_county = request.GET.get("county", "")
    selected_issue_type = request.GET.get("issue_type", "")
    selected_status = request.GET.get("status", "")
    selected_priority = request.GET.get("priority", "")
    selected_organization = request.GET.get("organization", "")
    unassigned = request.GET.get("unassigned", "")
    invalid_filter = False

    if search:
        reports = reports.annotate(
            _reporter_full_name=Concat(
                "reporter__first_name",
                Value(" "),
                "reporter__last_name",
            )
        )
        search_filter = (
            Q(area__icontains=search)
            | Q(location_description__icontains=search)
            | Q(county__icontains=search)
            | Q(_reporter_full_name__icontains=search)
            | Q(reporter__first_name__icontains=search)
            | Q(reporter__last_name__icontains=search)
            | Q(reporter__username__icontains=search)
            | Q(reporter__email__icontains=search)
        )
        if search.isdecimal():
            search_filter |= Q(pk=int(search))
        matching_issue_types = [
            value
            for value, label in Report.ISSUE_TYPE_CHOICES
            if search.casefold() in value.casefold()
            or search.casefold() in label.casefold()
        ]
        if matching_issue_types:
            search_filter |= Q(issue_type__in=matching_issue_types)
        reports = reports.filter(search_filter)

    filter_choices = (
        ("county", selected_county, {value for value, _ in Report.COUNTY_CHOICES}),
        (
            "issue_type",
            selected_issue_type,
            {value for value, _ in Report.ISSUE_TYPE_CHOICES},
        ),
        ("status", selected_status, {value for value, _ in Report.STATUS_CHOICES}),
        (
            "priority",
            selected_priority,
            {value for value, _ in Report.PRIORITY_CHOICES},
        ),
    )
    for field, selected_value, valid_values in filter_choices:
        if selected_value:
            if selected_value in valid_values:
                reports = reports.filter(**{field: selected_value})
            else:
                invalid_filter = True

    if selected_organization:
        if selected_organization == "unassigned":
            reports = reports.filter(organization__isnull=True)
            unassigned = "1"
            selected_organization = ""
        else:
            try:
                organization_id = int(selected_organization)
                if Organization.objects.filter(pk=organization_id).exists():
                    reports = reports.filter(organization_id=organization_id)
                else:
                    invalid_filter = True
            except (TypeError, ValueError):
                invalid_filter = True

    if unassigned:
        if unassigned in ("1", "true", "on"):
            reports = reports.filter(organization__isnull=True)
            selected_organization = ""
            unassigned = "1"
        else:
            invalid_filter = True

    if invalid_filter:
        reports = reports.none()

    filter_params = {
        key: value
        for key, value in {
            "search": search,
            "county": selected_county,
            "issue_type": selected_issue_type,
            "status": selected_status,
            "priority": selected_priority,
            "organization": selected_organization,
            "unassigned": unassigned,
        }.items()
        if value
    }

    def page_url(page_number):
        return f"?{urlencode({**filter_params, 'page': page_number})}"

    page_obj = Paginator(reports, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "core/admin_reports.html",
        {
            "page_obj": page_obj,
            "search": search,
            "selected_county": selected_county,
            "selected_issue_type": selected_issue_type,
            "selected_status": selected_status,
            "selected_priority": selected_priority,
            "selected_organization": selected_organization,
            "unassigned": unassigned,
            "counties": Report.COUNTY_CHOICES,
            "issue_types": Report.ISSUE_TYPE_CHOICES,
            "statuses": Report.STATUS_CHOICES,
            "priorities": Report.PRIORITY_CHOICES,
            "organizations": Organization.objects.order_by("name"),
            "invalid_filter": invalid_filter,
            "previous_page_url": page_url(page_obj.previous_page_number())
            if page_obj.has_previous()
            else "",
            "next_page_url": page_url(page_obj.next_page_number())
            if page_obj.has_next()
            else "",
        },
    )


@administrator_required
@require_http_methods(["GET", "POST"])
def admin_report_detail(request, report_id):
    report = get_object_or_404(
        Report.objects.select_related(
            "reporter",
            "organization",
            "work_order__engineer",
            "work_order__assigned_by",
        ),
        pk=report_id,
    )
    form = AdminReportManagementForm(
        request.POST or None,
        instance=report,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Report management changes saved.")
            return redirect("admin_report_detail", report_id=report.pk)
        messages.error(request, "Review the highlighted fields and try again.")

    return render(
        request,
        "core/admin_report_detail.html",
        {"report": report, "management_form": form},
        status=400 if request.method == "POST" and not form.is_valid() else 200,
    )


@administrator_required
def admin_work_orders(request):
    page_obj = Paginator(
        MaintenanceWorkOrder.objects.select_related(
            "report", "report__organization", "engineer"
        ).order_by("-assigned_at"),
        25,
    ).get_page(request.GET.get("page"))
    return render(request, "core/admin_work_orders.html", {"page_obj": page_obj})


@administrator_required
def admin_work_order_detail(request, work_order_id):
    work_order = get_object_or_404(
        MaintenanceWorkOrder.objects.select_related(
            "report", "report__organization", "report__reporter", "engineer", "assigned_by"
        ),
        pk=work_order_id,
    )
    return render(
        request,
        "core/admin_work_order_detail.html",
        {"work_order": work_order},
    )


def register_page(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone_number = request.POST.get('phone_number', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        terms_accepted = request.POST.get('terms')

        # Basic validation
        if not full_name or not email or not password or not confirm_password:
            messages.error(request, 'Please complete all required fields.')
            return render(request, 'core/register.html')

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'Enter a valid email address.')
            return render(request, 'core/register.html')

        if not terms_accepted:
            messages.error(
                request,
                'Confirm that your information is accurate and does not include sensitive personal data.',
            )
            return render(request, 'core/register.html')

        if password != confirm_password:
            messages.error(request, 'The passwords do not match.')
            return render(request, 'core/register.html')

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with this email already exists.')
            return render(request, 'core/register.html')

        # Use the email as the Django username for now.
        # This keeps email-based login simple while preserving
        # Django's built-in authentication system.
        username = email

        if User.objects.filter(username=username).exists():
            messages.error(request, 'An account with this email already exists.')
            return render(request, 'core/register.html')

        # Validate password using Django's configured password validators.
        try:
            validate_password(password)
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)

            return render(request, 'core/register.html')

        # Split full name into first name + surname.
        name_parts = full_name.split(maxsplit=1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Create the resident account.
        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role='resident',
        )

        messages.success(
            request,
            'Your FlowTrack account has been created successfully. Please sign in.'
        )

        return redirect('login')

    return render(request, 'core/register.html')