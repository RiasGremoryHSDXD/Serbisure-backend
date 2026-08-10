from django.urls import path
from .views import BookingView, BookingFeedView

urlpatterns = [
    path('post/', BookingView.as_view(), name='booking-post'),
    path('feed/', BookingFeedView.as_view(), name='booking-feed')
]