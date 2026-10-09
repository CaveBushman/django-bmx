"""Unit tests for accounts.forms.SignUpForm (previously 0% covered)."""
from django.test import TestCase

from accounts.forms import SignUpForm
from accounts.models import Account


class SignUpFormTests(TestCase):
    def _payload(self, **overrides):
        data = {
            "username": "newuser",
            "first_name": "New",
            "last_name": "User",
            "email": "new@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        data.update(overrides)
        return data

    def test_valid_form_saves_account(self):
        form = SignUpForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.username, "newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(Account.objects.filter(username="newuser").exists())

    def test_email_is_required(self):
        form = SignUpForm(data=self._payload(email=""))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_first_and_last_name_required(self):
        form = SignUpForm(data=self._payload(first_name="", last_name=""))
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)
        self.assertIn("last_name", form.errors)

    def test_password_mismatch_rejected(self):
        form = SignUpForm(data=self._payload(password2="Different123!"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_declared_fields_present(self):
        form = SignUpForm()
        for field in ("username", "first_name", "last_name", "email"):
            self.assertIn(field, form.fields)
