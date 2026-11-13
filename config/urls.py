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
from core.views import (
    admin_dashboard,
    admin_organization_form,
    admin_organizations,
    admin_report_detail,
    admin_reports,
    admin_user_create,
    admin_user_detail,
    admin_user_edit,
    admin_user_password_reset,
    admin_users,
    admin_organization_detail,
    admin_work_order_detail,
    admin_work_orders,
    home,
    login_page,
    register_page,
    resident_dashboard,
)
from maintenance.views import (
    assign_engineer,
    engineer_work_order_detail,
    engineer_work_orders,
)
from reports.views import (
    delete_report,
    edit_report,
    manager_dashboard,
    manager_report_detail,
    manager_work_orders,
    my_reports,
    organization_report_queue,
    report_detail,
    report_issue,
)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('login/', login_page, name='login'),
    path('register/', register_page, name='register'),
    path('dashboard/', resident_dashboard, name='resident_dashboard'),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/users/', admin_users, name='admin_users'),
    path('admin-dashboard/users/new/', admin_user_create, name='admin_user_create'),
    path('admin-dashboard/users/<int:user_id>/edit/', admin_user_edit, name='admin_user_edit'),
    path('admin-dashboard/users/<int:user_id>/reset-password/', admin_user_password_reset, name='admin_user_password_reset'),
    path('admin-dashboard/users/<int:user_id>/', admin_user_detail, name='admin_user_detail'),
    path('admin-dashboard/organizations/', admin_organizations, name='admin_organizations'),
    path('admin-dashboard/organizations/new/', admin_organization_form, name='admin_organization_create'),
    path('admin-dashboard/organizations/<int:organization_id>/edit/', admin_organization_form, name='admin_organization_edit'),
    path('admin-dashboard/organizations/<int:organization_id>/', admin_organization_detail, name='admin_organization_detail'),
    path('admin-dashboard/reports/', admin_reports, name='admin_reports'),
    path('admin-dashboard/reports/<int:report_id>/', admin_report_detail, name='admin_report_detail'),
    path('admin-dashboard/work-orders/', admin_work_orders, name='admin_work_orders'),
    path('admin-dashboard/work-orders/<int:work_order_id>/', admin_work_order_detail, name='admin_work_order_detail'),
    path('manager-dashboard/', manager_dashboard, name='manager_dashboard'),
    path('manager-dashboard/work-orders/', manager_work_orders, name='manager_work_orders'),
    path('engineer-dashboard/', engineer_work_orders, name='engineer_dashboard'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('reports/new/', report_issue, name='report_issue'),
    path('reports/', my_reports, name='my_reports'),
    path('reports/<int:report_id>/edit/', edit_report, name='edit_report'),
    path('reports/<int:report_id>/delete/', delete_report, name='delete_report'),
    path('reports/<int:report_id>/', report_detail, name='report_detail'),
    path('operations/reports/', organization_report_queue, name='organization_report_queue'),
    path('operations/reports/<int:report_id>/', manager_report_detail, name='manager_report_detail'),
    path('operations/reports/<int:report_id>/assign/', assign_engineer, name='assign_engineer'),
    path('maintenance/work-orders/', engineer_work_orders, name='engineer_work_orders'),
    path('maintenance/work-orders/<int:work_order_id>/', engineer_work_order_detail, name='engineer_work_order_detail'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)