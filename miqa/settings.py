# flake8: noqa N802
from __future__ import annotations
import os
from pathlib import Path

from composed_configuration import (
    ComposedConfiguration,
    ConfigMixin,
    DevelopmentBaseConfiguration,
    HerokuProductionBaseConfiguration,
    HttpsMixin,
    ProductionBaseConfiguration,
    SmtpEmailMixin,
    TestingBaseConfiguration,
    S3StorageMixin,
)
from composed_configuration._configuration import _BaseConfiguration
from configurations import values


class MiqaMixin(ConfigMixin):
    WSGI_APPLICATION = 'miqa.wsgi.application'
    ROOT_URLCONF = 'miqa.urls'
    HOMEPAGE_REDIRECT_URL = values.Value(environ=True, default=None)

    BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

    # Django logins should only last for 30 minutes, the same as the duration of the OAuth token.
    SESSION_COOKIE_AGE = 1800

    # This is required for the /api/v1/logout/ view to have access to the session cookie.
    CORS_ALLOW_CREDENTIALS = True

    CORS_ORIGIN_ALLOW_ALL = True
    CORS_ORIGIN_WHITELIST = (
      os.getenv('client_host'),
    )
    
    # CORS_ALLOWED_ORIGINS = [os.getenv('client_host')]
    # CORS_ALLOW_HEADERS = ('*')
    # CORS_EXPOSE_HEADERS = ['Set-Cookie']
    # CORS_ALLOW_METHODS = [
    # '*'
    # ]
    # SESSION_COOKIE_SECURE = True

    # MIQA-specific settings
    ZARR_SUPPORT = False
    S3_SUPPORT = True

    # Demo mode is for app.miqaweb.io (Do not enable for normal instances)
    DEMO_MODE = values.BooleanValue(environ=True, default=False)
    # ITRUST Authentication
    ITRUST_MODE = values.BooleanValue(environ=True, default=True)
    # It is recommended to enable the following for demo mode:
    NORMAL_USERS_CAN_CREATE_PROJECTS = values.BooleanValue(environ=True, default=False)
    # Enable the following to replace null creation times for scan decisions with import time
    REPLACE_NULL_CREATION_DATETIMES = values.BooleanValue(environ=True, default=False)

    # Override default signup sheet to ask new users for first and last name
    ACCOUNT_FORMS = {'signup': 'miqa.core.rest.accounts.AccountSignupForm'}

    @staticmethod
    def before_binding(configuration: ComposedConfiguration) -> None:
        # Install local apps first, to ensure any overridden resources are found first
        configuration.INSTALLED_APPS = [
            'miqa.core.apps.CoreConfig',
            'auth_style',
            'debug_toolbar',
        ] + configuration.INSTALLED_APPS

        # Install additional apps
        configuration.INSTALLED_APPS += [
            's3_file_field',
            'guardian',
            'allauth.socialaccount.providers.openid_connect'
        ]

        configuration.TEMPLATES[0]['DIRS'] += [
            Path(configuration.BASE_DIR, 'miqa/templates/'),
        ]

        # guardian's authentication backend
        configuration.AUTHENTICATION_BACKENDS += [
            'guardian.backends.ObjectPermissionBackend',
        ]

        # disable guardian anonymous user
        configuration.ANONYMOUS_USER_NAME = None

        # oauth session
        configuration.OAUTH2_PROVIDER['ACCESS_TOKEN_EXPIRE_SECONDS'] = 1800  # 30 minutes

        # drf
        configuration.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = [
            'rest_framework.permissions.IsAuthenticated'
        ]
        configuration.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] += [
            'rest_framework.authentication.TokenAuthentication'
        ]
        configuration.REST_FRAMEWORK[
            'EXCEPTION_HANDLER'
        ] = 'miqa.core.rest.exceptions.custom_exception_handler'

        configuration.GLOBAL_SETTINGS = {
            # 'DATASET': '/scratch/IVG_scratch/ziaeid2/sarcoma/Dataset/',
            # 'DATASET': '/var/opt/MIQA/miqa/samples/WSI/',
            'DATASET': '/mnt/hpc/webdata/server/fsivgl-rms01d/shared_data/WSI/',
            'SHARED_PARTITION': '/mnt/hpc/webdata/server/' + os.getenv('host') + '/',
            'MODULES': {
                'SEGMENTATION': {
                    'color': '#008ffb',
                    'script': 'infer_wsi.py',
                    'output_field': '', # name of score in script output file
                    'score_name': 'seg_highest',
                },
                'MYOD1': {
                    'color': '#00e396',
                    'script': 'myod1.py',
                    'output_field': 'Positive Score',
                    'score_name': 'myod1_score'
                },
                'SURVIVABILITY': {
                    'color': '#feb019',
                    'script': 'survivability.py',
                    'output_field': 'secondBest',
                    'score_name': 'surv_score'
                },
                'TP53': {
                    'color': '#ff4560',
                    'script': 'tp53_inference.py',
                    'output_field': 'tp53 score',
                    'score_name': 'tp53_score'
                },
                'SUBTYPE': {
                    'color': '#775dd0',
                    'script': 'subtype_inference.py',
                    'output_field': 'Subtype',
                    'score_name': 'subtype_score'
                }
            },
            'COHORT_MYOD1': '/mnt/hpc/webdata/server/' + os.getenv('host') + '/data/rms_myod1_cohort.csv',
            'COHORT_SURVIVABILITY': '/mnt/hpc/webdata/server/' + os.getenv('host') + '/data/rms_survivability_cohort.csv'
        }

        configuration.SESSIONS_ENGINE='django.contrib.sessions.backends.cache'

        configuration.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
                'LOCATION': '127.0.0.1:11211',
            }
        }
        configuration.MIDDLEWARE = [
            "corsheaders.middleware.CorsMiddleware",
            "django.middleware.common.CommonMiddleware",
        ] + configuration.MIDDLEWARE
