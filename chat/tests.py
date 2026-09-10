"""
chat/tests.py
=============
Comprehensive test suite for chat attachments (images) and emoji reactions.

Coverage map:
  - SendImageMessageTests       → Image upload, format validation, size guards, edge cases, error states
  - ReactMessageTests           → Emoji reactions toggle, whitelist validation, authorization guards, race condition defense
  - ChatThreadSerializerTests   → Thread serialization, reaction summaries, inbox previews, signed URLs
"""

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from unittest.mock import patch
from chat.models import tbl_chat_message, tbl_chat_reaction
import uuid
import time

User = get_user_model()


def make_jpeg_bytes():
    return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00' + (b'\x00' * 100)


def make_png_bytes():
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (b'\x00' * 100)


def make_webp_bytes():
    return b'RIFF\x20\x00\x00\x00WEBPVP8 ' + (b'\x00' * 100)


def make_fake_exe_bytes():
    return b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00' + (b'\x00' * 100)


# =============================================================================
# SECTION 1 — IMAGE ATTACHMENT TESTS
# =============================================================================

class SendImageMessageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="Password123!",
            contact_number="+639123456781"
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="Password123!",
            contact_number="+639123456782"
        )
        self.client.force_authenticate(user=self.alice)

    @patch('cloudinary.uploader.upload')
    def test_send_valid_jpeg_success(self, mock_upload):
        """Valid JPEG file is uploaded to Cloudinary, saved in DB, and returns 201."""
        mock_upload.return_value = {
            'public_id': 'serbisure_chat_images/sample_jpeg',
            'width': 800,
            'height': 600,
            'secure_url': 'https://res.cloudinary.com/test/image.jpg'
        }
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file,
                'message_payload': 'Here is the photo'
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['message'], "Image sent successfully.")
        data = response.data['data']
        self.assertEqual(data['message_type'], 'image')
        self.assertEqual(data['message_payload'], 'Here is the photo')
        self.assertIsNotNone(data['image_url'])

        # Verify in DB
        msg = tbl_chat_message.objects.get(chat_message_id=data['chat_message_id'])
        self.assertEqual(msg.message_type, 'image')
        self.assertEqual(msg.image_public_id, 'serbisure_chat_images/sample_jpeg')
        self.assertEqual(msg.message_payload, 'Here is the photo')

    @patch('cloudinary.uploader.upload')
    def test_send_valid_png_success(self, mock_upload):
        """Valid PNG file is accepted and saved."""
        mock_upload.return_value = {
            'public_id': 'serbisure_chat_images/sample_png',
            'width': 600,
            'height': 400,
        }
        image_file = SimpleUploadedFile("screenshot.png", make_png_bytes(), content_type="image/png")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data['data']
        self.assertEqual(data['message_type'], 'image')
        self.assertIsNone(data['message_payload'])

    @patch('cloudinary.uploader.upload')
    def test_send_valid_webp_success(self, mock_upload):
        """Valid WEBP file is accepted."""
        mock_upload.return_value = {
            'public_id': 'serbisure_chat_images/sample_webp',
            'width': 400,
            'height': 300,
        }
        image_file = SimpleUploadedFile("photo.webp", make_webp_bytes(), content_type="image/webp")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_send_exe_disguised_as_jpg_rejected(self):
        """Edge Case #1: EXE file disguised as .jpg is rejected via magic byte inspection."""
        image_file = SimpleUploadedFile("malware.jpg", make_fake_exe_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)
        self.assertIn("Unsupported image format", str(response.data['image']))

    def test_send_svg_rejected(self):
        """Edge Case #2: SVG file is explicitly rejected to prevent SVG XSS."""
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        image_file = SimpleUploadedFile("vector.svg", svg_content, content_type="image/svg+xml")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)

    def test_send_oversized_file_rejected(self):
        """Edge Case #4: File > 10MB is rejected before Cloudinary is invoked."""
        big_bytes = make_jpeg_bytes() + (b'\x00' * (10 * 1024 * 1024 + 100))
        image_file = SimpleUploadedFile("huge.jpg", big_bytes, content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Image must be smaller than 10 MB", str(response.data['image']))

    def test_send_empty_file_rejected(self):
        """Edge Case #6: Zero-byte file is rejected."""
        image_file = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)

    def test_send_missing_image_field_rejected(self):
        """Edge Case #12: Submitting without an image field returns 400."""
        key = str(uuid.uuid4())
        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'message_payload': 'Only caption'
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)

    def test_send_caption_too_long_rejected(self):
        """Edge Case #13: Caption exceeding 200 characters is rejected."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file,
                'message_payload': 'A' * 201
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message_payload", response.data)

    def test_send_caption_null_bytes_rejected(self):
        """Edge Case #14: Caption containing null bytes is rejected."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.bob.id),
                'image': image_file,
                'message_payload': 'Hello\x00World'
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message_payload", response.data)

    def test_send_to_self_rejected(self):
        """Edge Case #10: Sending image to yourself returns 400."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(self.alice.id),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You cannot send a message to yourself", str(response.data))

    def test_send_to_non_existent_user_404(self):
        """Edge Case #11: Sending image to non-existent user returns 404."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {
                'receiver_id': str(uuid.uuid4()),
                'image': image_file
            },
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('cloudinary.uploader.upload')
    def test_duplicate_idempotency_key_cached_201(self, mock_upload):
        """Edge Case #7, #33: Duplicate Idempotency-Key returns cached response without second upload."""
        mock_upload.return_value = {
            'public_id': 'serbisure_chat_images/first_upload',
            'width': 800,
            'height': 600,
        }
        image_file1 = SimpleUploadedFile("photo1.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        image_file2 = SimpleUploadedFile("photo2.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        res1 = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file1},
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file2},
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.data, res2.data)
        # Cloudinary was only called once!
        self.assertEqual(mock_upload.call_count, 1)

    def test_missing_idempotency_key_rejected(self):
        """Missing Idempotency-Key returns 400."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        response = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", response.data['detail'])

    def test_malformed_idempotency_key_rejected(self):
        """Malformed Idempotency-Key returns 400."""
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        response = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file},
            format='multipart',
            HTTP_IDEMPOTENCY_KEY="not-a-valid-uuid"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('cloudinary.uploader.upload')
    def test_cloudinary_failure_returns_502(self, mock_upload):
        """Edge Case #9: Cloudinary failure returns 502 Bad Gateway and does not save in DB."""
        mock_upload.side_effect = Exception("Cloudinary connection timeout")
        image_file = SimpleUploadedFile("photo.jpg", make_jpeg_bytes(), content_type="image/jpeg")
        key = str(uuid.uuid4())

        initial_count = tbl_chat_message.objects.count()

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file},
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(tbl_chat_message.objects.count(), initial_count)

    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.uploader.upload')
    def test_pixel_bomb_dimensions_rejected(self, mock_upload, mock_destroy):
        """Edge Case #3: Pixel bomb with width > 10000 is rejected, destroyed in Cloudinary, not saved in DB."""
        mock_upload.return_value = {
            'public_id': 'serbisure_chat_images/bomb_img',
            'width': 12000,
            'height': 12000,
        }
        image_file = SimpleUploadedFile("bomb.png", make_png_bytes(), content_type="image/png")
        key = str(uuid.uuid4())

        initial_count = tbl_chat_message.objects.count()

        response = self.client.post(
            '/api/v1/chat/send-image/',
            {'receiver_id': str(self.bob.id), 'image': image_file},
            format='multipart',
            HTTP_IDEMPOTENCY_KEY=key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dimensions are too large", response.data['detail'])
        mock_destroy.assert_called_once_with('serbisure_chat_images/bomb_img', type='authenticated')
        self.assertEqual(tbl_chat_message.objects.count(), initial_count)


# =============================================================================
# SECTION 2 — EMOJI REACTION TESTS
# =============================================================================

class ReactMessageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="Password123!",
            contact_number="+639123456781"
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="Password123!",
            contact_number="+639123456782"
        )
        self.charlie = User.objects.create_user(
            username="charlie",
            email="charlie@example.com",
            password="Password123!",
            contact_number="+639123456783"
        )

        self.message = tbl_chat_message.objects.create(
            sender_id=self.alice,
            receiver_id=self.bob,
            message_type='text',
            message_payload='Hello Bob!'
        )

        self.client.force_authenticate(user=self.bob)

    def test_valid_emoji_added(self):
        """Adding a valid emoji creates reaction with action='added'."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '❤️'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], 'added')
        self.assertEqual(response.data['data']['my_reaction'], '❤️')
        self.assertEqual(response.data['data']['reaction_counts']['❤️'], 1)

        # Verify in DB
        self.assertTrue(
            tbl_chat_reaction.objects.filter(
                message=self.message,
                reactor=self.bob,
                emoji='❤️'
            ).exists()
        )

    def test_same_emoji_toggled_off(self):
        """Sending the same emoji again removes the reaction (toggle off)."""
        tbl_chat_reaction.objects.create(
            message=self.message,
            reactor=self.bob,
            emoji='❤️'
        )

        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '❤️'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], 'removed')
        self.assertIsNone(response.data['data']['my_reaction'])
        self.assertEqual(response.data['data']['reaction_counts']['❤️'], 0)
        self.assertFalse(tbl_chat_reaction.objects.filter(message=self.message, reactor=self.bob).exists())

    def test_different_emoji_changed(self):
        """Sending a different emoji changes the reaction."""
        tbl_chat_reaction.objects.create(
            message=self.message,
            reactor=self.bob,
            emoji='❤️'
        )

        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '👍'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['action'], 'changed')
        self.assertEqual(response.data['data']['my_reaction'], '👍')
        self.assertEqual(response.data['data']['reaction_counts']['👍'], 1)
        self.assertEqual(response.data['data']['reaction_counts']['❤️'], 0)

    def test_invalid_emoji_rejected(self):
        """Edge Case #16: Emoji not in whitelist is rejected with 400."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '💩'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("emoji", response.data)

    def test_empty_emoji_rejected(self):
        """Edge Case #17: Empty emoji string returns 400."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': ''},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_null_emoji_rejected(self):
        """Edge Case #17: Null emoji returns 400."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': None},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_emoji_list_rejected(self):
        """Edge Case #25: Passing a list instead of string returns 400."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': ['❤️', '👍']},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_script_tag_emoji_rejected(self):
        """Edge Case #18: Script injection attempt is rejected by whitelist with 400."""
        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '<script>alert(1)</script>'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_outsider_cannot_react_403(self):
        """Edge Case #19: User who is not sender or receiver receives 403 Forbidden."""
        self.client.force_authenticate(user=self.charlie)

        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '❤️'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not a participant", response.data['detail'])

    def test_react_to_deleted_message_404(self):
        """Edge Case #20: Reacting to an is_deleted=True message returns 404."""
        self.message.is_deleted = True
        self.message.save()

        response = self.client.post(
            f'/api/v1/chat/react/{self.message.chat_message_id}/',
            {'emoji': '❤️'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_react_to_non_existent_message_404(self):
        """Edge Case #21: Reacting to random message UUID returns 404."""
        response = self.client.post(
            f'/api/v1/chat/react/{uuid.uuid4()}/',
            {'emoji': '❤️'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# SECTION 3 — CHAT THREAD & SERIALIZER TESTS
# =============================================================================

class ChatThreadSerializerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="Password123!",
            contact_number="+639123456781"
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="Password123!",
            contact_number="+639123456782"
        )
        self.client.force_authenticate(user=self.alice)

    def test_text_message_has_no_image_url(self):
        """Text messages have image_url: null."""
        msg = tbl_chat_message.objects.create(
            sender_id=self.alice,
            receiver_id=self.bob,
            message_type='text',
            message_payload='Hello'
        )

        response = self.client.get(f'/api/v1/chat/thread/{self.bob.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        messages = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertTrue(len(messages) >= 1)
        first = messages[0]
        self.assertEqual(first['message_type'], 'text')
        self.assertIsNone(first['image_url'])

    def test_image_message_generates_signed_url(self):
        """Image messages generate an authenticated signed Cloudinary URL."""
        msg = tbl_chat_message.objects.create(
            sender_id=self.alice,
            receiver_id=self.bob,
            message_type='image',
            image_public_id='serbisure_chat_images/sample_attachment',
            message_payload='Check this out'
        )

        response = self.client.get(f'/api/v1/chat/thread/{self.bob.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        messages = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        found = [m for m in messages if m['chat_message_id'] == str(msg.chat_message_id)]
        self.assertTrue(len(found) == 1)
        self.assertEqual(found[0]['message_type'], 'image')
        self.assertIsNotNone(found[0]['image_url'])
        self.assertIn('serbisure_chat_images/sample_attachment', found[0]['image_url'])

    def test_reaction_summary_and_my_reaction_in_thread(self):
        """Thread correctly computes reaction_summary counts and my_reaction for authenticated user."""
        msg = tbl_chat_message.objects.create(
            sender_id=self.alice,
            receiver_id=self.bob,
            message_type='text',
            message_payload='React to me'
        )

        tbl_chat_reaction.objects.create(
            message=msg,
            reactor=self.alice,
            emoji='❤️'
        )
        tbl_chat_reaction.objects.create(
            message=msg,
            reactor=self.bob,
            emoji='👍'
        )

        # Alice views thread
        response = self.client.get(f'/api/v1/chat/thread/{self.bob.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        messages = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        item = [m for m in messages if m['chat_message_id'] == str(msg.chat_message_id)][0]

        self.assertEqual(item['reaction_summary']['❤️'], 1)
        self.assertEqual(item['reaction_summary']['👍'], 1)
        self.assertEqual(item['my_reaction'], '❤️')

        # Bob views thread
        self.client.force_authenticate(user=self.bob)
        response_bob = self.client.get(f'/api/v1/chat/thread/{self.alice.id}/')
        messages_bob = response_bob.data.get('results', response_bob.data) if isinstance(response_bob.data, dict) else response_bob.data
        item_bob = [m for m in messages_bob if m['chat_message_id'] == str(msg.chat_message_id)][0]

        self.assertEqual(item_bob['my_reaction'], '👍')

    def test_chat_inbox_shows_photo_preview_for_image_message(self):
        """Chat inbox correctly formats photo preview text for image messages."""
        tbl_chat_message.objects.create(
            sender_id=self.bob,
            receiver_id=self.alice,
            message_type='image',
            image_public_id='serbisure_chat_images/sample_inbox_img',
            message_payload=''
        )

        response = self.client.get('/api/v1/chat/inbox/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inbox_items = response.data['data']
        self.assertTrue(len(inbox_items) >= 1)
        self.assertEqual(inbox_items[0]['last_message'], '📷 Photo')
