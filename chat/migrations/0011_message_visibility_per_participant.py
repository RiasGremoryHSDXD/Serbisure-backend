from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('chat', '0010_account_access_audit')]

    operations = [
        migrations.AddField(
            model_name='tbl_chat_message', name='hidden_by_sender',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tbl_chat_message', name='hidden_by_receiver',
            field=models.BooleanField(default=False),
        ),
    ]
