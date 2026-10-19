import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def ensure_cancellation_columns(apps, schema_editor):
    model = apps.get_model('booking', 'tbl_booking')
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {column.name: column for column in connection.introspection.get_table_description(cursor, model._meta.db_table)}
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    fields = [
        ('cancellation_reason', models.CharField(blank=True, null=True, default='', max_length=255)),
        ('cancelled_by', models.ForeignKey(apps.get_model('accounts', 'tbl_user_profile'), blank=True, null=True,
            db_column='cancelled_by', on_delete=django.db.models.deletion.SET_NULL, related_name='cancelled_bookings')),
        ('cancelled_at', models.DateTimeField(blank=True, null=True)),
        ('cancellation_penalty_points', models.PositiveSmallIntegerField(default=0)),
    ]
    for name, field in fields:
        field.set_attributes_from_name(name)
        field.model = model
        existing = columns.get(field.column)
        if existing is None:
            schema_editor.add_field(model, field)
            continue
        expected_type = 'UUIDField' if isinstance(field, models.ForeignKey) else field.get_internal_type()
        if expected_type == 'PositiveSmallIntegerField':
            expected_type = 'SmallIntegerField'
        actual_type = connection.introspection.get_field_type(existing.type_code, existing)
        if actual_type != expected_type or existing.null_ok != field.null:
            raise RuntimeError(f'Existing {model._meta.db_table}.{name} has an incompatible definition. No values were replaced.')
        if isinstance(field, models.CharField) and existing.internal_size != 255:
            raise RuntimeError('Existing cancellation_reason must support 255 characters.')
        if isinstance(field, models.ForeignKey):
            target = (field.remote_field.model._meta.db_table, 'id')
            if not any(value.get('foreign_key') == target and value.get('columns') == [field.column] for value in constraints.values()):
                raise RuntimeError('Existing cancelled_by foreign key does not match the user table.')


class Migration(migrations.Migration):
    dependencies = [
        ('booking', '0014_tbl_booking_daily_end_time_and_more'),
        ('accounts', '0022_tbl_user_profile_penalty_month'),
    ]
    operations = [migrations.SeparateDatabaseAndState(state_operations=[
        migrations.AddField(model_name='tbl_booking', name='cancellation_reason', field=models.CharField(blank=True, null=True, default='', max_length=255)),
        migrations.AddField(model_name='tbl_booking', name='cancelled_by', field=models.ForeignKey(blank=True, null=True, db_column='cancelled_by', on_delete=django.db.models.deletion.SET_NULL, related_name='cancelled_bookings', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='tbl_booking', name='cancelled_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='tbl_booking', name='cancellation_penalty_points', field=models.PositiveSmallIntegerField(default=0)),
    ], database_operations=[migrations.RunPython(ensure_cancellation_columns, migrations.RunPython.noop)])]
