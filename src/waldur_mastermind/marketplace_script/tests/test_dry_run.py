from unittest import mock

from ddt import data, ddt
from rest_framework import test

from waldur_core.permissions.enums import PermissionEnum
from waldur_core.permissions.fixtures import CustomerRole
from waldur_mastermind.marketplace import models as marketplace_models
from waldur_mastermind.marketplace.tests import factories as marketplace_factories
from waldur_mastermind.marketplace_script import models as marketplace_script_models
from waldur_mastermind.marketplace_script import tasks as marketplace_script_tasks

from . import fixtures


@ddt
@mock.patch("waldur_mastermind.marketplace_script.utils.execute_script")
class DryRunTest(test.APITransactionTestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.ScriptFixture()
        self.offering = self.fixture.offering
        self.offering.options.update({"option1": []})
        self.offering.project = self.fixture.offering_project
        self.offering.customer = self.fixture.offering_customer
        self.offering.state = marketplace_models.Offering.States.ACTIVE
        self.offering.save()
        self.url = self.fixture.get_dry_run_url(self.offering)
        self.async_url = self.fixture.get_async_dry_run_url(self.offering)

        CustomerRole.OWNER.add_permission(PermissionEnum.DRY_RUN_OFFERING_SCRIPT)
        CustomerRole.MANAGER.add_permission(PermissionEnum.DRY_RUN_OFFERING_SCRIPT)

    @data("staff", "offering_owner", "service_manager")
    def test_dry_run_is_allowed(self, user, execute_script):
        output = self.offering.secret_options["create"]
        execute_script.return_value = output
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        data = {
            "plan": marketplace_factories.PlanFactory.get_url(self.fixture.plan),
            "type": "Create",
            "attributes": {"option1": "value1"},
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual({"output": output}, response.json())

    @data("owner", "admin", "manager", "member")
    def test_dry_run_is_forbidden(self, user, execute_script):
        output = self.offering.secret_options["create"]
        execute_script.return_value = output
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        data = {
            "plan": marketplace_factories.PlanFactory.get_url(self.fixture.plan),
            "type": "Create",
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(403, response.status_code)

    def test_pull_dry_run(self, execute_script):
        output = self.offering.secret_options["pull"]
        execute_script.return_value = output
        user = self.fixture.staff
        self.client.force_authenticate(user)
        data = {
            "plan": marketplace_factories.PlanFactory.get_url(self.fixture.plan),
            "type": "Pull",
            "attributes": {"option1": "value1"},
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(200, response.status_code)
        self.assertEqual({"output": output}, response.json())

    def test_async_dry_run(self, execute_script):
        output = self.offering.secret_options["create"]
        execute_script.return_value = output
        user = getattr(self.fixture, "staff")
        self.client.force_authenticate(user)
        data = {
            "plan": marketplace_factories.PlanFactory.get_url(self.fixture.plan),
            "type": "Create",
            "attributes": {"option1": "value1"},
        }
        response = self.client.post(self.async_url, data=data)
        self.assertEqual(202, response.status_code)
        self.assertTrue(
            marketplace_script_models.DryRun.objects.filter(
                uuid=response.data["uuid"]
            ).exists()
        )

        # test a task
        dry_run = marketplace_script_models.DryRun.objects.get(
            uuid=response.data["uuid"]
        )
        self.assertTrue(dry_run.order)
        marketplace_script_tasks.dry_run_executor(dry_run.id)
        dry_run.refresh_from_db()
        self.assertEqual(dry_run.output, output)
        self.assertFalse(dry_run.order)
