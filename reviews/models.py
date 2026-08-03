from django.db import models
from django.conf import settings
from django.db.models import CheckConstraint, Q
import uuid

class tbl_review(models.Model):
    review_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    booking_id = models.ForeignKey(
        'booking.tbl_booking', # Points safely to the booking app
        on_delete=models.CASCADE,
        related_name='reviews',
        db_column='booking_id'
    )
    
    reviewer_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_given',
        db_column='reviewer_id'
    )
    
    reviewee_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received',
        db_column='reviewee_id'
    )
    
    unstructured_feedback = models.TextField(blank=True, null=True)
    nlp_sentiment = models.CharField(max_length=20, blank=True, null=True)
    review_direction = models.CharField(max_length=30)

    class Meta:
        db_table = 'tbl_review'
        constraints = [
            CheckConstraint(
                condition=Q(nlp_sentiment__in=['Positive', 'Negative', 'Neutral']),
                name='valid_nlp_sentiment_enum'
            ),
            CheckConstraint(
                condition=Q(review_direction__in=['EmployerToWorker', 'WorkerToEmployer']),
                name='valid_review_direction_enum'
            )
        ]
