import logging
import base64
import asyncio
import json
import urllib.parse
from typing import Optional

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from xmlrpc import client as xmlrpc_client

from config import load_config, validate_config


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
user_partner_map: dict[int, int] = {}


class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_email = State()


class BookingStates(StatesGroup):
    choosing_center = State()
    has_favorite_trainer = State() 
    choosing_type = State()
    choosing_trainer = State()
    choosing_court = State()
    choosing_date = State()
    choosing_start = State()
    choosing_end = State()


class OdooClient:
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.uid: Optional[int] = None
        self.common_proxy = xmlrpc_client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.object_proxy = xmlrpc_client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def authenticate(self) -> int:
        try:
            logger.info(f"Attempting to authenticate to Odoo: db={self.db}, username={self.username}, url={self.url}")
            uid = self.common_proxy.authenticate(self.db, self.username, self.password, {})
            logger.info(f"Authentication result: uid={uid} (type: {type(uid)})")
            if not uid:
                logger.error(f"Authentication failed: uid={uid}, db={self.db}, username={self.username}")
                raise RuntimeError(f"Failed to authenticate to Odoo: invalid credentials or user doesn't exist (db={self.db}, username={self.username})")
            self.uid = uid
            logger.info(f"Successfully authenticated: uid={uid}")
            return uid
        except Exception as e:
            logger.exception(f"Exception during authentication: {e}")
            raise

    def create_partner(self, vals: dict) -> int:
        if self.uid is None:
            self.authenticate()
        partner_id = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'res.partner',
            'create',
            [vals],
        )
        return partner_id

    def write_partner(self, partner_id: int, vals: dict) -> None:
        if not vals:
            return
        if self.uid is None:
            self.authenticate()
        self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'res.partner',
            'write',
            [[partner_id], vals],
        )

    def find_partner_by_phone(self, phone_number: str) -> Optional[dict]:
        if self.uid is None:
            self.authenticate()
        domain = ['|', ('phone', '=', phone_number), ('mobile', '=', phone_number)]
        partners = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'res.partner',
            'search_read',
            [domain, ['id', 'name', 'phone', 'mobile', 'email', 'balance', 'telegram_chat_id']],
            {'limit': 1},
        )
        return partners[0] if partners else None

    def read_partner_balance(self, partner_id: int) -> float:
        if self.uid is None:
            self.authenticate()
        res = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'res.partner',
            'read',
            [[partner_id], ['balance']],
        )
        if res and isinstance(res, list):
            return float(res[0].get('balance') or 0.0)
        return 0.0

    def get_partner_info(self, partner_id: int) -> Optional[dict]:
        """Получает информацию о партнере: ФИО и баланс"""
        if self.uid is None:
            self.authenticate()
        res = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'res.partner',
            'read',
            [[partner_id], ['name', 'balance']],
        )
        if res and isinstance(res, list):
            return res[0]
        return None

    def get_partner_trainings(self, partner_id: int) -> list:
        """Получает список тренировок партнера: завершенные и не начатые"""
        if self.uid is None:
            self.authenticate()
        from datetime import date
        today = date.today().isoformat()
        completed = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'training.booking',
            'search_read',
            [[('customer_id', '=', partner_id), ('state', '=', 'completed')]],
            {
                'fields': ['name', 'booking_date', 'start_time', 'end_time', 'training_type_id', 'trainer_id', 'court_id', 'state'],
                'order': 'booking_date desc, start_time desc',
                'limit': 50,
            },
        )
        not_started = self.object_proxy.execute_kw(
            self.db,
            self.uid,
            self.password,
            'training.booking',
            'search_read',
            [[('customer_id', '=', partner_id), ('state', 'in', ['draft', 'confirmed']), ('booking_date', '>=', today)]],
            {
                'fields': ['name', 'booking_date', 'start_time', 'end_time', 'training_type_id', 'trainer_id', 'court_id', 'state'],
                'order': 'booking_date asc, start_time asc',
                'limit': 50,
            },
        )

        trainings = []
        for training in completed + not_started:
            # Форматируем время
            start_hour = int(training.get('start_time', 0))
            start_min = int((training.get('start_time', 0) - start_hour) * 60)
            end_hour = int(training.get('end_time', 0))
            end_min = int((training.get('end_time', 0) - end_hour) * 60)
            
            training_type_name = training.get('training_type_id', [False, ''])[1] if training.get('training_type_id') else 'Не указан'
            trainer_name = training.get('trainer_id', [False, ''])[1] if training.get('trainer_id') else 'Не указан'
            court_name = training.get('court_id', [False, ''])[1] if training.get('court_id') else 'Не указан'
            
            trainings.append({
                'id': training.get('id'),
                'name': training.get('name', 'Без номера'),
                'date': training.get('booking_date', ''),
                'start_time': f"{start_hour:02d}:{start_min:02d}",
                'end_time': f"{end_hour:02d}:{end_min:02d}",
                'training_type': training_type_name,
                'trainer': trainer_name,
                'court': court_name,
                'state': training.get('state', 'draft'),
            })
        
        return trainings

    def send_booking_request_to_manager(self, partner_id: int, sports_center_id: int) -> bool:
        """Отправляет сообщение менеджеру о необходимости записать пользователя на тренировку"""
        if self.uid is None:
            self.authenticate()
        try:
            # Получаем информацию о клиенте
            partner_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.partner',
                'read',
                [[partner_id], ['name', 'phone', 'mobile', 'email']],
            )
            if not partner_info:
                return False
            
            partner = partner_info[0]
            partner_name = partner.get('name', 'Неизвестный клиент')
            
            # Получаем информацию о спортивном центре и его менеджере
            center_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'sports.center',
                'read',
                [[sports_center_id], ['name', 'manager_id']],
            )
            if not center_info:
                logger.error(f"Sports center {sports_center_id} not found")
                return False
            
            center = center_info[0]
            center_name = center.get('name', 'Неизвестный центр')
            
            if not center.get('manager_id'):
                logger.error(f"Sports center {sports_center_id} ({center_name}) has no manager")
                return False
            
            manager_employee_id = center['manager_id'][0]
            logger.info(f"Found manager employee ID: {manager_employee_id} for center {center_name}")
            
            # Получаем информацию о менеджере (user_id)
            manager_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'hr.employee',
                'read',
                [[manager_employee_id], ['user_id', 'name']],
            )
            if not manager_info or not manager_info[0].get('user_id'):
                logger.error(f"Manager employee {manager_employee_id} not found or has no user_id")
                return False
            
            manager_user_id = manager_info[0]['user_id'][0]
            manager_name = manager_info[0].get('name', 'Менеджер')
            logger.info(f"Found manager user ID: {manager_user_id}, name: {manager_name}")
            
            # Получаем partner_id менеджера
            manager_user_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.users',
                'read',
                [[manager_user_id], ['partner_id', 'name']],
            )
            if not manager_user_info or not manager_user_info[0].get('partner_id'):
                logger.error(f"Manager user {manager_user_id} not found or has no partner_id")
                return False
            
            manager_partner_id = manager_user_info[0]['partner_id'][0]
            logger.info(f"Found manager partner ID: {manager_partner_id}")
            
            # Формируем URL для перехода на карточку клиента
            base_url = self.url.rstrip('/')
            partner_url = f"{base_url}/web#id={partner_id}&model=res.partner&view_type=form"
            
            # Формируем текст сообщения
            message_body = f"""📝 Необходимо записать на тренировку пользователя

Клиент: {partner_name} (ID: {partner_id})
Спортивный центр: {center_name}
Телефон: {partner.get('phone') or partner.get('mobile') or '-'}
Email: {partner.get('email') or '-'}

{partner_url}

[Открыть карточку клиента]"""
            
            # Добавляем менеджера как follower к партнеру
            try:
                self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.partner',
                    'message_subscribe',
                    [[partner_id], [manager_partner_id]],
                )
                logger.info(f"Added manager {manager_name} as follower to partner {partner_id}")
            except Exception as e:
                logger.warning(f"Failed to add manager as follower: {e}")
            
            # Создаем сообщение через message_post
            message_id = None
            try:
                # Получаем res_model_id для res.partner
                res_model_ids = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'ir.model',
                    'search',
                    [[('model', '=', 'res.partner')]],
                    {'limit': 1},
                )
                res_model_id = res_model_ids[0] if res_model_ids else None
                
                if not res_model_id:
                    logger.error("Could not find res_model_id for res.partner")
                    return False
                
                # Получаем partner_id текущего пользователя (от имени бота)
                current_user_info = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.users',
                    'read',
                    [[self.uid], ['partner_id']],
                )
                current_partner_id = current_user_info[0]['partner_id'][0] if current_user_info and current_user_info[0].get('partner_id') else None
                
                # Создаем сообщение напрямую через mail.message
                message_vals = {
                    'model': 'res.partner',
                    'res_id': partner_id,
                    'message_type': 'notification',
                    'body': message_body,
                    'subject': f'📝 Необходимо записать на тренировку пользователя {partner_name}',
                    'partner_ids': [[6, 0, [manager_partner_id]]],
                }
                if current_partner_id:
                    message_vals['author_id'] = current_partner_id
                
                message_id = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'mail.message',
                    'create',
                    [message_vals],
                )
                
                logger.info(f"Created booking request message: message_id={message_id}")
                
            except Exception as e:
                logger.error(f"Failed to create message: {e}")
                # Пробуем через message_post как fallback
                try:
                    message_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'res.partner',
                        'message_post',
                        [partner_id],
                        {
                            'body': message_body,
                            'subject': f'📝 Необходимо записать на тренировку пользователя {partner_name}',
                            'message_type': 'notification',
                            'partner_ids': [manager_partner_id],
                        },
                    )
                    
                    if isinstance(message_id, (list, tuple)):
                        message_id = message_id[0] if message_id else None
                    
                    logger.info(f"Created message via message_post (fallback): message_id={message_id}")
                except Exception as e2:
                    logger.error(f"Failed to create message via message_post fallback: {e2}")
                    return False
            
            # Принудительно создаем уведомление в Inbox для менеджера
            if message_id:
                try:
                    # Проверяем, существует ли уже уведомление для этого сообщения и партнера
                    existing_notification = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.notification',
                        'search',
                        [[('mail_message_id', '=', message_id), ('res_partner_id', '=', manager_partner_id)]],
                        {'limit': 1},
                    )
                    
                    if not existing_notification:
                        # Создаем уведомление для Inbox
                        try:
                            notification_id = self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'create',
                                [{
                                    'mail_message_id': message_id,
                                    'res_partner_id': manager_partner_id,
                                    'notification_type': 'inbox',
                                    'notification_status': 'ready',
                                    'is_read': False,
                                }],
                            )
                            logger.info(f"Created inbox notification: notification_id={notification_id}")
                        except Exception as create_error:
                            # Если уведомление уже существует (дубликат), это нормально
                            error_str = str(create_error)
                            if 'duplicate key' in error_str.lower() or 'unique constraint' in error_str.lower():
                                logger.info("Notification already exists (created automatically)")
                            else:
                                logger.warning(f"Could not create notification: {create_error}")
                    else:
                        logger.info(f"Notification already exists for manager (notification_id: {existing_notification[0] if existing_notification else 'N/A'})")
                        # Убеждаемся, что уведомление имеет правильный тип
                        try:
                            self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'write',
                                [existing_notification, {
                                    'notification_type': 'inbox',
                                    'notification_status': 'ready',
                                    'is_read': False,
                                }],
                            )
                            logger.info("Updated notification to ensure it's in inbox")
                        except Exception as update_error:
                            logger.warning(f"Could not update notification: {update_error}")
                            
                except Exception as e:
                    logger.warning(f"Could not create/check notification: {e}")
            
            # Создаем Activity (задачу) для менеджера
            try:
                from datetime import datetime, timedelta
                activity_type_id = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'mail.activity.type',
                    'search',
                    [[('name', 'ilike', 'call')]],
                    {'limit': 1},
                )
                if not activity_type_id:
                    activity_type_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.activity.type',
                        'search',
                        [[]],
                        {'limit': 1},
                    )
                
                if activity_type_id:
                    activity_type_id = activity_type_id[0]
                else:
                    activity_type_id = 1
                
                res_model_ids = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'ir.model',
                    'search',
                    [[('model', '=', 'res.partner')]],
                    {'limit': 1},
                )
                res_model_id = res_model_ids[0] if res_model_ids else None
                
                if res_model_id:
                    activity_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.activity',
                        'create',
                        [{
                            'res_id': partner_id,
                            'res_model_id': res_model_id,
                            'activity_type_id': activity_type_id,
                            'user_id': manager_user_id,
                            'summary': f'📝 Необходимо записать на тренировку пользователя {partner_name}',
                            'note': message_body,
                            'date_deadline': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                        }],
                    )
                    logger.info(f"Created activity for manager: activity_id={activity_id}")
            except Exception as e:
                logger.warning(f"Could not create activity: {e}")
            
            logger.info(f"Successfully sent booking request message to manager {manager_name} (user_id: {manager_user_id}, partner_id: {manager_partner_id})")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to send booking request to manager: {e}")
            return False

    def get_trainer_availability_dates(self, trainer_id: int, sports_center_id: int) -> list:
        """Получает даты, когда тренер работает в текущем месяце"""
        if self.uid is None:
            self.authenticate()
        try:
            from datetime import date, datetime, timedelta
            
            today = date.today()
            month_start = today.replace(day=1)
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)
            
            # Получаем доступности тренера
            availabilities = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'trainer.availability',
                'search_read',
                [[
                    ('employee_id', '=', trainer_id),
                    ('sports_center_id', '=', sports_center_id),
                    ('start_datetime', '<=', datetime.combine(month_end, datetime.max.time()).isoformat()),
                    ('end_datetime', '>=', datetime.combine(month_start, datetime.min.time()).isoformat()),
                ]],
                {'fields': ['start_datetime', 'end_datetime'], 'order': 'start_datetime asc'},
            )
            
            # Собираем уникальные даты работы
            working_dates = set()
            for avail in availabilities:
                try:
                    # Odoo возвращает дату в формате 'YYYY-MM-DD HH:MM:SS'
                    start_str = avail['start_datetime']
                    end_str = avail['end_datetime']
                    
                    # Парсим дату
                    if 'T' in start_str:
                        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00').split('+')[0])
                    else:
                        start_dt = datetime.strptime(start_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    
                    if 'T' in end_str:
                        end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00').split('+')[0])
                    else:
                        end_dt = datetime.strptime(end_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    
                    current_date = start_dt.date()
                    end_date = end_dt.date()
                    
                    while current_date <= end_date and current_date <= month_end:
                        if current_date >= month_start:
                            working_dates.add(current_date)
                        current_date += timedelta(days=1)
                except Exception as e:
                    logger.warning(f"Failed to parse date from availability: {e}")
                    continue
            
            # Сортируем даты
            return sorted(list(working_dates))
        except Exception as e:
            logger.exception(f"Failed to get trainer availability dates: {e}")
            return []

    def send_booking_request_to_trainer(self, partner_id: int, trainer_id: int, sports_center_id: int) -> bool:
        """Отправляет сообщение тренеру о желании клиента записаться к нему"""
        if self.uid is None:
            self.authenticate()
        try:
            # Получаем информацию о клиенте
            partner_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.partner',
                'read',
                [[partner_id], ['name', 'phone', 'mobile', 'email']],
            )
            if not partner_info:
                return False
            
            partner = partner_info[0]
            partner_name = partner.get('name', 'Неизвестный клиент')
            
            # Получаем информацию о тренере
            trainer_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'hr.employee',
                'read',
                [[trainer_id], ['user_id', 'name']],
            )
            if not trainer_info or not trainer_info[0].get('user_id'):
                logger.error(f"Trainer {trainer_id} not found or has no user_id")
                return False
            
            trainer_user_id = trainer_info[0]['user_id'][0]
            trainer_name = trainer_info[0].get('name', 'Тренер')
            
            # Получаем partner_id тренера
            trainer_user_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.users',
                'read',
                [[trainer_user_id], ['partner_id', 'name']],
            )
            if not trainer_user_info or not trainer_user_info[0].get('partner_id'):
                logger.error(f"Trainer user {trainer_user_id} not found or has no partner_id")
                return False
            
            trainer_partner_id = trainer_user_info[0]['partner_id'][0]
            
            # Получаем информацию о спортивном центре
            center_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'sports.center',
                'read',
                [[sports_center_id], ['name']],
            )
            center_name = center_info[0].get('name', 'Неизвестный центр') if center_info else 'Неизвестный центр'
            
            # Формируем текст сообщения
            message_body = f"""🎾 Клиент хочет записаться к Вам на тренировку
Клиент: {partner_name} (ID: {partner_id})
Спортивный центр: {center_name}
Телефон: {partner.get('phone') or partner.get('mobile') or '-'}
Email: {partner.get('email') or '-'}"""
            
            # Добавляем тренера как follower к партнеру
            try:
                self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.partner',
                    'message_subscribe',
                    [[partner_id], [trainer_partner_id]],
                )
                logger.info(f"Added trainer {trainer_name} as follower to partner {partner_id}")
            except Exception as e:
                logger.warning(f"Failed to add trainer as follower: {e}")
            
            # Создаем сообщение напрямую через mail.message (как для менеджера)
            message_id = None
            try:
                # Получаем res_model_id для res.partner
                res_model_ids = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'ir.model',
                    'search',
                    [[('model', '=', 'res.partner')]],
                    {'limit': 1},
                )
                res_model_id = res_model_ids[0] if res_model_ids else None
                
                if not res_model_id:
                    logger.error("Could not find res_model_id for res.partner")
                    return False
                
                # Получаем partner_id текущего пользователя (от имени бота)
                current_user_info = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.users',
                    'read',
                    [[self.uid], ['partner_id']],
                )
                current_partner_id = current_user_info[0]['partner_id'][0] if current_user_info and current_user_info[0].get('partner_id') else None
                
                # Создаем сообщение напрямую через mail.message
                message_vals = {
                    'model': 'res.partner',
                    'res_id': partner_id,
                    'message_type': 'notification',
                    'body': message_body,
                    'subject': f'🎾 Клиент {partner_name} хочет записаться к Вам',
                    'partner_ids': [[6, 0, [trainer_partner_id]]],
                }
                if current_partner_id:
                    message_vals['author_id'] = current_partner_id
                
                message_id = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'mail.message',
                    'create',
                    [message_vals],
                )
                
                logger.info(f"Created booking request message to trainer: message_id={message_id}")
                
            except Exception as e:
                logger.error(f"Failed to create message: {e}")
                # Пробуем через message_post как fallback
                try:
                    message_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'res.partner',
                        'message_post',
                        [partner_id],
                        {
                            'body': message_body,
                            'subject': f'🎾 Клиент {partner_name} хочет записаться к Вам',
                            'message_type': 'notification',
                            'partner_ids': [trainer_partner_id],
                        },
                    )
                    
                    if isinstance(message_id, (list, tuple)):
                        message_id = message_id[0] if message_id else None
                    
                    logger.info(f"Created message via message_post (fallback): message_id={message_id}")
                except Exception as e2:
                    logger.error(f"Failed to create message via message_post fallback: {e2}")
                    return False
            
            # Принудительно создаем уведомление в Inbox для тренера
            if message_id:
                try:
                    # Проверяем, существует ли уже уведомление для этого сообщения и партнера
                    existing_notification = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.notification',
                        'search',
                        [[('mail_message_id', '=', message_id), ('res_partner_id', '=', trainer_partner_id)]],
                        {'limit': 1},
                    )
                    
                    if not existing_notification:
                        # Создаем уведомление для Inbox
                        try:
                            notification_id = self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'create',
                                [{
                                    'mail_message_id': message_id,
                                    'res_partner_id': trainer_partner_id,
                                    'notification_type': 'inbox',
                                    'notification_status': 'ready',
                                    'is_read': False,
                                }],
                            )
                            logger.info(f"Created inbox notification for trainer: notification_id={notification_id}")
                        except Exception as create_error:
                            # Если уведомление уже существует (дубликат), это нормально
                            error_str = str(create_error)
                            if 'duplicate key' in error_str.lower() or 'unique constraint' in error_str.lower():
                                logger.info("Notification already exists (created automatically)")
                            else:
                                logger.warning(f"Could not create notification for trainer: {create_error}")
                    else:
                        logger.info(f"Notification already exists for trainer (notification_id: {existing_notification[0] if existing_notification else 'N/A'})")
                        # Убеждаемся, что уведомление имеет правильный тип
                        try:
                            self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'write',
                                [existing_notification, {
                                    'notification_type': 'inbox',
                                    'notification_status': 'ready',
                                    'is_read': False,
                                }],
                            )
                            logger.info("Updated notification to ensure it's in inbox")
                        except Exception as update_error:
                            logger.warning(f"Could not update notification: {update_error}")
                            
                except Exception as e:
                    logger.warning(f"Could not create/check notification for trainer: {e}")
            
            logger.info(f"Successfully sent booking request message to trainer {trainer_name} (user_id: {trainer_user_id}, partner_id: {trainer_partner_id})")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to send booking request to trainer: {e}")
            return False

    def send_balance_request_to_manager(self, partner_id: int, amount: float, manager_user_id: int) -> bool:
        """Отправляет сообщение менеджеру о запросе пополнения баланса в чат Odoo"""
        if self.uid is None:
            self.authenticate()
        try:
            # Получаем информацию о клиенте
            partner_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.partner',
                'read',
                [[partner_id], ['name', 'phone', 'mobile', 'email']],
            )
            if not partner_info:
                return False
            
            partner = partner_info[0]
            partner_name = partner.get('name', 'Неизвестный клиент')
            
            # Формируем URL для перехода на карточку клиента
            base_url = self.url.rstrip('/')
            partner_url = f"{base_url}/web#id={partner_id}&model=res.partner&view_type=form"
            
            # Формируем текст сообщения в простом текстовом формате
            # Odoo может не рендерить HTML в сообщениях, поэтому используем простой текст
            message_body = f"""💳 Запрос на пополнение баланса

Клиент: {partner_name} (ID: {partner_id})
Запрашиваемая сумма: {amount:.2f}
Телефон: {partner.get('phone') or partner.get('mobile') or '-'}
Email: {partner.get('email') or '-'}

{partner_url}

[Открыть карточку клиента]"""
            
            # Получаем partner_id менеджера (Mitchell Admin)
            manager_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.users',
                'read',
                [[manager_user_id], ['partner_id', 'name']],
            )
            if not manager_info or not manager_info[0].get('partner_id'):
                logger.error(f"Manager user {manager_user_id} not found or has no partner_id")
                return False
            
            manager_partner_id = manager_info[0]['partner_id'][0]
            manager_name = manager_info[0].get('name', 'Менеджер')
            
            # Получаем partner_id текущего пользователя (от имени бота)
            current_user_info = self.object_proxy.execute_kw(
                self.db,
                self.uid,
                self.password,
                'res.users',
                'read',
                [[self.uid], ['partner_id']],
            )
            current_partner_id = current_user_info[0]['partner_id'][0] if current_user_info else None
            
            # Сначала добавляем менеджера как follower к партнеру
            try:
                self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.partner',
                    'message_subscribe',
                    [[partner_id], [manager_partner_id]],
                )
                logger.info(f"Added manager {manager_name} as follower to partner {partner_id}")
            except Exception as e:
                logger.warning(f"Failed to add manager as follower: {e}")
            
            # Создаем сообщение, которое будет видно в Inbox менеджера
            # Используем комбинацию методов для гарантированного отображения
            message_id = None
            
            try:
                # Способ 1: Создаем сообщение через message_post на карточке партнера
                # Это автоматически создаст уведомления для followers
                message_id = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'res.partner',
                    'message_post',
                    [partner_id],
                    {
                        'body': message_body,
                        'subject': f'💳 Запрос на пополнение баланса от {partner_name}',
                        'message_type': 'notification',
                        'partner_ids': [manager_partner_id],  # Менеджер - получатель
                    },
                )
                
                if isinstance(message_id, (list, tuple)):
                    message_id = message_id[0] if message_id else None
                
                logger.info(f"Created message via message_post: message_id={message_id}")
                
            except Exception as e:
                logger.error(f"Failed to create message via message_post: {e}")
            
            # Создаем уведомление в Inbox (если message_post не создал его автоматически)
            if message_id:
                try:
                    # Получаем информацию о сообщении, чтобы проверить, есть ли уже уведомления
                    message_info = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.message',
                        'read',
                        [[message_id], ['notification_ids', 'partner_ids']],
                    )
                    
                    if message_info:
                        # Проверяем, есть ли уже уведомление для менеджера
                        notification_ids = message_info[0].get('notification_ids', [])
                        needs_notification = True
                        
                        if notification_ids:
                            # Проверяем существующие уведомления
                            existing_notifications = self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'read',
                                [notification_ids, ['res_partner_id', 'notification_type']],
                            )
                            for notif in existing_notifications:
                                if notif.get('res_partner_id') == manager_partner_id and notif.get('notification_type') == 'inbox':
                                    needs_notification = False
                                    break
                        
                        if needs_notification:
                            # Создаем уведомление для Inbox
                            notification_id = self.object_proxy.execute_kw(
                                self.db,
                                self.uid,
                                self.password,
                                'mail.notification',
                                'create',
                                [{
                                    'mail_message_id': message_id,
                                    'res_partner_id': manager_partner_id,
                                    'notification_type': 'inbox',
                                    'is_read': False,
                                }],
                            )
                            logger.info(f"Created inbox notification: notification_id={notification_id}")
                        else:
                            logger.info("Notification already exists for manager")
                            
                except Exception as e:
                    logger.warning(f"Could not create/check notification: {e}")
            
            # Также создаем Activity (задачу) для менеджера, чтобы точно было видно
            try:
                from datetime import datetime, timedelta
                activity_type_id = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'mail.activity.type',
                    'search',
                    [[('name', 'ilike', 'call')]],
                    {'limit': 1},
                )
                if not activity_type_id:
                    # Если нет типа активности, ищем любой доступный
                    activity_type_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.activity.type',
                        'search',
                        [[]],
                        {'limit': 1},
                    )
                
                if activity_type_id:
                    activity_type_id = activity_type_id[0]
                else:
                    activity_type_id = 1  # Используем ID по умолчанию
                
                # Получаем res_model_id для res.partner
                res_model_ids = self.object_proxy.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'ir.model',
                    'search',
                    [[('model', '=', 'res.partner')]],
                    {'limit': 1},
                )
                res_model_id = res_model_ids[0] if res_model_ids else None
                
                if res_model_id:
                    # Создаем активность для менеджера
                    activity_id = self.object_proxy.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        'mail.activity',
                        'create',
                        [{
                            'res_id': partner_id,
                            'res_model_id': res_model_id,
                            'activity_type_id': activity_type_id,
                            'user_id': manager_user_id,  # Назначаем менеджеру
                            'summary': f'💳 Запрос на пополнение баланса от {partner_name}',
                            'note': message_body,
                            'date_deadline': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                        }],
                    )
                    logger.info(f"Created activity for manager: activity_id={activity_id}")
                else:
                    logger.warning("Could not find res_model_id for res.partner, skipping activity creation")
            except Exception as e:
                logger.warning(f"Could not create activity: {e}")
            
            logger.info(f"Successfully sent balance request message to manager {manager_name} (user_id: {manager_user_id}, partner_id: {manager_partner_id}, message_id={message_id})")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to send balance request to manager: {e}")
            return False


