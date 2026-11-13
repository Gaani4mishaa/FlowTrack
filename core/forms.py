from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from accounts.models import Organization
from maintenance.models import MaintenanceWorkOrder
from reports.models import Report


class AdminUserCreationForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "tel"}),
    )
    role = forms.ChoiceField()
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        required=False,
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        self.fields["role"].choices = [
            choice for choice in user_model.ROLE_CHOICES if choice[0] != "admin"
        ]
        self.fields["organization"].queryset = Organization.objects.filter(
            is_active=True
        ).order_by("name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        if user_model.objects.filter(username__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        organization = cleaned_data.get("organization")
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if role in ("manager", "engineer") and organization is None:
            self.add_error(
                "organization",
                "Managers and engineers must belong to an active organization.",
            )

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "The passwords do not match.")

        if password and role:
            user_model = get_user_model()
            candidate = user_model(
                username=cleaned_data.get("email", ""),
                email=cleaned_data.get("email", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
            )
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                self.add_error("password", error)

        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot create a user from an invalid form.")

        user_model = get_user_model()
        role = self.cleaned_data["role"]
        user = user_model.objects.create_user(
            username=self.cleaned_data["email"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
            phone_number=self.cleaned_data["phone_number"].strip(),
            role=role,
            organization=(
                self.cleaned_data["organization"]
                if role in ("manager", "engineer")
                else None
            ),
        )
        return user


class AdminUserPasswordResetForm(forms.Form):
    password = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_reset = forms.BooleanField(
        label="I confirm that this will immediately replace the user's current password.",
        required=True,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "The passwords do not match.")

        if password:
            try:
                validate_password(password, user=self.user)
            except ValidationError as error:
                self.add_error("password", error)

        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot reset a password from an invalid form.")

        self.user.set_password(self.cleaned_data["password"])
        self.user.save(update_fields=("password",))
        return self.user


class AdminUserForm(forms.ModelForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta:
        model = get_user_model()
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",
            "organization",
            "is_active",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "phone_number": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_email = self.instance.email
        self.original_username = self.instance.username
        role = self.data.get(
            self.add_prefix("role"),
            self.instance.role,
        )
        organizations = Organization.objects.filter(is_active=True).order_by("name")
        if self.instance.pk and self.instance.organization_id:
            organizations = Organization.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.organization_id)
            ).order_by("name")
        self.fields["organization"].error_messages["invalid_choice"] = (
            "Choose an active organization for Managers and Engineers."
            if role in ("manager", "engineer")
            else (
                "Choose an active organization. Existing inactive assignments "
                "may be kept, but new assignments are not allowed."
            )
        )
        self.fields["organization"].queryset = organizations
        self.fields["organization"].required = False
        self.fields["organization"].help_text = (
            "Required for Managers and Engineers. Only active organizations "
            "can be selected for these roles."
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exclude(
            pk=self.instance.pk
        ).exists():
            raise ValidationError("An account with this email already exists.")
        if (
            self.instance.pk
            and self.original_username.casefold() == self.original_email.casefold()
            and email.casefold() != self.original_email.casefold()
            and user_model.objects.filter(username__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise ValidationError(
                "This email is already used as another account's username. "
                "Choose a different email to keep account sign-in unambiguous."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.original_username.casefold() == self.original_email.casefold():
            user.username = self.cleaned_data["email"]
        if commit:
            user.save()
            self.save_m2m()
        return user

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        organization = cleaned_data.get("organization")
        is_active = cleaned_data.get("is_active")
        organization_id = organization.pk if organization else None

        existing_inactive_assignment = (
            organization is not None
            and not organization.is_active
            and organization.pk == self.instance.organization_id
        )
        if role in ("manager", "engineer") and organization is None:
            self.add_error(
                "organization",
                "Managers and engineers must belong to an active organization.",
            )
        elif (
            role in ("manager", "engineer")
            and existing_inactive_assignment
            and role != self.instance.role
        ):
            self.add_error(
                "organization",
                "An inactive organization cannot be used for a new role assignment.",
            )
        elif (
            organization is not None
            and not organization.is_active
            and organization.pk != self.instance.organization_id
        ):
            self.add_error(
                "organization",
                "New user assignments can only be made to active organizations.",
            )

        if self.instance.pk:
            from maintenance.models import MaintenanceWorkOrder

            active_work_orders = MaintenanceWorkOrder.objects.filter(
                (Q(engineer=self.instance) | Q(assigned_by=self.instance)),
                status__in=("assigned", "in_progress"),
            ).select_related("report")
            conflicting_work_orders = []
            for work_order in active_work_orders:
                engineer_assignment_remains_valid = (
                    work_order.engineer_id != self.instance.pk
                    or (
                        role == "engineer"
                        and is_active
                        and organization_id == work_order.report.organization_id
                    )
                )
                manager_assignment_remains_valid = (
                    work_order.assigned_by_id != self.instance.pk
                    or (
                        role == "manager"
                        and is_active
                        and organization_id == work_order.report.organization_id
                    )
                )
                if not (
                    engineer_assignment_remains_valid
                    and manager_assignment_remains_valid
                ):
                    conflicting_work_orders.append(work_order)

            if conflicting_work_orders:
                assignment_list = ", ".join(
                    f"#{work_order.pk} ({work_order.get_status_display()})"
                    for work_order in conflicting_work_orders
                )
                self.add_error(
                    None,
                    (
                        f"Active work-order assignments {assignment_list} must be "
                        "completed or handled through the work-order workflow before "
                        "changing this account's role, organization, or active status."
                    ),
                )

        user_model = get_user_model()
        if (
            self.instance.pk
            and self.instance.role == "admin"
            and self.instance.is_active
            and (role != "admin" or not is_active)
            and not user_model.objects.filter(
                role="admin",
                is_active=True,
            ).exclude(pk=self.instance.pk).exists()
        ):
            self.add_error(
                "role",
                "The last active administrator cannot be deactivated or reassigned.",
            )

        return cleaned_data


class AdminOrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            "name",
            "organization_type",
            "county",
            "address",
            "phone",
            "email",
            "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk or not self.instance.is_active:
            self.fields.pop("confirm_deactivation", None)
        else:
            self.fields["confirm_deactivation"] = forms.BooleanField(
                required=False,
                label=(
                    "I understand this will suspend organization access "
                    "without moving its records."
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.instance.pk
            and self.instance.is_active
            and cleaned_data.get("is_active") is False
            and not cleaned_data.get("confirm_deactivation")
        ):
            self.add_error(
                "confirm_deactivation",
                "Confirm the deactivation warning before deactivating this organization.",
            )
        return cleaned_data


class AdminReportManagementForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ("organization", "priority", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organizations = Organization.objects.filter(is_active=True)
        if self.instance.pk and self.instance.organization_id:
            organizations = Organization.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.organization_id)
            )
        self.fields["organization"].queryset = organizations.order_by("name")
        self.fields["organization"].required = False
        self.fields["organization"].empty_label = "Unassigned"
        self.fields["organization"].error_messages["invalid_choice"] = (
            "Reports can only be assigned to active organizations."
        )

    def clean_organization(self):
        organization = self.cleaned_data.get("organization")
        if organization is not None and not organization.is_active:
            if organization.pk != self.instance.organization_id:
                raise ValidationError(
                    "Reports can only be assigned to active organizations."
                )
        if (
            self.instance.pk
            and organization != self.instance.organization
            and MaintenanceWorkOrder.objects.filter(report=self.instance).exists()
        ):
            raise ValidationError(
                "This report has a maintenance work order. Its organization cannot "
                "be changed because that would leave the Engineer and assigning "
                "Manager associated with a different organization."
            )
        return organization
