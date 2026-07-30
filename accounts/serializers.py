from rest_framework import serializers
from .models import tbl_user_profile
from datetime import date
from core.utils import convert_title, check_input_letters
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed, ValidationError
import uuid

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

        first_name = validated_data.get('first_name', '')
        middle_name = validated_data.get('middle_name', '')
        last_name = validated_data.get('last_name', '')

        combined = f"{first_name}{middle_name}{last_name}".replace(" ", "").lower()
        random_suffix = str(uuid.uuid4())[:5]

        validated_data['username'] = f"{combined}_{random_suffix}"

        user = tbl_user_profile(**validated_data)
        user.set_password(password)
        user.save()

        return user
    
    # Mandatory Value in creating a account
    # def mandatory_field_account_creation(self, value):


    # Custom Validation: Check if they are 18+
    def validate_date_of_birth(self, value):
        
        if value:
            today = date.today()
        
            # This handle leap year and birthday math automatically
            age = today.year - value.year - (( today.month, today.day) < (value.month, value.day))

            if age < 18:
                
                raise serializers.ValidationError("Minimum age is 18")

        return value

    def validate_password(self, value):

        # 1. Check length 
        if len(value) < 11: 
            raise serializers.ValidationError("Password must be at least 11 characters long.")

        if len(value) > 30:
            raise serializers.ValidationError("Password cannot exceed 30 characters.")

        # 2. Check for at least one number 
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError("Password must contain at least one number")

        # 3. Check for at least one letter 
        if not any(char.isalpha() for char in value):
            raise serializers.ValidationError("Password must contain at least one letter")
        
        return value         

    def validate_first_name(self, text):
        
        if not check_input_letters(text):
            raise serializers.ValidationError("First name must be 3-50 characters long and contain only letters and spaces.")
        
        return convert_title(text)
    
    def validate_middle_name(self, text):
        
        if not check_input_letters(text):
            raise serializers.ValidationError("Middle name must be 3-50 characters long and contain only letters and spaces.")
        
        return convert_title(text)
    
    def validate_last_name(self, text):
        
        if not check_input_letters(text):
            raise serializers.ValidationError("Last name must be 3-50 characters long and contain only letters and spaces.")
        
        return convert_title(text)

    def validate_account_type(self, value):
        if value == "Admin":
            raise serializers.ValidationError("You cannot create an Admin account through this public endpoints")
        return value
    
    def validate_email(self, value):
        return value.lower()
    

class CustomLoginSerializer(TokenObtainPairSerializer):
    default_error_messages = {
        "no_active_account": "Wrong email or password. Please try again!"
    }
    