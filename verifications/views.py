from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from .models import tbl_documents
from .serializers import DocumentUploadSerializer, AdminVerificationQueueSerializer
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import Throttled
from rest_framework import status
from rest_framework.response import Response
import math
class DocumentUploadThrottle(UserRateThrottle):
    rate = '20/d'


class DocumentUploadView(generics.CreateAPIView):
    throttle_classes = [DocumentUploadThrottle]
    queryset = tbl_documents.objects.all()
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
        user = request.user
        doc_type = request.data.get('document_type')

        if user.account_type == 'Kasambahay' and doc_type not in ['nbi_clearance', 'police_clearance']:
            return Response(
                {"error": "Kasambahay can only upload NBI or Police Clearances"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if user.account_type == 'Homeowner' and doc_type not in ['national_id_front', 'national_id_back']:
            return Response(
                {"error": "Homeowner can only upload a National ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Allow re-upload if previous document was Rejected. Block if Pending or Verified!
        active_doc = tbl_documents.objects.filter(
            user_profile=user,
            document_type=doc_type,
            verification_status__in=['Pending', 'Verified']
        ).first()

        if active_doc:
            status_text = "is currently pending review" if active_doc.verification_status == "Pending" else "is already verified"
            return Response(
                {"error": f"You have already submitted your {doc_type} ({status_text})."},
                status=status.HTTP_409_CONFLICT
            )
        
        response = super().create(request, *args, **kwargs)

        # Create user notification
        from notifications.models import tbl_notification
        doc_display = dict(tbl_documents.DOCUMENT_CHOICES).get(doc_type, doc_type)
        try:
            tbl_notification.objects.create(
                sender_id=user,
                receiver_id=user,
                notification_message=f"Your {doc_display} has been submitted and is queued for verification.",
            )
        except Exception:
            pass

        return response
    
    def throttled(self, request, wait):
        if wait > 3600:
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait / 60)} minutes"

        raise Throttled(detail=custom_message)


class UserVerificationStatusView(generics.GenericAPIView):
    """
    GET /api/v1/verifications/status/
    Returns the authenticated user's submitted documents, their status,
    any rejection reasons, and the overall account verification status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .serializers_admin import UserDocumentStatusSerializer
        from .services.document_processor import process_document_async
        from datetime import timedelta
        from django.utils import timezone
        import logging
        logger = logging.getLogger(__name__)

        user = request.user
        documents = tbl_documents.objects.filter(user_profile=user).order_by('-created_at')

        # Lazy retry: find stuck documents submitted > 30s ago that haven't finished OCR
        # or where previous extraction produced empty results ({})
        stuck_threshold = timezone.now() - timedelta(seconds=30)
        stuck_docs = [
            doc for doc in documents
            if doc.verification_status == 'Pending'
            and doc.ocr_retry_count < 3
            and doc.created_at <= stuck_threshold
            and (
                doc.ocr_processed_at is None
                or not doc.extracted_data
                or doc.extracted_data == {}
                or not (doc.ocr_raw_text and doc.ocr_raw_text.strip())
            )
        ]

        for doc in stuck_docs:
            logger.info(
                f"[LazyRetry] Retrying OCR for stuck document {doc.document_id} "
                f"({doc.document_type}), attempt {doc.ocr_retry_count + 1}/3"
            )
            doc.ocr_retry_count += 1
            doc.save(update_fields=['ocr_retry_count'])
            process_document_async(str(doc.document_id))

        serialized_docs = UserDocumentStatusSerializer(documents, many=True).data

        # Determine required document types depending on account type
        if user.account_type == 'Kasambahay':
            required_docs = ['nbi_clearance', 'police_clearance']
        elif user.account_type == 'Homeowner':
            required_docs = ['national_id_front', 'national_id_back']
        else:
            required_docs = []

        return Response({
            "account_type": user.account_type,
            "overall_status": user.verification_status,
            "required_documents": required_docs,
            "user_info": {
                "first_name": user.first_name,
                "middle_name": user.middle_name,
                "last_name": user.last_name,
                "date_of_birth": str(user.date_of_birth) if user.date_of_birth else None,
            },
            "documents": serialized_docs,
        }, status=status.HTTP_200_OK)


class UserDeleteRejectedDocumentView(generics.GenericAPIView):
    """
    DELETE /api/v1/verifications/documents/<document_id>/
    Allows user to delete a document ONLY IF it has been rejected,
    allowing them to clean up before re-submitting.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, document_id):
        try:
            doc = tbl_documents.objects.get(document_id=document_id, user_profile=request.user)
        except tbl_documents.DoesNotExist:
            return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

        if doc.verification_status != 'Rejected':
            return Response(
                {"error": f"Cannot delete a document with status '{doc.verification_status}'. Only rejected documents can be deleted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        doc.delete()
        return Response({"message": "Rejected document removed successfully."}, status=status.HTTP_200_OK)


# Backward-compatible alias
DeleteRejectedDocumentView = UserDeleteRejectedDocumentView
DocumentStatusView = UserVerificationStatusView



# ==========================================
# ADMIN VERIFICATION QUEUE & REVIEW ENDPOINTS
# ==========================================

class AdminVerificationQueueView(generics.ListAPIView):
    """
    Returns all verification requests for the Web Admin dashboard.
    Supports query params:
    - ?role=KASAMBAHAY | HOMEOWNER
    - ?status=PENDING | VERIFIED | REJECTED | NO_DOCUMENTS | ALL
    - ?barangay=Pagatpat | UNASSIGNED | ALL
    """
    permission_classes = [AllowAny] # Permissive for easy admin dashboard integration
    serializer_class = AdminVerificationQueueSerializer

    def get_queryset(self):
        doc_status = self.request.query_params.get('status')
        if doc_status and doc_status.upper() in ['NO_DOCUMENTS', 'UNSUBMITTED']:
            return tbl_documents.objects.none()

        # 1. National ID: Exclude national_id_back if the user already has a national_id_front,
        # ensuring National ID is represented as a single combined entry.
        front_user_ids = tbl_documents.objects.filter(
            document_type='national_id_front'
        ).values_list('user_profile_id', flat=True)

        # 2. Kasambahay Statutory Clearances: Exclude police_clearance if the user already has
        # an nbi_clearance, ensuring clearances are represented as a single combined package entry.
        nbi_user_ids = tbl_documents.objects.filter(
            document_type='nbi_clearance'
        ).values_list('user_profile_id', flat=True)

        qs = tbl_documents.objects.select_related('user_profile').exclude(
            document_type='national_id_back',
            user_profile_id__in=front_user_ids
        ).exclude(
            document_type='police_clearance',
            user_profile_id__in=nbi_user_ids
        ).order_by('-created_at')
        
        role = self.request.query_params.get('role')
        if role and role.upper() != 'ALL':
            qs = qs.filter(user_profile__account_type__iexact=role)
            
        if doc_status and doc_status.upper() != 'ALL':
            if doc_status.upper() in ['PENDING', 'PENDING / REVIEW']:
                qs = qs.filter(verification_status__in=['Pending', 'Unverified'])
            elif doc_status.upper() == 'VERIFIED':
                qs = qs.filter(verification_status='Verified')
            elif doc_status.upper() == 'REJECTED':
                qs = qs.filter(verification_status='Rejected')

        barangay = self.request.query_params.get('barangay')
        if self.request.user.is_authenticated and getattr(self.request.user, 'account_type', None) == 'Barangay':
            barangay = self.request.user.barangay

        from django.db.models import Q
        if barangay:
            if barangay.upper() in ['UNASSIGNED', 'NO LGU COVERAGE', 'NO_LGU']:
                from accounts.models import tbl_user_profile
                active_lgus = [
                    b.strip() for b in tbl_user_profile.objects.filter(
                        account_type='Barangay', is_active=True
                    ).exclude(barangay__isnull=True).exclude(barangay__exact='')
                    .values_list('barangay', flat=True) if b and b.strip()
                ]
                q_assigned = Q()
                for b in active_lgus:
                    q_assigned |= Q(user_profile__barangay__iexact=b)
                qs = qs.exclude(q_assigned)
            elif barangay.lower() not in ['all', 'all barangays']:
                qs = qs.filter(
                    Q(user_profile__barangay__iexact=barangay) |
                    Q(user_profile__barangay__icontains=barangay) |
                    Q(user_profile__city__icontains=barangay) |
                    Q(user_profile__street__icontains=barangay)
                )

        return qs

    def list(self, request, *args, **kwargs):
        from accounts.models import tbl_user_profile
        from django.db.models import Q
        import cloudinary.utils

        doc_status = request.query_params.get('status')
        role_param = request.query_params.get('role')
        barangay_param = request.query_params.get('barangay')

        if request.user.is_authenticated and getattr(request.user, 'account_type', None) == 'Barangay':
            barangay_param = request.user.barangay

        # Dynamic active LGU barangay set
        active_lgus = [
            b.strip() for b in tbl_user_profile.objects.filter(
                account_type='Barangay', is_active=True
            ).exclude(barangay__isnull=True).exclude(barangay__exact='')
            .values_list('barangay', flat=True) if b and b.strip()
        ]
        active_lgus_lower = [b.lower() for b in active_lgus]

        # 1. Fetch document entries unless specifically requesting only unsubmitted
        doc_data = []
        if not (doc_status and doc_status.upper() in ['NO_DOCUMENTS', 'UNSUBMITTED']):
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            doc_data = serializer.data

        # 2. Fetch unsubmitted users if status is NO_DOCUMENTS, UNSUBMITTED, ALL, or not specified
        unsubmitted_data = []
        if not doc_status or doc_status.upper() in ['ALL', 'NO_DOCUMENTS', 'UNSUBMITTED']:
            users_with_docs = tbl_documents.objects.values_list('user_profile_id', flat=True).distinct()
            unsub_qs = tbl_user_profile.objects.filter(
                account_type__in=['Homeowner', 'Kasambahay']
            ).exclude(id__in=users_with_docs).order_by('-date_joined')

            if role_param and role_param.upper() != 'ALL':
                unsub_qs = unsub_qs.filter(account_type__iexact=role_param)

            if barangay_param:
                if barangay_param.upper() in ['UNASSIGNED', 'NO LGU COVERAGE', 'NO_LGU']:
                    q_assigned = Q()
                    for b in active_lgus:
                        q_assigned |= Q(barangay__iexact=b)
                    unsub_qs = unsub_qs.exclude(q_assigned)
                elif barangay_param.lower() not in ['all', 'all barangays']:
                    unsub_qs = unsub_qs.filter(
                        Q(barangay__iexact=barangay_param) |
                        Q(barangay__icontains=barangay_param) |
                        Q(city__icontains=barangay_param) |
                        Q(street__icontains=barangay_param)
                    )

            for u in unsub_qs:
                full_name = f"{u.first_name} {u.last_name}".strip() or u.username
                role_norm = u.account_type.upper() if u.account_type else 'HOMEOWNER'
                if role_norm not in ['HOMEOWNER', 'KASAMBAHAY']:
                    role_norm = 'HOMEOWNER'

                avatar = u.profile_link or f"https://ui-avatars.com/api/?name={u.first_name}+{u.last_name}&background=F5A623&color=fff"
                if u.profile_link and not (u.profile_link.startswith('http://') or u.profile_link.startswith('https://')):
                    try:
                        temp_url, _ = cloudinary.utils.cloudinary_url(
                            u.profile_link,
                            type="authenticated",
                            sign_url=True,
                        )
                        avatar = temp_url
                    except Exception:
                        pass

                brgy = (u.barangay or '').strip()
                if not brgy:
                    street_lower = (u.street or '').lower()
                    city_lower = (u.city or '').lower()
                    for b in active_lgus:
                        if b.lower() in street_lower or b.lower() in city_lower:
                            brgy = b
                            break
                if not brgy:
                    brgy = 'Unassigned'

                has_lgu = bool(brgy and brgy.lower() in active_lgus_lower)
                req_label = "Statutory Clearances (NBI + Police)" if role_norm == 'KASAMBAHAY' else "National ID (Front + Back)"

                unsubmitted_data.append({
                    "id": f"unsubmitted_{u.id}",
                    "userId": str(u.id),
                    "name": full_name,
                    "role": role_norm,
                    "avatar": avatar,
                    "documentType": "No Documents Submitted",
                    "rawDocumentType": "unsubmitted",
                    "documentNumber": "Not Available",
                    "submittedDate": "Not Submitted",
                    "issuedDate": "N/A",
                    "validityDate": "N/A",
                    "status": "NO_DOCUMENTS",
                    "primaryStatus": "NO_DOCUMENTS",
                    "recordStatus": "Under Review",
                    "documentImage": "",
                    "documentImageBack": "",
                    "barangay": brgy,
                    "city": u.city or "Cagayan de Oro City",
                    "address": f"{u.street or ''}, {u.city or 'Cagayan de Oro City'}".strip(', '),
                    "contactNumber": u.contact_number or "+639123456789",
                    "email": u.email,
                    "notes": f"Pending initial upload of {req_label}",
                    "hasDocuments": False,
                    "hasLguCoverage": has_lgu,
                    "joinedDate": u.date_joined.strftime('%b %d, %Y') if u.date_joined else "Recent"
                })

        if doc_status and doc_status.upper() in ['NO_DOCUMENTS', 'UNSUBMITTED']:
            return Response(unsubmitted_data, status=status.HTTP_200_OK)

        return Response(doc_data + unsubmitted_data, status=status.HTTP_200_OK)


class AdminVerificationReviewView(generics.GenericAPIView):
    """
    Allows Admin or Barangay officer to approve or reject a document.
    POST body:
    {
        "action": "approve" | "reject" | "reset",
        "rejection_reason": "Optional notes or reason for rejection"
    }
    """
    permission_classes = [AllowAny]

    def post(self, request, document_id, *args, **kwargs):
        try:
            document = tbl_documents.objects.select_related('user_profile').get(document_id=document_id)
        except tbl_documents.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action', '').lower()
        reason = request.data.get('rejection_reason', '')

        if action not in ['approve', 'reject', 'reset']:
            return Response({"error": "action must be 'approve', 'reject', or 'reset'"}, status=status.HTTP_400_BAD_REQUEST)

        user = document.user_profile

        # Locate related package records to keep them in sync (e.g. National ID Front+Back or Kasambahay NBI+Police)
        related_package_docs = tbl_documents.objects.none()
        if document.document_type in ['national_id_front', 'national_id_back']:
            related_package_docs = tbl_documents.objects.filter(
                user_profile=user,
                document_type__in=['national_id_front', 'national_id_back']
            )
        elif document.document_type in ['nbi_clearance', 'police_clearance']:
            companion_type = 'police_clearance' if document.document_type == 'nbi_clearance' else 'nbi_clearance'
            has_companion = tbl_documents.objects.filter(user_profile=user, document_type=companion_type).exists()
            if has_companion:
                related_package_docs = tbl_documents.objects.filter(
                    user_profile=user,
                    document_type__in=['nbi_clearance', 'police_clearance']
                )

        if action == 'approve':
            document.verification_status = 'Verified'
            document.rejection_reason = None
            document.save()

            if related_package_docs.exists():
                related_package_docs.update(
                    verification_status='Verified',
                    rejection_reason=None
                )

            # Check if all user documents are verified
            user_docs = tbl_documents.objects.filter(user_profile=user)
            all_verified = user_docs.exists() and all(d.verification_status == 'Verified' for d in user_docs)
            if all_verified:
                user.verification_status = 'Verified'
                user.save(update_fields=['verification_status'])
            else:
                user.verification_status = 'Pending'
                user.save(update_fields=['verification_status'])

            return Response({
                "message": f"Document approved successfully.",
                "document": AdminVerificationQueueSerializer(document).data
            }, status=status.HTTP_200_OK)

        elif action == 'reject':
            document.verification_status = 'Rejected'
            document.rejection_reason = reason or "Document criteria not met"
            document.save()

            user.verification_status = 'Rejected'
            user.save(update_fields=['verification_status'])

            return Response({
                "message": "Document rejected.",
                "document": AdminVerificationQueueSerializer(document).data
            }, status=status.HTTP_200_OK)

        elif action == 'reset':
            document.verification_status = 'Pending'
            document.rejection_reason = None
            document.save()

            user_docs = tbl_documents.objects.filter(user_profile=user)
            if any(d.verification_status == 'Rejected' for d in user_docs):
                user.verification_status = 'Rejected'
            elif user_docs.exists() and all(d.verification_status == 'Verified' for d in user_docs):
                user.verification_status = 'Verified'
            else:
                user.verification_status = 'Pending'
            user.save(update_fields=['verification_status'])

            return Response({
                "message": "Document reset to Pending review.",
                "document": AdminVerificationQueueSerializer(document).data
            }, status=status.HTTP_200_OK)

