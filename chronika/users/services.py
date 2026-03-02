import logging
from google_auth.services import GoogleAccessTokens, UserInfo
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

User = get_user_model()

class AuthService:
    def __init__(self, user_info: UserInfo, google_tokens: GoogleAccessTokens):
        self.user_info = user_info
        self.google_tokens = google_tokens

    def authenticate_user(self):
        user, created = self.get_or_create_user()
        tokens = self._generate_jwt(user)
        logger.info("User %s authenticated (created=%s). Tokens generated.", user, created)
        return tokens, user, created
    
    def get_or_create_user(self):
        user, created = User.objects.get_or_create(
            google_id=self.user_info.sub,
            defaults={"email": self.user_info.email, "name": self.user_info.name, "picture": self.user_info.picture}
        )
        if created:
            logger.info("New user created with Google ID: %s", self.user_info.sub)
        else:
            logger.debug("Existing user found for Google ID: %s", self.user_info.sub)
        return user, created

    def _generate_jwt(self, user):
        refresh = RefreshToken.for_user(user)
        tokens = {
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh)
        }
        logger.debug("Generated JWT for user %s: %s", user, tokens)
        return tokens
    
    @staticmethod
    def verify_refresh_token(token_str: str):
        try:
            token = RefreshToken(token_str)
            return token
        except TokenError:
            raise AuthenticationFailed("Invalid or expired refresh token.")
