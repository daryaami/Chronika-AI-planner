
from django.urls import path

from .apis import GoogleLoginRedirectApi, GoogleLoginApi

app_name = 'google_auth'

urlpatterns = [
    path('redirect/', GoogleLoginRedirectApi.as_view(), name='google_auth_redirect'),
    path('callback/', GoogleLoginApi.as_view(), name='google_callback'),
]
