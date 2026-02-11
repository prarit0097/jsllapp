from django.contrib import admin
from django.urls import include, path

from apps.api.views import dashboard

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.api.urls')),
]