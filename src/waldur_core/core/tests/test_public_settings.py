from unittest import mock

from django.test import TestCase

from waldur_core.core import views


class TestPublicSettings(TestCase):
    def setUp(self):
        super().setUp()

        class MockExtension:
            def __init__(self, name):
                class Settings:
                    def __init__(self, name):
                        setattr(self, name, {})

                self.Settings = Settings(name)

            @staticmethod
            def get_public_settings():
                return ["INFO"]

            @staticmethod
            def get_dynamic_settings():
                return {"DYN": "dynamic"}

        extensions = {
            "WALDUR_CORE": {},
            "WALDUR_AUTH_SOCIAL": {},
            "WALDUR_FREEIPA": {},
            "WALDUR_KEYCLOAK": {},
            "WALDUR_HPC": {},
            "WALDUR_SLURM": {},
            "WALDUR_PID": {},
            "WALDUR_AUTH_SAML2": {},
            "WALDUR_MARKETPLACE": {},
            "WALDUR_OPENSTACK": {},
            "WALDUR_OPENSTACK_TENANT": {},
            "WALDUR_EXTENSION_1": {"ENABLED": False},
            "WALDUR_EXTENSION_2": {"ENABLED": True},
            "WALDUR_EXTENSION_3": {"SECRET": "secret", "INFO": "info"},
            "LANGUAGE_CODE": "en",
            "LANGUAGES": (("en", "English"), ("et", "Eesti")),
            "LANGUAGE_CHOICES": ["en"],
        }
        mock_settings = mock.Mock(**extensions)
        self.patcher_settings = mock.patch(
            "waldur_core.core.views.settings", new=mock_settings
        )
        self.patcher_settings.start()

        self.patcher = mock.patch("waldur_core.core.views.WaldurExtension")
        self.mock = self.patcher.start()
        self.mock.get_extensions.return_value = [
            MockExtension(e) for e in extensions.keys()
        ]

    def tearDown(self):
        super().tearDown()
        mock.patch.stopall()

    def test_if_extension_not_have_field_enabled_or_it_equally_true_this_extension_must_by_in_response(
        self,
    ):
        response = views.get_public_settings()
        self.assertTrue("WALDUR_EXTENSION_2" in response.keys())
        self.assertTrue("WALDUR_EXTENSION_3" in response.keys())

    def test_if_extension_have_field_enabled_and_it_equally_false_this_extension_not_to_be_in_response(
        self,
    ):
        response = views.get_public_settings()
        self.assertFalse("WALDUR_EXTENSION_1" in response.keys())

    def test_if_field_in_get_public_settings_it_value_must_by_in_response(self):
        response = views.get_public_settings()
        self.assertTrue("INFO" in response["WALDUR_EXTENSION_3"])
        self.assertTrue("DYN" in response["WALDUR_EXTENSION_3"])

    def test_if_field_not_in_get_public_settings_it_value_not_to_be_in_response(self):
        response = views.get_public_settings()
        self.assertFalse("SECRET" in response["WALDUR_EXTENSION_3"])
