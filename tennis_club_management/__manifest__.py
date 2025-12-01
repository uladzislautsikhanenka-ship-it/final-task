# -*- coding: utf-8 -*-
{
    'name': 'Tennis Club Management',
    'version': '18.0.1.0.18',
    'category': 'Sports',
    'summary': 'Система управления сетью теннисных клубов',
    'description': """
        Модуль для управления сетью теннисных клубов
        ===========================================
        
        Основные возможности:
        * Управление спортивными центрами и теннисными кортами
        * Система записи на тренировки
        * Финансовый учет и отчетность
        * Интеграция с Telegram ботом
    """,
    'author': 'Tennis Club Management',
    'website': 'https://www.tennisclub.com',
    'depends': [
        'base',
        'web',
        'hr',
        'calendar',
        'mail',
    ],
    'assets': {
        'web.assets_backend': [
            'tennis_club_management/static/src/js/trainer_upcoming_trainings.js',
            'tennis_club_management/static/src/xml/trainer_upcoming_trainings.xml',
            'tennis_club_management/static/src/js/plus_button_menu.js',
            'tennis_club_management/static/src/js/training_booking_date_selection.js',
            'tennis_club_management/static/src/js/training_booking_time_selection.js',
            'tennis_club_management/static/src/js/training_booking_timer.js',
            'tennis_club_management/static/src/js/training_booking_participants.js',
            'tennis_club_management/static/src/js/trainer_availability_calendar.js',
            'tennis_club_management/static/src/css/trainer_availability_calendar.css',
            'tennis_club_management/static/src/css/pending_approvals_badge.css',
        ],
    },
    'data': [
        'security/tennis_club_security.xml',
        'security/ir.model.access.csv',
        'data/tennis_club_users.xml',
        'data/init_balance_field.xml',
        'data/sequence_data.xml',
        'data/training_weekday_data.xml',
        'data/remove_settings_action.xml',
        'data/training_reminders_cron.xml',
        'views/trainer_availability_views.xml',
        'views/trainer_availability_wizard_views.xml',
        'views/training_booking_views.xml',
        'views/training_calendar_views.xml',
        'views/trainer_revenue_report_wizard_views.xml',
        'views/sports_center_analytics_views.xml',
        'report/full_analytics_report.xml',
        'views/full_analytics_views.xml',
        'report/trainer_revenue_report.xml',
        'views/sports_center_employee_views.xml',
        'views/sports_center_views.xml',
        'views/tennis_court_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/training_type_views.xml',
        'views/training_group_views.xml',
        'views/sports_center_training_price_views.xml',
        'views/dashboard_actions.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
