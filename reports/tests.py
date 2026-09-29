from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
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
		return Report.objects.create(
			reporter=reporter or self.resident,
			issue_type="blocked_drain",
			county="Nairobi City",
			area="South B",
			**overrides,
		)

	def test_resident_can_create_a_valid_report(self):
		response = self.client.post(reverse("report_issue"), self.report_data())

		report = Report.objects.get()
		self.assertRedirects(response, reverse("report_detail", args=[report.id]))
		self.assertEqual(report.reporter, self.resident)
		self.assertEqual(str(report.latitude), "-1.303200")
		self.assertEqual(str(report.longitude), "36.829100")

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
