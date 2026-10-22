import accounts.penalties
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0021_rename_cancellation_strikes_penalty_points')]
    operations = [migrations.AddField(
        model_name='tbl_user_profile', name='penalty_month',
        field=models.DateField(default=accounts.penalties.current_penalty_month),
    )]
