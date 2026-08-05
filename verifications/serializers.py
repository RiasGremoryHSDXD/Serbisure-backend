from rest_framework import serializers
from .models import tbl_documents
import cloudinary.uploader
import cloudinary.utils

class DocumentUploadSerializer(serializers.ModelSerializer):

    document_image = serializers.ImageField(
        write_only=True,
        required=True
    )

    class Meta:

        model = tbl_documents
        fields = [
            'document_id', 'document_type', 'date_issued', 
            'valid_until', 'document_image', 'document_url', 
            'verification_status', 'verifyBy'
        ]

        read_only_fields = [
            'document_url', 'verification_status', 'verifyBy',
            'valid_until', 'date_issued'
        ]


    def create(self, validated_data):

        # Grab the image 
        image_file = validated_data.pop('document_image')

        # Grab the user who is logged in (from the JWT token)
        user = self.context['request'].user

        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="serbisure_credentials/",
            type="authenticated"
        )

        # Get the permanent URL from Cloudinary
        public_id = upload_result.get('public_id')

        document = tbl_documents.objects.create(
            user_profile=user,
            document_url=public_id,
            **validated_data
        )

        return document

    def to_representation(self, instance):

        
        # Get the normal JSON output
        representation = super().to_representation(instance)

        # Grab the raw public_id from the database instance 
        public_id = instance.document_url

        if public_id:

            # Forge the temporary link
            temporary_url, options = cloudinary.utils.cloudinary_url(
                public_id,
                type="authenticated",
                sign_url=True,
            )

            # Swap the raw public_id with new link in the Json response
            representation['document_url'] = temporary_url

        return representation

    def validate_document_image(self, value):
        """
        Validate that the image is less than 10MB
        """

        max_size = 10 * 1024 * 1024

        if value.size > max_size:
            raise serializers.ValidationError("Image file must be under 10MB")
        
        return value