class DevelopmentConfiguration(MiqaMixin, DevelopmentBaseConfiguration):
    HOMEPAGE_REDIRECT_URL = values.Value(environ=True, default=os.getenv('client_host') + '/rms2_web/index.html')
    DevelopmentBaseConfiguration.SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
            "SERVERS": [
                {
                    "id": "itrust",  # 30 characters or less
                    "name": "ITRUST server",
                    "server_url": os.getenv('server_url'),
                    "token_auth_method": "code",
                    "APP": {
                        "client_id": os.getenv('client_id'),
                        "secret": os.getenv('client_secret'),
                    },
                },
            ]
        }
    }
    DevelopmentBaseConfiguration.STORAGES.update(
            {
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "LOCATION": "/mnt/docker/rms2_local"
                }
            }
        )
    ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
    ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
    ACCOUNT_EMAIL_REQUIRED = True 
    ACCOUNT_UNIQUE_EMAIL = True 
    ACCOUNT_USERNAME_REQUIRED = True 
    ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
    ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'

    SOCIALACCOUNT_LOGIN_ON_GET = True
    SOCIALACCOUNT_EMAIL_REQUIRED = False
    SOCIALACCOUNT_AUTO_SIGNUP = True

    SOCIALACCOUNT_EMAIL_VERIFICATION = None

    MIQA_URL_PREFIX = values.Value(environ=True, default='/')
    WHITENOISE_STATIC_PREFIX = '/static/'
    
    ALLOWED_HOSTS = ["*"]
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    CSRF_TRUSTED_ORIGINS = values.ListValue(environ=True, default=['https://fsabcl-onc03d.ncifcrf.gov/'])
    CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
    CSRF_COOKIE_NAME = 'csrftoken'
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = None
    SESSION_COOKIE_SAMESITE = None

    # True for remote minio
    MINIO_STORAGE_USE_HTTPS = True
    USE_X_FORWARDED_HOST = True
    @property
    def LOGIN_URL(self):
        """LOGIN_URL also needs to be behind MIQA_URL_PREFIX."""
        return os.getenv('client_host') + '/rms2/login.html'
    @property
    def STATIC_URL(self):
        """Prepend the MIQA_URL_PREFIX to STATIC_URL."""
        return f'{Path(self.MIQA_URL_PREFIX) / "rms2/static"}/'

    @property
    def LOGIN_REDIRECT_URL(self):
        # Do not forget to set application in django with corresponding redirect url (with '/')
        """When login is completed without `next` set, redirect to MIQA_URL_PREFIX."""
        return os.getenv('client_host') + '/rmsv2/index.html'

    @staticmethod
    def before_binding(configuration: ComposedConfiguration) -> None:
        # Register static files as templates so that the index.html built by the client is
        # available as a template.
        # This should be STATIC_ROOT, but that is bound as a property which cannot be evaluated
        # at this point, so we make this assumption about staticfiles instead.
        configuration.TEMPLATES[0]['DIRS'] += [
            configuration.BASE_DIR / 'staticfiles',
        ]


class TestingConfiguration(MiqaMixin, TestingBaseConfiguration):
    # We would like to test that the celery tasks work correctly when triggered from the API
    CELERY_TASK_ALWAYS_EAGER = True

class PyppeteerTestingConfiguration(MiqaMixin, DevelopmentBaseConfiguration):
    # We would like to test that the celery tasks work correctly when triggered from the API
    CELERY_TASK_ALWAYS_EAGER = True


