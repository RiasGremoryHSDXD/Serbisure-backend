from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import UserRegistrationView


urlpatterns = [

    # Registration Endpoints
    path('register/', UserRegistrationView.as_view(), name='register'),
    
    # Login Endpoints
    path('login/', TokenObtainPairView.as_view(), name='login'),

    # Refresh Endpoints (Used when the access token expires to get a new one)
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh')
]