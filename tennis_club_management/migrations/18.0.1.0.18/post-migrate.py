# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Добавляем поле group_id в базу данных, если его еще нет
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'training_booking' AND column_name = 'group_id'
    """)
    
    if not cr.fetchone():
        print("Добавляем поле group_id в таблицу training_booking...")
        cr.execute("""
            ALTER TABLE training_booking 
            ADD COLUMN group_id INTEGER
        """)
        
        # Добавляем внешний ключ, если таблица training_group существует
        cr.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'training_group'
        """)
        
        if cr.fetchone():
            cr.execute("""
                ALTER TABLE training_booking 
                ADD CONSTRAINT training_booking_group_id_fkey 
                FOREIGN KEY (group_id) 
                REFERENCES training_group(id) 
                ON DELETE SET NULL
            """)
        
        cr.commit()
        print("Поле group_id успешно добавлено в таблицу training_booking")
    else:
        print("Поле group_id уже существует в таблице training_booking")
    
    print("Миграция завершена.")





