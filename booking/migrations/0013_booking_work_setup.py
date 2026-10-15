import re
from django.db import migrations, models


def backfill_work_setup(apps, schema_editor):
    Booking = apps.get_model('booking', 'tbl_booking')
    alias = schema_editor.connection.alias
    # Only the generated opening paragraph describes the agreed setup.
    # Instructions, booking duration and profile preferences are not evidence.
    pattern = re.compile(r'\bstay[- ](in|out)\s+(?:setup|arrangement)\b', re.I)
    for booking in Booking.objects.using(alias).filter(work_setup__isnull=True).iterator():
        opening = re.split(r'\n\s*\n', booking.special_instruction or '', maxsplit=1)[0]
        matches = {value.lower() for value in pattern.findall(opening)}
        if len(matches) == 1:
            Booking.objects.using(alias).filter(pk=booking.pk).update(work_setup='stay_' + matches.pop())


class Migration(migrations.Migration):
    dependencies = [('booking', '0012_explicit_compensation_and_transitions')]
    operations = [
        migrations.AddField(
            model_name='tbl_booking', name='work_setup',
            field=models.CharField(max_length=8, choices=[('stay_in', 'Stay-in'), ('stay_out', 'Stay-out')],
                                   null=True, blank=True,
                                   help_text='Agreed work setup; null only for legacy posts without an unambiguous setup.'),
        ),
        migrations.RunPython(backfill_work_setup, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='tbl_booking',
            constraint=models.CheckConstraint(
                condition=models.Q(work_setup__isnull=True) | models.Q(work_setup__in=['stay_in', 'stay_out']),
                name='valid_booking_work_setup',
            ),
        ),
    ]
