from django.contrib.auth import authenticate, login
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import render, redirect

from accounts.models import User


def home(request):
    return render(request, 'core/home.html')


def login_page(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('resident_dashboard')

        messages.error(
            request,
            'The email or password you entered is incorrect.'
        )

    return render(request, 'core/login.html')

def resident_dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")

    from reports.models import Report

    reports = Report.objects.filter(
        reporter=request.user

    ).order_by("-created_at")

    total_reports = reports.count()
    in_progress_reports = reports.filter(
        status="in_progress"
    ).count()
    resolved_reports = reports.filter(
        status="resolved"
    ).count()

    recent_reports = reports[:5]

    return render(
        request,
        "core/resident_dashboard.html",
        {
            "total_reports": total_reports,
            "in_progress_reports": in_progress_reports,
            "resolved_reports": resolved_reports,
            "recent_reports": recent_reports,
        },
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