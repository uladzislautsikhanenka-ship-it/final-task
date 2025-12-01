# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Добавляет поле sports_center_id в таблицу res_partner"""
    cr.execute("""
        ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS sports_center_id INTEGER;
    """)
    
    # Добавляем внешний ключ
    try:
        cr.execute("""
            ALTER TABLE res_partner ADD CONSTRAINT fk_res_partner_sports_center 
            FOREIGN KEY (sports_center_id) REFERENCES sports_center(id) ON DELETE SET NULL;
        """)
    except Exception:
        # Внешний ключ уже существует
        pass
    
    # Создаем индекс
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_res_partner_sports_center_id ON res_partner(sports_center_id);
    """)
