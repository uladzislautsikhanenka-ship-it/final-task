# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Добавляет поле sports_center_id в таблицу res_partner"""
    # Проверяем, существует ли поле
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='res_partner' AND column_name='sports_center_id';
    """)
    
    if not cr.fetchone():
        # Добавляем поле
        cr.execute("""
            ALTER TABLE res_partner ADD COLUMN sports_center_id INTEGER;
        """)
        print("Поле sports_center_id добавлено в таблицу res_partner")
        
        # Создаем индекс
        cr.execute("""
            CREATE INDEX idx_res_partner_sports_center_id ON res_partner(sports_center_id);
        """)
        print("Индекс создан")
    else:
        print("Поле sports_center_id уже существует")
