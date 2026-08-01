from django.db import models
from django.conf import settings
import uuid 

# Create your models here.

class tbl_documents(models.Model):


    DOCUMENT_CHOICES = (
        ('nbi_clearance', 'NBI Clearance'),
        ('police_clearance', 'Police Clearance'),
        ('national_id', 'National ID')
    )
    
    document_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user_profile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_type = models.CharField(
        max_length=100,
        choices=DOCUMENT_CHOICES,
        blank=False,
        null=False,
    )

    document_url = models.CharField(
        max_length=255,
        blank=False,
        null=False
    )

    date_issued = models.DateField(
        blank=False,
        null=False
    )

    valid_until = models.DateField(
        blank=False,
        null=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


