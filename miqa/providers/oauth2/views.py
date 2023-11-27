from allauth.socialaccount.providers.oauth2.views import (OAuth2Adapter, OAuth2LoginView, OAuth2CallbackView)
from .provider import CustomProvider


class OAuth2AdapterRMS(OAuth2Adapter):
    provider_id = CustomProvider.id
    def get_callback_url(self, request, app):
        callback_url = '/rms2' + reverse(self.provider_id + "_callback")
        protocol = self.redirect_uri_protocol
        return build_absolute_uri(request, callback_url, protocol)

oauth2_login = OAuth2LoginView.adapter_view(OAuth2AdapterRMS)
oauth2_callback = OAuth2CallbackView.adapter_view(OAuth2AdapterRMS)