from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Organization
from maintenance.models import MaintenanceWorkOrder
from reports.models import Report


class PublicHomepageTests(TestCase):
	def test_homepage_renders_public_navigation_and_account_actions(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, reverse("register"))
		self.assertContains(response, reverse("login"))
		self.assertEqual(response.content.count(b'id="how-it-works"'), 1)
		self.assertNotContains(response, 'class="home-tracking"')
		self.assertContains(response, 'href="#how-it-works"')
		self.assertContains(response, 'href="#report-types"')
		self.assertContains(response, 'href="#roles"')
		self.assertContains(response, "images/drainage-channel.jpg")
		self.assertEqual(self.client.get(reverse("register")).status_code, 200)
		self.assertEqual(self.client.get(reverse("login")).status_code, 200)

	def test_homepage_explains_supported_workflow_and_issue_types(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		for stage in (
			"Report an issue",
			"Review and assign",
			"Maintenance work",
			"Track progress",
		):
			with self.subTest(stage=stage):
				self.assertContains(response, stage)
		for issue_type in (
			"Blocked drain",
			"Flooding",
			"Damaged culvert",
			"Overflowing drain",
			"Waste obstructing drainage",
			"Damaged drainage channel",
			"Other drainage issue",
		):
			with self.subTest(issue_type=issue_type):
				self.assertContains(response, issue_type)
		self.assertEqual(response.content.count(b'class="home-issue-card"'), 7)
		self.assertNotContains(response, "<svg", html=False)

	def test_signed_in_resident_home_links_remain_available(self):
		resident = get_user_model().objects.create_user(
			username="homepage-resident@example.com",
			email="homepage-resident@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)
		self.client.force_login(resident)

		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, reverse("report_issue"))
		self.assertContains(response, reverse("my_reports"))
		self.assertNotContains(response, 'class="home-nav-links"')


class RegistrationValidationTests(TestCase):
	def registration_data(self, **overrides):
		data = {
			"full_name": "Gideon Waweru",
			"email": "gideon@example.com",
			"phone_number": "+254700000000",
			"password": "Th!sIsANewStrongFlowTrackPassword935",
			"confirm_password": "Th!sIsANewStrongFlowTrackPassword935",
			"terms": "on",
		}
		data.update(overrides)
		return data

	def test_invalid_email_format_is_rejected(self):
		response = self.client.post(
			reverse("register"),
			self.registration_data(email="not-an-email"),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Enter a valid email address.")
		self.assertFalse(get_user_model().objects.filter(username="not-an-email").exists())

	def test_registration_requires_the_data_accuracy_confirmation(self):
		response = self.client.post(
			reverse("register"),
			self.registration_data(terms=""),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Confirm that your information is accurate")
		self.assertFalse(get_user_model().objects.filter(username="gideon@example.com").exists())

	def test_resident_can_register_with_valid_details(self):
		response = self.client.post(reverse("register"), self.registration_data())

		self.assertRedirects(response, reverse("login"))
		user = get_user_model().objects.get(username="gideon@example.com")
		self.assertEqual(user.role, "resident")


class ManagerAuthenticationTests(TestCase):
	def test_manager_sign_in_redirects_to_manager_dashboard(self):
		organization = Organization.objects.create(
			name="North District Works",
			organization_type="county",
			county="Nairobi City",
		)
		get_user_model().objects.create_user(
			username="manager@example.com",
			email="manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=organization,
		)

		response = self.client.post(
			reverse("login"),
			{"email": "manager@example.com", "password": "FlowTrack-test-123!"},
		)

		self.assertRedirects(response, reverse("manager_dashboard"))

	def test_engineer_sign_in_redirects_to_engineer_dashboard(self):
		organization = Organization.objects.create(
			name="Maintenance Team",
			organization_type="county",
			county="Nairobi City",
		)
		get_user_model().objects.create_user(
			username="engineer@example.com",
			email="engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=organization,
		)

		response = self.client.post(
			reverse("login"),
			{"email": "engineer@example.com", "password": "FlowTrack-test-123!"},
		)

		self.assertRedirects(response, reverse("engineer_dashboard"))


class AdminDashboardTests(TestCase):
	def setUp(self):
		self.organization = Organization.objects.create(
			name="North District Works",
			organization_type="county",
			county="Nairobi City",
		)
		self.admin = get_user_model().objects.create_user(
			username="admin@example.com",
			email="admin@example.com",
			password="FlowTrack-test-123!",
			first_name="System",
			last_name="Admin",
			role="admin",
		)
		self.reporter = get_user_model().objects.create_user(
			username="resident@example.com",
			email="resident@example.com",
			password="FlowTrack-test-123!",
			first_name="Amina",
			last_name="Resident",
			role="resident",
		)

	def create_report(self, status):
		return Report.objects.create(
			reporter=self.reporter,
			organization=self.organization,
			issue_type="blocked_drain",
			county="Nairobi City",
			area=f"{status.title()} Road",
			status=status,
		)

	def test_admin_role_can_view_real_dashboard_data(self):
		self.create_report("submitted")
		self.create_report("resolved")
		self.create_report("closed")
		self.client.force_login(self.admin)

		response = self.client.get(reverse("admin_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_users"], 2)
		self.assertEqual(response.context["total_reports"], 3)
		self.assertEqual(response.context["pending_reports"], 1)
		self.assertEqual(response.context["resolved_reports"], 1)
		self.assertContains(response, "System Admin")
		self.assertContains(response, "Submitted Road")
		self.assertNotContains(response, self.admin.password)
		self.assertNotContains(response, "password")

	def test_dashboard_statistics_cover_roles_priorities_and_workflow_statuses(self):
		user_model = get_user_model()
		manager = user_model.objects.create_user(
			username="dashboard-manager@example.com",
			role="manager",
			organization=self.organization,
		)
		engineer = user_model.objects.create_user(
			username="dashboard-engineer@example.com",
			role="engineer",
			organization=self.organization,
		)
		inactive_engineer = user_model.objects.create_user(
			username="inactive-dashboard-engineer@example.com",
			role="engineer",
			organization=self.organization,
			is_active=False,
		)

		reports_by_status = {}
		for status in ("submitted", "under_review", "assigned", "in_progress", "resolved", "closed"):
			reports_by_status[status] = self.create_report(status)

		unassigned_report = reports_by_status["submitted"]
		unassigned_report.organization = None
		unassigned_report.priority = "high"
		unassigned_report.save(update_fields=("organization", "priority"))
		reports_by_status["under_review"].priority = "critical"
		reports_by_status["under_review"].save(update_fields=("priority",))

		for status in ("assigned", "in_progress", "resolved"):
			MaintenanceWorkOrder.objects.create(
				report=reports_by_status[status],
				engineer=engineer,
				assigned_by=manager,
				status=status,
			)

		self.client.force_login(self.admin)
		response = self.client.get(reverse("admin_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.context["user_stats"],
			{
				"total": 5,
				"residents": 1,
				"managers": 1,
				"engineers": 2,
				"active": 4,
				"inactive": 1,
			},
		)
		self.assertEqual(response.context["total_organizations"], 1)
		self.assertEqual(response.context["awaiting_organization_reports"], 1)
		self.assertEqual(response.context["high_priority_reports"], 1)
		self.assertEqual(response.context["critical_priority_reports"], 1)
		self.assertEqual(response.context["pending_reports"], 4)
		self.assertEqual(response.context["total_work_orders"], 3)
		self.assertEqual(response.context["activity"]["submitted_reports"], 1)
		self.assertEqual(
			{item["value"]: item["count"] for item in response.context["report_statuses"]},
			{
				"submitted": 1,
				"under_review": 1,
				"assigned": 1,
				"in_progress": 1,
				"resolved": 1,
				"closed": 1,
			},
		)
		self.assertEqual(
			{item["value"]: item["count"] for item in response.context["work_order_statuses"]},
			{"assigned": 1, "in_progress": 1, "resolved": 1},
		)
		self.assertContains(response, "Submitted reports")
		self.assertNotContains(response, "New submissions")
		self.assertContains(response, reverse("admin_users"))
		self.assertContains(response, reverse("admin_reports"))
		self.assertContains(response, reverse("admin_work_orders"))
		self.assertFalse(user_model.objects.get(pk=inactive_engineer.pk).is_active)

	def test_admin_user_search_matches_first_last_full_name_and_email(self):
		self.client.force_login(self.admin)

		for query in ("Amina", "Resident", "Amina Resident", "resident@example.com"):
			with self.subTest(query=query):
				response = self.client.get(
					reverse("admin_users"),
					{"search": query},
				)
				self.assertEqual(response.status_code, 200)
				self.assertEqual(response.context["page_obj"].paginator.count, 1)
				self.assertEqual(
					response.context["page_obj"].object_list[0],
					self.reporter,
				)
				self.assertContains(response, query)

	def test_admin_user_list_combines_role_organization_and_status_filters(self):
		user_model = get_user_model()
		other_organization = Organization.objects.create(
			name="West District Works",
			organization_type="county",
			county="Nairobi City",
		)
		matching_user = user_model.objects.create_user(
			username="matching-manager@example.com",
			email="matching-manager@example.com",
			first_name="Matching",
			last_name="Manager",
			role="manager",
			organization=self.organization,
			is_active=True,
		)
		user_model.objects.create_user(
			username="other-org-manager@example.com",
			email="other-org-manager@example.com",
			role="manager",
			organization=other_organization,
		)
		user_model.objects.create_user(
			username="inactive-manager@example.com",
			email="inactive-manager@example.com",
			role="manager",
			organization=self.organization,
			is_active=False,
		)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_users"),
			{
				"search": "matching",
				"role": "manager",
				"organization": str(self.organization.id),
				"status": "active",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 1)
		self.assertEqual(
			response.context["page_obj"].object_list[0],
			matching_user,
		)
		self.assertContains(response, 'value="matching"')
		self.assertContains(response, 'value="manager" selected')
		self.assertContains(response, f'value="{self.organization.id}" selected')
		self.assertContains(response, 'value="active" selected')
		self.assertContains(response, "Clear filters")

	def test_invalid_user_filter_values_show_no_users_and_feedback(self):
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_users"),
			{"role": "root", "organization": "not-an-id", "status": "unknown"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 0)
		self.assertTrue(response.context["invalid_filter"])
		self.assertContains(response, "One or more filter values were invalid")
		self.assertContains(response, "No matching users")

	def test_user_search_and_filters_are_preserved_across_pagination(self):
		user_model = get_user_model()
		for index in range(26):
			user_model.objects.create_user(
				username=f"paged-resident-{index}@example.com",
				email=f"paged-resident-{index}@example.com",
				first_name="Paged",
				last_name=f"Resident{index}",
				role="resident",
				organization=self.organization,
				is_active=True,
			)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_users"),
			{
				"search": "Paged",
				"role": "resident",
				"organization": str(self.organization.id),
				"status": "active",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 26)
		self.assertTrue(response.context["page_obj"].has_next())
		self.assertEqual(
			response.context["next_page_url"],
			(
				f'?search=Paged&role=resident&organization={self.organization.id}'
				'&status=active&page=2'
			),
		)

	def test_non_admin_cannot_search_or_filter_user_directory(self):
		self.client.force_login(self.reporter)

		response = self.client.get(
			reverse("admin_users"),
			{
				"search": "Amina",
				"role": "resident",
				"organization": str(self.organization.id),
				"status": "active",
			},
		)

		self.assertEqual(response.status_code, 403)

	def test_dashboard_requires_admin_role(self):
		self.client.force_login(self.reporter)

		response = self.client.get(reverse("admin_dashboard"))

		self.assertEqual(response.status_code, 403)

	def test_anonymous_user_is_redirected_to_login(self):
		response = self.client.get(reverse("admin_dashboard"))

		self.assertRedirects(
			response,
			f"{reverse('login')}?next={reverse('admin_dashboard')}",
		)

	def test_admin_login_redirects_to_custom_dashboard(self):
		response = self.client.post(
			reverse("login"),
			{"email": self.admin.username, "password": "FlowTrack-test-123!"},
		)

		self.assertRedirects(response, reverse("admin_dashboard"))

	def test_admin_user_profile_displays_account_information(self):
		self.reporter.phone_number = "+254700123456"
		self.reporter.organization = self.organization
		self.reporter.save(update_fields=("phone_number", "organization"))
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_user_detail", args=(self.reporter.id,))
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Amina Resident")
		self.assertContains(response, "resident@example.com")
		self.assertContains(response, "Username")
		self.assertContains(response, "Amina")
		self.assertContains(response, "+254700123456")
		self.assertContains(response, "Resident")
		self.assertContains(response, self.organization.name)
		self.assertContains(response, "Active")
		self.assertContains(response, self.reporter.date_joined.strftime("%d %b %Y"))
		self.assertContains(response, "Never signed in")
		self.assertContains(response, reverse("admin_user_edit", args=(self.reporter.id,)))
		self.assertContains(
			response,
			reverse("admin_user_password_reset", args=(self.reporter.id,)),
		)
		self.assertContains(response, reverse("admin_users"))

	def test_admin_user_profile_handles_missing_optional_information(self):
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_user_detail", args=(self.reporter.id,))
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Not provided")
		self.assertContains(response, "Not assigned")
		self.assertContains(response, "Never signed in")

	def test_user_profile_requires_administrator_access(self):
		url = reverse("admin_user_detail", args=(self.reporter.id,))

		response = self.client.get(url)
		self.assertRedirects(response, f"{reverse('login')}?next={url}")

		self.client.force_login(self.reporter)
		response = self.client.get(url)
		self.assertEqual(response.status_code, 403)

	def test_admin_can_reset_user_password_without_changing_account_details(self):
		self.client.force_login(self.admin)
		original_details = {
			"first_name": self.reporter.first_name,
			"last_name": self.reporter.last_name,
			"email": self.reporter.email,
			"phone_number": self.reporter.phone_number,
			"role": self.reporter.role,
			"organization_id": self.reporter.organization_id,
			"is_active": self.reporter.is_active,
		}
		response = self.client.post(
			reverse(
				"admin_user_password_reset",
				args=(self.reporter.id,),
			),
			{
				"password": "NewReset!SecurePassword938",
				"confirm_password": "NewReset!SecurePassword938",
				"confirm_reset": "on",
			},
			follow=True,
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertTrue(self.reporter.check_password("NewReset!SecurePassword938"))
		self.assertEqual(
			int(self.client.session["_auth_user_id"]),
			self.admin.pk,
		)
		self.assertNotEqual(
			self.reporter.password,
			"NewReset!SecurePassword938",
		)
		self.assertEqual(
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": self.reporter.email,
				"phone_number": self.reporter.phone_number,
				"role": self.reporter.role,
				"organization_id": self.reporter.organization_id,
				"is_active": self.reporter.is_active,
			},
			original_details,
		)
		self.assertContains(response, "Password reset successfully")

	def test_password_reset_rejects_mismatched_confirmation(self):
		self.client.force_login(self.admin)
		old_password_hash = self.reporter.password

		response = self.client.post(
			reverse("admin_user_password_reset", args=(self.reporter.id,)),
			{
				"password": "NewReset!SecurePassword938",
				"confirm_password": "Different!SecurePassword938",
				"confirm_reset": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(response, "The passwords do not match.", status_code=400)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.password, old_password_hash)

	def test_password_reset_rejects_passwords_that_fail_validators(self):
		self.client.force_login(self.admin)
		old_password_hash = self.reporter.password

		response = self.client.post(
			reverse("admin_user_password_reset", args=(self.reporter.id,)),
			{
				"password": "weak",
				"confirm_password": "weak",
				"confirm_reset": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(response, "This password is too short", status_code=400)
		self.assertNotContains(response, 'value="weak"', status_code=400)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.password, old_password_hash)

	def test_password_reset_requires_explicit_confirmation(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_password_reset", args=(self.reporter.id,)),
			{
				"password": "NewReset!SecurePassword938",
				"confirm_password": "NewReset!SecurePassword938",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"This field is required.",
			status_code=400,
		)
		self.assertFalse(self.reporter.check_password("NewReset!SecurePassword938"))

	def test_password_reset_requires_administrator_access(self):
		url = reverse("admin_user_password_reset", args=(self.reporter.id,))

		response = self.client.get(url)
		self.assertRedirects(response, f"{reverse('login')}?next={url}")

		self.client.force_login(self.reporter)
		response = self.client.post(
			url,
			{
				"password": "NewReset!SecurePassword938",
				"confirm_password": "NewReset!SecurePassword938",
				"confirm_reset": "on",
			},
		)
		self.assertEqual(response.status_code, 403)
		self.reporter.refresh_from_db()
		self.assertFalse(self.reporter.check_password("NewReset!SecurePassword938"))

	def test_password_reset_requires_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)

		response = csrf_client.post(
			reverse("admin_user_password_reset", args=(self.reporter.id,)),
			{
				"password": "NewReset!SecurePassword938",
				"confirm_password": "NewReset!SecurePassword938",
				"confirm_reset": "on",
			},
		)

		self.assertEqual(response.status_code, 403)
		self.reporter.refresh_from_db()
		self.assertFalse(self.reporter.check_password("NewReset!SecurePassword938"))

	def test_password_reset_protects_staff_and_superuser_accounts(self):
		protected_user = get_user_model().objects.create_user(
			username="protected-staff@example.com",
			email="protected-staff@example.com",
			password="FlowTrack-test-123!",
			is_staff=True,
		)
		superuser = get_user_model().objects.create_superuser(
			username="protected-superuser@example.com",
			email="protected-superuser@example.com",
			password="FlowTrack-test-123!",
		)
		self.client.force_login(self.admin)

		for user in (protected_user, superuser):
			with self.subTest(user=user):
				response = self.client.get(
					reverse("admin_user_password_reset", args=(user.id,))
				)
				self.assertEqual(response.status_code, 403)
				post_response = self.client.post(
					reverse("admin_user_password_reset", args=(user.id,)),
					{
						"password": "NewReset!SecurePassword938",
						"confirm_password": "NewReset!SecurePassword938",
						"confirm_reset": "on",
					},
				)
				self.assertEqual(post_response.status_code, 403)
				user.refresh_from_db()
				self.assertTrue(user.check_password("FlowTrack-test-123!"))

	def test_admin_can_update_user_role_and_organization(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": self.reporter.email,
				"phone_number": self.reporter.phone_number,
				"role": "manager",
				"organization": self.organization.id,
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.role, "manager")
		self.assertEqual(self.reporter.organization, self.organization)

	def test_admin_can_update_user_email_and_phone(self):
		self.reporter.set_password("FlowTrack-test-123!")
		self.reporter.save(update_fields=("password",))
		self.client.force_login(self.admin)
		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": "Amina Updated",
				"last_name": "User",
				"email": "AMINA.updated@example.com",
				"phone_number": "+254711222333",
				"role": "resident",
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.first_name, "Amina Updated")
		self.assertEqual(self.reporter.last_name, "User")
		self.assertEqual(self.reporter.email, "amina.updated@example.com")
		self.assertEqual(self.reporter.username, "amina.updated@example.com")
		self.assertEqual(self.reporter.phone_number, "+254711222333")
		login_response = self.client.post(
			reverse("login"),
			{
				"email": "AMINA.UPDATED@example.com",
				"password": "FlowTrack-test-123!",
			},
		)
		self.assertRedirects(login_response, reverse("resident_dashboard"))

	def test_email_change_preserves_a_distinct_username(self):
		self.reporter.username = "legacy-resident-login"
		self.reporter.set_password("FlowTrack-test-123!")
		self.reporter.save(update_fields=("username", "password"))
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": "new-resident@example.com",
				"phone_number": self.reporter.phone_number,
				"role": self.reporter.role,
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.email, "new-resident@example.com")
		self.assertEqual(self.reporter.username, "legacy-resident-login")

	def test_email_change_rejects_conflicting_synchronized_username(self):
		get_user_model().objects.create_user(
			username="claimed@example.com",
			email="different@example.com",
			password="FlowTrack-test-123!",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": "CLAIMED@example.com",
				"phone_number": self.reporter.phone_number,
				"role": self.reporter.role,
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn(
			"This email is already used as another account's username.",
			response.context["form"].errors["email"][0],
		)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.email, "resident@example.com")
		self.assertEqual(self.reporter.username, "resident@example.com")

	def test_admin_user_edit_rejects_case_insensitive_duplicate_email(self):
		get_user_model().objects.create_user(
			username="another@example.com",
			email="another@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)
		self.client.force_login(self.admin)
		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": "ANOTHER@EXAMPLE.COM",
				"phone_number": self.reporter.phone_number,
				"role": "resident",
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"An account with this email already exists.",
			status_code=400,
		)
		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.email, "resident@example.com")

	def test_manager_and_engineer_cannot_be_assigned_to_inactive_organization(self):
		inactive_organization = Organization.objects.create(
			name="Inactive District",
			organization_type="county",
			county="Nairobi City",
			is_active=False,
		)
		self.client.force_login(self.admin)

		for role in ("manager", "engineer"):
			with self.subTest(role=role):
				response = self.client.post(
					reverse("admin_user_edit", args=(self.reporter.id,)),
					{
						"first_name": self.reporter.first_name,
						"last_name": self.reporter.last_name,
						"email": self.reporter.email,
						"phone_number": self.reporter.phone_number,
						"role": role,
						"organization": inactive_organization.id,
						"is_active": "on",
					},
				)
				self.assertEqual(response.status_code, 400)
				self.assertContains(
					response,
					"Choose an active organization for Managers and Engineers.",
					status_code=400,
				)

		self.reporter.refresh_from_db()
		self.assertEqual(self.reporter.role, "resident")
		self.assertIsNone(self.reporter.organization)

	def test_admin_can_activate_and_deactivate_user(self):
		self.client.force_login(self.admin)
		edit_url = reverse("admin_user_edit", args=(self.reporter.id,))
		payload = {
			"first_name": self.reporter.first_name,
			"last_name": self.reporter.last_name,
			"email": self.reporter.email,
			"phone_number": self.reporter.phone_number,
			"role": self.reporter.role,
			"organization": "",
			"is_active": "on",
		}

		self.reporter.is_active = False
		self.reporter.save(update_fields=("is_active",))
		activate_response = self.client.post(edit_url, payload)
		self.assertRedirects(
			activate_response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertTrue(self.reporter.is_active)

		payload.pop("is_active")
		deactivate_response = self.client.post(edit_url, payload)
		self.assertRedirects(
			deactivate_response,
			reverse("admin_user_detail", args=(self.reporter.id,)),
		)
		self.reporter.refresh_from_db()
		self.assertFalse(self.reporter.is_active)

	def test_editing_engineer_cannot_break_existing_work_order_assignment(self):
		engineer = get_user_model().objects.create_user(
			username="assigned-engineer@example.com",
			email="assigned-engineer@example.com",
			password="FlowTrack-test-123!",
			first_name="Assigned",
			last_name="Engineer",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="assigning-manager@example.com",
			email="assigning-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("assigned")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
		)
		other_organization = Organization.objects.create(
			name="Other District",
			organization_type="county",
			county="Nairobi City",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(engineer.id,)),
			{
				"first_name": engineer.first_name,
				"last_name": engineer.last_name,
				"email": engineer.email,
				"phone_number": engineer.phone_number,
				"role": "engineer",
				"organization": other_organization.id,
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			f"Active work-order assignments #{work_order.pk} (Assigned)",
			status_code=400,
		)
		engineer.refresh_from_db()
		self.assertEqual(engineer.organization, self.organization)

	def test_deactivation_with_only_resolved_work_orders_preserves_history(self):
		engineer = get_user_model().objects.create_user(
			username="resolved-engineer@example.com",
			email="resolved-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="resolved-manager@example.com",
			email="resolved-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("resolved")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="resolved",
			resolution_notes="Drainage cleared and flow restored.",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(engineer.id,)),
			{
				"first_name": engineer.first_name,
				"last_name": engineer.last_name,
				"email": engineer.email,
				"phone_number": engineer.phone_number,
				"role": engineer.role,
				"organization": self.organization.pk,
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(engineer.pk,)),
		)
		engineer.refresh_from_db()
		work_order.refresh_from_db()
		self.assertFalse(engineer.is_active)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.assigned_by_id, manager.pk)
		self.assertEqual(work_order.status, "resolved")

	def test_role_and_organization_changes_with_resolved_work_orders_preserve_history(self):
		engineer = get_user_model().objects.create_user(
			username="historical-engineer@example.com",
			email="historical-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="historical-manager@example.com",
			email="historical-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("resolved")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="resolved",
			resolution_notes="Work completed.",
		)
		new_organization = Organization.objects.create(
			name="Historical Assignment District",
			organization_type="county",
			county="Nairobi City",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(engineer.pk,)),
			{
				"first_name": engineer.first_name,
				"last_name": engineer.last_name,
				"email": engineer.email,
				"phone_number": engineer.phone_number,
				"role": "resident",
				"organization": new_organization.pk,
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(engineer.pk,)),
		)
		engineer.refresh_from_db()
		work_order.refresh_from_db()
		self.assertEqual(engineer.role, "resident")
		self.assertEqual(engineer.organization, new_organization)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.assigned_by_id, manager.pk)
		self.assertEqual(work_order.status, "resolved")

	def test_deactivation_with_in_progress_work_order_is_rejected(self):
		engineer = get_user_model().objects.create_user(
			username="active-engineer@example.com",
			email="active-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="active-manager@example.com",
			email="active-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("in_progress")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="in_progress",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(engineer.pk,)),
			{
				"first_name": engineer.first_name,
				"last_name": engineer.last_name,
				"email": engineer.email,
				"phone_number": engineer.phone_number,
				"role": engineer.role,
				"organization": self.organization.pk,
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			f"Active work-order assignments #{work_order.pk} (In Progress)",
			status_code=400,
		)
		engineer.refresh_from_db()
		self.assertTrue(engineer.is_active)
		self.assertEqual(work_order.engineer_id, engineer.pk)

	def test_assigning_manager_cannot_change_org_or_deactivate_with_active_order(self):
		engineer = get_user_model().objects.create_user(
			username="manager-work-engineer@example.com",
			email="manager-work-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="manager-with-work@example.com",
			email="manager-with-work@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("assigned")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="assigned",
		)
		other_organization = Organization.objects.create(
			name="Other Manager District",
			organization_type="county",
			county="Nairobi City",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(manager.pk,)),
			{
				"first_name": manager.first_name,
				"last_name": manager.last_name,
				"email": manager.email,
				"phone_number": manager.phone_number,
				"role": manager.role,
				"organization": other_organization.pk,
				"is_active": "",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			f"Active work-order assignments #{work_order.pk} (Assigned)",
			status_code=400,
		)
		manager.refresh_from_db()
		self.assertTrue(manager.is_active)
		self.assertEqual(manager.organization, self.organization)

	def test_resolved_work_order_does_not_prevent_assigning_manager_changes(self):
		engineer = get_user_model().objects.create_user(
			username="historical-work-engineer@example.com",
			email="historical-work-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		manager = get_user_model().objects.create_user(
			username="manager-with-history@example.com",
			email="manager-with-history@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		report = self.create_report("resolved")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="resolved",
			resolution_notes="Historical work completed.",
		)
		new_organization = Organization.objects.create(
			name="New Manager District",
			organization_type="county",
			county="Nairobi City",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(manager.pk,)),
			{
				"first_name": manager.first_name,
				"last_name": manager.last_name,
				"email": manager.email,
				"phone_number": manager.phone_number,
				"role": "resident",
				"organization": new_organization.pk,
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(manager.pk,)),
		)
		manager.refresh_from_db()
		work_order.refresh_from_db()
		self.assertEqual(manager.role, "resident")
		self.assertEqual(manager.organization, new_organization)
		self.assertEqual(work_order.assigned_by_id, manager.pk)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.status, "resolved")

	def test_admin_can_create_resident_with_hashed_password(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_create"),
			{
				"first_name": "New",
				"last_name": "Resident",
				"email": "New.Resident@example.com",
				"phone_number": "+254700000000",
				"role": "resident",
				"organization": "",
				"password": "NewResident!StrongPass123",
				"confirm_password": "NewResident!StrongPass123",
			},
		)

		self.assertRedirects(response, reverse("admin_users"))
		created_user = get_user_model().objects.get(
			email="new.resident@example.com"
		)
		self.assertEqual(created_user.username, "new.resident@example.com")
		self.assertEqual(created_user.role, "resident")
		self.assertIsNone(created_user.organization)
		self.assertTrue(created_user.check_password("NewResident!StrongPass123"))
		self.assertNotEqual(created_user.password, "NewResident!StrongPass123")

	def test_admin_can_create_manager_or_engineer_in_active_organization(self):
		self.client.force_login(self.admin)

		for role in ("manager", "engineer"):
			with self.subTest(role=role):
				email = f"new-{role}@example.com"
				response = self.client.post(
					reverse("admin_user_create"),
					{
						"first_name": "New",
						"last_name": role.title(),
						"email": email,
						"phone_number": "",
						"role": role,
						"organization": self.organization.id,
						"password": "NewAccount!StrongPass123",
						"confirm_password": "NewAccount!StrongPass123",
					},
				)

				self.assertRedirects(response, reverse("admin_users"))
				created_user = get_user_model().objects.get(email=email)
				self.assertEqual(created_user.role, role)
				self.assertEqual(created_user.organization, self.organization)

	def test_duplicate_email_is_rejected_case_insensitively(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_create"),
			{
				"first_name": "Duplicate",
				"last_name": "User",
				"email": "RESIDENT@EXAMPLE.COM",
				"role": "resident",
				"organization": "",
				"password": "Duplicate!StrongPassword123",
				"confirm_password": "Duplicate!StrongPassword123",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"An account with this email already exists.",
			status_code=400,
		)
		self.assertEqual(get_user_model().objects.filter(email__iexact="resident@example.com").count(), 1)

	def test_invalid_password_is_rejected(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_create"),
			{
				"first_name": "Weak",
				"last_name": "Password",
				"email": "weak-password@example.com",
				"role": "resident",
				"organization": "",
				"password": "weak",
				"confirm_password": "weak",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(response, "This password is too short", status_code=400)
		self.assertFalse(
			get_user_model().objects.filter(email="weak-password@example.com").exists()
		)

	def test_manager_and_engineer_creation_require_an_active_organization(self):
		self.client.force_login(self.admin)

		for role in ("manager", "engineer"):
			with self.subTest(role=role):
				response = self.client.post(
					reverse("admin_user_create"),
					{
						"first_name": "No",
						"last_name": "Organization",
						"email": f"no-{role}-organization@example.com",
						"role": role,
						"organization": "",
						"password": "NewAccount!StrongPass123",
						"confirm_password": "NewAccount!StrongPass123",
					},
				)

				self.assertEqual(response.status_code, 400)
				self.assertContains(
					response,
					"Managers and engineers must belong to an active organization.",
					status_code=400,
				)
				self.assertFalse(
					get_user_model()
					.objects.filter(email=f"no-{role}-organization@example.com")
					.exists()
				)

	def test_administrator_role_is_not_available_for_user_creation(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_create"),
			{
				"first_name": "Attempt",
				"last_name": "Admin",
				"email": "attempt-admin@example.com",
				"role": "admin",
				"organization": "",
				"password": "NewAccount!StrongPass123",
				"confirm_password": "NewAccount!StrongPass123",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(response, "Select a valid choice", status_code=400)
		self.assertFalse(
			get_user_model().objects.filter(email="attempt-admin@example.com").exists()
		)

	def test_non_admin_cannot_access_user_creation(self):
		self.client.force_login(self.reporter)

		response = self.client.get(reverse("admin_user_create"))

		self.assertEqual(response.status_code, 403)

	def test_anonymous_user_is_redirected_from_user_creation(self):
		response = self.client.get(reverse("admin_user_create"))

		self.assertRedirects(
			response,
			f"{reverse('login')}?next={reverse('admin_user_create')}",
		)

	def test_user_creation_post_requires_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)

		response = csrf_client.post(
			reverse("admin_user_create"),
			{
				"first_name": "No",
				"last_name": "CSRF",
				"email": "no-csrf@example.com",
				"role": "resident",
				"organization": "",
				"password": "NewAccount!StrongPass123",
				"confirm_password": "NewAccount!StrongPass123",
			},
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(
			get_user_model().objects.filter(email="no-csrf@example.com").exists()
		)

	def test_last_active_admin_cannot_be_demoted(self):
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(self.admin.id,)),
			{
				"first_name": self.admin.first_name,
				"last_name": self.admin.last_name,
				"email": self.admin.email,
				"phone_number": self.admin.phone_number,
				"role": "resident",
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.admin.refresh_from_db()
		self.assertEqual(self.admin.role, "admin")

	def test_admin_can_create_and_edit_organizations(self):
		self.client.force_login(self.admin)
		create_response = self.client.post(
			reverse("admin_organization_create"),
			{
				"name": "East District Works",
				"organization_type": "county",
				"county": "Nairobi City",
				"address": "",
				"phone": "",
				"email": "",
				"is_active": "on",
			},
		)

		new_organization = Organization.objects.get(name="East District Works")
		self.assertRedirects(
			create_response,
			reverse("admin_organization_detail", args=(new_organization.id,)),
		)
		edit_response = self.client.post(
			reverse("admin_organization_edit", args=(new_organization.id,)),
			{
				"name": "East District Drainage",
				"organization_type": "county",
				"county": "Nairobi City",
				"address": "",
				"phone": "",
				"email": "",
				"is_active": "",
				"confirm_deactivation": "on",
			},
		)

		self.assertRedirects(
			edit_response,
			reverse("admin_organization_detail", args=(new_organization.id,)),
		)
		new_organization.refresh_from_db()
		self.assertEqual(new_organization.name, "East District Drainage")
		self.assertFalse(new_organization.is_active)

	def test_organization_search_and_combined_filters(self):
		matching = Organization.objects.create(
			name="Central Response Unit",
			organization_type="county",
			county="Nairobi City",
			is_active=True,
		)
		Organization.objects.create(
			name="Central Old Unit",
			organization_type="county",
			county="Nairobi City",
			is_active=False,
		)
		Organization.objects.create(
			name="Central University",
			organization_type="university",
			county="Nairobi City",
			is_active=True,
		)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_organizations"),
			{
				"search": "Central",
				"status": "active",
				"type": "county",
				"county": "Nairobi City",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 1)
		self.assertEqual(response.context["page_obj"].object_list[0], matching)
		self.assertContains(response, 'value="Central"')
		self.assertContains(response, 'value="active" selected')
		self.assertContains(response, 'value="county" selected')
		self.assertContains(response, 'value="Nairobi City" selected')
		self.assertContains(response, "Clear filters")

	def test_organization_filter_pagination_preserves_selection(self):
		for index in range(26):
			Organization.objects.create(
				name=f"PageOrg{index:02}",
				organization_type="county",
				county="Nairobi",
				is_active=True,
			)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_organizations"),
			{
				"search": "PageOrg",
				"status": "active",
				"type": "county",
				"county": "Nairobi",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 26)
		self.assertEqual(
			response.context["next_page_url"],
			"?search=PageOrg&status=active&type=county&county=Nairobi&page=2",
		)

	def test_invalid_organization_filter_and_empty_results_show_feedback(self):
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_organizations"),
			{"status": "unknown"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 0)
		self.assertContains(response, "One or more filter values were invalid")
		self.assertContains(response, "No matching organizations")

	def test_organization_details_show_users_reports_and_work_orders(self):
		manager = get_user_model().objects.create_user(
			username="org-manager@example.com",
			email="org-manager@example.com",
			password="FlowTrack-test-123!",
			first_name="Miriam",
			last_name="Manager",
			role="manager",
			organization=self.organization,
		)
		engineer = get_user_model().objects.create_user(
			username="org-engineer@example.com",
			email="org-engineer@example.com",
			password="FlowTrack-test-123!",
			first_name="Eli",
			last_name="Engineer",
			role="engineer",
			organization=self.organization,
		)
		submitted = self.create_report("submitted")
		assigned = self.create_report("assigned")
		work_order = MaintenanceWorkOrder.objects.create(
			report=assigned,
			engineer=engineer,
			assigned_by=manager,
			status="assigned",
		)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_organization_detail", args=(self.organization.pk,))
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_users"], 2)
		self.assertEqual(response.context["manager_count"], 1)
		self.assertEqual(response.context["engineer_count"], 1)
		self.assertEqual(response.context["total_reports"], 2)
		self.assertEqual(response.context["total_work_orders"], 1)
		self.assertEqual(response.context["open_work_orders"], 1)
		report_status_counts = {
			item["value"]: item["count"]
			for item in response.context["report_statuses"]
		}
		self.assertEqual(report_status_counts["submitted"], 1)
		self.assertEqual(report_status_counts["assigned"], 1)
		self.assertContains(response, self.organization.name)
		self.assertContains(response, "Miriam Manager")
		self.assertContains(response, "Eli Engineer")
		self.assertContains(response, submitted.area)
		self.assertContains(response, f"#{work_order.pk}")

	def test_organization_deactivation_warns_and_preserves_associations(self):
		manager = get_user_model().objects.create_user(
			username="deactivate-manager@example.com",
			email="deactivate-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		engineer = get_user_model().objects.create_user(
			username="deactivate-engineer@example.com",
			email="deactivate-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		report = self.create_report("assigned")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="in_progress",
		)
		self.client.force_login(self.admin)
		edit_url = reverse("admin_organization_edit", args=(self.organization.pk,))

		warning_response = self.client.get(edit_url)
		self.assertEqual(warning_response.status_code, 200)
		self.assertEqual(
			warning_response.context["deactivation_warning"],
			{"users": 2, "reports": 1, "open_work_orders": 1},
		)
		self.assertContains(warning_response, "Deactivation preserves existing records")
		self.assertContains(warning_response, "1 open work order")

		payload = {
			"name": self.organization.name,
			"organization_type": self.organization.organization_type,
			"county": self.organization.county,
			"address": self.organization.address,
			"phone": self.organization.phone,
			"email": self.organization.email,
			"is_active": "",
		}
		unconfirmed_response = self.client.post(edit_url, payload)
		self.assertEqual(unconfirmed_response.status_code, 400)
		self.assertContains(
			unconfirmed_response,
			"Confirm the deactivation warning",
			status_code=400,
		)
		self.organization.refresh_from_db()
		self.assertTrue(self.organization.is_active)

		payload["confirm_deactivation"] = "on"
		deactivate_response = self.client.post(edit_url, payload)
		self.assertRedirects(
			deactivate_response,
			reverse("admin_organization_detail", args=(self.organization.pk,)),
		)
		self.organization.refresh_from_db()
		manager.refresh_from_db()
		engineer.refresh_from_db()
		report.refresh_from_db()
		work_order.refresh_from_db()
		self.assertFalse(self.organization.is_active)
		self.assertEqual(manager.organization_id, self.organization.pk)
		self.assertEqual(engineer.organization_id, self.organization.pk)
		self.assertEqual(report.organization_id, self.organization.pk)
		self.assertEqual(work_order.report_id, report.pk)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.assigned_by_id, manager.pk)
		self.assertEqual(work_order.status, "in_progress")
		self.assertEqual(
			self.client.get(reverse("organization_report_queue")).status_code,
			403,
		)

		payload["is_active"] = "on"
		payload.pop("confirm_deactivation")
		reactivate_response = self.client.post(edit_url, payload)
		self.assertRedirects(
			reactivate_response,
			reverse("admin_organization_detail", args=(self.organization.pk,)),
		)
		self.organization.refresh_from_db()
		self.assertTrue(self.organization.is_active)
		self.client.force_login(manager)
		self.assertEqual(
			self.client.get(reverse("organization_report_queue")).status_code,
			200,
		)

	def test_resident_cannot_be_newly_assigned_to_inactive_organization(self):
		inactive_organization = Organization.objects.create(
			name="Inactive User Target",
			organization_type="county",
			county="Nairobi City",
			is_active=False,
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(self.reporter.pk,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": self.reporter.email,
				"phone_number": self.reporter.phone_number,
				"role": "resident",
				"organization": inactive_organization.pk,
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"Choose an active organization. Existing inactive assignments may be",
			status_code=400,
		)
		self.reporter.refresh_from_db()
		self.assertIsNone(self.reporter.organization_id)

	def test_existing_user_assignment_to_deactivated_organization_can_be_retained(self):
		manager = get_user_model().objects.create_user(
			username="retained-manager@example.com",
			email="retained-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		self.organization.is_active = False
		self.organization.save(update_fields=("is_active",))
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_user_edit", args=(manager.pk,)),
			{
				"first_name": "Updated",
				"last_name": manager.last_name,
				"email": manager.email,
				"phone_number": manager.phone_number,
				"role": "manager",
				"organization": self.organization.pk,
				"is_active": "on",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_user_detail", args=(manager.pk,)),
		)
		manager.refresh_from_db()
		self.assertEqual(manager.first_name, "Updated")
		self.assertEqual(manager.organization_id, self.organization.pk)

	def test_report_list_and_detail_are_available_to_admin(self):
		report = self.create_report("submitted")
		self.client.force_login(self.admin)

		list_response = self.client.get(reverse("admin_reports"))
		detail_response = self.client.get(
			reverse("admin_report_detail", args=(report.id,))
		)

		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, "Inspect")
		self.assertEqual(detail_response.status_code, 200)
		self.assertContains(detail_response, "Submitted Road")

	def test_report_search_and_combined_filters(self):
		matching = self.create_report("submitted")
		matching.issue_type = "flooding"
		matching.area = "Central Bus Station"
		matching.save(update_fields=("issue_type", "area"))
		other = self.create_report("submitted")
		other.area = "Central Market"
		other.save(update_fields=("area",))
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_reports"),
			{
				"search": "Central",
				"county": matching.county,
				"issue_type": "flooding",
				"status": "submitted",
				"priority": "medium",
				"organization": str(self.organization.pk),
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["page_obj"].paginator.count, 1)
		self.assertEqual(response.context["page_obj"].object_list[0], matching)
		self.assertContains(response, "Central Bus Station")
		self.assertNotContains(response, "Central Market")

	def test_report_search_matches_report_id_and_reporter_name(self):
		report = self.create_report("submitted")
		self.client.force_login(self.admin)

		id_response = self.client.get(
			reverse("admin_reports"),
			{"search": str(report.pk)},
		)
		name_response = self.client.get(
			reverse("admin_reports"),
			{"search": "Amina Resident"},
		)

		self.assertEqual(id_response.context["page_obj"].paginator.count, 1)
		self.assertEqual(name_response.context["page_obj"].paginator.count, 1)

	def test_unassigned_report_filter_and_empty_state(self):
		report = self.create_report("submitted")
		report.organization = None
		report.save(update_fields=("organization",))
		self.create_report("resolved")
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_reports"),
			{"unassigned": "1"},
		)
		empty_response = self.client.get(
			reverse("admin_reports"),
			{"search": "No such drainage report"},
		)

		self.assertEqual(response.context["page_obj"].paginator.count, 1)
		self.assertContains(response, "Unassigned")
		self.assertEqual(empty_response.context["page_obj"].paginator.count, 0)
		self.assertContains(empty_response, "No matching reports")

	def test_report_pagination_preserves_active_filters(self):
		for index in range(26):
			report = self.create_report("submitted")
			report.area = f"Filtered Road {index:02}"
			report.save(update_fields=("area",))
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_reports"),
			{
				"county": "Nairobi City",
				"status": "submitted",
				"priority": "medium",
				"page": "1",
			},
		)

		self.assertEqual(response.context["page_obj"].paginator.count, 26)
		self.assertEqual(
			response.context["next_page_url"],
			"?county=Nairobi+City&status=submitted&priority=medium&page=2",
		)

	def test_admin_can_assign_report_and_update_priority_and_status(self):
		report = self.create_report("submitted")
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_report_detail", args=(report.pk,)),
			{
				"organization": self.organization.pk,
				"priority": "critical",
				"status": "under_review",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_report_detail", args=(report.pk,)),
		)
		report.refresh_from_db()
		self.assertEqual(report.organization_id, self.organization.pk)
		self.assertEqual(report.priority, "critical")
		self.assertEqual(report.status, "under_review")
		self.assertEqual(report.reporter_id, self.reporter.pk)

	def test_admin_report_management_rejects_inactive_organization(self):
		inactive_organization = Organization.objects.create(
			name="Inactive Report Target",
			organization_type="county",
			county="Nairobi City",
			is_active=False,
		)
		report = self.create_report("submitted")
		report.organization = None
		report.save(update_fields=("organization",))
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_report_detail", args=(report.pk,)),
			{
				"organization": inactive_organization.pk,
				"priority": "high",
				"status": "under_review",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"Reports can only be assigned to active organizations.",
			status_code=400,
		)
		report.refresh_from_db()
		self.assertIsNone(report.organization_id)
		self.assertEqual(report.priority, "medium")
		self.assertEqual(report.status, "submitted")

	def test_report_organization_cannot_change_when_work_order_exists(self):
		report = self.create_report("assigned")
		second_organization = Organization.objects.create(
			name="Second Report Organization",
			organization_type="county",
			county="Nairobi City",
		)
		manager = get_user_model().objects.create_user(
			username="report-manager@example.com",
			email="report-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		engineer = get_user_model().objects.create_user(
			username="report-engineer@example.com",
			email="report-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="in_progress",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_report_detail", args=(report.pk,)),
			{
				"organization": second_organization.pk,
				"priority": "critical",
				"status": "resolved",
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertContains(
			response,
			"cannot be changed because that would leave the Engineer",
			status_code=400,
		)
		report.refresh_from_db()
		work_order.refresh_from_db()
		self.assertEqual(report.organization_id, self.organization.pk)
		self.assertEqual(report.priority, "medium")
		self.assertEqual(report.status, "assigned")
		self.assertEqual(work_order.report_id, report.pk)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.assigned_by_id, manager.pk)
		self.assertEqual(work_order.status, "in_progress")

	def test_report_work_order_allows_other_management_updates_without_reassigning(self):
		report = self.create_report("assigned")
		manager = get_user_model().objects.create_user(
			username="same-org-manager@example.com",
			email="same-org-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		engineer = get_user_model().objects.create_user(
			username="same-org-engineer@example.com",
			email="same-org-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
		)
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			reverse("admin_report_detail", args=(report.pk,)),
			{
				"organization": self.organization.pk,
				"priority": "high",
				"status": "in_progress",
			},
		)

		self.assertRedirects(
			response,
			reverse("admin_report_detail", args=(report.pk,)),
		)
		report.refresh_from_db()
		work_order.refresh_from_db()
		self.assertEqual(report.priority, "high")
		self.assertEqual(report.status, "in_progress")
		self.assertEqual(report.organization_id, self.organization.pk)
		self.assertEqual(work_order.engineer_id, engineer.pk)
		self.assertEqual(work_order.assigned_by_id, manager.pk)

	def test_report_management_requires_admin_and_csrf(self):
		report = self.create_report("submitted")
		self.client.force_login(self.reporter)
		for method in ("get", "post"):
			with self.subTest(method=method):
				response = (
					self.client.get(reverse("admin_report_detail", args=(report.pk,)))
					if method == "get"
					else self.client.post(
						reverse("admin_report_detail", args=(report.pk,)),
						{
							"organization": self.organization.pk,
							"priority": "high",
							"status": "under_review",
						},
					)
				)
				self.assertEqual(response.status_code, 403)

		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)
		response = csrf_client.post(
			reverse("admin_report_detail", args=(report.pk,)),
			{
				"organization": self.organization.pk,
				"priority": "high",
				"status": "under_review",
			},
		)
		self.assertEqual(response.status_code, 403)
		report.refresh_from_db()
		self.assertEqual(report.status, "submitted")
		self.assertEqual(report.priority, "medium")

	def test_admin_can_inspect_work_order_progress(self):
		report = self.create_report("assigned")
		manager = get_user_model().objects.create_user(
			username="manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=self.organization,
		)
		engineer = get_user_model().objects.create_user(
			username="engineer@example.com",
			password="FlowTrack-test-123!",
			first_name="Maintenance",
			last_name="Engineer",
			role="engineer",
			organization=self.organization,
		)
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
		)
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_work_order_detail", args=(work_order.id,))
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Maintenance Engineer")
		self.assertContains(response, "Assigned")

	def test_admin_management_urls_reject_non_admin_users(self):
		self.client.force_login(self.reporter)

		for url_name in (
			"admin_users",
			"admin_organizations",
			"admin_organization_detail",
			"admin_organization_edit",
			"admin_reports",
			"admin_work_orders",
		):
			with self.subTest(url_name=url_name):
				url = (
					reverse(url_name, args=(self.organization.id,))
					if url_name in ("admin_organization_detail", "admin_organization_edit")
					else reverse(url_name)
				)
				self.assertEqual(self.client.get(url).status_code, 403)

	def test_administrator_management_pages_render(self):
		self.client.force_login(self.admin)
		urls = (
			reverse("admin_users"),
			reverse("admin_organizations"),
			reverse("admin_organization_create"),
			reverse("admin_organization_detail", args=(self.organization.id,)),
			reverse("admin_organization_edit", args=(self.organization.id,)),
			reverse("admin_work_orders"),
		)

		for url in urls:
			with self.subTest(url=url):
				self.assertEqual(self.client.get(url).status_code, 200)

	def test_staff_account_is_protected_from_dashboard_edits(self):
		self.reporter.is_staff = True
		self.reporter.save(update_fields=("is_staff",))
		self.client.force_login(self.admin)

		response = self.client.get(
			reverse("admin_user_detail", args=(self.reporter.id,))
		)

		self.assertEqual(response.status_code, 403)

	def test_administrator_form_posts_require_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)

		response = csrf_client.post(
			reverse("admin_organization_create"),
			{
				"name": "East District Works",
				"organization_type": "county",
				"county": "Nairobi City",
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(
			Organization.objects.filter(name="East District Works").exists()
		)

	def test_organization_edit_posts_require_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)

		response = csrf_client.post(
			reverse("admin_organization_edit", args=(self.organization.id,)),
			{
				"name": "Changed without CSRF",
				"organization_type": self.organization.organization_type,
				"county": self.organization.county,
				"address": self.organization.address,
				"phone": self.organization.phone,
				"email": self.organization.email,
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 403)
		self.organization.refresh_from_db()
		self.assertNotEqual(self.organization.name, "Changed without CSRF")

	def test_user_edit_posts_require_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.admin)

		response = csrf_client.post(
			reverse("admin_user_edit", args=(self.reporter.id,)),
			{
				"first_name": self.reporter.first_name,
				"last_name": self.reporter.last_name,
				"email": self.reporter.email,
				"phone_number": self.reporter.phone_number,
				"role": self.reporter.role,
				"organization": "",
				"is_active": "on",
			},
		)

		self.assertEqual(response.status_code, 403)
