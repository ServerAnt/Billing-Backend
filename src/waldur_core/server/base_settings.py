"""
Django base settings for Waldur Core.
"""
from datetime import timedelta
import locale
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import warnings

from waldur_core.core import WaldurExtension
from waldur_core.core.metadata import WaldurConfiguration
from waldur_core.server.admin.settings import *  # noqa: F403

encoding = locale.getpreferredencoding()
if encoding.lower() != 'utf-8':
    raise Exception("""Your system's preferred encoding is `{}`, but Waldur requires `UTF-8`.
Fix it by setting the LC_* and LANG environment settings. Example:
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
""".format(encoding))

ADMINS = ()

BASE_DIR = os.path.abspath(os.path.join(os.path.join(os.path.dirname(os.path.dirname(__file__)), '..'), '..'))

DEBUG = False

MEDIA_ROOT = '/media_root/'

MEDIA_URL = '/media/'

ALLOWED_HOSTS = []
SITE_ID = 1
DBTEMPLATES_USE_REVERSION = True
DBTEMPLATES_USE_CODEMIRROR = True

# Application definition
INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.humanize',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'waldur_core.landing',
    'waldur_core.logging',
    'waldur_core.core',
    'waldur_core.permissions',
    'waldur_core.quotas',
    'waldur_core.structure',
    'waldur_core.users',
    'waldur_core.media',

    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_swagger',
    'django_filters',

    'axes',
    'django_fsm',
    'reversion',
    'jsoneditor',
    'modeltranslation',

    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.storage',
    'health_check.contrib.migrations',
    'health_check.contrib.celery_ping',
    'dbtemplates',

    'binary_database_files',
    'netfields',

    'constance',
    'constance.backends.database',
)
INSTALLED_APPS += ADMIN_INSTALLED_APPS  # noqa: F405

MIDDLEWARE = (
    'waldur_core.server.middleware.cors_middleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'waldur_core.logging.middleware.CaptureEventContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
)

REST_FRAMEWORK = {
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'waldur_core.core.authentication.TokenAuthentication',
        'waldur_core.core.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'waldur_core.core.renderers.BrowsableAPIRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'oauth': '10/s',
    },
    'DEFAULT_PAGINATION_CLASS': 'waldur_core.core.pagination.LinkHeaderPagination',
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
    'PAGE_SIZE': 10,
    'EXCEPTION_HANDLER': 'waldur_core.core.views.exception_handler',

    # Return native `Date` and `Time` objects in `serializer.data`
    'DATETIME_FORMAT': None,
    'DATE_FORMAT': None,
    'TIME_FORMAT': None,
    'ORDERING_PARAM': 'o'
}

AUTHENTICATION_BACKENDS = (
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
    'waldur_core.core.authentication.AuthenticationBackend',
)

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

ANONYMOUS_USER_ID = None

CONTEXT_PROCESSORS = (
    'django.template.context_processors.debug',
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
    'django.template.context_processors.i18n',
    'django.template.context_processors.media',
    'django.template.context_processors.static',
    'django.template.context_processors.tz',
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': (os.path.join(BASE_DIR, 'src', 'waldur_core', 'templates'),),
        'OPTIONS': {
            'context_processors': CONTEXT_PROCESSORS,
            'loaders': ADMIN_TEMPLATE_LOADERS + (
                'dbtemplates.loader.Loader',
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ),  # noqa: F405
        },
    },
]

ROOT_URLCONF = 'waldur_core.server.urls'

AUTH_USER_MODEL = 'core.User'

# Session
# https://docs.djangoproject.com/en/2.2/ref/settings/#sessions
SESSION_COOKIE_AGE = 3600
SESSION_SAVE_EVERY_REQUEST = True

WSGI_APPLICATION = 'waldur_core.server.wsgi.application'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'src', 'waldur_core', 'locale'),
)

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/
STATIC_URL = '/static/'

# Celery
CELERY_BROKER_URL = 'redis://localhost'
CELERY_RESULT_BACKEND = 'redis://localhost'

