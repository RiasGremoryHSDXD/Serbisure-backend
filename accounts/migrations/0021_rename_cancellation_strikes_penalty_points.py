from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0020_tbl_user_profile_chat_suspended_until_and_more')]

    operations = [
        migrations.RenameField(
            model_name='tbl_user_profile',
            old_name='cancellation_strikes',
            new_name='penalty_points',
        ),
        migrations.AlterField(
            model_name='tbl_user_profile',
            name='penalty_points',
            field=models.IntegerField(default=0, help_text='Accumulated booking cancellation penalty points'),
        ),
    ]
