from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    rule = env.ref('tennis_club_management.rule_res_users_tennis_self', raise_if_not_found=False)
    if rule:
        rule.unlink()

