
import os
import base64
import json
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'


def decode_base64_data(encoded_data: str) -> dict:
    try:
        normalized = encoded_data.replace('-', '+').replace('_', '/')
        padding = '=' * (4 - len(normalized) % 4) % 4
        padded = normalized + padding
        decoded_bytes = base64.b64decode(padded)
        decoded_str = decoded_bytes.decode('utf-8')
        return json.loads(decoded_str)
    except Exception as e:
        logger.error(f"Ошибка декодирования данных: {e}")
        raise ValueError(f"Не удалось декодировать данные: {str(e)}")


@app.route('/')
def index():
    return render_template('trainings.html')


@app.route('/trainings')
def trainings():
    return render_template('trainings.html')


@app.route('/api/health')
def health_check():
    """Проверка здоровья сервиса"""
    return jsonify({
        'status': 'ok',
        'service': 'tennis-club-webapp',
        'version': '1.0.0'
    })


@app.route('/api/decode', methods=['POST'])
def api_decode():
    """
    API endpoint для декодирования данных.
    Принимает base64 закодированные данные и возвращает JSON.
    """
    try:
        data = request.get_json()
        if not data or 'encoded_data' not in data:
            return jsonify({'error': 'Отсутствует параметр encoded_data'}), 400
        
        encoded_data = data['encoded_data']
        decoded_data = decode_base64_data(encoded_data)
        
        return jsonify({
            'success': True,
            'data': decoded_data
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.exception("Ошибка при декодировании данных")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 ошибки"""
    return jsonify({'error': 'Страница не найдена'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Обработчик 500 ошибки"""
    logger.exception("Внутренняя ошибка сервера")
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


if __name__ == '__main__':
    # Получаем настройки из переменных окружения или используем значения по умолчанию
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 6000))
    debug = app.config['DEBUG']
    
    logger.info(f"Запуск Flask сервиса на {host}:{port}")
    logger.info(f"Режим отладки: {debug}")
    
    app.run(host=host, port=port, debug=debug)

