from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization


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
	def test_manager_sign_in_redirects_to_organization_queue(self):
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

		self.assertRedirects(response, reverse("organization_report_queue"))