cfg = load_config()
validate_config(cfg)

bot = Bot(token=cfg['TELEGRAM_BOT_TOKEN'])
router = Router()
odoo = OdooClient(
    url=cfg['ODOO_URL'],
    db=cfg['ODOO_DB'],
    username=cfg['ODOO_USERNAME'],
    password=cfg['ODOO_PASSWORD'],
)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! Для записи в теннисный клуб пройдите быструю регистрацию.\n"
        "Пожалуйста, введите ваше ФИО:"
    )
    await state.set_state(RegistrationStates.waiting_for_name)


@router.message(Command("info"))
async def cmd_info(message: types.Message, state: FSMContext):
    """Обработчик команды /info - информация о пользователе и тренировках"""
    # Проверяем, зарегистрирован ли пользователь
    partner_id = user_partner_map.get(message.from_user.id)
    if not partner_id:
        await message.answer(
            "Вы не зарегистрированы. Пожалуйста, сначала пройдите регистрацию командой /start"
        )
        return
    
    try:
        # Получаем информацию о пользователе
        partner_info = odoo.get_partner_info(partner_id)
        if not partner_info:
            await message.answer("Не удалось получить информацию о пользователе.")
            return
        
        # Получаем тренировки
        trainings = odoo.get_partner_trainings(partner_id)
        
        # Формируем URL для WebApp с данными пользователя
        webapp_base_url = cfg.get('WEBAPP_URL', 'https://6v7876sr-6000.euw.devtunnels.ms/')
        use_webapp = cfg.get('USE_WEBAPP', False)
        
        # Подготавливаем данные для передачи
        user_data = {
            'partner_id': partner_id,
            'name': partner_info.get('name', 'Не указано'),
            'balance': partner_info.get('balance', 0.0),
            'trainings': trainings,
        }
        
        # Кодируем данные в base64 (URL-safe) для передачи через URL
        data_json = json.dumps(user_data, ensure_ascii=False)
        data_encoded = base64.urlsafe_b64encode(data_json.encode('utf-8')).decode('utf-8').rstrip('=')
        webapp_url = f"{webapp_base_url}?data={data_encoded}"
        
        # Создаем инлайн кнопку: WebApp (требует HTTPS) или обычная URL (работает с HTTP)
        if use_webapp and webapp_base_url.startswith('https://'):
            # Используем WebApp кнопку только если URL начинается с https://
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Перейти к моим тренировкам",
                            web_app=WebAppInfo(url=webapp_url)
                        )
                    ]
                ]
            )
        else:
            # Используем обычную URL кнопку (работает с HTTP для локальной разработки)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Перейти к моим тренировкам",
                            url=webapp_url
                        )
                    ]
                ]
            )
        
        # Отправляем сообщение с кнопкой
        await message.answer(
            f"👤 ФИО: {partner_info.get('name', 'Не указано')}\n"
            f"💰 Баланс: {partner_info.get('balance', 0.0):.2f} руб.\n"
            f"📊 Всего тренировок: {len(trainings)}\n\n"
            "Нажмите на кнопку ниже, чтобы посмотреть подробную информацию о ваших тренировках:",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Failed to get info for /info command")
        await message.answer("Произошла ошибка при получении информации. Попробуйте позже.")


@router.message(Command("my_balance"))
async def cmd_my_balance(message: types.Message, state: FSMContext):
    """Обработчик команды /my_balance - запрос на пополнение баланса"""
    # Проверяем, зарегистрирован ли пользователь
    partner_id = user_partner_map.get(message.from_user.id)
    if not partner_id:
        await message.answer(
            "Вы не зарегистрированы. Пожалуйста, сначала пройдите регистрацию командой /start"
        )
        return
    
    # Получаем текущий баланс
    try:
        balance = odoo.read_partner_balance(partner_id)
        # Показываем текущий баланс и предлагаем выбрать сумму для пополнения
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="50", callback_data=f"balance:request:50"),
                    InlineKeyboardButton(text="75", callback_data=f"balance:request:75"),
                ],
                [
                    InlineKeyboardButton(text="100", callback_data=f"balance:request:100"),
                    InlineKeyboardButton(text="200", callback_data=f"balance:request:200"),
                ],
            ]
        )
        await message.answer(
            f"Ваш текущий баланс: {balance:.2f}\n\n"
            "Выберите сумму для пополнения баланса:",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Failed to read balance for /my_balance command")
        await message.answer("Произошла ошибка при получении баланса. Попробуйте позже.")


@router.message(StateFilter(RegistrationStates.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с вашим ФИО:")
        return
    
    full_name = message.text.strip()
    if len(full_name) < 2:
        await message.answer("Имя слишком короткое. Введите корректное ФИО:")
        return
    await state.update_data(name=full_name)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться телефоном", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Нажмите кнопку, чтобы отправить номер телефона:", reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_contact)


@router.message(StateFilter(RegistrationStates.waiting_for_contact))
async def process_contact(message: types.Message, state: FSMContext):
    if not message.contact or not message.contact.phone_number:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Поделиться телефоном", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer("Пожалуйста, используйте кнопку ниже, чтобы отправить номер телефона:", reply_markup=kb)
        return
    phone_number = message.contact.phone_number
    # Сохраняем как phone и mobile одинаково
    await state.update_data(phone=phone_number, mobile=phone_number)

    # Проверка: уже зарегистрирован?
    try:
        existing = odoo.find_partner_by_phone(phone_number)
    except Exception:
        logger.exception("Failed to check existing partner by phone")
        existing = None

    if existing:
        balance = 0.0
        try:
            balance = float(existing.get('balance') or 0.0)
        except Exception:
            logger.warning("Balance parse failed for existing partner")
        # Обновляем telegram_chat_id при необходимости
        current_chat_id = str(message.from_user.id)
        stored_chat_id = existing.get('telegram_chat_id')
        stored_chat_id_str = str(stored_chat_id) if stored_chat_id else None
        if current_chat_id and current_chat_id != stored_chat_id_str:
            try:
                odoo.write_partner(existing['id'], {'telegram_chat_id': current_chat_id})
            except Exception:
                logger.exception("Failed to update telegram_chat_id for partner %s", existing.get('id'))
        # Если баланс меньше 100 — начислим до 100
        try:
            if balance < 100.0:
                odoo.object_proxy.execute_kw(
                    odoo.db,
                    odoo.uid or odoo.authenticate(),
                    odoo.password,
                    'res.partner',
                    'write',
                    [[existing['id']], {'balance': 100.0}],
                )
                balance = 100.0
        except Exception:
            logger.exception("Failed to top up balance to 100 for existing partner")
        # Привязываем чат к существующему партнёру
        try:
            user_partner_map[message.from_user.id] = int(existing.get('id'))
        except Exception:
            pass
        centers_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Смотреть спортивные центры", callback_data="centers:list")]]
        )
        await message.answer(
            f"Вы уже зарегистрированы как: {existing.get('name')}. Ваш баланс: {balance:.2f}",
            reply_markup=centers_kb,
        )
        await state.clear()
        return

    await message.answer("Укажите ваш email (или пропустите, отправив '-'):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RegistrationStates.waiting_for_email)


def _sanitize_email(text: str) -> Optional[str]:
    t = text.strip()
    if t == '-' or not t:
        return None
    if '@' in t and '.' in t:
        return t
    return None


@router.message(StateFilter(RegistrationStates.waiting_for_email))
async def process_email_and_register(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с email или '-' для пропуска:")
        return
    
    email = _sanitize_email(message.text)
    if email is None and message.text.strip() not in ('-', ''):
        await message.answer("Некорректный email. Введите корректный email или '-' для пропуска:")
        return

    data = await state.get_data()
    vals = {
        'name': data.get('name'),
        'phone': data.get('phone'),
        'mobile': data.get('mobile'),
        'email': email,
        'is_company': False,
        'active': True,
        'telegram_chat_id': str(message.from_user.id),
    }

    default_center = cfg.get('DEFAULT_SPORTS_CENTER_ID')
    if default_center:
        try:
            vals['sports_center_id'] = int(default_center)
        except ValueError:
            logger.warning("DEFAULT_SPORTS_CENTER_ID is not an integer; ignoring")

    # Safety: ensure no unsupported fields slip in (e.g., customer_rank)
    if 'customer_rank' in vals:
        del vals['customer_rank']

    try:
        logger.info("Creating res.partner with vals: %s", {k: v for k, v in vals.items() if k != 'email' or v})
        # Начисляем стартовый баланс 100
        vals['balance'] = 100.0
        partner_id = odoo.create_partner(vals)
        # Читаем баланс созданного клиента
        balance = 0.0
        try:
            balance_list = odoo.object_proxy.execute_kw(
                odoo.db,
                odoo.uid or odoo.authenticate(),
                odoo.password,
                'res.partner',
                'read',
                [[partner_id], ['balance']],
            )
            if balance_list and isinstance(balance_list, list):
                balance = balance_list[0].get('balance', 0.0)
        except Exception:
            logger.exception("Failed to read partner balance")

        # Инлайн-кнопка для просмотра центров
        centers_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Смотреть спортивные центры", callback_data="centers:list")]]
        )
        # Привязываем чат к партнеру (в памяти)
        try:
            user_partner_map[message.from_user.id] = partner_id
        except Exception:
            pass
        await message.answer(f"Вы успешно зарегистрировались! Ваш текущий баланс: {balance:.2f}", reply_markup=centers_kb)
        admin_chat_id = cfg.get('ADMIN_CHAT_ID')
        if admin_chat_id:
            await message.bot.send_message(
                chat_id=int(admin_chat_id),
                text=(
                    f"Новая регистрация\n"
                    f"ID: {partner_id}\n"
                    f"Имя: {vals.get('name')}\n"
                    f"Тел: {vals.get('phone')} | Моб: {vals.get('mobile')}\n"
                    f"Email: {vals.get('email') or '-'}"
                ),
            )
    except Exception:
        logger.exception("Failed to create partner in Odoo")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")

    await state.clear()


async def main() -> None:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot, skip_updates=True)


# ----- Инлайн-обработчики центров -----

@router.callback_query(lambda c: c.data == 'centers:list')
async def list_centers(callback: types.CallbackQuery):
    try:
        centers = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'sports.center',
            'search_read',
            [[]],
            {'fields': ['name'], 'limit': 25, 'order': 'name asc'},
        )
        if not centers:
            await callback.message.edit_text("Спортивные центры не найдены.")
            await callback.answer()
            return

        rows = []
        row = []
        for c in centers:
            row.append(InlineKeyboardButton(text=c['name'], callback_data=f"centers:detail:{c['id']}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите спортивный центр:", reply_markup=kb)
        await callback.answer()
    except Exception:
        logger.exception("Failed to list sports centers")
        await callback.answer("Ошибка загрузки центров", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith('centers:detail:'))
async def center_detail(callback: types.CallbackQuery):
    try:
        parts = callback.data.split(':')
        center_id = int(parts[-1])
        # Читаем центр и связанные корты
        center_list = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'sports.center',
            'read',
            [[center_id], ['name', 'work_start_time', 'work_end_time', 'total_courts']],
        )
        if not center_list:
            await callback.answer("Центр не найден", show_alert=True)
            return
        center = center_list[0]

        # Ищем корты по sports_center_id
        courts = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'tennis.court',
            'search_read',
            [[('sports_center_id', '=', center_id)], ['name', 'surface_type', 'capacity', 'has_lighting', 'has_roof', 'state']],
        )

        lines = [
            f"🏟 {center.get('name')}",
            f"🕒 Время работы: {center.get('work_start_time') or '-'} — {center.get('work_end_time') or '-'}",
            f"🏁 Кол-во кортов: {center.get('total_courts') if center.get('total_courts') is not None else len(courts)}",
            "",
        ]
        if courts:
            for ct in courts:
                lines.append(
                    "• "
                    f"{ct.get('name')} | тип: {ct.get('surface_type')} | вместимость: {ct.get('capacity')} | "
                    f"освещение: {'да' if ct.get('has_lighting') else 'нет'} | крыша: {'да' if ct.get('has_roof') else 'нет'} | "
                    f"состояние: {ct.get('state')}"
                )
        else:
            lines.append("Кортов не найдено.")

        # Попробуем получить до 5 фотографий центра
        images: list[dict] = []
        try:
            images = odoo.object_proxy.execute_kw(
                odoo.db,
                odoo.uid or odoo.authenticate(),
                odoo.password,
                'sports.center.image',
                'search_read',
                [[('sports_center_id', '=', center_id)]],
                {'fields': ['image', 'name', 'sequence'], 'limit': 5, 'order': 'sequence asc, id asc'},
            ) or []
        except Exception:
            logger.exception("Failed to load center images")

        text_caption = "\n".join(lines).strip()

        if images:
            media: list[types.InputMediaPhoto] = []
            for idx, img in enumerate(images):
                b64 = img.get('image')
                if not b64:
                    continue
                try:
                    raw = base64.b64decode(b64)
                except Exception:
                    continue
                file_name = f"center_{center_id}_{idx+1}.jpg"
                input_file = types.BufferedInputFile(raw, filename=file_name)
                if idx == 0:
                    media.append(types.InputMediaPhoto(media=input_file, caption=text_caption))
                else:
                    media.append(types.InputMediaPhoto(media=input_file))

            # Если получилось собрать хотя бы одну фотографию — отправляем медиа-группой
            if media:
                try:
                    await callback.message.answer_media_group(media)
                except Exception:
                    logger.exception("Failed to send media group, fallback to text only")
                    media = []

            if media:
                # После фотографий отправим отдельным сообщением кнопки
                book_kb = InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Записаться", callback_data=f"centers:book:{center_id}")]]
                )
                await callback.message.answer("Вы можете записаться по кнопке ниже:", reply_markup=book_kb)
                await callback.answer()
                return

        # Если фотографий нет или не удалось отправить, покажем текст как раньше
        book_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Записаться", callback_data=f"centers:book:{center_id}")]]
        )
        await callback.message.edit_text(text_caption, reply_markup=book_kb)
        await callback.answer()
    except Exception:
        logger.exception("Failed to load center details")
        await callback.answer("Ошибка загрузки центра", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith('centers:book:'))
