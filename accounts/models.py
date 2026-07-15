from django.contrib.auth.models import AbstractUser
from django.db import models

class tbl_user_profile(AbstractUser):

    # Define our ENUM choices up here 

    ACCOUNT_TYPE_CHOICES = (
        ('Kasambahay', 'Kasambahay'),
        ('Homeowner', 'Homeowner'),
    )

    VERIFICATION_STATUS_CHOICES = (
        ('Unverified', 'Unverified'),
        ('Pending', 'Pending'),
        ('Verified', 'Verified'),
        ('Rejected', 'Rejected')
    )

    # Note: first_name, last_name, email, password, and 
    # date_joined are already built-in because we are using AbstractUser

    # Custom text and date fields

    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    religion = models.CharField(max_length=100, blank=True, null=True)
    nationality = models.CharField(max_length=100, blank=True, null=True)
    street = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    zipcode = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
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