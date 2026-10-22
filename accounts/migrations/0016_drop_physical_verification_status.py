from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_alter_tbl_user_profile_options_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE accounts_tbl_user_profile DROP COLUMN IF EXISTS verification_status;",
            reverse_sql="ALTER TABLE accounts_tbl_user_profile ADD COLUMN IF NOT EXISTS verification_status VARCHAR(20) DEFAULT 'Unverified';",
        ),
    ]
