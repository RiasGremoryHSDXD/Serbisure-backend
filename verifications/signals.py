import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from verifications.models import tbl_documents, tbl_audit_logs
from verifications.services.audit_logger import record_audit_log

logger = logging.getLogger(__name__)


@receiver(post_save, sender=tbl_documents)
def document_post_save_audit(sender, instance, created, **kwargs):
    """
    Automatically logs newly uploaded documents.
    """
    if created:
        try:
            record_audit_log(
                document=instance,
                action='UPLOADED',
                actor=getattr(instance, 'user_profile', None),
                target_user=getattr(instance, 'user_profile', None),
                previous_status=None,
                new_status=getattr(instance, 'verification_status', 'Pending'),
                reason="Document uploaded and queued for verification."
            )
        except Exception as e:
            logger.error(f"[Signal] Error in document_post_save_audit: {e}", exc_info=True)


@receiver(post_delete, sender=tbl_documents)
def document_post_delete_audit(sender, instance, **kwargs):
    """
    Automatically logs document deletions as a safety net if not already logged by a view.
    """
    try:
        doc_id = getattr(instance, 'document_id', None)
        if not doc_id:
            return

        # Check if an explicit DELETED audit log was already recorded for this document recently
        recent_threshold = timezone.now() - timedelta(seconds=3)
        already_logged = tbl_audit_logs.objects.filter(
            document_id_snapshot=doc_id,
            action='DELETED',
            created_at__gte=recent_threshold
        ).exists()

        if not already_logged:
            record_audit_log(
                document=None,
                action='DELETED',
                actor=None,
                target_user=getattr(instance, 'user_profile', None),
                previous_status=getattr(instance, 'verification_status', 'Deleted'),
                new_status='Deleted',
                reason="Document was removed from database.",
                document_snapshot={
                    'document_id': doc_id,
                    'document_type': getattr(instance, 'document_type', None),
                    'document_number': getattr(instance, 'document_number', None),
                }
            )
    except Exception as e:
        logger.error(f"[Signal] Error in document_post_delete_audit: {e}", exc_info=True)
