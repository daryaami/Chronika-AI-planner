from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

def get_user_by_email(email):
    """
    Возвращает пользователя по email, если он существует, иначе None.
    """
    try:
        return get_user_model().objects.get(email=email)
    except ObjectDoesNotExist:
        return None
    

def get_user_by_google_id(google_id):
    """
    Возвращает пользователя по google_id, если он существует, иначе None.
    """
    try:
        return get_user_model().objects.get(google_id=google_id)
    except ObjectDoesNotExist:
        return None