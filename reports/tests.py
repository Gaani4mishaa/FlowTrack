from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from PIL import Image

from accounts.models import Organization
from maintenance.models import MaintenanceWorkOrder
from .admin import ReportAdminForm
from .models import Report


class ResidentReportWorkflowTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		user_model = get_user_model()
		cls.resident = user_model.objects.create_user(
			username="resident@example.com",
			email="resident@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)
		cls.other_resident = user_model.objects.create_user(
			username="other@example.com",
			email="other@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)

	def setUp(self):
		self.client.force_login(self.resident)

	def report_data(self, **overrides):
		data = {
			"issue_type": "blocked_drain",
			"county": "Nairobi City",
			"area": "South B",
			"location_description": "Near the bus stop",
			"latitude": "-1.303200",
			"longitude": "36.829100",
			"description": "Water is not draining after rain.",
		}
		data.update(overrides)
		return data

	def create_report(self, reporter=None, **overrides):
		report_data = {
			"reporter": reporter or self.resident,
			"issue_type": "blocked_drain",
			"county": "Nairobi City",
			"area": "South B",
		}
		report_data.update(overrides)
		return Report.objects.create(**report_data)

	def test_resident_can_create_a_valid_report(self):
		response = self.client.post(reverse("report_issue"), self.report_data())

		report = Report.objects.get()
		self.assertRedirects(response, reverse("report_detail", args=[report.id]))
		self.assertEqual(report.reporter, self.resident)
		self.assertEqual(report.issue_type, "blocked_drain")
		self.assertEqual(report.county, "Nairobi City")
		self.assertEqual(report.area, "South B")
		self.assertEqual(report.location_description, "Near the bus stop")
		self.assertEqual(report.description, "Water is not draining after rain.")
		self.assertEqual(str(report.latitude), "-1.303200")
		self.assertEqual(str(report.longitude), "36.829100")
		self.assertEqual(report.status, "submitted")
		self.assertEqual(report.priority, "medium")

	def test_resident_can_submit_a_photo_with_coordinates(self):
		image_data = BytesIO()
		Image.new("RGB", (2, 2), color="blue").save(image_data, format="JPEG")
		photo = SimpleUploadedFile(
			"drainage.jpg",
			image_data.getvalue(),
			content_type="image/jpeg",
		)

		with TemporaryDirectory() as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				response = self.client.post(
					reverse("report_issue"),
					{**self.report_data(latitude="0", longitude="0"), "photo": photo},
				)

				report = Report.objects.get()
				self.assertRedirects(response, reverse("report_detail", args=[report.id]))
				self.assertEqual(report.reporter, self.resident)
				self.assertEqual(str(report.latitude), "0.000000")
				self.assertEqual(str(report.longitude), "0.000000")
				self.assertTrue(report.photo.name.startswith("reports/"))
				self.assertTrue(report.photo.storage.exists(report.photo.name))

	def test_gps_coordinates_have_visible_confirmation_and_specific_error_feedback(self):
		response = self.client.get(reverse("report_issue"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="latitude"')
		self.assertContains(response, 'id="longitude"')
		self.assertContains(response, 'aria-live="polite"')
		self.assertContains(response, "Coordinates captured:")
		self.assertContains(response, "Location permission was denied.")
		self.assertContains(response, "location request timed out.")
		self.assertContains(response, "County and area must still be entered manually.")

	def test_resident_report_is_visible_in_history_and_admin_management(self):
		self.client.post(reverse("report_issue"), self.report_data())
		report = Report.objects.get()

		history_response = self.client.get(reverse("my_reports"))
		self.assertEqual(history_response.status_code, 200)
		self.assertContains(history_response, "South B")
		self.assertContains(history_response, "Medium")
		self.assertContains(history_response, "Submitted")
		self.assertEqual(list(history_response.context["reports"]), [report])

		admin = get_user_model().objects.create_user(
			username="report-admin@example.com",
			email="report-admin@example.com",
			role="admin",
		)
		self.client.force_login(admin)
		admin_response = self.client.get(reverse("admin_reports"))
		self.assertEqual(admin_response.status_code, 200)
		self.assertContains(admin_response, "South B")

	def test_dashboard_counts_only_the_signed_in_residents_reports(self):
		self.create_report(status="submitted", area="Awaiting Road")
		self.create_report(status="under_review", area="Review Road")
		self.create_report(status="in_progress", area="Active Road")
		self.create_report(status="resolved", area="Resolved Road")
		self.create_report(reporter=self.other_resident, status="submitted", area="Other Resident Road")

		response = self.client.get(reverse("resident_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_reports"], 4)
		self.assertEqual(response.context["awaiting_review_reports"], 2)
		self.assertEqual(response.context["in_progress_reports"], 1)
		self.assertEqual(response.context["resolved_reports"], 1)
		self.assertNotContains(response, "Other Resident Road")
		self.assertContains(response, reverse("report_issue"))
		self.assertContains(response, reverse("my_reports"))

	def test_my_reports_is_paginated_and_scoped_to_the_resident(self):
		for index in range(11):
			self.create_report(area=f"Resident Road {index}")
		self.create_report(reporter=self.other_resident, area="Private Other Road")

		first_page = self.client.get(reverse("my_reports"))
		second_page = self.client.get(reverse("my_reports"), {"page": 2})

		self.assertEqual(first_page.context["page_obj"].paginator.count, 11)
		self.assertEqual(len(first_page.context["reports"]), 10)
		self.assertEqual(len(second_page.context["reports"]), 1)
		self.assertContains(first_page, "Page 1 of 2")
		self.assertContains(first_page, "Next")
		self.assertNotContains(first_page, "Private Other Road")
		self.assertNotContains(second_page, "Private Other Road")

	def test_report_detail_shows_only_recorded_status_and_work_order_progress(self):
		organization = Organization.objects.create(
			name="South B Drainage Services",
			organization_type="county",
			county="Nairobi City",
		)
		manager = get_user_model().objects.create_user(
			username="resident-test-manager@example.com",
			role="manager",
			organization=organization,
		)
		engineer = get_user_model().objects.create_user(
			username="resident-test-engineer@example.com",
			role="engineer",
			organization=organization,
		)
		report = self.create_report(
			status="in_progress",
			organization=organization,
			latitude=0,
			longitude=0,
		)
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
			status="in_progress",
			resolution_notes="Clearing debris; work is ongoing.",
		)

		response = self.client.get(reverse("report_detail", args=[report.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "South B Drainage Services")
		self.assertContains(response, "0.000000, 0.000000")
		self.assertContains(response, "In Progress")
		self.assertContains(response, "Clearing debris; work is ongoing.")
		self.assertContains(response, "Current status recorded for this report.")
		self.assertContains(response, "earlier status changes are not retained")
		self.assertFalse(response.context["can_manage_report"])
		self.assertEqual(response.context["work_order"], work_order)
		self.assertNotContains(response, "The report is updated when the issue has been resolved.")

	def test_resident_cannot_modify_another_residents_report(self):
		report = self.create_report(reporter=self.other_resident)

		for name in ("report_detail", "edit_report", "delete_report"):
			with self.subTest(view=name):
				response = self.client.get(reverse(name, args=[report.id]))
				self.assertEqual(response.status_code, 404)

		self.assertTrue(Report.objects.filter(pk=report.pk).exists())

	def test_edit_form_cannot_change_workflow_priority_or_organization(self):
		organization = Organization.objects.create(
			name="Existing Assignment",
			organization_type="county",
			county="Nairobi City",
		)
		report = self.create_report(organization=organization)
		data = self.report_data(
			area="Updated Area",
			status="closed",
			priority="critical",
			organization="",
		)

		response = self.client.post(reverse("edit_report", args=[report.pk]), data)

		self.assertRedirects(response, reverse("report_detail", args=[report.pk]))
		report.refresh_from_db()
		self.assertEqual(report.area, "Updated Area")
		self.assertEqual(report.status, "submitted")
		self.assertEqual(report.priority, "medium")
		self.assertEqual(report.organization, organization)

	def test_report_with_work_order_cannot_be_edited_or_deleted(self):
		organization = Organization.objects.create(
			name="Maintenance Assignment",
			organization_type="county",
			county="Nairobi City",
		)
		manager = get_user_model().objects.create_user(
			username="assigned-manager@example.com",
			role="manager",
			organization=organization,
		)
		engineer = get_user_model().objects.create_user(
			username="assigned-engineer@example.com",
			role="engineer",
			organization=organization,
		)
		report = self.create_report(organization=organization, status="submitted")
		work_order = MaintenanceWorkOrder.objects.create(
			report=report,
			engineer=engineer,
			assigned_by=manager,
		)

		edit_response = self.client.post(
			reverse("edit_report", args=[report.pk]),
			self.report_data(area="Changed Area"),
		)
		delete_response = self.client.post(reverse("delete_report", args=[report.pk]))

		self.assertRedirects(edit_response, reverse("report_detail", args=[report.pk]))
		self.assertRedirects(delete_response, reverse("report_detail", args=[report.pk]))
		report.refresh_from_db()
		self.assertEqual(report.area, "South B")
		self.assertTrue(MaintenanceWorkOrder.objects.filter(pk=work_order.pk).exists())

	def test_non_residents_cannot_use_resident_dashboard_or_report_pages(self):
		manager = get_user_model().objects.create_user(
			username="resident-route-manager@example.com",
			role="manager",
		)
		self.client.force_login(manager)

		for name in ("resident_dashboard", "report_issue", "my_reports"):
			with self.subTest(view=name):
				self.assertEqual(self.client.get(reverse(name)).status_code, 403)

	def test_invalid_issue_and_unpaired_coordinates_are_rejected(self):
		response = self.client.post(
			reverse("report_issue"),
			self.report_data(issue_type="made_up", longitude=""),
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Report.objects.count(), 0)
		self.assertContains(response, "Select a valid choice")
		self.assertContains(response, "Enter both location coordinates")

	def test_out_of_range_coordinates_are_rejected(self):
		response = self.client.post(
			reverse("report_issue"),
			self.report_data(latitude="91", longitude="181"),
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Report.objects.count(), 0)
		self.assertContains(response, "Latitude must be between -90 and 90", html=False)

	def test_oversized_photo_is_rejected(self):
		photo = SimpleUploadedFile(
			"large.jpg",
			b"x" * (5 * 1024 * 1024 + 1),
			content_type="image/jpeg",
		)

		data = self.report_data()
		data["photo"] = photo
		response = self.client.post(reverse("report_issue"), data)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Report.objects.count(), 0)
		self.assertContains(response, "Choose an image smaller than 5 MB")

	def test_resident_can_edit_their_submitted_report(self):
		report = self.create_report()

		response = self.client.post(
			reverse("edit_report", args=[report.id]),
			self.report_data(area="Hurlingham"),
		)

		self.assertRedirects(response, reverse("report_detail", args=[report.id]))
		report.refresh_from_db()
		self.assertEqual(report.area, "Hurlingham")

	def test_resident_cannot_access_another_residents_report(self):
		report = self.create_report(reporter=self.other_resident)

		response = self.client.get(reverse("edit_report", args=[report.id]))

		self.assertEqual(response.status_code, 404)

	def test_report_cannot_be_changed_after_review_starts(self):
		report = self.create_report(status="under_review")

		response = self.client.get(reverse("edit_report", args=[report.id]))

		self.assertRedirects(response, reverse("report_detail", args=[report.id]))
		report.refresh_from_db()
		self.assertEqual(report.status, "under_review")

	def test_report_cannot_be_deleted_after_review_starts(self):
		report = self.create_report(status="under_review")

		response = self.client.post(reverse("delete_report", args=[report.id]))

		self.assertRedirects(response, reverse("report_detail", args=[report.id]))
		self.assertTrue(Report.objects.filter(id=report.id).exists())

	def test_delete_requires_confirmation_and_post(self):
		report = self.create_report()

		confirmation = self.client.get(reverse("delete_report", args=[report.id]))
		self.assertEqual(confirmation.status_code, 200)
		self.assertContains(confirmation, "cannot be undone")

		response = self.client.post(reverse("delete_report", args=[report.id]))
		self.assertRedirects(response, reverse("my_reports"))
		self.assertFalse(Report.objects.filter(id=report.id).exists())


class OrganizationReportQueueTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		user_model = get_user_model()
		cls.organization = Organization.objects.create(
			name="North District Works",
			organization_type="county",
			county="Nairobi City",
		)
		cls.other_organization = Organization.objects.create(
			name="West District Works",
			organization_type="county",
			county="Nairobi City",
		)
		cls.manager = user_model.objects.create_user(
			username="manager@example.com",
			email="manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=cls.organization,
		)
		cls.other_manager = user_model.objects.create_user(
			username="other-manager@example.com",
			email="other-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=cls.other_organization,
		)
		cls.resident = user_model.objects.create_user(
			username="queue-resident@example.com",
			email="queue-resident@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)

	def setUp(self):
		self.client.force_login(self.manager)

	def create_report(self, organization, area):
		return Report.objects.create(
			reporter=self.resident,
			organization=organization,
			issue_type="blocked_drain",
			county="Nairobi City",
			area=area,
		)

	def test_manager_queue_contains_only_reports_assigned_to_their_organization(self):
		own_report = self.create_report(self.organization, "South B")
		other_report = self.create_report(self.other_organization, "Westlands")
		unassigned_report = self.create_report(None, "Kilimani")

		response = self.client.get(reverse("organization_report_queue"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f"Report #{own_report.id}")
		self.assertNotContains(response, f"Report #{other_report.id}")
		self.assertNotContains(response, f"Report #{unassigned_report.id}")

	def test_manager_dashboard_shows_organization_scoped_summary_and_recent_reports(self):
		pending = self.create_report(self.organization, "South B")
		pending.status = "under_review"
		pending.save(update_fields=("status",))
		active_report = self.create_report(self.organization, "Kilimani")
		active_report.status = "in_progress"
		active_report.save(update_fields=("status",))
		resolved_report = self.create_report(self.organization, "Eastleigh")
		resolved_report.status = "resolved"
		resolved_report.save(update_fields=("status",))
		other_report = self.create_report(self.other_organization, "Westlands")

		engineer = get_user_model().objects.create_user(
			username="dashboard-org-engineer@example.com",
			role="engineer",
			organization=self.organization,
		)
		active_order = MaintenanceWorkOrder.objects.create(
			report=active_report,
			engineer=engineer,
			assigned_by=self.manager,
			status="in_progress",
		)
		resolved_order = MaintenanceWorkOrder(
			report=resolved_report,
			engineer=engineer,
			assigned_by=self.manager,
			status="resolved",
			resolution_notes="Cleared debris and confirmed the drain is flowing.",
			resolved_at=timezone.now(),
		)
		resolved_order.full_clean()
		resolved_order.save()

		response = self.client.get(reverse("manager_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["assigned_reports_count"], 3)
		self.assertEqual(response.context["pending_reviews_count"], 1)
		self.assertEqual(response.context["active_work_orders_count"], 1)
		self.assertEqual(response.context["resolved_work_orders_count"], 1)
		self.assertContains(response, "South B")
		self.assertNotContains(response, "Westlands")
		self.assertEqual(
			set(response.context["recent_work_orders"]),
			{active_order, resolved_order},
		)
		self.assertFalse(Report.objects.filter(pk=other_report.pk, organization=self.organization).exists())

	def test_manager_dashboards_show_useful_empty_states_and_require_manager_role(self):
		dashboard = self.client.get(reverse("manager_dashboard"))
		work_orders = self.client.get(reverse("manager_work_orders"))
		self.assertContains(dashboard, "No reports assigned yet")
		self.assertContains(dashboard, "No work orders yet")
		self.assertContains(work_orders, "No work orders assigned")

		self.client.force_login(self.resident)
		self.assertEqual(self.client.get(reverse("manager_dashboard")).status_code, 403)
		self.assertEqual(self.client.get(reverse("manager_work_orders")).status_code, 403)

	def test_manager_work_orders_are_organization_scoped_and_filterable(self):
		organization_engineer = get_user_model().objects.create_user(
			username="manager-work-engineer@example.com",
			role="engineer",
			organization=self.organization,
		)
		other_engineer = get_user_model().objects.create_user(
			username="manager-other-engineer@example.com",
			role="engineer",
			organization=self.other_organization,
		)
		own_report = self.create_report(self.organization, "South B")
		other_report = self.create_report(self.other_organization, "Westlands")
		own_order = MaintenanceWorkOrder.objects.create(
			report=own_report,
			engineer=organization_engineer,
			assigned_by=self.manager,
		)
		other_order = MaintenanceWorkOrder.objects.create(
			report=other_report,
			engineer=other_engineer,
			assigned_by=self.other_manager,
		)

		response = self.client.get(
			reverse("manager_work_orders"),
			{"search": "South B", "status": "assigned"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(list(response.context["work_orders"]), [own_order])
		self.assertContains(response, "South B")
		self.assertNotContains(response, "Westlands")
		self.assertFalse(
			MaintenanceWorkOrder.objects.filter(pk=other_order.pk, report__organization=self.organization).exists()
		)

	def test_manager_report_filters_work_together_and_pagination_preserves_them(self):
		target = self.create_report(self.organization, "South B")
		target.priority = "high"
		target.status = "under_review"
		target.save(update_fields=("priority", "status"))
		for index in range(11):
			self.create_report(self.organization, f"South B Road {index}")

		response = self.client.get(
			reverse("organization_report_queue"),
			{
				"search": "South B",
				"status": "under_review",
				"priority": "high",
				"county": "Nairobi City",
				"issue_type": "blocked_drain",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(list(response.context["reports"]), [target])
		self.assertContains(response, f"Report #{target.id}")
		self.assertNotContains(response, "South B Road 0")

		for index in range(11):
			report = self.create_report(self.organization, f"Filtered Road {index}")
			report.status = "under_review"
			report.priority = "high"
			report.save(update_fields=("status", "priority"))
		paged_response = self.client.get(
			reverse("organization_report_queue"),
			{
				"search": "Filtered Road",
				"status": "under_review",
				"priority": "high",
				"county": "Nairobi City",
				"issue_type": "blocked_drain",
			},
		)
		self.assertEqual(paged_response.context["page_obj"].paginator.count, 11)
		self.assertContains(paged_response, "Page 1 of 2")
		self.assertContains(paged_response, "status=under_review")
		self.assertContains(paged_response, "priority=high")

	def test_manager_can_view_full_details_for_their_organization_report(self):
		report = self.create_report(self.organization, "South B")
		report.location_description = "Near the bus stop"
		report.latitude = "-1.303200"
		report.longitude = "36.829100"
		report.description = "Water is not draining after rain."
		report.priority = "high"
		report.save()

		response = self.client.get(
			reverse("manager_report_detail", args=[report.id])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Near the bus stop")
		self.assertContains(response, "Water is not draining after rain.")
		self.assertContains(response, "-1.303200, 36.829100")
		self.assertContains(response, "Open map")
		self.assertContains(response, "High")
		self.assertContains(response, "Start review")

	def test_manager_cannot_view_another_organizations_report_details(self):
		report = self.create_report(self.other_organization, "Westlands")

		response = self.client.get(
			reverse("manager_report_detail", args=[report.id])
		)

		self.assertEqual(response.status_code, 404)

	def test_non_manager_cannot_view_manager_report_details(self):
		self.client.force_login(self.resident)
		report = self.create_report(self.organization, "South B")

		response = self.client.get(
			reverse("manager_report_detail", args=[report.id])
		)

		self.assertEqual(response.status_code, 403)

	def test_anonymous_user_cannot_access_manager_queue_or_report_details(self):
		report = self.create_report(self.organization, "South B")
		self.client.logout()

		for url in (
			reverse("organization_report_queue"),
			reverse("manager_report_detail", args=[report.id]),
		):
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertEqual(response.status_code, 302)
				self.assertIn(reverse("login"), response.url)

	def test_manager_can_set_priority_and_start_review(self):
		report = self.create_report(self.organization, "South B")

		response = self.client.post(
			reverse("organization_report_queue"),
			{"report_id": report.id, "priority": "high"},
		)

		self.assertRedirects(response, reverse("organization_report_queue"))
		report.refresh_from_db()
		self.assertEqual(report.priority, "high")
		self.assertEqual(report.status, "under_review")

	def test_manager_can_update_priority_without_reverting_review_status(self):
		report = self.create_report(self.organization, "South B")
		report.status = "under_review"
		report.save(update_fields=("status",))

		self.client.post(
			reverse("organization_report_queue"),
			{"report_id": report.id, "priority": "critical"},
		)

		report.refresh_from_db()
		self.assertEqual(report.priority, "critical")
		self.assertEqual(report.status, "under_review")

	def test_manager_cannot_update_another_organizations_report(self):
		report = self.create_report(self.other_organization, "Westlands")

		response = self.client.post(
			reverse("organization_report_queue"),
			{"report_id": report.id, "priority": "critical"},
		)

		self.assertEqual(response.status_code, 404)
		report.refresh_from_db()
		self.assertEqual(report.priority, "medium")
		self.assertEqual(report.status, "submitted")

	def test_invalid_priority_does_not_change_report(self):
		report = self.create_report(self.organization, "South B")

		response = self.client.post(
			reverse("organization_report_queue"),
			{"report_id": report.id, "priority": "urgent"},
		)

		self.assertRedirects(response, reverse("organization_report_queue"))
		report.refresh_from_db()
		self.assertEqual(report.priority, "medium")
		self.assertEqual(report.status, "submitted")

	def test_closed_maintenance_stages_cannot_be_retriaged(self):
		for status in ("assigned", "in_progress", "resolved", "closed"):
			with self.subTest(status=status):
				report = self.create_report(self.organization, f"Area {status}")
				report.status = status
				report.save(update_fields=("status",))

				response = self.client.post(
					reverse("organization_report_queue"),
					{"report_id": report.id, "priority": "critical"},
				)

				self.assertRedirects(response, reverse("organization_report_queue"))
				report.refresh_from_db()
				self.assertEqual(report.priority, "medium")
				self.assertEqual(report.status, status)

	def test_malformed_report_id_is_handled_without_server_error(self):
		response = self.client.post(
			reverse("organization_report_queue"),
			{"report_id": "not-a-number", "priority": "high"},
		)

		self.assertRedirects(response, reverse("organization_report_queue"))

	def test_non_manager_is_forbidden(self):
		self.client.force_login(self.resident)

		response = self.client.get(reverse("organization_report_queue"))

		self.assertEqual(response.status_code, 403)
		self.assertNotContains(
			response,
			"Ask a FlowTrack administrator",
			status_code=403,
		)

	def test_manager_without_organization_is_forbidden(self):
		user_model = get_user_model()
		manager = user_model.objects.create_user(
			username="unassigned-manager@example.com",
			email="unassigned-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
		)
		self.client.force_login(manager)

		response = self.client.get(reverse("organization_report_queue"))

		self.assertEqual(response.status_code, 403)
		self.assertContains(response, "Ask a FlowTrack administrator", status_code=403)

	def test_manager_of_inactive_organization_is_forbidden(self):
		self.other_organization.is_active = False
		self.other_organization.save(update_fields=("is_active",))
		self.client.force_login(self.other_manager)

		response = self.client.get(reverse("organization_report_queue"))

		self.assertEqual(response.status_code, 403)
		self.assertContains(response, "Ask a FlowTrack administrator", status_code=403)


class ReportAdminOrganizationAssignmentTests(TestCase):
	def setUp(self):
		self.organization = Organization.objects.create(
			name="Active Report Organization",
			organization_type="county",
			county="Nairobi City",
			is_active=True,
		)
		self.inactive_organization = Organization.objects.create(
			name="Inactive Report Organization",
			organization_type="county",
			county="Nairobi City",
			is_active=False,
		)
		self.reporter = get_user_model().objects.create_user(
			username="admin-form-resident@example.com",
			email="admin-form-resident@example.com",
			password="FlowTrack-test-123!",
		)
		self.report = Report.objects.create(
			reporter=self.reporter,
			issue_type="blocked_drain",
			county="Nairobi City",
			area="Central",
		)

	def test_report_admin_allows_assignment_to_active_organization(self):
		form = ReportAdminForm(
			{
				"reporter": self.reporter.pk,
				"organization": self.organization.pk,
				"issue_type": "blocked_drain",
				"county": "Nairobi City",
				"area": "Central",
				"location_description": "",
				"latitude": "",
				"longitude": "",
				"photo": "",
				"description": "",
				"status": "submitted",
				"priority": "medium",
			},
			instance=self.report,
		)

		self.assertTrue(form.is_valid(), form.errors)

	def test_report_admin_rejects_new_assignment_to_inactive_organization(self):
		form = ReportAdminForm(
			{
				"reporter": self.reporter.pk,
				"organization": self.inactive_organization.pk,
				"issue_type": "blocked_drain",
				"county": "Nairobi City",
				"area": "Central",
				"location_description": "",
				"latitude": "",
				"longitude": "",
				"photo": "",
				"description": "",
				"status": "submitted",
				"priority": "medium",
			},
			instance=self.report,
		)

		self.assertFalse(form.is_valid())
		self.assertIn("organization", form.errors)

	def test_existing_report_can_keep_its_deactivated_organization(self):
		self.report.organization = self.inactive_organization
		self.report.save(update_fields=("organization",))
		form = ReportAdminForm(instance=self.report)

		self.assertEqual(
			form.fields["organization"].clean(self.inactive_organization.pk),
			self.inactive_organization,
		)
