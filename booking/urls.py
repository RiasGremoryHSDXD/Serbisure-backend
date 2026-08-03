from django.urls import path
from .views import BookingView

urlpatterns = [
    path('post/', BookingView.as_view(), name='booking-post')
]