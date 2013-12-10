try:
    from django.conf.urls import include, patterns, url
except ImportError:
    # Django 1.4
    from django.conf.urls.defaults import include, patterns, url

from scarlet import cms

cms.autodiscover()
urlpatterns = patterns('',
    (r'^admin/', include(cms.site.urls)),
)
