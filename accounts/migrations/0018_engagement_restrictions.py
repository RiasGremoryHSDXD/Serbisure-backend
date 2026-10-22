from django.db import migrations, models


def ensure_restriction_columns(apps, schema_editor):
    """Adopt compatible columns from legacy installations without replacing data."""
    model = apps.get_model('accounts', 'tbl_user_profile')
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = {column.name: column for column in
                   connection.introspection.get_table_description(cursor, model._meta.db_table)}
    for name, field in (('cancellation_strikes', models.IntegerField(default=0)),
                        ('is_restricted', models.BooleanField(default=False))):
        field.set_attributes_from_name(name)
        field.model = model
        existing = columns.get(field.column)
        if existing is None:
            schema_editor.add_field(model, field)
        elif connection.introspection.get_field_type(existing.type_code, existing) != field.get_internal_type() or existing.null_ok:
            raise RuntimeError(f'Existing {model._meta.db_table}.{name} has an incompatible definition. Resolve its schema explicitly; no values were replaced.')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0017_tbl_user_profile_unique_lgu_account_per_barangay')]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(model_name='tbl_user_profile', name='cancellation_strikes', field=models.IntegerField(default=0, help_text='Accumulated booking cancellation penalty strikes')),
                migrations.AddField(model_name='tbl_user_profile', name='is_restricted', field=models.BooleanField(default=False, help_text='Indicates whether user account is restricted from bookings')),
            ],
            database_operations=[migrations.RunPython(ensure_restriction_columns, migrations.RunPython.noop)],
        ),
    ]
