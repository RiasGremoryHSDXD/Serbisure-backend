from decimal import Decimal
from django.db import migrations, models
from django.db.models import Count


def prepare_existing_rows(apps, schema_editor):
    Booking = apps.get_model('booking', 'tbl_booking')
    Assignment = apps.get_model('booking', 'tbl_booking_assignment')
    alias = schema_editor.connection.alias
    if Assignment.objects.using(alias).values('booking_id').annotate(total=Count('pk')).filter(total__gt=1).exists():
        raise RuntimeError('Duplicate booking assignments exist. Resolve them explicitly before applying this migration; no records were deleted.')
    Booking.objects.using(alias).filter(booking_type='long_term').update(rate_period='month', rate_needs_review=True)
    # Preserve original amounts. The poster must confirm ambiguous legacy monthly values.
    Booking.objects.using(alias).filter(booking_type='short_term').update(rate_period='day')


class Migration(migrations.Migration):
    dependencies = [('booking', '0011_tbl_saved_post')]
    operations = [
        migrations.RemoveConstraint(model_name='tbl_booking', name='valid_daily_rate'),
        migrations.RenameField(model_name='tbl_booking', old_name='daily_rate', new_name='rate_amount'),
        migrations.AddField(model_name='tbl_booking', name='rate_period',
                            field=models.CharField(choices=[('day', 'Day'), ('month', 'Month')], default='day', max_length=5), preserve_default=False),
        migrations.AddField(model_name='tbl_booking', name='rate_needs_review', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='tbl_booking', name='started_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='tbl_booking', name='completed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(prepare_existing_rows, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='tbl_booking', constraint=models.CheckConstraint(condition=models.Q(rate_amount__gte=Decimal('1.00')), name='valid_rate_amount')),
        migrations.AddConstraint(model_name='tbl_booking', constraint=models.CheckConstraint(condition=models.Q(booking_type='short_term', rate_period='day') | models.Q(booking_type='long_term', rate_period='month'), name='booking_rate_period_matches_type')),
        migrations.AddConstraint(model_name='tbl_booking_assignment', constraint=models.UniqueConstraint(fields=['booking_id'], name='one_assignment_per_booking')),
    ]
