import uuid
import django.db.models.deletion
from django.db import migrations, models


def seed_current_status(apps, schema_editor):
    """Baseline at rollout time only: never invent past toggle dates."""
    User = apps.get_model('accounts', 'tbl_user_profile')
    Document = apps.get_model('verifications', 'tbl_documents')
    History = apps.get_model('accounts', 'tbl_worker_status_history')
    db = schema_editor.connection.alias
    for worker in User.objects.using(db).filter(account_type='Kasambahay').iterator():
        latest = {}
        for doc in Document.objects.using(db).filter(user_profile_id=worker.pk, document_type__in=['nbi_clearance', 'police_clearance']).order_by('created_at', 'document_id'):
            latest[doc.document_type] = doc
        docs = list(latest.values())
        dates = [doc.valid_until for doc in docs if doc.valid_until]
        History.objects.using(db).create(worker_id=worker.pk, worker_id_snapshot=worker.pk,
            status=worker.is_on_job, barangay=worker.barangay or '',
            is_verified=worker.is_active and len(docs) == 2 and all(doc.verification_status == 'Verified' for doc in docs),
            clearance_valid_until=min(dates) if dates else None)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0022_tbl_user_profile_penalty_month'), ('verifications', '0009_normalize_document_scores')]
    operations = [
        migrations.CreateModel(name='tbl_worker_status_history', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('worker_id_snapshot', models.UUIDField(editable=False)),
            ('status', models.BooleanField(help_text='True: Occupied; False: Available')),
            ('barangay', models.CharField(blank=True, max_length=100)),
            ('changed_at', models.DateTimeField(auto_now_add=True)),
            ('is_verified', models.BooleanField(default=False, help_text='Active worker with both required clearances approved at this event')),
            ('clearance_valid_until', models.DateField(blank=True, null=True)),
            ('worker', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='status_history', to='accounts.tbl_user_profile')),
        ], options={'db_table': 'tbl_worker_status_history', 'indexes': [models.Index(fields=['worker_id_snapshot', '-changed_at'], name='worker_status_latest_idx')]}),
        migrations.RunPython(seed_current_status, migrations.RunPython.noop),
    ]
