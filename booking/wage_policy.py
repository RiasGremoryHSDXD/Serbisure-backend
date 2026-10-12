"""One policy for posting, negotiation and acceptance; amounts have explicit periods."""
import re
from decimal import Decimal, InvalidOperation
from django.conf import settings
from rest_framework.exceptions import ValidationError

MONTHLY_POLICIES = {
    'REGION_X': (Decimal('6500.00'), 'RBX-DW-06'),
    'NCR': (Decimal('7800.00'), 'NCR-DW-06'),
}
DOLE_CONTRACT_PDF_URL = 'https://nwpc.dole.gov.ph/wp-content/uploads/2023/04/Sample_Contract-Kasambahay.pdf'


def rate_period_for(booking_type):
    if booking_type not in ('short_term', 'long_term'):
        raise ValidationError({'booking_type': 'Choose short_term or long_term.'})
    return 'month' if booking_type == 'long_term' else 'day'


def resolve_region(region='', address=''):
    text = str(region or address or '').strip().lower()
    if re.search(r'\bncr\b|metro manila|national capital|\bmanila\b|quezon city|makati|taguig|pasig', text):
        return 'NCR'
    if re.search(r'region\s*(x\b|10\b)|northern mindanao|cagayan de oro|\bcdo\b|misamis|bukidnon|camiguin|lanao del norte|iligan|\b9000\b', text):
        return 'REGION_X'
    raise ValidationError({'region': 'Wage policy is currently supported for Region X and NCR. Select a supported work region.'})


def get_minimum_wage_info(booking_type, address_or_zip='', region=''):
    period = rate_period_for(booking_type)
    if period == 'day':
        minimum = Decimal(str(getattr(settings, 'SERBISURE_SHORT_TERM_MIN_RATE', '600.00')))
        return {'booking_type': booking_type, 'rate_period': period, 'minimum_rate': str(minimum),
                'min_daily_rate': str(minimum), 'min_monthly_rate': None,
                'is_statutory_mandatory': False, 'wage_order': None, 'law': None,
                'description': f'SerbiSure platform minimum: PHP {minimum:,.2f}/day. Selecting short-term does not establish a legal exemption.'}
    key = resolve_region(region, address_or_zip)
    minimum, order = MONTHLY_POLICIES[key]
    return {'booking_type': booking_type, 'rate_period': period, 'minimum_rate': str(minimum),
            'min_daily_rate': None, 'min_monthly_rate': str(minimum),
            'is_statutory_mandatory': True, 'wage_order': order,
            'law': 'Republic Act No. 10361',
            'description': f'Domestic-worker minimum: PHP {minimum:,.2f}/month under {order}.'}


def validate_rate(amount, booking_type, region='', address='', field='rate_amount', period=None):
    expected = rate_period_for(booking_type)
    if period is not None and period != expected:
        raise ValidationError({'rate_period': f'{booking_type} compensation must be per {expected}.'})
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0 or value > Decimal('999999.99'):
            raise InvalidOperation
        if value != value.quantize(Decimal('0.01')):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Enter a positive amount up to PHP 999,999.99 with at most two decimal places.'})
    policy = get_minimum_wage_info(booking_type, address, region)
    if value < Decimal(policy['minimum_rate']):
        raise ValidationError({field: f"Minimum compensation is PHP {Decimal(policy['minimum_rate']):,.2f}/{expected}. {policy['description']}"})
    return value