class ProductionConfiguration(MiqaMixin, ProductionBaseConfiguration):
    HOMEPAGE_REDIRECT_URL = values.Value(environ=True, default=os.getenv('client_host') + '/rms2_web/index.html')
    ProductionBaseConfiguration.SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
            "SERVERS": [
                {
                    "id": "itrust",  # 30 characters or less
                    "name": "ITRUST server",
                    "server_url": os.getenv('server_url'),
                    "token_auth_method": "code",
                    "APP": {
                        "client_id": os.getenv('client_id'),
                        "secret": os.getenv('client_secret'),
                    },
                },
            ]
        }
    }

    ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
    ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
    ACCOUNT_EMAIL_REQUIRED = True 
    ACCOUNT_UNIQUE_EMAIL = True 
    ACCOUNT_USERNAME_REQUIRED = True 
    ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
    ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'

    SOCIALACCOUNT_LOGIN_ON_GET = True
    SOCIALACCOUNT_EMAIL_REQUIRED = False
    SOCIALACCOUNT_AUTO_SIGNUP = True

    SOCIALACCOUNT_EMAIL_VERIFICATION = None

    MIQA_URL_PREFIX = values.Value(environ=True, default='/')
    WHITENOISE_STATIC_PREFIX = '/static/'
    
    ALLOWED_HOSTS = ["*"]
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    CSRF_TRUSTED_ORIGINS = values.ListValue(environ=True, default=['https://clinomics.ccr.cancer.gov/', 'https://fsabcl-onc03p.ncifcrf.gov/'])
    CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
    CSRF_COOKIE_NAME = 'csrftoken'
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = None
    SESSION_COOKIE_SAMESITE = None

    # True for remote minio
    # MINIO_STORAGE_USE_HTTPS = True
    USE_X_FORWARDED_HOST = True
    @property
    def LOGIN_URL(self):
        """LOGIN_URL also needs to be behind MIQA_URL_PREFIX."""
        return os.getenv('client_host') +'/rmsv2/login.html'
    @property
    def STATIC_URL(self):
        """Prepend the MIQA_URL_PREFIX to STATIC_URL."""
        return f'{Path(self.MIQA_URL_PREFIX) / "rmsv2/static"}/'

    @property
    def LOGIN_REDIRECT_URL(self):
        # Do not forget to set application in django with corresponding redirect url (with '/')
        """When login is completed without `next` set, redirect to MIQA_URL_PREFIX."""
        # return os.getenv('client_host') + '/rms2'
        # return self.MIQA_URL_PREFIX
        return f'{os.getenv("client_host") / "rmsv2/index.html"}/'

    @staticmethod
    def before_binding(configuration: ComposedConfiguration) -> None:
        # Register static files as templates so that the index.html built by the client is
        # available as a template.
        # This should be STATIC_ROOT, but that is bound as a property which cannot be evaluated
        # at this point, so we make this assumption about staticfiles instead.
        configuration.TEMPLATES[0]['DIRS'] += [
            configuration.BASE_DIR / 'staticfiles',
        ]



class DockerComposeProductionConfiguration(
    MiqaMixin,
    SmtpEmailMixin,
    HttpsMixin,
    S3StorageMixin,
    _BaseConfiguration,
):
    """For the production deployment using docker-compose."""

    MIQA_URL_PREFIX = values.Value(environ=True, default='/')

    # Configure connection to S3 bucket by setting the following environment variables:
    # AWS_DEFAULT_REGION
    # AWS_ACCESS_KEY_ID
    # AWS_SECRET_ACCESS_KEY
    # DJANGO_STORAGE_BUCKET_NAME

    # Needed to support the reverse proxy configuration
    USE_X_FORWARDED_HOST = True

    @property
    def STATIC_URL(self):
        """Prepend the MIQA_URL_PREFIX to STATIC_URL."""
        return f'{Path(self.MIQA_URL_PREFIX) / "static"}/'

    @property
    def FORCE_SCRIPT_NAME(self):
        """
        Set FORCE_SCRIPT_NAME to MIQA_URL_PREFIX, a more user-friendly name.

        This is necessary so that {url} blocks in templates include the MIQA_URL_PREFIX.
        Without it, links in the admin console would not have the prefix, and would not resolve.
        """
        return self.MIQA_URL_PREFIX

    # Whitenoise needs to serve the static files from /static/, even though Django needs to think
    # that they are served from {MIQA_URL_PREFIX}/static/. The nginx server will strip away the
    # prefix from incoming requests.
    WHITENOISE_STATIC_PREFIX = '/static/'

    @property
    def LOGIN_URL(self):
        """LOGIN_URL also needs to be behind MIQA_URL_PREFIX."""
        return str(Path(self.MIQA_URL_PREFIX) / 'accounts' / 'login') + '/'

    @property
    def LOGIN_REDIRECT_URL(self):
        """When login is completed without `next` set, redirect to MIQA_URL_PREFIX."""
        return self.MIQA_URL_PREFIX

    # We trust the reverse proxy to redirect HTTP traffic to HTTPS
    SECURE_SSL_REDIRECT = False

    # This must be set when deployed behind a proxy
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # If nginx settings include an upstream definition, then the Host HTTP field may not match the
    # Referrer HTTP field, which causes Django to reject all non-safe HTTP operations as a CSRF
    # safeguard.
    # To circumvent this, include the expected value of the Referrer field in this setting.
    CSRF_TRUSTED_ORIGINS = values.ListValue(environ=True, default=[])

    @staticmethod
    def before_binding(configuration: ComposedConfiguration) -> None:
        # Register static files as templates so that the index.html built by the client is
        # available as a template.
        # This should be STATIC_ROOT, but that is bound as a property which cannot be evaluated
        # at this point, so we make this assumption about staticfiles instead.
        configuration.TEMPLATES[0]['DIRS'] += [
            configuration.BASE_DIR / 'staticfiles',
        ]


class HerokuProductionConfiguration(MiqaMixin, HerokuProductionBaseConfiguration):
    ZARR_SUPPORT = False
