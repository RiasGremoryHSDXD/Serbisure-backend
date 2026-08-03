from django.db import models
from django.conf import settings
from django.db.models import CheckConstraint, Q
import uuid 

# Create your models here.

class tbl_booking(models.Model):

    BOOKING_TYPE_CHOICES = (
        ('short_term', 'Short Term'),
        ('long_term', 'Long Term')
    )

    BOOKING_STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('InProgress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled')
    )

    booking_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    poster_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_post',
        limit_choices_to={'account_type__in': ['Homeowner', 'Kasambahay']},
        db_column='poster_id'
    )

    booking_type = models.CharField(
        max_length=20,
        choices=BOOKING_TYPE_CHOICES,
        blank=False,
        null=False
    )

    booking_status = models.CharField(
        max_length=20,
        choices=BOOKING_STATUS_CHOICES,
        default='Pending',
        blank=False,
        null=False
    )

    service_category = models.CharField(
        max_length=255,
        blank=False,
        null=False
    )

    start_time = models.DateTimeField(
        blank=False,
        null=False
    )

    end_time = models.DateTimeField(
        blank=True,
        null=True
    )

    service_address = models.CharField(
        max_length=255,
        blank=False,
        null=False
    )

    special_instruction = models.TextField(
        blank=True,
        null=True
    )

    createdAt = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.service_category} - {self.booking_status}"

    
    class Meta:
        db_table = 'tbl_booking'

        constraints = [

            CheckConstraint(
                condition=Q(booking_type__in=['short_term', 'long_term']),
                name='valid_booking_type_enum'
            ),

            CheckConstraint(
                condition=Q(booking_status__in=['Pending', 'Accepted', 'InProgress', 'Completed', 'Cancelled']),
                name='valid_booking_status_enum'
            )
        ]