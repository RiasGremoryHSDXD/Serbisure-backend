from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CheckConstraint, Q
from django.core.validators import RegexValidator
import uuid 

class tbl_user_profile(AbstractUser):

    # Define our ENUM choices up here 

    ACCOUNT_TYPE_CHOICES = (
        ('Kasambahay', 'Kasambahay'),
        ('Homeowner', 'Homeowner'),
        ('Barangay', 'Barangay'),
        ('Admin', 'Admin')
    )

    VERIFICATION_STATUS_CHOICES = (
        ('Unverified', 'Unverified'),
        ('Pending', 'Pending'),
        ('Verified', 'Verified'),
        ('Rejected', 'Rejected')
    )

    GENDER_CHOICES = (
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other')
    )

    # Note: first_name, last_name, email, password, and 
    # date_joined are already built-in because we are using AbstractUser

    # Custom text and date fields

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    religion = models.CharField(max_length=100, blank=True, null=True)
    nationality = models.CharField(max_length=100, blank=True, null=True)
    street = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    
    zipcode = models.CharField(
        max_length=4, 
        blank=True, 
        null=True,
        validators=[
            RegexValidator(
                regex=r'^\d{4}$',
                message='Zipcode must be exactly 4 digits (e.g 1000)'
            )
        ]
    )

    country = models.CharField(max_length=100, blank=True, null=True)
    gender = models.CharField(
        max_length=20, 
        choices=GENDER_CHOICES,
        blank=True, 
        null=True
    )

    email = models.EmailField(unique=True)

    contact_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^639\d{9}$',
                message='Contact number must be exactly 12 digits and start with "639"'
            )
        ]
    )


    language = models.CharField(max_length=100, blank=True, null=True)

    # Custome ENUM fields using the choices we defined above

    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='Homeowner'
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='Unverified'
    )

    def __str__(self):
        return self.username
    
    class Meta: 
        constraints = [
            # Lock down the account_type column in the database

            CheckConstraint(
                condition=Q(account_type__in=['Kasambahay', 'Homeowner', 'Barangay', 'Admin']),
                name='valid_account_type_enum'
            ),

            CheckConstraint(
                condition=Q(verification_status__in=['Unverified', 'Pending', 'Verified', 'Rejected']),
                name='valid_verification_status_enum'
            ),

            CheckConstraint(
                condition=Q(gender__in=['Male', 'Female', 'Other']),
                name='valid_gender_enum'
            )
        ]