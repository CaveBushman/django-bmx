from django.test import SimpleTestCase

from event.utils import is_valid_uci_id


class IsValidUciIdTests(SimpleTestCase):
    def test_accepts_eleven_ascii_digits(self):
        self.assertTrue(is_valid_uci_id("10012345678"))

    def test_rejects_wrong_length(self):
        self.assertFalse(is_valid_uci_id("1001234567"))
        self.assertFalse(is_valid_uci_id("100123456789"))
        self.assertFalse(is_valid_uci_id(""))

    def test_rejects_non_ascii_digits(self):
        self.assertFalse(is_valid_uci_id("1001234567²"))
        self.assertFalse(is_valid_uci_id("١٠٠١٢٣٤٥٦٧٨"))

    def test_rejects_letters(self):
        self.assertFalse(is_valid_uci_id("CZE19990101"))
