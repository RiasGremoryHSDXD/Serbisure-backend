from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserRegistrationView, CustomLoginView, ProfileImageUploadView


urlpatterns = [

    # Registration Endpoints
    path('register/', UserRegistrationView.as_view(), name='register'),
    
    # Login Endpoints
    path('login/', CustomLoginView.as_view(), name='login'),

    # Profile Endpoints
    path('profile-image/', ProfileImageUploadView.as_view(), name='profile-image'),

    # Refresh Endpoints (Used when the access token expires to get a new one)
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh')
]