from django.urls import path
from .views import (
    DocumentUploadView, 
    DocumentStatusView, 
    DeleteRejectedDocumentView,
    AdminVerificationQueueView,
    AdminVerificationReviewView
)

urlpatterns = [
    # Mobile App Endpoints
    path('upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('status/', DocumentStatusView.as_view(), name='document-status'),
    path('documents/<uuid:document_id>/', DeleteRejectedDocumentView.as_view(), name='delete-document'),

    # Admin Web Dashboard Endpoints
    path('admin/queue/', AdminVerificationQueueView.as_view(), name='admin-verification-queue'),
    path('admin/review/<uuid:document_id>/', AdminVerificationReviewView.as_view(), name='admin-verification-review'),
]