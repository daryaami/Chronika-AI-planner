from django.urls import path

from .apis import AssistantActionApi, AssistantMessageApi


urlpatterns = [
    path("message/", AssistantMessageApi.as_view(), name="assistant_message"),
    path("action/", AssistantActionApi.as_view(), name="assistant_action"),
]
