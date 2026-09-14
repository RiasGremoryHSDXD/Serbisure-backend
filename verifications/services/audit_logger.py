import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


def get_client_ip(request) -> Optional[str]:
    """
    Safely extract client IP from request headers (handling reverse proxies / load balancers).
    """
    if not request:
        return None
    try:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
            return ip
        return request.META.get('REMOTE_ADDR')
    except Exception:
        return None


def get_user_agent(request) -> Optional[str]:
    """
    Safely extract user agent, truncated to 500 characters.
    """
    if not request:
        return None
    try:
        ua = request.META.get('HTTP_USER_AGENT', '')
        return str(ua)[:500] if ua else None
    except Exception:
        return None


def record_audit_log(
    document: Any = None,
    action: str = 'UPDATED',
    actor: Any = None,
    target_user: Any = None,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    reason: Optional[str] = None,
    request: Any = None,
    metadata: Optional[dict] = None,
    document_snapshot: Optional[dict] = None
) -> Optional[Any]:
    """
    Idiot-proof audit logger for document verification events.
    Guarantees:
    - Never throws an uncaught exception to caller.
    - Preserves historical actor & target names even if user accounts are later deleted.
    - Preserves document UUID & details even if document rows are permanently deleted.
    - Records IP address and User-Agent when request is provided.
    """
    try:
        from verifications.models import tbl_audit_logs

        # 1. Resolve Actor (who did it)
        resolved_actor = actor
        if not resolved_actor and request and hasattr(request, 'user'):
            if getattr(request.user, 'is_authenticated', False):
                resolved_actor = request.user

        actor_name = None
        actor_email = None
        actor_role = None
        actor_barangay = None

        if resolved_actor and getattr(resolved_actor, 'is_authenticated', False):
            first = getattr(resolved_actor, 'first_name', '') or ''
            last = getattr(resolved_actor, 'last_name', '') or ''
            full = f"{first} {last}".strip()
            actor_name = full or getattr(resolved_actor, 'username', None) or getattr(resolved_actor, 'email', 'Unknown Officer')
            actor_email = getattr(resolved_actor, 'email', None)
            actor_role = getattr(resolved_actor, 'account_type', None)
            actor_barangay = getattr(resolved_actor, 'barangay', None)
        else:
            resolved_actor = None
            actor_name = "System / Automated"
            actor_role = "System"

        # 2. Resolve Target Resident (whose document it is)
        resolved_target = target_user
        if not resolved_target and document and hasattr(document, 'user_profile'):
            resolved_target = document.user_profile

        target_name = None
        target_email = None
        target_role = None
        target_barangay = None

        if resolved_target:
            t_first = getattr(resolved_target, 'first_name', '') or ''
            t_last = getattr(resolved_target, 'last_name', '') or ''
            t_full = f"{t_first} {t_last}".strip()
            target_name = t_full or getattr(resolved_target, 'username', None) or getattr(resolved_target, 'email', 'Unknown Resident')
            target_email = getattr(resolved_target, 'email', None)
            target_role = getattr(resolved_target, 'account_type', None)
            target_barangay = getattr(resolved_target, 'barangay', None)

        # 3. Resolve Document Info & Snapshot
        doc_instance = document if (document and hasattr(document, 'document_id')) else None
        doc_id_snapshot = getattr(doc_instance, 'document_id', None)
        doc_type = getattr(doc_instance, 'document_type', None)
        doc_number = getattr(doc_instance, 'document_number', None)

        # Allow fallback from document_snapshot dict if document was already deleted
        if document_snapshot:
            doc_id_snapshot = doc_id_snapshot or document_snapshot.get('document_id')
            doc_type = doc_type or document_snapshot.get('document_type')
            doc_number = doc_number or document_snapshot.get('document_number')

        # 4. Resolve Action & Statuses
        std_action = str(action or 'UPDATED').upper().strip()
        final_prev_status = previous_status
        final_new_status = new_status or (getattr(doc_instance, 'verification_status', None) if doc_instance else None)

        # 5. Telemetry
        client_ip = get_client_ip(request)
        ua = get_user_agent(request)
        final_meta = metadata or {}

        # 6. Create Audit Log Entry
        log_entry = tbl_audit_logs.objects.create(
            actor=resolved_actor,
            actor_name=actor_name,
            actor_email=actor_email,
            actor_role=actor_role,
            actor_barangay=actor_barangay,
            target_user=resolved_target,
            target_name=target_name,
            target_email=target_email,
            target_role=target_role,
            target_barangay=target_barangay,
            document=doc_instance,
            document_id_snapshot=doc_id_snapshot,
            document_type=doc_type,
            document_number=doc_number,
            action=std_action,
            previous_status=final_prev_status,
            new_status=final_new_status,
            reason=reason,
            ip_address=client_ip,
            user_agent=ua,
            metadata=final_meta
        )

        logger.info(
            f"[AuditLog] Recorded {std_action} for document {doc_id_snapshot} "
            f"by {actor_name} ({actor_role}) on {target_name}."
        )
        return log_entry

    except Exception as e:
        logger.error(f"[AuditLog] Failed to create audit log safely: {e}", exc_info=True)
        return None
