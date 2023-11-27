from allauth.socialaccount import providers
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class CustomAccount(ProviderAccount):
    pass


class CustomProvider(OAuth2Provider):

    id = 'customprovider'
    name = 'My Custom OAuth2 Provider'
    account_class = CustomAccount


providers.registry.register(CustomProvider)