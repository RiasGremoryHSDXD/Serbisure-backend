from django.db import migrations, models


def normalize_scores(apps, schema_editor):
    Document = apps.get_model('verifications', 'tbl_documents')
    alias = schema_editor.connection.alias
    for document in Document.objects.using(alias).all().iterator():
        score = document.ocr_match_score
        if score is not None:
            score = score * 100 if 0 <= score <= 1 else score
            if not 0 <= score <= 100:
                score = None
        document.ocr_match_score = score
        document.face_liveness_score = None
        if document.document_number and document.document_number.startswith('DOC-'):
            document.document_number = None
        document.save(using=alias, update_fields=['ocr_match_score', 'face_liveness_score', 'document_number'])


class Migration(migrations.Migration):
    dependencies = [('verifications', '0008_alter_tbl_documents_extracted_data_tbl_audit_logs')]
    operations = [
        migrations.RunPython(normalize_scores, migrations.RunPython.noop),
        migrations.AlterField(model_name='tbl_documents', name='ocr_match_score',
            field=models.FloatField(blank=True, null=True, help_text='Document text matching percentage (0-100); null when evidence is unavailable')),
    ]
