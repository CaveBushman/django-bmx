"""Unit tests for bmx.storage.RobustManifestStorage (previously 0% covered)."""
import re
from unittest.mock import patch

from django.test import TestCase

from bmx.storage import RobustManifestStorage


class RobustManifestStorageTests(TestCase):
    def setUp(self):
        self.storage = RobustManifestStorage()

    def test_manifest_not_strict(self):
        self.assertFalse(self.storage.manifest_strict)

    def test_stored_name_returns_hashed_when_available(self):
        with patch(
            "bmx.storage.CompressedManifestStaticFilesStorage.stored_name",
            return_value="css/app.abc123.css",
        ):
            self.assertEqual(self.storage.stored_name("css/app.css"), "css/app.abc123.css")

    def test_stored_name_falls_back_on_value_error(self):
        with patch(
            "bmx.storage.CompressedManifestStaticFilesStorage.stored_name",
            side_effect=ValueError("missing from manifest"),
        ):
            self.assertEqual(self.storage.stored_name("missing.png"), "missing.png")

    def test_url_converter_returns_converted_when_ok(self):
        def parent_converter(name, hashed_files, template=None):
            return lambda m: "converted-url"

        with patch(
            "bmx.storage.CompressedManifestStaticFilesStorage.url_converter",
            side_effect=parent_converter,
        ):
            converter = self.storage.url_converter("app.css", {})
            match = re.match(r".*", "anything")
            self.assertEqual(converter(match), "converted-url")

    def test_url_converter_falls_back_to_original_on_error(self):
        def boom(matchobj):
            raise Exception("MissingFileError")

        def parent_converter(name, hashed_files, template=None):
            return boom

        with patch(
            "bmx.storage.CompressedManifestStaticFilesStorage.url_converter",
            side_effect=parent_converter,
        ):
            converter = self.storage.url_converter("app.css", {})
            match = re.match(r"url\(([^)]+)\)", "url(missing.map)")
            self.assertEqual(converter(match), "url(missing.map)")
