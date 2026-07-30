from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.core.cache import cache
from .models import tbl_user_profile
from .serializers import UserRegistrationSerializer
import uuid 


class TestUserModels(TestCase):
    
    def test_create_superuser(self):
        """
        Ensure the terminal command can successfully create superadmin
        """

        admin = tbl_user_profile.objects.create_superuser(
            username = "admin_master",
            email="admin@example.com",
            password="StrongPassword123!"
        )

        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertEqual(admin.username, "admin_master")

class TestSerializers(TestCase):
    
    def setUp(self):
        self.valid_data = {
            "email": "test@example.com",
            "password": "StrongPassword123!",
            "first_name": "Juan",
            "middle_name": "Dela",
            "last_name": "Cruz",
            "account_type": "Homeowner"
        }
    
    def test_admin_account_blocked(self):
        """
        Ensure nobody can create an Admin account through the public serializers
        """

        self.valid_data["account_type"] = "Admin"
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())

    def test_password_validation(self):
        """
        Ensure password without number or letters are Rejected
        """
        self.valid_data["password"] = "allletters"
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())

        self.valid_data["password"] = "123456789"
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())

    def test_username_auto_generation(self):
        """
        Ensure the Serializer successfully builds the clean UUID username
        """
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()

        self.assertTrue(user.username.startswith("juandelacruz_"))
        self.assertTrue(user.check_password("StrongPassword123!"))

class TestUserAPIEndpoints(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.register_url = "/api/v1/accounts/register/"
        self.login_url = "/api/v1/accounts/login/"
        cache.clear() 
    
        self.valid_payload = {
            "email": "api@example.com",
            "password": "StrongPassword123!",
            "first_name": "Naruto",
            "last_name": "Uzumaki",
            "account_type": "Homeowner"
        }

        self.idempotency_key  = str(uuid.uuid4())

    def test_registration_require_idempotency_key(self):
        """
        Ensure successful registration and test that double-clinking return the cache
        """

        # 1st Click (Should hit the database and return 201)
        response1 = self.client.post(
            self.register_url,
            self.valid_payload,
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key
        )

        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(tbl_user_profile.objects.count(), 1)

        # 2nd Click (should instally return 201 from the Cache without hitting the DB)
        response2 = self.client.post(
            self.register_url,
            self.valid_payload,
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key 
        )

        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(tbl_user_profile.objects.count(), 1)

    def test_login_success(self):
        """
        Ensure user can get JWT token
        """

        tbl_user_profile.objects.create_user(
            username="testuser",
            email="login@example.com",
            password="password123!"
        )

        response = self.client.post(self.login_url, {
            "email": "login@example.com",
            "password": "password123!"
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_brute_force_protection(self):
        """
        Ensure hacker are locked out after 5 failed attempts
        """

        for i in range(5):
            response = self.client.post(self.login_url, {
                "email": "hacker@example.com",
                "password": "WrongPassword!"
            })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


        # The 6th Attempt should trigger the sliding window Throttle
        response6 = self.client.post(self.login_url, {
            "email":"hacker@example.com",
            "password": "WrongPassword!"
        })

        self.assertEqual(response6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)