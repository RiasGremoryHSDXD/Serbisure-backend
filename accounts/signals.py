from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from .models import tbl_user_profile, tbl_worker_status_history
from verifications.models import tbl_documents


@receiver(post_delete, sender=tbl_documents)
def clearance_removed(sender, instance, using, **kwargs):
    origin = kwargs.get('origin')
    if isinstance(origin, tbl_user_profile) or getattr(origin, 'model', None) is tbl_user_profile:
        return
    from .workforce import record_worker_status
    record_worker_status(instance.user_profile_id, using=using)


@receiver(pre_delete, sender=tbl_user_profile)
def worker_removed(sender, instance, using, **kwargs):
    # Preserve previous months while ending eligibility at deletion time.
    if instance.account_type == 'Kasambahay':
        tbl_worker_status_history.objects.using(using).create(worker_id_snapshot=instance.pk,
            status=instance.is_on_job, barangay=instance.barangay or '', is_verified=False)
