from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

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
