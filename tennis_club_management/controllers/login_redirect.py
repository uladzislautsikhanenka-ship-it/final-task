import werkzeug.urls

from odoo.addons.web.controllers.home import Home
from odoo.http import request


class TennisLoginRedirect(Home):
    def _login_redirect(self, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)

        if user.exists():
            internal_group = request.env.ref('base.group_user', raise_if_not_found=False)
            if internal_group and not user.has_group('base.group_user'):
                user.write({'groups_id': [(4, internal_group.id)]})

            manager_group = request.env.ref('tennis_club_management.group_tennis_manager', raise_if_not_found=False)
            director_group = request.env.ref('tennis_club_management.group_tennis_director', raise_if_not_found=False)
            trainer_group = request.env.ref('tennis_club_management.group_tennis_trainer', raise_if_not_found=False)
            settings_group = request.env.ref('tennis_club_management.group_tennis_settings_access', raise_if_not_found=False)

            employee = request.env['hr.employee'].sudo().search([
                ('user_id', '=', user.id)
            ], limit=1)
            if employee:
                employee._sync_role_user_accounts()
            elif trainer_group and user.has_group('tennis_club_management.group_tennis_trainer'):
                employee = request.env['hr.employee'].sudo().ensure_employee_for_user(user)
                if employee:
                    employee._sync_role_user_accounts()
            elif user.login == 'trainer':
                if settings_group and user.has_group('tennis_club_management.group_tennis_settings_access'):
                    user.with_context({}).write({'groups_id': [(3, settings_group.id)]})
                remove_groups = []
                if manager_group and user.has_group('tennis_club_management.group_tennis_manager'):
                    remove_groups.append((3, manager_group.id))
                if director_group and user.has_group('tennis_club_management.group_tennis_director'):
                    remove_groups.append((3, director_group.id))
                if remove_groups:
                    user.with_context({}).write({'groups_id': remove_groups})
                if trainer_group and not user.has_group('tennis_club_management.group_tennis_trainer'):
                    user.with_context({}).write({'groups_id': [(4, trainer_group.id)]})
            
            # Удаляем группу настроек у всех тренеров при каждом логине
            if trainer_group and settings_group and user.has_group('tennis_club_management.group_tennis_trainer'):
                if user.has_group('tennis_club_management.group_tennis_settings_access'):
                    user.with_context({}).write({'groups_id': [(3, settings_group.id)]})
            
            if not user.company_id:
                company = request.env.company
                commands = []
                if company:
                    commands.append((4, company.id))
                if commands:
                    user.with_context({}).write({'company_ids': commands})
                    user.with_context({}).write({'company_id': company.id if company else False})

        if redirect:
            return redirect

        if user.exists() and user._is_internal():
            return '/odoo'

        url = user._mfa_url()
        if redirect and url:
            parsed = werkzeug.urls.url_parse(url)
            qs = parsed.decode_query()
            qs['redirect'] = redirect
            return parsed.replace(query=werkzeug.urls.url_encode(qs)).to_url()
        return url or '/web/login_successful'