CELERY_TASK_QUEUES = {
    'tasks': {'exchange': 'tasks'},
    'heavy': {'exchange': 'heavy'},
    'background': {'exchange': 'background'},
}
CELERY_TASK_DEFAULT_QUEUE = 'tasks'
CELERY_TASK_ROUTES = ('waldur_core.server.celery.PriorityRouter',)

CACHES = {
    'default': {
        'BACKEND': 'redis_cache.RedisCache',
        'LOCATION': 'redis://localhost',
        'OPTIONS': {
            'DB': 1,
            'PARSER_CLASS': 'redis.connection.HiredisParser',
            'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
            'PICKLE_VERSION': -1,
        },
    },
}

# Regular tasks
CELERY_BEAT_SCHEDULE = {
    'pull-service-properties': {
        'task': 'waldur_core.structure.ServicePropertiesListPullTask',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'pull-service-resources': {
        'task': 'waldur_core.structure.ServiceResourcesListPullTask',
        'schedule': timedelta(hours=1),
        'args': (),
    },
    'pull-service-subresources': {
        'task': 'waldur_core.structure.ServiceSubResourcesListPullTask',
        'schedule': timedelta(hours=2),
        'args': (),
    },
    'check-expired-permissions': {
        'task': 'waldur_core.permissions.check_expired_permissions',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'cancel-expired-invitations': {
        'task': 'waldur_core.users.cancel_expired_invitations',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'cancel_expired_group_invitations': {
        'task': 'waldur_core.users.cancel_expired_group_invitations',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'send-reminder-for-pending-invitations': {
        'task': 'waldur_core.users.send_reminder_for_pending_invitations',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'structure-set-erred-stuck-resources': {
        'task': 'waldur_core.structure.SetErredStuckResources',
        'schedule': timedelta(hours=1),
        'args': (),
    },
    'create_customer_permission_reviews': {
        'task': 'waldur_core.structure.create_customer_permission_reviews',
        'schedule': timedelta(hours=24),
        'args': (),
    },
    'update-custom-quotas': {
        'task': 'waldur_core.quotas.update_custom_quotas',
        'schedule': timedelta(hours=1),
        'args': (),
    },
    'update-standard-quotas': {
        'task': 'waldur_core.quotas.update_standard_quotas',
        'schedule': timedelta(hours=24),
        'args': (),
    },
}

globals().update(WaldurConfiguration().dict())

CONSTANCE_BACKEND = 'constance.backends.database.DatabaseBackend'
CONSTANCE_DBS = "default"
CONSTANCE_SUPERUSER_ONLY = False
CONSTANCE_IGNORE_ADMIN_VERSION_CHECK = True
CONSTANCE_ADDITIONAL_FIELDS = {
    'image_field': ['django.forms.ImageField', {'required': False}]
}
CONSTANCE_CONFIG = {
    'SITE_NAME': ('Waldur', 'Human-friendly name of the Waldur deployment.'),
    'SITE_DESCRIPTION': (
        'Your single pane of control for managing projects, teams and resources in a self-service manner.',
        'Description of the Waldur deployment.'
    ),
    'SITE_ADDRESS': ('', 'It is used in marketplace order header.'),
    'SITE_EMAIL': ('', 'It is used in marketplace order header and UI footer.'),
    'SITE_PHONE': ('', 'It is used in marketplace order header and UI footer.'),
    'CURRENCY_NAME': ('EUR', 'It is used in marketplace order details and invoices for currency formatting.'),
    'DOCS_URL': ('', 'Renders link to docs in header'),
    'SHORT_PAGE_TITLE': ('Waldur', 'It is used as prefix for page title.'),
    'FULL_PAGE_TITLE': (
        'Waldur | Cloud Service Management',
        "It is used as default page title if it's not specified explicitly."
    ),
    'BRAND_COLOR': ('#3a8500', 'Hex color definition is used in HomePort landing page for login button.'),
    'BRAND_LABEL_COLOR': ('#000000', 'Hex color definition is used in HomePort landing page for font color of login button.'),
    'HERO_LINK_LABEL': (
        '',
        'Label for link in hero section of HomePort landing page. It can be lead to support site or blog post.'
    ),
    'HERO_LINK_URL': ('', 'Link URL in hero section of HomePort landing page.'),
    'SUPPORT_PORTAL_URL': ('', 'Link URL to support portal. Rendered as a shortcut on dashboard'),
    # images, logos, favicons
    'POWERED_BY_LOGO': ('', 'The image rendered at the bottom of login menu in HomePort.', 'image_field'),
    'HERO_IMAGE': ('', 'The image rendered at hero section of HomePort landing page.', 'image_field'),
    'SIDEBAR_LOGO': ('', 'The image rendered at the top of sidebar menu in HomePort.', 'image_field'),
    'SIDEBAR_LOGO_MOBILE': (
        '', 'The image rendered at the top of mobile sidebar menu in HomePort.', 'image_field'
    ),
    'SITE_LOGO': ('', 'The image used in marketplace order header.', 'image_field'),
    'LOGIN_LOGO': ('', 'A custom .png image file for login page', 'image_field'),
    'FAVICON': ('', 'A custom favicon .png image file', 'image_field'),

}

CONSTANCE_CONFIG_FIELDSETS = {
    'Whitelabeling settings (Text, links, etc)': (
        'SITE_NAME', 'SITE_DESCRIPTION', 'SITE_ADDRESS', 'SITE_EMAIL', 'SITE_PHONE',
        'CURRENCY_NAME', 'DOCS_URL', 'SHORT_PAGE_TITLE', 'FULL_PAGE_TITLE',
        'BRAND_COLOR', 'BRAND_LABEL_COLOR', 'HERO_LINK_LABEL', 'HERO_LINK_URL', 'SUPPORT_PORTAL_URL',
    ),
    'Whitelabeling settings (Logos, images, favicons)': (
        'SITE_LOGO', 'SIDEBAR_LOGO', 'SIDEBAR_LOGO_MOBILE', 'POWERED_BY_LOGO', 'HERO_IMAGE', 'LOGIN_LOGO', 'FAVICON'
    )
}

for ext in WaldurExtension.get_extensions():
    INSTALLED_APPS += (ext.django_app(),)

    for name, task in ext.celery_tasks().items():
        if name in CELERY_BEAT_SCHEDULE:
            warnings.warn(
                "Celery beat task %s from Waldur extension %s "
                "is overlapping with primary tasks definition" % (name, ext.django_app()))
        else:
            CELERY_BEAT_SCHEDULE[name] = task

    for key, val in ext.Settings.__dict__.items():
        if not key.startswith('_'):
            globals()[key] = val

    ext.update_settings(globals())


# Swagger
SWAGGER_SETTINGS = {
    # USE_SESSION_AUTH parameter should be equal to DEBUG parameter.
    # If it is True, LOGIN_URL and LOGOUT_URL must be specified.
    'USE_SESSION_AUTH': False,
    'APIS_SORTER': 'alpha',
    'JSON_EDITOR': True,
    'SECURITY_DEFINITIONS': {
        'api_key': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
        },
    },
}

AXES_ONLY_USER_FAILURES = True
AXES_COOLOFF_TIME = timedelta(minutes=10)
AXES_FAILURE_LIMIT = 5

# Django File Storage API
DEFAULT_FILE_STORAGE = 'binary_database_files.storage.DatabaseStorage'
DB_FILES_AUTO_EXPORT_DB_TO_FS = False
DATABASE_FILES_URL_METHOD = 'URL_METHOD_2'

# Disable excessive xmlschema and django-axes logging
import logging
logging.getLogger("xmlschema").propagate = False
logging.getLogger("axes").propagate = False

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LANGUAGES = (
    ('en', 'English'),
    ('et', 'Eesti'),
    ('lt', 'Lietuvių'),
    ('lv', 'Latviešu'),
    ('ru', 'Русский'),
    ('it', 'Italiano'),
    ('de', 'Deutsch'),
    ('da', 'Dansk'),
    ('sv', 'Svenska'),
    ('es', 'Español'),
    ('fr', 'Français'),
    ('nb', 'Norsk'),
    ('ar', 'العربية'),
    ('cs', 'Čeština'),
)

LANGUAGE_CHOICES = ['en', 'et', 'lt', 'lv', 'ru', 'it', 'de', 'da', 'sv', 'es', 'fr', 'nb', 'ar', 'cs']
