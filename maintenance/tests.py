from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Organization
from reports.models import Report

from .models import MaintenanceWorkOrder


class MaintenanceWorkOrderWorkflowTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		user_model = get_user_model()
		cls.organization = Organization.objects.create(
			name="North Maintenance",
			organization_type="county",
			county="Nairobi City",
		)
		cls.other_organization = Organization.objects.create(
			name="West Maintenance",
			organization_type="county",
			county="Nairobi City",
		)
		cls.manager = user_model.objects.create_user(
			username="work-manager@example.com",
			email="work-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=cls.organization,
		)
		cls.other_manager = user_model.objects.create_user(
			username="other-work-manager@example.com",
			email="other-work-manager@example.com",
			password="FlowTrack-test-123!",
			role="manager",
			organization=cls.other_organization,
		)
		cls.engineer = user_model.objects.create_user(
			username="engineer@example.com",
			email="engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=cls.organization,
		)
		cls.peer_engineer = user_model.objects.create_user(
			username="peer-engineer@example.com",
			email="peer-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=cls.organization,
		)
		cls.other_engineer = user_model.objects.create_user(
			username="other-engineer@example.com",
			email="other-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=cls.other_organization,
		)
		cls.resident = user_model.objects.create_user(
			username="work-resident@example.com",
			email="work-resident@example.com",
			password="FlowTrack-test-123!",
			role="resident",
		)

	def setUp(self):
		self.client.force_login(self.manager)

	def create_report(self, area, organization=None, status="under_review"):
		return Report.objects.create(
			reporter=self.resident,
			organization=organization or self.organization,
			issue_type="blocked_drain",
			county="Nairobi City",
			area=area,
			status=status,
		)

	def create_work_order(self, report, engineer=None, status="assigned", notes=""):
		work_order = MaintenanceWorkOrder(
			report=report,
			engineer=engineer or self.engineer,
			assigned_by=(
				self.manager
				if report.organization_id == self.organization.id
				else self.other_manager
			),
			status=status,
			resolution_notes=notes,
		)
		work_order.full_clean()
		work_order.save()
		report.status = status
		report.save(update_fields=("status",))
		return work_order

	def test_manager_assigns_same_organization_engineer_and_report_advances(self):
		report = self.create_report("South B")

		response = self.client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.engineer.id},
		)

		self.assertRedirects(response, reverse("organization_report_queue"))
		work_order = MaintenanceWorkOrder.objects.get(report=report)
		self.assertEqual(work_order.engineer, self.engineer)
		self.assertEqual(work_order.assigned_by, self.manager)
		report.refresh_from_db()
		self.assertEqual(report.status, "assigned")

	def test_manager_assignment_picker_only_lists_active_engineers_in_their_organization(self):
		self.create_report("South B")
		inactive_engineer = get_user_model().objects.create_user(
			username="inactive-engineer@example.com",
			email="inactive-engineer@example.com",
			password="FlowTrack-test-123!",
			role="engineer",
			organization=self.organization,
			is_active=False,
		)
		self.client.force_login(self.manager)

		response = self.client.get(reverse("organization_report_queue"))

		self.assertContains(response, self.engineer.username)
		self.assertContains(response, self.peer_engineer.username)
		self.assertNotContains(response, self.other_engineer.username)
		self.assertNotContains(response, inactive_engineer.username)

	def test_manager_cannot_assign_an_engineer_from_another_organization(self):
		report = self.create_report("South B")

		response = self.client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.other_engineer.id},
		)

		self.assertRedirects(response, reverse("organization_report_queue"))
		self.assertFalse(MaintenanceWorkOrder.objects.filter(report=report).exists())
		report.refresh_from_db()
		self.assertEqual(report.status, "under_review")

	def test_manager_cannot_assign_report_outside_organization(self):
		report = self.create_report("Westlands", organization=self.other_organization)

		response = self.client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.engineer.id},
		)

		self.assertEqual(response.status_code, 404)
		self.assertFalse(MaintenanceWorkOrder.objects.filter(report=report).exists())

	def test_only_under_review_reports_can_be_assigned(self):
		report = self.create_report("South B", status="submitted")

		response = self.client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.engineer.id},
		)

		self.assertEqual(response.status_code, 404)
		self.assertFalse(MaintenanceWorkOrder.objects.filter(report=report).exists())

	def test_engineer_sees_only_work_orders_assigned_to_them(self):
		own_report = self.create_report("South B")
		peer_report = self.create_report("Kilburn")
		other_org_report = self.create_report("Westlands", organization=self.other_organization)
		own_order = self.create_work_order(own_report, self.engineer)
		peer_order = self.create_work_order(peer_report, self.peer_engineer)
		other_org_order = self.create_work_order(other_org_report, self.other_engineer)
		self.client.force_login(self.engineer)

		response = self.client.get(reverse("engineer_work_orders"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f"Report #{own_order.report_id}")
		self.assertNotContains(response, f"Report #{peer_order.report_id}")
		self.assertNotContains(response, f"Report #{other_org_order.report_id}")

	def test_engineer_dashboard_shows_all_status_counts_and_resolved_work(self):
		pending_report = self.create_report("Assigned Road")
		active_report = self.create_report("Active Road")
		resolved_report = self.create_report("Resolved Road")
		pending_order = self.create_work_order(pending_report, self.engineer)
		active_order = self.create_work_order(active_report, self.engineer, status="in_progress")
		resolved_order = self.create_work_order(
			resolved_report,
			self.engineer,
			status="resolved",
			notes="Cleared the blockage and checked water flow.",
		)
		self.client.force_login(self.engineer)

		response = self.client.get(reverse("engineer_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_count"], 3)
		self.assertEqual(response.context["assigned_count"], 1)
		self.assertEqual(response.context["in_progress_count"], 1)
		self.assertEqual(response.context["resolved_count"], 1)
		self.assertContains(response, f"Report #{resolved_order.report_id}")
		self.assertContains(response, "Cleared the blockage")
		self.assertContains(response, f"Report #{pending_order.report_id}")
		self.assertContains(response, f"Report #{active_order.report_id}")

	def test_engineer_dashboard_search_and_status_filter_are_combined(self):
		target_report = self.create_report("South B")
		target_order = self.create_work_order(target_report, self.engineer, status="in_progress")
		self.create_work_order(
			self.create_report("South B"),
			self.engineer,
			status="assigned",
		)
		self.client.force_login(self.engineer)

		response = self.client.get(
			reverse("engineer_work_orders"),
			{"search": "South B", "status": "in_progress"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["work_orders"], [target_order])
		self.assertContains(response, "South B")
		self.assertNotContains(response, "Assigned Road")

	def test_engineer_dashboard_has_an_empty_state_when_no_work_is_assigned(self):
		self.client.force_login(self.engineer)

		response = self.client.get(reverse("engineer_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["total_count"], 0)
		self.assertContains(response, "No work orders assigned")

	def test_engineer_can_open_full_details_for_their_work_order(self):
		report = self.create_report("South B")
		report.location_description = "Beside the market entrance"
		report.latitude = "-1.303200"
		report.longitude = "36.829100"
		report.description = "Drain is blocked after heavy rainfall."
		report.priority = "critical"
		report.save()
		work_order = self.create_work_order(report)
		self.client.force_login(self.engineer)

		response = self.client.get(
			reverse("engineer_work_order_detail", args=[work_order.id])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Beside the market entrance")
		self.assertContains(response, "Drain is blocked after heavy rainfall.")
		self.assertContains(response, "-1.303200, 36.829100")
		self.assertContains(response, "Critical")
		self.assertContains(response, "Start work")

	def test_engineer_cannot_open_another_engineers_work_order_details(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report, self.peer_engineer)
		self.client.force_login(self.engineer)

		response = self.client.get(
			reverse("engineer_work_order_detail", args=[work_order.id])
		)

		self.assertEqual(response.status_code, 404)

	def test_non_engineer_cannot_open_engineer_work_order_details(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		self.client.force_login(self.manager)

		response = self.client.get(
			reverse("engineer_work_order_detail", args=[work_order.id])
		)

		self.assertEqual(response.status_code, 403)

	def test_anonymous_user_cannot_access_engineer_queue_or_work_order_details(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		self.client.logout()

		for url in (
			reverse("engineer_work_orders"),
			reverse("engineer_work_order_detail", args=[work_order.id]),
		):
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertEqual(response.status_code, 302)
				self.assertIn(reverse("login"), response.url)

	def test_non_engineer_cannot_open_engineer_work_orders(self):
		self.client.force_login(self.manager)

		response = self.client.get(reverse("engineer_work_orders"))

		self.assertEqual(response.status_code, 403)

	def test_engineer_cannot_use_manager_assignment_action(self):
		report = self.create_report("South B")
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.engineer.id},
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(MaintenanceWorkOrder.objects.filter(report=report).exists())

	def test_manager_cannot_update_an_engineers_work_order(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		self.client.force_login(self.manager)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{"work_order_id": work_order.id, "status": "in_progress"},
		)

		self.assertEqual(response.status_code, 403)
		work_order.refresh_from_db()
		self.assertEqual(work_order.status, "assigned")

	def test_invalid_work_order_status_transition_is_rejected(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{
				"work_order_id": work_order.id,
				"status": "resolved",
				"resolution_notes": "Attempting to skip the in-progress step.",
			},
		)

		self.assertRedirects(response, reverse("engineer_work_orders"))
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "assigned")
		self.assertEqual(report.status, "assigned")
		self.assertIsNone(work_order.resolved_at)

	def test_work_order_post_actions_require_csrf(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		csrf_client = Client(enforce_csrf_checks=True)

		csrf_client.force_login(self.manager)
		assignment_response = csrf_client.post(
			reverse("assign_engineer", args=[report.id]),
			{"engineer": self.peer_engineer.id},
		)
		self.assertEqual(assignment_response.status_code, 403)
		self.assertEqual(MaintenanceWorkOrder.objects.filter(report=report).count(), 1)
		triage_report = self.create_report("CSRF review road", status="submitted")
		triage_response = csrf_client.post(
			reverse("organization_report_queue"),
			{"report_id": triage_report.id, "priority": "high"},
		)
		self.assertEqual(triage_response.status_code, 403)
		triage_report.refresh_from_db()
		self.assertEqual(triage_report.status, "submitted")
		self.assertEqual(triage_report.priority, "medium")

		csrf_client.force_login(self.engineer)
		update_response = csrf_client.post(
			reverse("engineer_work_orders"),
			{"work_order_id": work_order.id, "status": "in_progress"},
		)
		self.assertEqual(update_response.status_code, 403)
		work_order.refresh_from_db()
		self.assertEqual(work_order.status, "assigned")

		detail_update_response = csrf_client.post(
			reverse("engineer_work_order_detail", args=[work_order.id]),
			{"status": "in_progress", "resolution_notes": ""},
		)
		self.assertEqual(detail_update_response.status_code, 403)
		work_order.refresh_from_db()
		self.assertEqual(work_order.status, "assigned")

	def test_engineer_can_start_work_and_report_status_stays_in_sync(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report)
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{"work_order_id": work_order.id, "status": "in_progress", "resolution_notes": ""},
		)

		self.assertRedirects(response, reverse("engineer_work_orders"))
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "in_progress")
		self.assertIsNotNone(work_order.started_at)
		self.assertEqual(report.status, "in_progress")

	def test_engineer_must_provide_resolution_notes_to_complete_work(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report, status="in_progress")
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{"work_order_id": work_order.id, "status": "resolved", "resolution_notes": "  "},
		)

		self.assertRedirects(response, reverse("engineer_work_orders"))
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "in_progress")
		self.assertEqual(report.status, "in_progress")
		self.assertIsNone(work_order.resolved_at)

	def test_engineer_can_resolve_with_a_note_and_reporter_sees_it(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report, status="in_progress")
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{
				"work_order_id": work_order.id,
				"status": "resolved",
				"resolution_notes": "Removed debris and confirmed the drain is clear.",
			},
		)

		self.assertRedirects(response, reverse("engineer_work_orders"))
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "resolved")
		self.assertIsNotNone(work_order.resolved_at)
		self.assertEqual(report.status, "resolved")

		self.client.force_login(self.resident)
		detail = self.client.get(reverse("report_detail", args=[report.id]))
		self.assertContains(detail, "Removed debris and confirmed the drain is clear.")

	def test_engineer_can_update_progress_from_work_order_detail(self):
		report = self.create_report("Detail Action Road")
		work_order = self.create_work_order(report)
		self.client.force_login(self.engineer)

		start_response = self.client.post(
			reverse("engineer_work_order_detail", args=[work_order.id]),
			{"status": "in_progress", "resolution_notes": ""},
		)

		self.assertRedirects(
			start_response,
			reverse("engineer_work_order_detail", args=[work_order.id]),
		)
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "in_progress")
		self.assertEqual(report.status, "in_progress")

		resolve_response = self.client.post(
			reverse("engineer_work_order_detail", args=[work_order.id]),
			{
				"status": "resolved",
				"resolution_notes": "Removed the obstruction and verified that water drains normally.",
			},
		)
		self.assertRedirects(
			resolve_response,
			reverse("engineer_work_order_detail", args=[work_order.id]),
		)
		work_order.refresh_from_db()
		report.refresh_from_db()
		self.assertEqual(work_order.status, "resolved")
		self.assertEqual(report.status, "resolved")
		self.assertEqual(
			work_order.resolution_notes,
			"Removed the obstruction and verified that water drains normally.",
		)
		self.client.force_login(self.resident)
		resident_detail = self.client.get(reverse("report_detail", args=[report.id]))
		self.assertContains(resident_detail, "verified that water drains normally")

	def test_engineer_cannot_update_a_work_order_assigned_to_another_engineer(self):
		report = self.create_report("South B")
		work_order = self.create_work_order(report, self.peer_engineer)
		self.client.force_login(self.engineer)

		response = self.client.post(
			reverse("engineer_work_orders"),
			{"work_order_id": work_order.id, "status": "in_progress", "resolution_notes": ""},
		)

		self.assertEqual(response.status_code, 404)
		work_order.refresh_from_db()
		self.assertEqual(work_order.status, "assigned")
