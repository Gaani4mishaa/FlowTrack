from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
