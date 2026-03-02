from django.urls import path
from .apis import RefreshJWTView, LogoutView, ProfileView, TokenPingView


urlpatterns = [
    path("refresh/", RefreshJWTView.as_view(), name="token_refresh"),
    path('ping/', TokenPingView.as_view(), name='ping'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
]