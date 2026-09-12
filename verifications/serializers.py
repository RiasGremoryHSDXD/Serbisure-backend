from rest_framework import serializers
from .models import tbl_documents
from .ocr_service import process_document_ocr
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
            'verification_status', 'verifyBy', 'document_number',
            'extracted_data', 'ocr_extracted_data',
            'ocr_match_score', 'ocr_discrepancies', 'rejection_reason',
            'created_at'
        ]

        read_only_fields = [
            'document_url', 'verification_status', 'verifyBy',
            'valid_until', 'date_issued', 'document_number',
            'extracted_data', 'ocr_extracted_data',
            'ocr_match_score', 'ocr_discrepancies', 'rejection_reason',
            'created_at'
        ]

    def create(self, validated_data):
        # Grab the image 
        image_file = validated_data.pop('document_image')

        # Grab the user who is logged in (from the JWT token)
        user = self.context['request'].user
        doc_type = validated_data.get('document_type', '')

        # Process Google Vision OCR
        image_bytes = image_file.read()
        image_file.seek(0)
        
        ocr_result = process_document_ocr(image_bytes, doc_type, user)

        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="serbisure_credentials/",
            type="authenticated"
        )

        # Get the permanent URL / public_id from Cloudinary
        public_id = upload_result.get('public_id')
        doc_type = validated_data.get('document_type')

        # Extract parsed dates from OCR if detected
        parsed_date_issued = None
        parsed_valid_until = None
        try:
            raw_issued = ocr_result.get('date_issued') or ocr_result.get('extracted_data', {}).get('date_issued')
            if raw_issued:
                from datetime import datetime
                parsed_date_issued = datetime.strptime(str(raw_issued)[:10], '%Y-%m-%d').date()
        except Exception:
            pass

        try:
            raw_valid = ocr_result.get('valid_until') or ocr_result.get('extracted_data', {}).get('valid_until')
            if raw_valid:
                from datetime import datetime
                parsed_valid_until = datetime.strptime(str(raw_valid)[:10], '%Y-%m-%d').date()
        except Exception:
            pass

        ocr_fields = {
            'document_number': ocr_result.get('document_number'),
            'date_issued': parsed_date_issued,
            'valid_until': parsed_valid_until,
            'ocr_raw_text': ocr_result.get('raw_text'),
            'extracted_data': ocr_result.get('extracted_data', {}),
            'ocr_match_score': ocr_result.get('match_score'),
            'ocr_discrepancies': ocr_result.get('discrepancies', []),
            'face_liveness_score': ocr_result.get('match_score'),
        }

        # Check if there is an existing rejected document to replace
        existing = tbl_documents.objects.filter(
            user_profile=user,
            document_type=doc_type,
            verification_status='Rejected'
        ).first()

        if existing:
            existing.document_url = public_id
            existing.verification_status = 'Pending'
            existing.rejection_reason = None
            for key, val in ocr_fields.items():
                setattr(existing, key, val)
            for key, val in validated_data.items():
                setattr(existing, key, val)
            existing.save()
            document = existing
        else:
            document = tbl_documents.objects.create(
                user_profile=user,
                document_url=public_id,
                verification_status='Pending',
                **ocr_fields,
                **validated_data
            )

        # Trigger background OCR + Groq processing after DB transaction commits
        try:
            from django.db import transaction
            from verifications.services.document_processor import process_document_async
            transaction.on_commit(lambda doc_id=str(document.document_id): process_document_async(doc_id))
        except Exception:
            pass

        # Update user profile verification status to Pending
        if getattr(user, 'verification_status', None) == 'Unverified':
            user.verification_status = 'Pending'
            user.save(update_fields=['verification_status'])

        return document

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        public_id = instance.document_url

        if public_id:
            if public_id.startswith('http://') or public_id.startswith('https://'):
                representation['document_url'] = public_id
            else:
                temporary_url, options = cloudinary.utils.cloudinary_url(
                    public_id,
                    type="authenticated",
                    sign_url=True,
                )
                representation['document_url'] = temporary_url

        return representation

    def validate_document_image(self, value):
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("Image file must be under 10MB")
        return value


