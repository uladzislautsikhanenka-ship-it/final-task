from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Partner = env['res.partner'].sudo()
    
    # Добавляем поле is_employee в базу данных, если его еще нет
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'res_partner' AND column_name = 'is_employee'
    """)
    
    if not cr.fetchone():
        print("Добавляем поле is_employee в таблицу res_partner...")
        cr.execute("""
            ALTER TABLE res_partner 
            ADD COLUMN is_employee BOOLEAN DEFAULT FALSE
        """)
        cr.commit()
        print("Поле is_employee успешно добавлено в таблицу res_partner")
    else:
        print("Поле is_employee уже существует в таблице res_partner")
    
    # Обновляем поле is_employee для всех партнеров
    print("Обновляем поле is_employee для всех партнеров...")
    Partner._update_is_employee_for_all()
    cr.commit()
    print("Миграция завершена. Поле is_employee обновлено для всех партнеров.")


