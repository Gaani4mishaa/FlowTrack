"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from core.views import home, login_page, register_page, resident_dashboard
from reports.views import delete_report, edit_report, report_issue, my_reports, report_detail
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('login/', login_page, name='login'),
    path('register/', register_page, name='register'),
    path('dashboard/', resident_dashboard, name='resident_dashboard'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('reports/new/', report_issue, name='report_issue'),
    path('reports/', my_reports, name='my_reports'),
    path('reports/<int:report_id>/edit/', edit_report, name='edit_report'),
    path('reports/<int:report_id>/delete/', delete_report, name='delete_report'),
    path('reports/<int:report_id>/', report_detail, name='report_detail'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)