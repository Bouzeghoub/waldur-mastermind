from __future__ import unicode_literals, division

import datetime
import decimal
import itertools
import logging
from calendar import monthrange

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.lru_cache import lru_cache
from django.utils.translation import ugettext_lazy as _
from model_utils import FieldTracker

from waldur_core.core.fields import JSONField
from waldur_core.core import models as core_models, utils as core_utils
from waldur_core.core.exceptions import IncorrectStateException
from waldur_core.structure import models as structure_models

from waldur_mastermind.common import mixins as common_mixins
from waldur_mastermind.packages import models as package_models
from waldur_mastermind.support import models as support_models

from . import managers, utils, registrators


logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class Invoice(core_models.UuidMixin, models.Model):
    """ Invoice describes billing information about purchased packages for customers on a monthly basis """

    class Permissions(object):
        customer_path = 'customer'

    class Meta(object):
        unique_together = ('customer', 'month', 'year')

    class States(object):
        PENDING = 'pending'
        CREATED = 'created'
        PAID = 'paid'
        CANCELED = 'canceled'

        CHOICES = ((PENDING, _('Pending')), (CREATED, _('Created')), (PAID, _('Paid')), (CANCELED, _('Canceled')))

    month = models.PositiveSmallIntegerField(default=utils.get_current_month,
                                             validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveSmallIntegerField(default=utils.get_current_year)
    state = models.CharField(max_length=30, choices=States.CHOICES, default=States.PENDING)
    customer = models.ForeignKey(structure_models.Customer,
                                 verbose_name=_('organization'),
                                 related_name='+',
                                 on_delete=models.CASCADE)
    current_cost = models.DecimalField(default=0, max_digits=10, decimal_places=2,
                                       help_text=_('Cached value for current cost.'),
                                       editable=False)
    tax_percent = models.DecimalField(default=0, max_digits=4, decimal_places=2,
                                      validators=[MinValueValidator(0), MaxValueValidator(100)])
    invoice_date = models.DateField(null=True, blank=True,
                                    help_text=_('Date then invoice moved from state pending to created.'))

    tracker = FieldTracker()

    def update_current_cost(self):
        self.current_cost = self.total_current
        self.save(update_fields=['current_cost'])

    @property
    def tax(self):
        return self.price * self.tax_percent / 100

    @property
    def total(self):
        return self.price + self.tax

    @property
    def price(self):
        return sum((item.price for item in self.items))

    @property
    def tax_current(self):
        return self.price_current * self.tax_percent / 100

    @property
    def total_current(self):
        return self.price_current + self.tax_current

    @property
    def price_current(self):
        return sum((item.price_current for item in self.items))

    @property
    def items(self):
        return itertools.chain(self.openstack_items.all(),
                               self.offering_items.all(),
                               self.generic_items.all())

    @property
    def due_date(self):
        if self.invoice_date:
            return self.invoice_date + datetime.timedelta(days=settings.WALDUR_INVOICES['PAYMENT_INTERVAL'])

    @property
    def number(self):
        return 100000 + self.id

    def set_created(self):
        """
        Performs following actions:
            - Freeze all invoice items
            - Change state from pending to billed
        """
        if self.state != self.States.PENDING:
            raise IncorrectStateException(_('Invoice must be in pending state.'))

        self.state = self.States.CREATED
        self.invoice_date = timezone.now().date()
        self.save(update_fields=['state', 'invoice_date'])

    def freeze(self):
        for item in self.items:
            item.freeze()

    def register_offering(self, offering, start=None):
        if start is None:
            start = timezone.now()

        end = core_utils.month_end(start)
        OfferingItem.objects.create(
            offering=offering,
            unit_price=offering.unit_price,
            unit=offering.unit,
            invoice=self,
            start=start,
            end=end,
        )

    def __str__(self):
        return '%s | %s-%s' % (self.customer, self.year, self.month)


@python_2_unicode_compatible
class InvoiceItem(common_mixins.ProductCodeMixin, common_mixins.UnitPriceMixin):
    """
    Mixin which identifies invoice item to be used for price calculation.
    """

    class Meta(object):
        abstract = True

    start = models.DateTimeField(default=utils.get_current_month_start,
                                 help_text=_('Date and time when item usage has started.'))
    end = models.DateTimeField(default=utils.get_current_month_end,
                               help_text=_('Date and time when item usage has ended.'))

    # Project name and UUID should be stored separately because project is not available after removal
    project = models.ForeignKey(structure_models.Project, on_delete=models.SET_NULL, null=True)
    project_name = models.CharField(max_length=150, blank=True)
    project_uuid = models.CharField(max_length=32, blank=True)

    @classmethod
    @lru_cache(maxsize=1)
    def get_all_models(cls):
        return [model for model in apps.get_models() if issubclass(model, cls)]

    @property
    def tax(self):
        return self.price * self.invoice.tax_percent / 100

    @property
    def total(self):
        return self.price + self.tax

    def _price(self, current=False):
        return self.unit_price * decimal.Decimal(self.get_factor(current))

    def get_factor(self, current=False):
        month_days = monthrange(self.start.year, self.start.month)[1]

        if self.unit == self.Units.QUANTITY:
            return self.quantity
        elif self.unit == self.Units.PER_DAY:
            if current:
                return utils.get_full_days(self.start, timezone.now())
            else:
                return self.usage_days
        elif self.unit == self.Units.PER_HALF_MONTH:
            if (self.start.day == 1 and self.end.day == 15) or (self.start.day == 16 and self.end.day == month_days):
                return 1
            elif (self.start.day == 1 and self.end.day == month_days):
                return 2
            elif (self.start.day == 1 and self.end.day > 15):
                return 1 + (self.end.day - 15) / (month_days / 2)
            elif (self.start.day < 16 and self.end.day == month_days):
                return 1 + (16 - self.start.day) / (month_days / 2)
            else:
                return (self.end.day - self.start.day + 1) / (month_days / 2)
        # By default PER_MONTH
        else:
            if self.start.day == 1 and self.end.day == month_days:
                return 1

            use_days = (self.end - self.start).days + 1
            return use_days / month_days

    @property
    def price(self):
        return self._price()

    @property
    def price_current(self):
        return self._price(current=True)

    @property
    def usage_days(self):
        """
        Returns the number of days package was used from the time
        it was purchased or from the start of current month
        """
        full_days = utils.get_full_days(self.start, self.end)
        return full_days

    def terminate(self, end=None):
        self.freeze()
        self.end = end or timezone.now()
        self.save(update_fields=['end'])

    def name(self):
        raise NotImplementedError()

    def freeze(self):
        raise NotImplementedError()

    def __str__(self):
        return self.name

    def create_compensation(self, name, **kwargs):
        FIELDS = (
            'invoice',
            'project',
            'project_name',
            'project_uuid',
            'product_code',
            'article_code',
            'unit',
            'unit_price',
            'start',
            'end',
        )

        params = {field: getattr(self, field) for field in FIELDS}
        params.update(kwargs)
        if params['unit_price'] > 0:
            params['unit_price'] *= -1
        params['details'] = {
            'name': _('Compensation for downtime. Resource name: %s') % name
        }

        return GenericInvoiceItem.objects.create(**params)


class GenericInvoiceItem(InvoiceItem):
    """
    It is expected that get_scope_type method is defined as class method in scope class
    as it is used in generic invoice item serializer.
    """
    invoice = models.ForeignKey(Invoice, related_name='generic_items')
    content_type = models.ForeignKey(ContentType, null=True, related_name='+')
    object_id = models.PositiveIntegerField(null=True)
    quantity = models.PositiveIntegerField(default=0)

    scope = GenericForeignKey('content_type', 'object_id')
    details = JSONField(default=dict, blank=True, help_text=_('Stores data about scope'))

    objects = managers.GenericInvoiceItemManager()
    tracker = FieldTracker()

    @property
    def name(self):
        if self.details:
            return self.details['name']
        if self.scope:
            return registrators.RegistrationManager.get_name(self.scope)

    def freeze(self):
        if self.scope:
            self.details = registrators.RegistrationManager.get_details(self.scope)
            self.details['name'] = registrators.RegistrationManager.get_name(self.scope)
            self.details['scope_uuid'] = self.scope.uuid.hex
            self.save(update_fields=['details'])


class OfferingItem(InvoiceItem):
    """ OfferingItem stores details for invoices about purchased custom offering item. """
    invoice = models.ForeignKey(Invoice, related_name='offering_items')
    offering = models.ForeignKey(support_models.Offering, on_delete=models.SET_NULL, null=True, related_name='+')
    offering_details = JSONField(default=dict, blank=True, help_text=_('Stores data about offering'))
    tracker = FieldTracker()

    @property
    def name(self):
        if self.offering_details:
            name = self.offering_details.get('offering_name', self.project_name)
            return '%s (%s)' % (name, self.offering_details['offering_type'])

        return '%s (%s)' % (self.offering.name, self.offering.type)

    def freeze(self):
        """
        Saves offering type and offering name in "offering_details" if offering exists
        """
        if self.offering:
            self.offering_details['offering_type'] = self.offering.type
            self.offering_details['offering_name'] = self.offering.name
            self.offering_details['offering_uuid'] = self.offering.uuid.hex
            self.offering = None
            self.save(update_fields=['offering_details', 'offering'])

    def get_offering_uuid(self):
        if self.offering:
            return self.offering.uuid.hex
        else:
            return self.offering_details.get('offering_uuid')

    def get_offering_type(self):
        if self.offering:
            return self.offering.type
        else:
            return self.offering_details.get('offering_type')


class OpenStackItem(InvoiceItem):
    """ OpenStackItem stores details for invoices about purchased OpenStack packages """

    invoice = models.ForeignKey(Invoice, related_name='openstack_items')

    package = models.ForeignKey(package_models.OpenStackPackage, on_delete=models.SET_NULL, null=True, related_name='+')
    package_details = JSONField(default=dict, blank=True, help_text=_('Stores data about package'))
    tracker = FieldTracker()

    @property
    def name(self):
        template_category = self.get_template_category()
        if template_category:
            return '%s (%s / %s)' % (self.get_tenant_name(), template_category, self.get_template_name())
        else:
            return '%s (%s)' % (self.get_tenant_name(), self.get_template_name())

    def freeze(self):
        """
        Saves tenant and package template names and uuids in "package_details" if package exists
        """
        if self.package:
            self.package_details['tenant_name'] = self.package.tenant.name
            self.package_details['tenant_uuid'] = self.package.tenant.uuid.hex
            self.package_details['template_name'] = self.package.template.name
            self.package_details['template_uuid'] = self.package.template.uuid.hex
            self.package_details['template_category'] = self.package.template.category
            self.package = None
            self.save(update_fields=['package', 'package_details'])

    def shift_backward(self, days=1):
        """
        Shifts end date to N 'days' ago.
        If N is larger than it lasts - zero length will be set.
        :param days: number of days to shift end date
        """
        if (self.end - self.start).days > days:
            end = self.end - timezone.timedelta(days=1)
        else:
            end = self.start

        self.end = end
        self.save()

    def extend_to_the_end_of_the_day(self):
        self.end = self.end.replace(hour=23, minute=59, second=59)
        self.save()

    def get_tenant_name(self):
        if self.package:
            return self.package.tenant.name
        else:
            return self.package_details.get('tenant_name')

    def get_tenant_uuid(self):
        if self.package:
            return self.package.tenant.uuid.hex
        else:
            return self.package_details.get('tenant_uuid')

    def get_template_name(self):
        if self.package:
            return self.package.template.name
        else:
            return self.package_details.get('template_name')

    def get_template_uuid(self):
        if self.package:
            return self.package.template.uuid.hex
        else:
            return self.package_details.get('template_uuid')

    def get_template_category(self):
        if self.package:
            return self.package.template.get_category_display()
        else:
            template_category = self.package_details.get('template_category')
            if template_category:
                categories = dict(package_models.PackageTemplate.Categories.CHOICES)
                template_category = categories[template_category]

            return template_category


def get_default_downtime_start():
    return timezone.now() - settings.WALDUR_INVOICES['DOWNTIME_DURATION_MINIMAL']


class ServiceDowntime(models.Model):
    """
    Currently this model is restricted to OpenStack package only.
    It is expected that implementation would be generalized to support other resources as well.
    """
    start = models.DateTimeField(
        default=get_default_downtime_start,
        help_text=_('Date and time when downtime has started.')
    )
    end = models.DateTimeField(
        default=timezone.now,
        help_text=_('Date and time when downtime has ended.')
    )
    package = models.ForeignKey(package_models.OpenStackPackage)

    def clean(self):
        self._validate_duration()
        self._validate_offset()
        self._validate_intersection()

    def _validate_duration(self):
        duration = self.end - self.start

        duration_min = settings.WALDUR_INVOICES['DOWNTIME_DURATION_MINIMAL']
        if duration_min is not None and duration < duration_min:
            raise ValidationError(
                _('Downtime duration is too small. Minimal duration is %s') % duration_min
            )

        duration_max = settings.WALDUR_INVOICES['DOWNTIME_DURATION_MAXIMAL']
        if duration_max is not None and duration > duration_max:
            raise ValidationError(
                _('Downtime duration is too big. Maximal duration is %s') % duration_max
            )

    def _validate_offset(self):
        if self.start > timezone.now() or self.end > timezone.now():
            raise ValidationError(
                _('Future downtime is not supported yet. '
                  'Please select date in the past instead.')
            )

    def get_intersection_subquery(self):
        left = Q(start__gte=self.start, start__lte=self.end)
        right = Q(end__gte=self.start, end__lte=self.end)
        inside = Q(start__gte=self.start, end__lte=self.end)
        outside = Q(start__lte=self.start, end__gte=self.end)
        return Q(left | right | inside | outside)

    def _validate_intersection(self):
        qs = ServiceDowntime.objects.filter(self.get_intersection_subquery(), package=self.package)
        if qs.exists():
            ids = ', '.join(str(item.id) for item in qs)
            raise ValidationError(
                _('Downtime period intersects with another period with ID: %s.') % ids
            )
