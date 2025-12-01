from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    telegram_bot_token = fields.Char(
        string='Telegram Bot Token',
        config_parameter='tennis_club.telegram_bot_token',
        help='Токен Telegram бота, используемого для отправки уведомлений клиентам.'
    )
    telegram_api_base_url = fields.Char(
        string='API Telegram',
        default='https://api.telegram.org',
        config_parameter='tennis_club.telegram_api_base_url',
        help='Базовый URL API Telegram. По умолчанию https://api.telegram.org'
    )


