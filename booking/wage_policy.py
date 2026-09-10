import re
from decimal import Decimal

# DOLE RTWPB Statutory Minimum Wages for Kasambahay (Domestic Workers)
# Region X (Northern Mindanao / Cagayan de Oro): Wage Order RBX-DW-06 (₱6,500/month)
# NCR (National Capital Region / Metro Manila): Wage Order NCR-DW-06 (₱7,800/month)
# Formula: Monthly Minimum / 26 standard working days (6 days/week under Batas Kasambahay RA 10361)

REGIONAL_MIN_WAGE_DAILY = {
    'REGION_X': Decimal('250.00'),  # ₱6,500 / 26 = ₱250.00/day
    'NCR': Decimal('300.00'),       # ₱7,800 / 26 = ₱300.00/day
}

# Standard default statutory floor across Philippine provinces
DEFAULT_MIN_WAGE_DAILY = Decimal('250.00')

# Short-term services (occasional, incidental, task-based) are exempt under Section 4(d) of RA 10361
SHORT_TERM_MIN_RATE = Decimal('1.00')

# Regex patterns using word boundaries for short tokens to prevent false positives
# e.g., 'McDonalds' must NOT match 'cdo', 'Bancroft' must NOT match 'ncr', '09179000123' must NOT match '9000'
REGION_10_PATTERNS = [
    r'\bcdo\b', r'\b9000\b', r'\bregion x\b', r'\bregion 10\b',
    r'cagayan de oro', r'misamis', r'bukidnon', r'camiguin',
    r'lanao del norte', r'iligan', r'el salvador', r'gingoog',
    r'malaybalay', r'valencia', r'northern mindanao'
]

NCR_PATTERNS = [
    r'\bncr\b', r'metro manila', r'national capital region',
    r'manila', r'quezon city', r'makati', r'taguig', r'pasig',
    r'mandaluyong', r'marikina', r'pasay', r'parañaque', r'paranaque',
    r'las piñas', r'las pinas', r'muntinlupa', r'caloocan',
    r'malabon', r'navotas', r'valenzuela', r'san juan', r'pateros'
]


def get_minimum_daily_wage(booking_type: str, address_or_zip: str = '') -> Decimal:
    """
    Returns the statutory minimum daily rate for domestic workers.
    - If booking_type is 'long_term': Enforces RTWPB Batas Kasambahay statutory wage floor.
    - If booking_type is 'short_term': Exempt under RA 10361 Sec 4(d); returns standard baseline (₱1.00).
    """
    b_type = str(booking_type or '').strip().lower()
    if b_type != 'long_term':
        return SHORT_TERM_MIN_RATE

    addr = str(address_or_zip or '').lower()

    # Region X (Northern Mindanao / Cagayan de Oro)
    if any(re.search(p, addr) for p in REGION_10_PATTERNS):
        return REGIONAL_MIN_WAGE_DAILY['REGION_X']

    # NCR / Metro Manila
    if any(re.search(p, addr) for p in NCR_PATTERNS):
        return REGIONAL_MIN_WAGE_DAILY['NCR']

    return DEFAULT_MIN_WAGE_DAILY


def get_monthly_equivalent(daily_rate: Decimal) -> Decimal:
    """
    Computes approximate monthly salary based on 26 working days
    (1 mandatory rest day per week under Section 21 of Batas Kasambahay).
    """
    return daily_rate * Decimal('26')


def get_minimum_wage_info(booking_type: str, address_or_zip: str = '') -> dict:
    """
    Returns structured statutory wage policy metadata, including regional wage orders
    and recommended ranges for frontend consumption.
    """
    b_type = str(booking_type or '').strip().lower()
    if b_type == 'long_term':
        min_daily = get_minimum_daily_wage('long_term', address_or_zip)
        min_monthly = get_monthly_equivalent(min_daily)
        addr = str(address_or_zip or '').lower()

        if any(re.search(p, addr) for p in REGION_10_PATTERNS):
            wage_order = 'RTWPB RBX-DW-06 (Region X)'
        elif any(re.search(p, addr) for p in NCR_PATTERNS):
            wage_order = 'RTWPB NCR-DW-06 (NCR)'
        else:
            wage_order = 'Batas Kasambahay Statutory Floor'

        return {
            'booking_type': 'long_term',
            'min_daily_rate': str(min_daily),
            'min_monthly_rate': str(min_monthly),
            'working_days_per_month': 26,
            'is_statutory_mandatory': True,
            'wage_order': wage_order,
            'law': 'Republic Act No. 10361 (Batas Kasambahay)',
            'description': (
                f"Under Batas Kasambahay (RA 10361) and {wage_order}, the statutory minimum daily wage "
                f"for regular domestic work is ₱{min_daily:.2f}/day (approx. ₱{min_monthly:,.2f}/month for 26 working days)."
            )
        }
    else:
        return {
            'booking_type': 'short_term',
            'min_daily_rate': '1.00',
            'min_monthly_rate': None,
            'working_days_per_month': None,
            'is_statutory_mandatory': False,
            'wage_order': None,
            'law': 'Republic Act No. 10361 Section 4(d) (Exempt)',
            'recommended_market_range': {
                'min': '350.00',
                'max': '800.00'
            },
            'description': (
                "Short-term / occasional domestic work is legally exempt from statutory minimum wage mandates under "
                "Section 4(d) of RA 10361. Rates are flexible and negotiated directly between parties."
            )
        }