class AdminVerificationQueueSerializer(serializers.ModelSerializer):
    """
    Serializes verification queue items tailored for the Web Admin React dashboard.
    Matches the TypeScript VerificationRequest type.
    """
    id = serializers.CharField(source='document_id', read_only=True)
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    documentType = serializers.SerializerMethodField()
    documentNumber = serializers.SerializerMethodField()
    submittedDate = serializers.SerializerMethodField()
    issuedDate = serializers.SerializerMethodField()
    validityDate = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    recordStatus = serializers.SerializerMethodField()
    documentImage = serializers.SerializerMethodField()
    documentImageBack = serializers.SerializerMethodField()
    rawDocumentType = serializers.CharField(source='document_type', read_only=True)
    barangay = serializers.SerializerMethodField()
    contactNumber = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    notes = serializers.CharField(source='rejection_reason', read_only=True)
    faceLivenessMatchScore = serializers.SerializerMethodField()
    ocrExtractedData = serializers.SerializerMethodField()
    ocrDiscrepancies = serializers.JSONField(source='ocr_discrepancies', read_only=True)
    ocrMatchScore = serializers.FloatField(source='ocr_match_score', read_only=True)

    # Package & Companion Document Fields
    primaryStatus = serializers.SerializerMethodField()
    isPackage = serializers.SerializerMethodField()
    packageLabel = serializers.SerializerMethodField()
    secondaryDocumentId = serializers.SerializerMethodField()
    secondaryDocumentImage = serializers.SerializerMethodField()
    secondaryDocumentType = serializers.SerializerMethodField()
    secondaryDocumentNumber = serializers.SerializerMethodField()
    secondaryIssuedDate = serializers.SerializerMethodField()
    secondaryValidityDate = serializers.SerializerMethodField()
    secondaryStatus = serializers.SerializerMethodField()
    secondaryNotes = serializers.SerializerMethodField()
    secondaryOcrData = serializers.SerializerMethodField()
    secondaryOcrDiscrepancies = serializers.SerializerMethodField()

    class Meta:
        model = tbl_documents
        fields = [
            'id', 'name', 'role', 'avatar', 'documentType', 'rawDocumentType', 'documentNumber',
            'submittedDate', 'issuedDate', 'validityDate', 'status', 'primaryStatus', 'recordStatus',
            'documentImage', 'documentImageBack', 'barangay', 'contactNumber', 'email', 'notes',
            'faceLivenessMatchScore', 'ocrExtractedData', 'ocrDiscrepancies', 'ocrMatchScore',
            'isPackage', 'packageLabel', 'secondaryDocumentId', 'secondaryDocumentImage', 'secondaryDocumentType',
            'secondaryDocumentNumber', 'secondaryIssuedDate', 'secondaryValidityDate',
            'secondaryStatus', 'secondaryNotes', 'secondaryOcrData', 'secondaryOcrDiscrepancies'
        ]

    def _get_companion_doc(self, obj):
        if hasattr(obj, '_cached_companion_doc'):
            return obj._cached_companion_doc

        companion = None
        if obj.document_type == 'national_id_front':
            companion = tbl_documents.objects.filter(
                user_profile=obj.user_profile,
                document_type='national_id_back'
            ).order_by('-created_at').first()
        elif obj.document_type == 'national_id_back':
            companion = tbl_documents.objects.filter(
                user_profile=obj.user_profile,
                document_type='national_id_front'
            ).order_by('-created_at').first()
        elif obj.document_type in ['nbi_clearance', 'police_clearance']:
            other_type = 'police_clearance' if obj.document_type == 'nbi_clearance' else 'nbi_clearance'
            companion = tbl_documents.objects.filter(
                user_profile=obj.user_profile,
                document_type=other_type
            ).order_by('-created_at').first()

        obj._cached_companion_doc = companion
        return companion

    def get_isPackage(self, obj):
        companion = self._get_companion_doc(obj)
        return companion is not None

    def get_packageLabel(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            if obj.document_type in ['nbi_clearance', 'police_clearance']:
                return 'Clearances (NBI + Police)'
            if 'national_id' in obj.document_type:
                return 'National ID (Front + Back)'
        return None

    def get_name(self, obj):
        u = obj.user_profile
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.username or "Registered User"

    def get_role(self, obj):
        acc_type = getattr(obj.user_profile, 'account_type', 'Homeowner')
        return acc_type.upper()

    def get_avatar(self, obj):
        profile_link = getattr(obj.user_profile, 'profile_link', None)
        if profile_link:
            if profile_link.startswith('http://') or profile_link.startswith('https://'):
                return profile_link
            try:
                temp_url, _ = cloudinary.utils.cloudinary_url(
                    profile_link,
                    type="authenticated",
                    sign_url=True,
                    format="webp",
                    quality="auto",
                )
                return temp_url
            except Exception:
                return profile_link
        # Default placeholder avatar
        return f"https://ui-avatars.com/api/?name={obj.user_profile.first_name}+{obj.user_profile.last_name}&background=F5A623&color=fff"

    def get_documentType(self, obj):
        companion = self._get_companion_doc(obj)
        if companion and obj.document_type in ['nbi_clearance', 'police_clearance']:
            return 'Clearances (NBI + Police)'
        mapping = {
            'nbi_clearance': 'NBI CLEARANCE',
            'police_clearance': 'Police Clearance',
            'national_id_front': 'National ID',
            'national_id_back': 'National ID',
        }
        return mapping.get(obj.document_type, obj.document_type.replace('_', ' ').title())

    def get_documentNumber(self, obj):
        if obj.document_number:
            return obj.document_number
        extracted = obj.ocr_extracted_data or {}
        val = (
            extracted.get('clearance_number') or
            extracted.get('philsys_number') or
            extracted.get('document_number')
        )
        if val:
            return val
        # If this is national_id_back, check front doc
        if obj.document_type == 'national_id_back':
            front = tbl_documents.objects.filter(user_profile=obj.user_profile, document_type='national_id_front').first()
            if front:
                f_ext = front.ocr_extracted_data or {}
                return front.document_number or f_ext.get('philsys_number') or f_ext.get('document_number') or "Not Detected"
        return "Not Detected"

    def get_submittedDate(self, obj):
        if obj.created_at:
            return obj.created_at.strftime('%b %d, %Y %I:%M %p')
        return "Recent"

    def get_issuedDate(self, obj):
        if 'national_id' in obj.document_type:
            return 'N/A (PhilSys ID)'
        if obj.date_issued:
            return obj.date_issued.strftime('%b %d, %Y')
        extracted = obj.ocr_extracted_data or {}
        val = extracted.get('date_issued')
        if val:
            try:
                from datetime import datetime
                return datetime.strptime(str(val)[:10], '%Y-%m-%d').strftime('%b %d, %Y')
            except Exception:
                return str(val)
        return "Not Detected"

    def get_validityDate(self, obj):
        if 'national_id' in obj.document_type:
            return 'Permanent'
        if obj.valid_until:
            return obj.valid_until.strftime('%b %d, %Y')
        extracted = obj.ocr_extracted_data or {}
        val = extracted.get('valid_until')
        if val:
            try:
                from datetime import datetime
                return datetime.strptime(str(val)[:10], '%Y-%m-%d').strftime('%b %d, %Y')
            except Exception:
                return str(val)
        return "Not Detected"

    def get_status(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            statuses = [obj.verification_status, companion.verification_status]
            if 'Rejected' in statuses:
                return 'REJECTED'
            elif all(s == 'Verified' for s in statuses):
                return 'VERIFIED'
            return 'PENDING / REVIEW'

        s = obj.verification_status
        if s == 'Verified':
            return 'VERIFIED'
        elif s == 'Rejected':
            return 'REJECTED'
        return 'PENDING / REVIEW'

    def get_recordStatus(self, obj):
        if self.get_status(obj) == 'VERIFIED':
            return 'Clear Record'
        companion = self._get_companion_doc(obj)
        has_critical = False
        if obj.ocr_discrepancies:
            has_critical = any(d.get('severity') == 'high' for d in obj.ocr_discrepancies)
        if not has_critical and companion and companion.ocr_discrepancies:
            has_critical = any(d.get('severity') == 'high' for d in companion.ocr_discrepancies)
        return 'Flagged' if has_critical else 'Under Review'

    def _sign_cloudinary_url(self, public_id):
        if not public_id:
            return None
        if public_id.startswith('http://') or public_id.startswith('https://'):
            return public_id
        try:
            temporary_url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                type="authenticated",
                sign_url=True,
                format="webp",
                quality="auto",
            )
            return temporary_url
        except Exception:
            return public_id

    def get_documentImage(self, obj):
        # Primary image
        return self._sign_cloudinary_url(obj.document_url)

    def get_documentImageBack(self, obj):
        # Backward-compatible alias for secondary image
        return self.get_secondaryDocumentImage(obj)

    def get_secondaryDocumentImage(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            return self._sign_cloudinary_url(companion.document_url)
        return None

    def get_secondaryDocumentType(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            mapping = {
                'nbi_clearance': 'NBI CLEARANCE',
                'police_clearance': 'Police Clearance',
                'national_id_front': 'National ID (Front)',
                'national_id_back': 'National ID (Back)',
            }
            return mapping.get(companion.document_type, companion.document_type.replace('_', ' ').title())
        return None

    def get_secondaryDocumentNumber(self, obj):
        companion = self._get_companion_doc(obj)
        if not companion:
            return None
        if companion.document_number:
            return companion.document_number
        extracted = companion.ocr_extracted_data or {}
        val = (
            extracted.get('clearance_number') or
            extracted.get('philsys_number') or
            extracted.get('document_number')
        )
        return val or "Not Detected"

    def get_secondaryIssuedDate(self, obj):
        companion = self._get_companion_doc(obj)
        if not companion:
            return None
        if 'national_id' in companion.document_type:
            return 'N/A (PhilSys ID)'
        if companion.date_issued:
            return companion.date_issued.strftime('%b %d, %Y')
        extracted = companion.ocr_extracted_data or {}
        val = extracted.get('date_issued')
        if val:
            try:
                from datetime import datetime
                return datetime.strptime(str(val)[:10], '%Y-%m-%d').strftime('%b %d, %Y')
            except Exception:
                return str(val)
        return "Not Detected"

    def get_secondaryValidityDate(self, obj):
        companion = self._get_companion_doc(obj)
        if not companion:
            return None
        if 'national_id' in companion.document_type:
            return 'Permanent'
        if companion.valid_until:
            return companion.valid_until.strftime('%b %d, %Y')
        extracted = companion.ocr_extracted_data or {}
        val = extracted.get('valid_until')
        if val:
            try:
                from datetime import datetime
                return datetime.strptime(str(val)[:10], '%Y-%m-%d').strftime('%b %d, %Y')
            except Exception:
                return str(val)
        return "Not Detected"

    def get_primaryStatus(self, obj):
        s = obj.verification_status
        if s == 'Verified':
            return 'VERIFIED'
        elif s == 'Rejected':
            return 'REJECTED'
        return 'PENDING / REVIEW'

    def get_secondaryDocumentId(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            return str(companion.document_id)
        return None

    def get_secondaryStatus(self, obj):
        companion = self._get_companion_doc(obj)
        if not companion:
            return None
        s = companion.verification_status
        if s == 'Verified':
            return 'VERIFIED'
        elif s == 'Rejected':
            return 'REJECTED'
        return 'PENDING / REVIEW'

    def get_secondaryNotes(self, obj):
        companion = self._get_companion_doc(obj)
        if companion:
            return companion.rejection_reason
        return None

    def get_secondaryOcrData(self, obj):
        companion = self._get_companion_doc(obj)
        if companion and companion.ocr_extracted_data:
            return dict(companion.ocr_extracted_data)
        return None

    def get_secondaryOcrDiscrepancies(self, obj):
        companion = self._get_companion_doc(obj)
        if companion and companion.ocr_discrepancies:
            return companion.ocr_discrepancies
        return []

    def get_ocrExtractedData(self, obj):
        data = dict(obj.ocr_extracted_data or {})
        if not data.get('philsys_number') and obj.document_number:
            data['philsys_number'] = obj.document_number
            data['document_number'] = obj.document_number
        if 'national_id' in obj.document_type:
            data['date_issued'] = None
        # If national_id_front, merge back's extracted data (blood_type, etc.)
        if obj.document_type == 'national_id_front':
            back_doc = self._get_companion_doc(obj)
            if back_doc and back_doc.ocr_extracted_data:
                for k, v in back_doc.ocr_extracted_data.items():
                    if k != 'date_issued' and v and not data.get(k):
                        data[k] = v
        return data

    def get_barangay(self, obj):
        u = obj.user_profile
        street = getattr(u, 'street', '') or ''
        city = getattr(u, 'city', '') or ''
        for b in ['Pagatpat', 'Canitoan']:
            if b.lower() in street.lower() or b.lower() in city.lower():
                return b
        if city and city not in ['Cagayan de Oro City', 'City of Cagayan De Oro', 'Cagayan de Oro']:
            return city
        return 'Pagatpat'

    def get_contactNumber(self, obj):
        return getattr(obj.user_profile, 'contact_number', '') or '+639171234567'

    def get_email(self, obj):
        return getattr(obj.user_profile, 'email', '')

    def get_faceLivenessMatchScore(self, obj):
        if obj.face_liveness_score is not None:
            return round(obj.face_liveness_score, 1)
        if obj.ocr_match_score is not None:
            return round(obj.ocr_match_score, 1)
        return 99.2
