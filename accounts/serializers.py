from rest_framework import serializers
from .models import tbl_user_profile

class UserRegistrationSerializer(serializers.ModelSerializer):
    # This enrsure the password is required to create an account,
    # but the API will never will accidentally send it back to the frontend

    password = serializers.CharField(write_only=True)

    class Meta: 
        model = tbl_user_profile

        # These are the fields the user is allowed to submit when registering
        
        fields = [
            'first_name',
            'middle_name',
            'last_name',
            'date_of_birth',
            'religion',
            'nationality',
            'street',
            'city',
            'province',
            'zipcode',
            'country',
            'gender',
            'contact_number',
            'language',
            'email',
            'password',
            'account_type',
            'verification_status', 
        ]

    # We override the standard save method to ensure the password gets hashed
    def create(self, validated_data):
        
        # 1. Take the password out of the data so we can securely hash it
        password = validated_data.pop('password')

        # 2. AbstractUser REQUIRES a username. Since we don't have one,
        # let's just use thier email as thier username behind the scene
        email = validated_data.get('email')

        # 3. Create the user. The **validated_data automatically passes all
        # field (first_name, religion, city, etc) to the database

        user = tbl_user_profile.objects.create_user(
            username=email,
            password=password,
            **validated_data
        )

        return user

