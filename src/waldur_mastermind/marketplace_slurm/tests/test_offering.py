from rest_framework import test, status

from waldur_core.structure.tests import factories as structure_factories
from waldur_core.structure.tests import fixtures as structure_fixtures
from waldur_mastermind.common.mixins import UnitPriceMixin
from waldur_mastermind.marketplace.tests import factories as marketplace_factories
from waldur_mastermind.marketplace_slurm import PLUGIN_NAME
from waldur_slurm.apps import SlurmConfig
from waldur_mastermind.slurm_invoices import models as slurm_invoices_models


class SlurmPackageTest(test.APITransactionTestCase):
    def test_create_slurm_package(self):
        fixture = structure_fixtures.ProjectFixture()
        url = marketplace_factories.OfferingFactory.get_list_url()
        self.client.force_authenticate(fixture.staff)
        service_settings = structure_factories.ServiceSettingsFactory(type=SlurmConfig.service_name)
        category = marketplace_factories.CategoryFactory()

        payload = {
            'name': 'offering',
            'type': PLUGIN_NAME,
            'scope': structure_factories.ServiceSettingsFactory.get_url(settings=service_settings),
            'category': marketplace_factories.CategoryFactory.get_url(category=category),
            'customer': structure_factories.CustomerFactory.get_url(customer=fixture.customer),
            'plans': [
                {
                    'name': 'default',
                    'description': 'default plan',
                    'unit': UnitPriceMixin.Units.QUANTITY,
                    'unit_price': 100,
                    'prices': {
                        'cpu': 10,
                        'gpu': 100,
                        'ram': 1000,
                    },
                }
            ]
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        package = slurm_invoices_models.SlurmPackage.objects.last()
        self.assertEqual(package.service_settings, service_settings)
        self.assertEqual(package.cpu_price, 10)
        self.assertEqual(package.gpu_price, 100)
        self.assertEqual(package.ram_price, 1000)