async def start_booking(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(':')
        center_id = int(parts[-1])
        await state.update_data(sports_center_id=center_id)

        # Спрашиваем про любимого тренера
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data=f"book:favorite_trainer:yes"),
                    InlineKeyboardButton(text="Нет", callback_data=f"book:favorite_trainer:no"),
                ]
            ]
        )
        await callback.message.edit_text("Есть ли у Вас любимый тренер?", reply_markup=kb)
        await state.set_state(BookingStates.has_favorite_trainer)
        await callback.answer()
    except Exception:
        logger.exception("Failed to start booking")
        await callback.answer("Ошибка начала записи", show_alert=True)


@router.callback_query(StateFilter(BookingStates.has_favorite_trainer), lambda c: c.data and c.data.startswith('book:favorite_trainer:'))
async def handle_favorite_trainer(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик ответа на вопрос о любимом тренере"""
    try:
        answer = callback.data.split(':')[-1]  # 'yes' или 'no'
        data = await state.get_data()
        center_id = data['sports_center_id']
        partner_id = user_partner_map.get(callback.from_user.id)
        
        if answer == 'yes':
            # Показываем список тренеров
            if not partner_id:
                await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
                await state.clear()
                return
            
            # Получаем список тренеров спортивного центра
            trainers = odoo.object_proxy.execute_kw(
                odoo.db,
                odoo.uid or odoo.authenticate(),
                odoo.password,
                'hr.employee',
                'search_read',
                [[('sports_center_id', '=', center_id), ('position', '=', 'trainer')]],
                {'fields': ['name', 'image_1920'], 'order': 'name asc'},
            )
            
            if not trainers:
                await callback.answer("Тренеры не найдены", show_alert=True)
                return
            
            # Создаем кнопки с тренерами
            rows = []
            row = []
            for trainer in trainers:
                trainer_name = trainer.get('name', 'Без имени')
                row.append(InlineKeyboardButton(text=trainer_name, callback_data=f"book:trainer_select:{trainer['id']}"))
                if len(row) == 2:
                    rows.append(row)
                    row = []
            if row:
                rows.append(row)
            
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
            await callback.message.edit_text("Расскажите кто?", reply_markup=kb)
            await callback.answer()
            return
        
        # Если ответ "Нет"
        if not partner_id:
            await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
            await state.clear()
            return
        
        # Отправляем сообщение менеджеру
        success = odoo.send_booking_request_to_manager(partner_id, center_id)
        
        if success:
            await callback.message.edit_text(
                "Мы подберем Вам самого лучшего! 🎾\n\n"
                "Ваш запрос отправлен менеджеру спортивного центра. "
                "Ожидайте подтверждения записи."
            )
        else:
            await callback.message.edit_text(
                "Мы подберем Вам самого лучшего! 🎾\n\n"
                "Произошла ошибка при отправке запроса менеджеру. "
                "Попробуйте позже или свяжитесь с нами напрямую."
            )
        
        await state.clear()
        await callback.answer()
    except Exception:
        logger.exception("Failed to handle favorite trainer question")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith('book:trainer_select:'))
async def show_trainer_info(callback: types.CallbackQuery, state: FSMContext):
    """Показывает информацию о выбранном тренере"""
    # Отвечаем на callback сразу, чтобы избежать ошибки "query is too old"
    try:
        await callback.answer()
    except Exception:
        # Если callback уже устарел, продолжаем выполнение без ответа
        pass
    
    try:
        trainer_id = int(callback.data.split(':')[-1])
        data = await state.get_data()
        center_id = data['sports_center_id']
        
        # Получаем информацию о тренере
        trainer_info = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'hr.employee',
            'read',
            [[trainer_id], ['name', 'image_1920']],
        )
        
        if not trainer_info:
            try:
                await callback.answer("Тренер не найден", show_alert=True)
            except Exception:
                # Callback уже устарел, просто отправляем сообщение
                await callback.message.answer("Тренер не найден")
            return
        
        trainer = trainer_info[0]
        trainer_name = trainer.get('name', 'Тренер')
        
        # Получаем даты работы тренера в текущем месяце
        working_dates = odoo.get_trainer_availability_dates(trainer_id, center_id)
        
        # Форматируем даты для отображения
        from datetime import date, datetime
        today = date.today()
        month_name = today.strftime('%B %Y')
        
        if working_dates:
            # Форматируем даты красиво
            from datetime import date as date_type
            # Группируем даты по неделям (7 дней подряд)
            date_lines = []
            current_group = []
            
            for work_date in working_dates:
                if not current_group:
                    current_group = [work_date]
                elif (work_date - current_group[-1]).days <= 7:
                    current_group.append(work_date)
                else:
                    # Завершаем текущую группу
                    if len(current_group) == 1:
                        date_lines.append(f"📅 {current_group[0].strftime('%d.%m')}")
                    else:
                        date_lines.append(f"📅 {current_group[0].strftime('%d.%m')} - {current_group[-1].strftime('%d.%m')}")
                    current_group = [work_date]
            
            # Добавляем последнюю группу
            if current_group:
                if len(current_group) == 1:
                    date_lines.append(f"📅 {current_group[0].strftime('%d.%m')}")
                else:
                    date_lines.append(f"📅 {current_group[0].strftime('%d.%m')} - {current_group[-1].strftime('%d.%m')}")
            
            dates_text = '\n'.join(date_lines)
        else:
            dates_text = "📅 Расписание уточняется"
        
        # Формируем текст сообщения
        text = f"👤 {trainer_name}\n\n{dates_text}"
        
        # Получаем фото тренера
        trainer_image = trainer.get('image_1920')
        
        # Создаем кнопку "Хочу записаться к нему"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Хочу записаться к нему", callback_data=f"book:request_trainer:{trainer_id}")]]
        )
        
        if trainer_image:
            try:
                # Убираем префикс data:image/...;base64, если есть
                if ',' in trainer_image:
                    trainer_image = trainer_image.split(',', 1)[1]
                
                # Декодируем base64 изображение
                raw = base64.b64decode(trainer_image)
                
                # Проверяем размер изображения (Telegram ограничивает до 10MB)
                if len(raw) > 10 * 1024 * 1024:
                    logger.warning(f"Trainer image too large: {len(raw)} bytes")
                    # Отправляем только текст, если изображение слишком большое
                    await callback.message.edit_text(text, reply_markup=kb)
                    # Не отвечаем на callback, так как уже ответили в начале функции
                    return
                
                # Проверяем, что это действительно изображение (проверяем первые байты)
                if len(raw) < 10:
                    logger.warning("Trainer image data too short")
                    await callback.message.edit_text(text, reply_markup=kb)
                    # Не отвечаем на callback, так как уже ответили в начале функции
                    return
                
                file_name = f"trainer_{trainer_id}.jpg"
                input_file = types.BufferedInputFile(raw, filename=file_name)
                
                # Отправляем фото с подписью
                await callback.message.answer_photo(
                    photo=input_file,
                    caption=text,
                    reply_markup=kb
                )
                # Не отвечаем на callback, так как уже ответили в начале функции
            except Exception as e:
                logger.exception(f"Failed to send trainer photo: {e}")
                # Если не удалось отправить фото, отправляем текст
                try:
                    await callback.message.edit_text(text, reply_markup=kb)
                except Exception:
                    # Если и edit_text не работает, пробуем answer
                    await callback.message.answer(text, reply_markup=kb)
                # Не отвечаем на callback, так как уже ответили в начале функции
        else:
            # Если нет фото, отправляем только текст
            await callback.message.edit_text(text, reply_markup=kb)
            # Не отвечаем на callback, так как уже ответили в начале функции
            
    except Exception:
        logger.exception("Failed to show trainer info")
        try:
            await callback.answer("Ошибка загрузки информации о тренере", show_alert=True)
        except Exception:
            # Callback уже устарел, просто отправляем сообщение
            try:
                await callback.message.answer("Ошибка загрузки информации о тренере")
            except Exception:
                pass


@router.callback_query(lambda c: c.data and c.data.startswith('book:request_trainer:'))
async def request_trainer_booking(callback: types.CallbackQuery, state: FSMContext):
    """Отправляет запрос тренеру о желании клиента записаться"""
    try:
        trainer_id = int(callback.data.split(':')[-1])
        data = await state.get_data()
        center_id = data['sports_center_id']
        partner_id = user_partner_map.get(callback.from_user.id)
        
        if not partner_id:
            await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
            await state.clear()
            return
        
        # Отправляем сообщение тренеру
        success = odoo.send_booking_request_to_trainer(partner_id, trainer_id, center_id)
        
        if success:
            try:
                await callback.message.edit_text(
                    "✅ Ваш запрос отправлен тренеру!\n\n"
                    "Ожидайте подтверждения записи."
                )
            except Exception:
                # Если не удалось отредактировать (например, это фото), отправляем новое сообщение
                await callback.message.answer(
                    "✅ Ваш запрос отправлен тренеру!\n\n"
                    "Ожидайте подтверждения записи."
                )
        else:
            try:
                await callback.message.edit_text(
                    "❌ Произошла ошибка при отправке запроса тренеру.\n\n"
                    "Попробуйте позже или свяжитесь с нами напрямую."
                )
            except Exception:
                # Если не удалось отредактировать (например, это фото), отправляем новое сообщение
                await callback.message.answer(
                    "❌ Произошла ошибка при отправке запроса тренеру.\n\n"
                    "Попробуйте позже или свяжитесь с нами напрямую."
                )
        
        await state.clear()
        await callback.answer()
    except Exception:
        logger.exception("Failed to request trainer booking")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_type), lambda c: c.data and c.data.startswith('book:type:'))
async def choose_type(callback: types.CallbackQuery, state: FSMContext):
    try:
        type_id = int(callback.data.split(':')[-1])
        await state.update_data(training_type_id=type_id)
        # После выбора типа — выбираем корт
        data = await state.get_data()
        center_id = data['sports_center_id']
        courts = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'tennis.court',
            'search_read',
            [[('sports_center_id', '=', center_id)]],
            {'fields': ['name']},
        )
        if not courts:
            await callback.answer("Кортов не найдено", show_alert=True)
            return
        rows = []
        row = []
        for ct in courts:
            row.append(InlineKeyboardButton(text=ct['name'], callback_data=f"book:court:{ct['id']}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите корт:", reply_markup=kb)
        await state.set_state(BookingStates.choosing_court)
        await callback.answer()
    except Exception:
        logger.exception("Failed to list courts for booking")
        await callback.answer("Ошибка загрузки кортов", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_trainer), lambda c: c.data and c.data.startswith('book:trainer:'))
async def choose_trainer(callback: types.CallbackQuery, state: FSMContext):
    try:
        trainer_id = int(callback.data.split(':')[-1])
        await state.update_data(trainer_id=trainer_id)
        # Далее — выбор даты на 7 дней вперёд
        from datetime import date, timedelta
        today = date.today()
        rows = []
        row = []
        for i in range(7):
            d = today + timedelta(days=i)
            text = d.strftime('%d.%m')
            row.append(InlineKeyboardButton(text=text, callback_data=f"book:date:{d.isoformat()}"))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите дату:", reply_markup=kb)
        await state.set_state(BookingStates.choosing_date)
        await callback.answer()
    except Exception:
        logger.exception("Failed to choose trainer")
        await callback.answer("Ошибка выбора тренера", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_court), lambda c: c.data and c.data.startswith('book:court:'))
async def choose_court(callback: types.CallbackQuery, state: FSMContext):
    try:
        court_id = int(callback.data.split(':')[-1])
        await state.update_data(court_id=court_id)
        # Теперь выбираем тренера (список тренеров центра)
        data = await state.get_data()
        center_id = data['sports_center_id']
        trainers = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'hr.employee',
            'search_read',
            [[('sports_center_id', '=', center_id), ('position', '=', 'trainer')]],
            {'fields': ['name']},
        )
        if not trainers:
            await callback.answer("Тренеры не найдены", show_alert=True)
            return
        rows = []
        row = []
        for tr in trainers:
            row.append(InlineKeyboardButton(text=tr['name'], callback_data=f"book:trainer:{tr['id']}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите тренера:", reply_markup=kb)
        await state.set_state(BookingStates.choosing_trainer)
        await callback.answer()
    except Exception:
        logger.exception("Failed to choose court or list trainers")
        await callback.answer("Ошибка выбора корта", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_date), lambda c: c.data and c.data.startswith('book:date:'))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    try:
        iso = callback.data.split(':')[-1]
        await state.update_data(booking_date=iso)
        data = await state.get_data()
        # Получаем доступные тайм-слоты с учётом тренера и корта на выбранный день
        available = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'training.booking',
            'get_available_times',
            [data['court_id'], iso, data.get('trainer_id'), data.get('sports_center_id')],
        )
        if not available:
            await callback.message.edit_text("Нет доступного времени на выбранную дату. Выберите другую дату.")
            await callback.answer()
            return

        rows = []
        row = []
        for slot in available:
            # slot: {'label': '10:00', 'value': 10.0}
            label = slot.get('label') or f"{slot.get('value', 0):.2f}"
            value = slot.get('value')
            row.append(InlineKeyboardButton(text=label, callback_data=f"book:start:{value}"))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите время начала:", reply_markup=kb)
        await state.set_state(BookingStates.choosing_start)
        await callback.answer()
    except Exception:
        logger.exception("Failed to choose date")
        await callback.answer("Ошибка выбора даты", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_start), lambda c: c.data and c.data.startswith('book:start:'))
async def choose_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        start_f = float(callback.data.split(':')[-1])
        await state.update_data(start_time=start_f)
        # Предложим окончания в рамках тех же доступных слотов (после старта)
        data = await state.get_data()
        available = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'training.booking',
            'get_available_times',
            [data['court_id'], data['booking_date'], data.get('trainer_id'), data.get('sports_center_id')],
        )
        rows = []
        row = []
        for slot in available:
            end_val = float(slot.get('value'))
            if end_val <= start_f:
                continue
            label = slot.get('label') or f"{end_val:.2f}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"book:end:{end_val}"))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await callback.message.edit_text("Выберите время окончания:", reply_markup=kb)
        await state.set_state(BookingStates.choosing_end)
        await callback.answer()
    except Exception:
        logger.exception("Failed to choose start time")
        await callback.answer("Ошибка выбора времени", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_end), lambda c: c.data and c.data.startswith('book:end:'))
async def choose_end(callback: types.CallbackQuery, state: FSMContext):
    try:
        end_f = float(callback.data.split(':')[-1])
        await state.update_data(end_time=end_f)
        # Создаём запись сразу (тренер уже выбран ранее)
        data = await state.get_data()
        partner_id = user_partner_map.get(callback.from_user.id)
        if not partner_id:
            await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
            await state.clear()
            return
        vals = {
            'sports_center_id': data['sports_center_id'],
            'customer_id': partner_id,
            'training_type_id': data['training_type_id'],
            'court_id': data['court_id'],
            'booking_date': data['booking_date'],
            'start_time': data['start_time'],
            'end_time': data['end_time'],
            'trainer_id': data['trainer_id'],
            'state': 'draft',  # Создаём в draft, потом подтвердим
        }
        booking_id = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'training.booking',
            'create',
            [vals],
        )
        # Подтверждаем запись (списывает баланс)
        try:
            odoo.object_proxy.execute_kw(
                odoo.db,
                odoo.uid or odoo.authenticate(),
                odoo.password,
                'training.booking',
                'action_confirm',
                [[booking_id]],
            )
        except Exception:
            logger.exception("Failed to confirm booking, but created as draft")
            # Запись создана в draft, но не подтверждена
        await callback.message.edit_text(
            "Запись создана!\n"
            f"Дата: {data['booking_date']}\n"
            f"Время: {data['start_time']:.2f} — {data['end_time']:.2f}"
        )
        await state.clear()
        await callback.answer()
    except Exception:
        logger.exception("Failed to create booking")
        await callback.answer("Ошибка создания записи", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith('balance:request:'))
async def handle_balance_request(callback: types.CallbackQuery):
    """Обработчик выбора суммы для пополнения баланса"""
    try:
        # Извлекаем сумму из callback_data
        amount_str = callback.data.split(':')[-1]
        amount = float(amount_str)
        
        # Получаем ID партнера
        partner_id = user_partner_map.get(callback.from_user.id)
        if not partner_id:
            await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
            return
        
        # Получаем ID менеджера из конфига
        manager_user_id = cfg.get('MANAGER_USER_ID')
        if not manager_user_id:
            await callback.answer("Не настроен менеджер для получения уведомлений.", show_alert=True)
            return
        
        # Отправляем сообщение менеджеру в Odoo
        success = odoo.send_balance_request_to_manager(partner_id, amount, int(manager_user_id))
        
        if success:
            await callback.message.edit_text(
                f"✅ Запрос на пополнение баланса на сумму {amount:.2f} отправлен менеджеру.\n"
                "Ожидайте подтверждения."
            )
            await callback.answer()
        else:
            await callback.answer("Ошибка при отправке запроса менеджеру. Попробуйте позже.", show_alert=True)
    except ValueError:
        await callback.answer("Неверная сумма.", show_alert=True)
    except Exception:
        logger.exception("Failed to handle balance request")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(StateFilter(BookingStates.choosing_trainer), lambda c: c.data and c.data.startswith('book:trainer:'))
async def finalize_booking(callback: types.CallbackQuery, state: FSMContext):
    try:
        trainer_id = int(callback.data.split(':')[-1])
        await state.update_data(trainer_id=trainer_id)
        data = await state.get_data()

        # Ищем клиента по сохранённому соответствию
        partner_id = user_partner_map.get(callback.from_user.id)
        if not partner_id:
            await callback.answer("Не удалось определить клиента. Повторите регистрацию.", show_alert=True)
            await state.clear()
            return

        # Создаём training.booking
        vals = {
            'sports_center_id': data['sports_center_id'],
            'customer_id': partner_id,
            'training_type_id': data['training_type_id'],
            'court_id': data['court_id'],
            'booking_date': data['booking_date'],
            'start_time': data['start_time'],
            'end_time': data['end_time'],
            'state': 'confirmed',
        }
        booking_id = odoo.object_proxy.execute_kw(
            odoo.db,
            odoo.uid or odoo.authenticate(),
            odoo.password,
            'training.booking',
            'create',
            [vals],
        )
        await callback.message.edit_text(
            "Запись создана!\n"
            f"Дата: {data['booking_date']}\n"
            f"Время: {data['start_time']:.2f} — {data['end_time']:.2f}"
        )
        await state.clear()
        await callback.answer()
    except Exception:
        logger.exception("Failed to create booking")
        await callback.answer("Ошибка создания записи", show_alert=True)


if __name__ == '__main__':
    logger.info("Starting Telegram bot (aiogram 3.x)...")
    asyncio.run(main())


