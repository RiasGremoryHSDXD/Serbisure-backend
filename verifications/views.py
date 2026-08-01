from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .models import tbl_documents
from .serializers import DocumentUploadSerializer

class DocumentUploadView(generics.CreateAPIView):
    queryset = tbl_documents.objects.all()
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsAuthenticated]

    parser_classes = (MultiPartParser, FormParser)

    