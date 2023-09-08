from django.middleware.csrf import get_token
from django.http import HttpResponse
import json

def getToken(request):
    token = get_token(request)
    print(request.COOKIES)
    return HttpResponse(json.dumps({'token': token}), content_type="application/json,charset=utf-8")
