from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse


class UserAdminDeletionProtectionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="FlowTrack-test-123!",
        )
        self.user = get_user_model().objects.create_user(
            username="resident@example.com",
            email="resident@example.com",
            password="Resident-test-123!",
            first_name="Amina",
            last_name="Resident",
        )
        self.client.force_login(self.admin)

    def test_user_delete_page_is_forbidden_and_account_is_preserved(self):
        response = self.client.get(
            reverse("admin:accounts_user_delete", args=(self.user.pk,))
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_bulk_delete_action_is_unavailable_and_cannot_delete_users(self):
        changelist_url = reverse("admin:accounts_user_changelist")
        list_response = self.client.get(changelist_url)

        self.assertEqual(list_response.status_code, 200)
        self.assertNotContains(list_response, "delete_selected")

        response = self.client.post(
            changelist_url,
            {
                "action": "delete_selected",
                "select_across": "1",
                "_selected_action": [str(self.user.pk)],
            },
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_user_accounts_remain_viewable_and_editable_in_django_admin(self):
        change_url = reverse("admin:accounts_user_change", args=(self.user.pk,))

        response = self.client.get(change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.email)
        self.assertContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="password"')


class UserEmailConstraintTests(TestCase):
    def test_database_rejects_case_insensitive_duplicate_emails(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="first@example.com",
            email="First@example.com",
            password="First-test-123!",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user_model.objects.create_user(
                    username="second@example.com",
                    email="FIRST@EXAMPLE.COM",
                    password="Second-test-123!",
                )
