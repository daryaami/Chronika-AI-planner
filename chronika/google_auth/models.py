from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class GoogleRefreshToken(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="google_refresh_token"
    )
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Google Refresh Token for {self.user.email}"
    
    class Meta:
        verbose_name = "Google Refresh Token"
        verbose_name_plural = "Google Refresh Tokens"
        ordering = ["-created_at"]
