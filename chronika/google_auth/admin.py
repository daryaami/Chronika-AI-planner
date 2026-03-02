from django.contrib import admin
from .models import GoogleRefreshToken

class GoogleRefreshTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'refresh_token', 'created_at', 'updated_at')
    exclude = ('created_at', 'updated_at')

admin.site.register(GoogleRefreshToken, GoogleRefreshTokenAdmin)
