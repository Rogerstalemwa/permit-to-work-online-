from django.urls import path
from permits import views as v
urlpatterns = [
    path('', v.index), path('verify/<str:t>', v.index), path('api/verify/<str:t>', v.verify),
    path('api/state', v.state), path('api/setup', v.setup), path('api/login', v.login), path('api/logout', v.logout), path('api/me/pin', v.my_pin), path('api/forgot', v.forgot), path('api/reset', v.reset_pin), path('api/recover', v.recover),
    path('api/serial', v.serial), path('api/permit', v.permit), path('api/draft', v.draft), path('api/photo', v.photo), path('api/notes', v.notes),
    path('api/admin/accounts', v.admin_accounts), path('api/admin/save', v.admin_save), path('api/admin/active', v.admin_active),
    path('api/admin/delete', v.admin_delete), path('api/admin/struct', v.admin_struct), path('api/admin/permit-types', v.admin_permit_types), path('api/admin/log', v.admin_log), path('api/admin/escalation', v.admin_escalation),
    path('api/admin/notice', v.admin_notice), path('api/admin/rams', v.admin_rams), path('api/admin/toolbox', v.admin_toolbox), path('api/admin/export', v.admin_export), path('api/admin/recovery', v.admin_recovery), path('api/admin/testmail', v.admin_testmail), path('api/admin/reset', v.admin_reset),
]
