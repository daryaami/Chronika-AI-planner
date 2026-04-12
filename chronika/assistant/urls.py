from django.urls import path

from .apis import AssistantMessageApi


urlpatterns = [
    path("message/", AssistantMessageApi.as_view(), name="assistant_message"),
]
