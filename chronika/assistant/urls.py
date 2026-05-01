from django.urls import path

from .apis import AssistantActionApi, AssistantClearChatApi, AssistantHistoryApi, AssistantMessageApi


urlpatterns = [
    path("message/", AssistantMessageApi.as_view(), name="assistant_message"),
    path("action/", AssistantActionApi.as_view(), name="assistant_action"),
    path("history/", AssistantHistoryApi.as_view(), name="assistant_history"),
    path("clear/", AssistantClearChatApi.as_view(), name="assistant_clear"),
]
