# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Добавляем поле balance в таблицу res_partner"""
    if not version:
        return
    
    # Проверяем, существует ли уже поле balance
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'res_partner' AND column_name = 'balance'
    """)
    
    if not cr.fetchone():
        # Добавляем поле balance в таблицу res_partner
        cr.execute("""
            ALTER TABLE res_partner 
            ADD COLUMN balance FLOAT DEFAULT 0.0
        """)
        
        # Обновляем существующие записи, устанавливая баланс в 0
        cr.execute("""
            UPDATE res_partner 
            SET balance = 0.0 
            WHERE balance IS NULL
        """)
