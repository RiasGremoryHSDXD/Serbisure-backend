from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .models import tbl_documents
from .serializers import DocumentUploadSerializer
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import Throttled
from core.utils import check_valid_uuid
from rest_framework import status
from rest_framework.response import Response
import math 

class DocumentUploadThrottle(UserRateThrottle):
    rate = '5/d'

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
        # 3600 seconds = 1 hour
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