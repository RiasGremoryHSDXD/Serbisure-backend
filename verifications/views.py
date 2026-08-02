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

        if tbl_documents.objects.filter(user_profile=user, document_type=doc_type).exists():
            return Response(
                {"error": f"You have already submitted your {doc_type}"},
                status=status.HTTP_409_CONFLICT
            )
        
        return super().create(request, *args, **kwargs)
    
    def throttled(self, request, wait):
        # 3600 seconds = 1 hour
        if wait > 3600:
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait / 60)} minutes"

        raise Throttled(detail=custom_message)