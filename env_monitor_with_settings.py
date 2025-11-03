"""양계장 환경 센서 실시간 모니터링 시스템 (최적화 버전)"""
import logging
import math
import time
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

# 하드웨어 관련 (필요시에만 import)
try:
    import board
    import adafruit_dht
    import spidev
    import RPi.GPIO as GPIO
    import mysql.connector
    import requests
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    HARDWARE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"하드웨어 라이브러리 일부를 사용할 수 없습니다: {e}")
    HARDWARE_AVAILABLE = False

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('env_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask 로거 설정 (콘솔에서만 숨기기)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.WARNING)  # INFO 레벨 로그 숨김

# 로그 파일 생성 확인
logger.info("로그 파일 정상 생성 확인됨")

# ========== Flask 서버 추가 ==========
app = Flask(__name__)
CORS(app)

# 전역 변수로 최신 센서 데이터 저장
latest_sensor_data = {
    'temperature': 0,
    'humidity': 0,
    'lux': 0,
    'co2': 0,
    'no2': 0,
    'co': 0,
    'nh3': 0,
    'timestamp': None,
    'is_warming': False  # 시작 시 정상 상태로 설정
}

# 최근 30초간의 센서 데이터 히스토리 저장 (2초마다 업데이트)
sensor_history = {
    'temperature': [],
    'humidity': [],
    'lux': [],
    'co2': [],
    'no2': [],
    'co': [],
    'nh3': [],
    'timestamps': []
}
MAX_HISTORY_SIZE = 15  # 30초 ÷ 2초 = 15개 데이터 포인트

# 전역 변수로 시스템 인스턴스 저장
system_instance = None

def update_sensor_history(sensor_data):
    """센서 히스토리 업데이트 (최근 30초간 데이터 유지)"""
    global sensor_history
    
    current_time = datetime.now().isoformat()
    
    logger.debug(f"히스토리 업데이트 시작 - 센서 데이터: {sensor_data}")
    
    # 각 센서 데이터 추가
    for sensor_type in ['temperature', 'humidity', 'lux', 'co2', 'no2', 'co', 'nh3']:
        if sensor_type in sensor_data:
            old_size = len(sensor_history[sensor_type])
            sensor_history[sensor_type].append(sensor_data[sensor_type])
            
            # 최대 크기 초과 시 오래된 데이터 제거
            if len(sensor_history[sensor_type]) > MAX_HISTORY_SIZE:
                sensor_history[sensor_type].pop(0)
            
            logger.debug(f"{sensor_type}: {old_size} -> {len(sensor_history[sensor_type])} (값: {sensor_data[sensor_type]})")
    
    # 타임스탬프 추가
    old_timestamp_size = len(sensor_history['timestamps'])
    sensor_history['timestamps'].append(current_time)
    if len(sensor_history['timestamps']) > MAX_HISTORY_SIZE:
        sensor_history['timestamps'].pop(0)
    
    logger.debug(f"타임스탬프: {old_timestamp_size} -> {len(sensor_history['timestamps'])}")
    logger.debug(f"전체 히스토리 상태: 온도={len(sensor_history['temperature'])}, 타임스탬프={len(sensor_history['timestamps'])}")

# Flask API 엔드포인트
@app.route('/api/realtime')
def get_realtime():
    """실시간 센서 데이터"""
    # 예열 중일 때는 데이터 제공하지 않음
    is_warming = latest_sensor_data.get('is_warming', False)
    
    if is_warming:
        logger.debug(f"🚫 예열 중 - API 요청 차단: is_warming={is_warming}")
        return jsonify({
            'success': False,
            'message': '센서 예열 중입니다. 잠시 후 다시 시도해주세요.',
            'is_warming': True
        })
    
    logger.debug(f"✅ 정상 모드 - API 요청 허용: is_warming={is_warming}")
    return jsonify({
        'success': True,
        'data': latest_sensor_data
    })

@app.route('/api/status')
def get_status():
    """시스템 상태"""
    return jsonify({
        'success': True,
        'message': '라즈베리파이 센서 시스템 작동 중',
        'is_warming': latest_sensor_data.get('is_warming', False),
        'timestamp': latest_sensor_data.get('timestamp')
    })

@app.route('/api/history-status')
def get_history_status():
    """히스토리 데이터 상태 확인"""
    global sensor_history
    return jsonify({
        'success': True,
        'data': {
            'temperature_count': len(sensor_history.get('temperature', [])),
            'humidity_count': len(sensor_history.get('humidity', [])),
            'timestamps_count': len(sensor_history.get('timestamps', [])),
            'max_history_size': MAX_HISTORY_SIZE,
            'latest_temperature': sensor_history.get('temperature', [])[-1] if sensor_history.get('temperature') else None,
            'latest_timestamp': sensor_history.get('timestamps', [])[-1] if sensor_history.get('timestamps') else None
        }
    })

@app.route('/api/settings/apply', methods=['POST'])
def apply_settings():
    """설정 적용 요청 처리"""
    try:
        # 전역 변수로 설정 관리자에 접근
        global system_instance
        if system_instance and hasattr(system_instance, 'settings_manager'):
            # 설정을 즉시 데이터베이스에서 다시 로드
            success = system_instance.settings_manager.load_settings_from_db()
            if success:
                logger.info("설정이 즉시 적용되었습니다.")
                return jsonify({
                    'success': True,
                    'message': '설정이 성공적으로 적용되었습니다.'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '설정 로드에 실패했습니다.'
                })
        else:
            return jsonify({
                'success': False,
                'message': '시스템 인스턴스를 찾을 수 없습니다.'
            })
    except Exception as e:
        logger.error(f"설정 적용 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'설정 적용 실패: {str(e)}'
        }), 500

@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    """설정을 직접 업데이트"""
    try:
        settings_data = request.get_json()
        if not settings_data:
            return jsonify({
                'success': False,
                'message': '설정 데이터가 없습니다.'
            }), 400
        
        # 전역 변수로 설정 관리자에 접근
        global system_instance
        if system_instance and hasattr(system_instance, 'settings_manager'):
            # 설정을 수동으로 업데이트
            for key, value in settings_data.items():
                if hasattr(system_instance.settings_manager, 'settings'):
                    system_instance.settings_manager.settings[key] = value
            
            logger.info(f"설정이 직접 업데이트됨: {settings_data}")
            
            # LED 설정이 변경되었는지 확인
            if 'manualLedThreshold' in settings_data or 'autoLedMode' in settings_data:
                logger.info(f"LED 설정 변경됨 - autoLedMode: {settings_data.get('autoLedMode')}, manualLedThreshold: {settings_data.get('manualLedThreshold')}")
            
            return jsonify({
                'success': True,
                'message': '설정이 성공적으로 업데이트되었습니다.',
                'data': settings_data
            })
        else:
            return jsonify({
                'success': False,
                'message': '시스템 인스턴스를 찾을 수 없습니다.'
            }), 500
    except Exception as e:
        logger.error(f"설정 업데이트 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'설정 업데이트 실패: {str(e)}'
        }), 500

@app.route('/api/settings/current', methods=['GET'])
def get_current_settings():
    """현재 설정 조회"""
    try:
        global system_instance
        if system_instance and hasattr(system_instance, 'settings_manager'):
            current_settings = system_instance.settings_manager.settings
            return jsonify({
                'success': True,
                'data': current_settings
            })
        else:
            return jsonify({
                'success': False,
                'message': '시스템 인스턴스를 찾을 수 없습니다.'
            }), 500
    except Exception as e:
        logger.error(f"현재 설정 조회 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'설정 조회 실패: {str(e)}'
        }), 500

@app.route('/api/sensor-history/<sensor_type>')
def get_sensor_history(sensor_type):
    """특정 센서의 최근 30초간 히스토리 데이터 조회"""
    try:
        global sensor_history
        
        logger.info(f"센서 히스토리 요청: {sensor_type}")
        
        # 유효한 센서 타입인지 확인
        valid_sensors = ['temperature', 'humidity', 'lux', 'co2', 'no2', 'co', 'nh3']
        if sensor_type not in valid_sensors:
            logger.warning(f"유효하지 않은 센서 타입: {sensor_type}")
            return jsonify({
                'success': False,
                'message': f'유효하지 않은 센서 타입: {sensor_type}'
            }), 400
        
        # 센서 데이터와 타임스탬프 반환
        sensor_data = sensor_history.get(sensor_type, [])
        timestamps = sensor_history.get('timestamps', [])
        
        logger.info(f"센서 데이터 크기: {len(sensor_data)}, 타임스탬프 크기: {len(timestamps)}")
        
        # 데이터 포인트 수가 일치하도록 조정
        min_length = min(len(sensor_data), len(timestamps))
        sensor_data = sensor_data[-min_length:] if min_length > 0 else []
        timestamps = timestamps[-min_length:] if min_length > 0 else []
        
        logger.info(f"조정된 데이터 크기: {len(sensor_data)}")
        
        return jsonify({
            'success': True,
            'data': {
                'sensor_type': sensor_type,
                'values': sensor_data,
                'timestamps': timestamps,
                'count': len(sensor_data)
            }
        })
        
    except Exception as e:
        logger.error(f"센서 히스토리 조회 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'센서 히스토리 조회 실패: {str(e)}'
        }), 500

# Flask 서버를 별도 쓰레드에서 실행
def run_flask():
    if HARDWARE_AVAILABLE:
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    else:
        logging.warning("하드웨어가 사용 불가능하여 Flask 서버를 시작하지 않습니다.")


class EnvConfig:
    """환경 센서 설정 (최적화된 버전)"""
    def __init__(self):
        # GPIO 핀 설정
        self.MOTOR_A = 24
        self.MOTOR_B = 23
        self.LED_PIN = 16
        self.SERVO_PIN = 18
        
        # 센서 채널
        self.LDR_CHANNEL = 0
        self.MQ_CHANNEL = 1
        
        # 센서 보정값
        self.RLOAD = 10.0
        self.RO_CLEAN_AIR_FACTOR = 9.83
        
        # 가스 센서 곡선 계수
        self.CO2_CURVE_A = 116.6020682
        self.CO2_CURVE_B = -2.769034857
        self.CO_PARA = 23.943
        self.CO_PARB = 1.11
        self.NH3_PARA = 102.2
        self.NH3_PARB = 2.473
        self.NO2_PARA = 116.6020682
        self.NO2_PARB = 2.76963857
        
        # 서보모터 설정
        self.SERVO_MIN_DUTY = 3
        self.SERVO_MAX_DUTY = 12
        
        # 기타 설정
        self.FARM_NUM = 1
        self.FREQ = 100
        self.WARMUP_DURATION = 1800  # 30분
        
        # 서보 모터 관련 설정
        self.SERVO_THRESHOLD = 60  # 습도 기준값


class EnvSettingsManager:
    """환경 설정 관리"""
    
    def __init__(self, db_manager, farm_num=1):
        self.db_manager = db_manager
        self.farm_num = farm_num
        self.sunrise_sunset_api = SunriseSunsetAPI()
        self.settings = self.load_default_settings()
        self.last_update = None
    
    def load_default_settings(self):
        """기본 설정값 로드"""
        return {
            'ledThreshold': 300,
            'doorOpenTemp': 25,
            'doorCloseTemp': 15,
            'fanHumidityThreshold': 75,
            'fanCO2Threshold': 1000,
            'fanCOThreshold': 30,
            'fanSpeed': 60,
            'tempHighAlert': 35,
            'tempLowAlert': 10,
            'humidityHighAlert': 85,
            'humidityLowAlert': 30,
            'co2Alert': 2000,
            'coAlert': 50,
            'nh3Alert': 25,
            'envStatusGood': 80,
            'envStatusFair': 60,
            'autoLedMode': True,
            'manualLedThreshold': 300,
            'locationLat': 37.5665,
            'locationLng': 126.9780,
            'sleepStartHour': 22,
            'sleepEndHour': 6,
            'sleepModeEnabled': True,
            'servoThreshold': 60,
            'useSimpleSensorMode': False  # 고급 모드 사용 (센서 특성곡선 적용)
        }
    
    def load_settings_from_backend(self):
        """스프링 백엔드에서 설정을 가져옴"""
        try:
            response = requests.get('http://192.168.30.111:8080/api/env-settings', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    settings_data = data.get('data', {})
                    self.settings.update(settings_data)
                    logger.debug(f"백엔드 설정 로드 성공")
                    return True
                else:
                    logger.warning(f"백엔드 응답 실패: {data}")
            else:
                logger.warning(f"백엔드 연결 실패: {response.status_code}")
        except Exception as e:
            logger.error(f"백엔드 설정 로드 실패: {e}")
        
        return False

    def load_settings_from_db(self):
        """데이터베이스에서 설정 로드"""
        logger.debug("데이터베이스에서 환경 설정 로드 시도...")
        
        # 먼저 백엔드에서 설정 로드 시도
        backend_success = self.load_settings_from_backend()
        if backend_success:
            return True
        
        # 백엔드 실패 시 데이터베이스에서 로드
        with self.db_manager.get_connection() as conn:
            if not conn:
                logger.error("데이터베이스 연결 실패")
                return False
            
            try:
                cursor = conn.cursor()
                sql = "SELECT * FROM ENV_SETTINGS WHERE ID = 1"
                logger.info(f"SQL 실행: {sql}")
                cursor.execute(sql)
                result = cursor.fetchone()
                
                if result:
                    logger.info(f"데이터베이스에서 설정 조회 성공: {result}")
                    
                    # 데이터베이스 컬럼명을 설정 키로 매핑
                    column_mapping = {
                        'LED_THRESHOLD': 'ledThreshold',
                        'DOOR_OPEN_TEMP': 'doorOpenTemp',
                        'DOOR_CLOSE_TEMP': 'doorCloseTemp',
                        'FAN_HUMIDITY_THRESHOLD': 'fanHumidityThreshold',
                        'FAN_CO2_THRESHOLD': 'fanCO2Threshold',
                        'FAN_CO_THRESHOLD': 'fanCOThreshold',
                        'FAN_SPEED': 'fanSpeed',
                        'TEMP_HIGH_ALERT': 'tempHighAlert',
                        'TEMP_LOW_ALERT': 'tempLowAlert',
                        'HUMIDITY_HIGH_ALERT': 'humidityHighAlert',
                        'HUMIDITY_LOW_ALERT': 'humidityLowAlert',
                        'CO2_ALERT': 'co2Alert',
                        'CO_ALERT': 'coAlert',
                        'NH3_ALERT': 'nh3Alert',
                        'ENV_STATUS_GOOD': 'envStatusGood',
                        'ENV_STATUS_FAIR': 'envStatusFair',
                        'AUTO_LED_MODE': 'autoLedMode',
                        'MANUAL_LED_THRESHOLD': 'manualLedThreshold',
                        'LOCATION_LAT': 'locationLat',
                        'LOCATION_LNG': 'locationLng',
                        'SLEEP_START_HOUR': 'sleepStartHour',
                        'SLEEP_END_HOUR': 'sleepEndHour',
                        'SLEEP_MODE_ENABLED': 'sleepModeEnabled',
                        'SERVO_THRESHOLD': 'servoThreshold',
                        'USE_SIMPLE_SENSOR_MODE': 'useSimpleSensorMode'
                    }
                    
                    # 결과를 딕셔너리로 변환
                    columns = [desc[0] for desc in cursor.description]
                    row_dict = dict(zip(columns, result))
                    logger.info(f"컬럼 매핑: {columns}")
                    logger.info(f"행 데이터: {row_dict}")
                    
                    # 설정 업데이트
                    for db_col, setting_key in column_mapping.items():
                        if db_col in row_dict and row_dict[db_col] is not None:
                            old_value = self.settings.get(setting_key)
                            
                            # 타입별 처리
                            if db_col in ['AUTO_LED_MODE', 'SLEEP_MODE_ENABLED', 'USE_SIMPLE_SENSOR_MODE']:
                                self.settings[setting_key] = bool(row_dict[db_col])
                            elif db_col in ['LOCATION_LAT', 'LOCATION_LNG']:
                                self.settings[setting_key] = float(row_dict[db_col])
                            elif db_col in ['SLEEP_START_HOUR', 'SLEEP_END_HOUR']:
                                self.settings[setting_key] = int(row_dict[db_col])
                            else:
                                self.settings[setting_key] = float(row_dict[db_col])
                            
                            logger.debug(f"설정 업데이트: {setting_key}")
                    
                    self.last_update = datetime.now()
                    logger.debug(f"환경 설정이 데이터베이스에서 로드됨")
                    return True
                else:
                    logger.warning("데이터베이스에서 환경 설정을 찾을 수 없습니다. 기본값을 사용합니다.")
                    return False
                    
            except mysql.connector.Error as err:
                logger.error(f'환경 설정 로드 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def get_setting(self, key, default=None):
        """설정값 조회"""
        return self.settings.get(key, default)
    
    def update_setting(self, key, value):
        """설정값 업데이트"""
        self.settings[key] = value
    
    def should_reload_settings(self):
        """설정을 다시 로드해야 하는지 확인 (5분마다)"""
        if self.last_update is None:
            return True
        
        time_diff = datetime.now() - self.last_update
        return time_diff.total_seconds() > 300  # 5분
    
    def get_led_threshold(self):
        """LED 기준값 반환 (자동 모드면 일몰/일출 기반 계산, 수동 모드면 수동 설정값)"""
        auto_mode = self.get_setting('autoLedMode', True)
        
        if auto_mode:
            # 자동 모드: 일몰/일출 시간 기반 계산
            lat = self.get_setting('locationLat', 37.5665)
            lng = self.get_setting('locationLng', 126.9780)
            
            auto_threshold = self.sunrise_sunset_api.calculate_auto_led_threshold(lat, lng)
            logger.info(f"자동 LED 기준값 계산: {auto_threshold} lux (위도: {lat}, 경도: {lng})")
            return auto_threshold
        else:
            # 수동 모드: 사용자 설정값 사용
            manual_threshold = self.get_setting('manualLedThreshold', 300)
            logger.info(f"수동 LED 기준값 사용: {manual_threshold} lux")
            return manual_threshold
    
    def is_sleep_time(self):
        """현재 시간이 수면 시간인지 확인"""
        sleep_mode_enabled = self.get_setting('sleepModeEnabled', True)
        
        if not sleep_mode_enabled:
            return False
        
        sleep_start = self.get_setting('sleepStartHour', 22)
        sleep_end = self.get_setting('sleepEndHour', 6)
        current_hour = datetime.now().hour
        
        # 수면 시간이 자정을 넘어가는 경우 (예: 22시 ~ 6시)
        if sleep_start > sleep_end:
            return current_hour >= sleep_start or current_hour < sleep_end
        else:
            # 수면 시간이 같은 날 내에 있는 경우 (예: 10시 ~ 18시)
            return sleep_start <= current_hour < sleep_end


class SunriseSunsetAPI:
    """일몰/일출 시간 API 클래스 (기상청 API 우선 사용)"""
    
    def __init__(self):
        # 기상청 단기예보 조회서비스 API
        self.kma_api_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
        self.kma_api_key = "YOUR_API_KEY"  # 실제 사용시 기상청 API 키 필요
        
        # 백업용 Sunrise-Sunset API
        self.sunrise_sunset_url = "https://api.sunrise-sunset.org/json"
        
        self.cache = {}  # 캐시를 위한 딕셔너리
        self.cache_duration = 3600  # 1시간 캐시
    
    def get_sunrise_sunset_from_kma(self, lat: float, lng: float, date: str = None) -> Dict[str, Any]:
        """기상청 API로 일몰/일출 시간 조회"""
        try:
            # 기상청 API는 좌표를 격자 좌표로 변환해야 함
            nx, ny = self._lat_lng_to_grid(lat, lng)
            
            # 현재 시간 기준으로 조회
            now = datetime.now()
            base_date = now.strftime('%Y%m%d')
            base_time = now.strftime('%H%M')
            
            params = {
                'serviceKey': self.kma_api_key,
                'numOfRows': 1000,
                'pageNo': 1,
                'dataType': 'JSON',
                'base_date': base_date,
                'base_time': base_time,
                'nx': nx,
                'ny': ny
            }
            
            response = requests.get(self.kma_api_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['response']['header']['resultCode'] == '00':
                items = data['response']['body']['items']['item']
                
                # 일몰/일출 시간 찾기
                sunrise_time = None
                sunset_time = None
                
                for item in items:
                    if item['category'] == 'SUNRISE':
                        sunrise_time = item['fcstTime']
                    elif item['category'] == 'SUNSET':
                        sunset_time = item['fcstTime']
                
                if sunrise_time and sunset_time:
                    result = {
                        'sunrise': sunrise_time,
                        'sunset': sunset_time,
                        'date': date or now.strftime('%Y-%m-%d'),
                        'source': 'KMA'
                    }
                    logger.info(f"기상청 API로 일몰/일출 정보 조회 성공: {date}")
                    return result
                else:
                    logger.warning("기상청 API에서 일몰/일출 시간을 찾을 수 없음")
                    return None
            else:
                logger.error(f"기상청 API 오류: {data['response']['header']['resultMsg']}")
                return None
                
        except Exception as e:
            logger.error(f"기상청 API 요청 실패: {e}")
            return None
    
    def _lat_lng_to_grid(self, lat: float, lng: float) -> Tuple[int, int]:
        """위도/경도를 기상청 격자 좌표로 변환"""
        # 기상청 격자 좌표 변환 공식
        RE = 6371.00877  # 지구 반경(km)
        GRID = 5.0       # 격자 간격(km)
        SLAT1 = 30.0     # 투영 위도1(degree)
        SLAT2 = 60.0     # 투영 위도2(degree)
        OLON = 126.0     # 기준점 경도(degree)
        OLAT = 38.0      # 기준점 위도(degree)
        XO = 43          # 기준점 X좌표(GRID)
        YO = 136         # 기준점 Y좌표(GRID)
        
        DEGRAD = math.pi / 180.0
        RADDEG = 180.0 / math.pi
        
        re = RE / GRID
        slat1 = SLAT1 * DEGRAD
        slat2 = SLAT2 * DEGRAD
        olon = OLON * DEGRAD
        olat = OLAT * DEGRAD
        
        sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
        sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
        sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
        sf = math.pow(sf, sn) * math.cos(slat1) / sn
        ro = math.tan(math.pi * 0.25 + olat * 0.5)
        ro = re * sf / math.pow(ro, sn)
        
        ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
        theta = lng * DEGRAD - olon
        
        x = math.floor(ra * math.sin(theta) + XO + 0.5)
        y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
        
        return int(x), int(y)
    
    def get_sunrise_sunset(self, lat: float, lng: float, date: str = None) -> Dict[str, Any]:
        """일몰/일출 시간 조회 (기상청 API 우선, 백업용 Sunrise-Sunset API)"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        cache_key = f"{lat}_{lng}_{date}"
        
        # 캐시 확인
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_duration:
                logger.info(f"캐시에서 일몰/일출 정보 반환: {date}")
                return cached_data
        
        # 1. 기상청 API 시도
        result = self.get_sunrise_sunset_from_kma(lat, lng, date)
        
        # 2. 기상청 API 실패시 백업 API 사용
        if not result:
            logger.info("기상청 API 실패, 백업 API 사용")
            try:
                params = {
                    'lat': lat,
                    'lng': lng,
                    'date': date,
                    'formatted': 0  # ISO 8601 형식으로 반환
                }
                
                response = requests.get(self.sunrise_sunset_url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                
                if data['status'] == 'OK':
                    result = {
                        'sunrise': data['results']['sunrise'],
                        'sunset': data['results']['sunset'],
                        'day_length': data['results']['day_length'],
                        'date': date,
                        'source': 'Sunrise-Sunset'
                    }
                    logger.info(f"백업 API로 일몰/일출 정보 조회 성공: {date}")
                else:
                    logger.error(f"백업 API 오류: {data}")
                    return None
                    
            except requests.RequestException as e:
                logger.error(f"백업 API 요청 실패: {e}")
                return None
            except Exception as e:
                logger.error(f"백업 API 정보 처리 오류: {e}")
                return None
        
        if result:
            # 캐시에 저장
            self.cache[cache_key] = (result, time.time())
            return result
        
        return None
    
    def calculate_auto_led_threshold(self, lat: float, lng: float) -> int:
        """일몰/일출 시간을 기반으로 자동 LED 기준값 계산"""
        try:
            # 오늘 날짜의 일몰/일출 정보 조회
            sunset_info = self.get_sunrise_sunset(lat, lng)
            
            if not sunset_info:
                logger.warning("일몰/일출 정보를 가져올 수 없어 기본값 사용")
                return 300
            
            # 일몰 시간 파싱 (UTC 시간)
            sunset_utc = datetime.fromisoformat(sunset_info['sunset'].replace('Z', '+00:00'))
            
            # 현재 시간 (UTC)
            now_utc = datetime.now(tz=sunset_utc.tzinfo)
            
            # 일몰 1시간 전부터 LED 켜기 시작
            led_start_time = sunset_utc - timedelta(hours=1)
            
            # 일출 1시간 후까지 LED 켜기 유지
            sunrise_utc = datetime.fromisoformat(sunset_info['sunrise'].replace('Z', '+00:00'))
            led_end_time = sunrise_utc + timedelta(hours=1)
            
            # 현재 시간이 LED 켜야 할 시간대인지 확인
            if led_start_time <= now_utc <= led_end_time:
                # 밤 시간대: 낮은 조도에서도 LED 켜기 (기준값 낮춤)
                auto_threshold = 200
                logger.info(f"밤 시간대 LED 기준값: {auto_threshold} lux")
            else:
                # 낮 시간대: 높은 조도에서만 LED 켜기 (기준값 높임)
                auto_threshold = 500
                logger.info(f"낮 시간대 LED 기준값: {auto_threshold} lux")
            
            return auto_threshold
            
        except Exception as e:
            logger.error(f"자동 LED 기준값 계산 오류: {e}")
            return 300  # 기본값 반환


class DatabaseManager:
    """데이터베이스 연결 관리 (최적화된 버전)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connection_pool = []
        self._max_pool_size = 5
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            # 연결 풀에서 기존 연결 재사용 시도
            if self._connection_pool:
                conn = self._connection_pool.pop()
                if conn.is_connected():
                    yield conn
                    return
                else:
                    conn.close()
            
            # 새 연결 생성
            conn = mysql.connector.connect(**self.config)
            yield conn
        except mysql.connector.Error as err:
            logger.error(f'데이터베이스 연결 오류: {err}')
            yield None
        finally:
            if conn and conn.is_connected():
                # 연결을 풀에 반환 (최대 크기 제한)
                if len(self._connection_pool) < self._max_pool_size:
                    self._connection_pool.append(conn)
                else:
                    conn.close()
    
    def save_farm_status(self, sensor_data: Dict[str, Any], farm_num: int) -> bool:
        """축사 환경 정보 저장 (배치 처리)"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            try:
                cursor = conn.cursor()
                sql = """
                INSERT INTO FARM_STATUS(
                    NO2_DATA, TEMP_DATA, HUM_DATA, LUX_DATA, 
                    CO_DATA, CO2_DATA, NH3_DATA, FARM_ID
                ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    sensor_data['no2'],
                    sensor_data['temperature'],
                    sensor_data['humidity'],
                    sensor_data['lux'],
                    sensor_data['co'],
                    sensor_data['co2'],
                    sensor_data['nh3'],
                    farm_num
                ))
                conn.commit()
                logger.info(f"환경 정보 저장 완료")
                return True
            except mysql.connector.Error as err:
                logger.error(f'환경 정보 저장 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def save_danger_notice(self, content: str, category: str, farm_num: int) -> bool:
        """위험 알림 저장"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            try:
                cursor = conn.cursor()
                sql = """
                INSERT INTO DANGER_NOTICE(
                    NOTICE_CONTENT, NOTICE_CATEGORY, FARM_NUM
                ) VALUES(%s, %s, %s)
                """
                cursor.execute(sql, (content, category, farm_num))
                conn.commit()
                logger.warning(f"⚠️ 위험 알림: [{category}] {content}")
                return True
            except mysql.connector.Error as err:
                logger.error(f'위험 알림 저장 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def cleanup(self):
        """연결 풀 정리"""
        for conn in self._connection_pool:
            if conn.is_connected():
                conn.close()
        self._connection_pool.clear()


class EnvSensorReader:
    """환경 센서 읽기 (최적화된 버전)"""
    
    def __init__(self, config: EnvConfig):
        self.config = config
        if HARDWARE_AVAILABLE:
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 1000000
            self.dht_sensor = adafruit_dht.DHT22(board.D17)
        else:
            self.spi = None
            self.dht_sensor = None
        self.ro_value = 15.0
        self._last_readings = {}  # 캐시된 센서 값들
        self._cache_timeout = 5  # 5초 캐시
    
    def read_adc(self, channel: int) -> int:
        if not HARDWARE_AVAILABLE or not self.spi:
            return 512  # 중간값 반환
        
        if channel > 7 or channel < 0:
            return -1
        r = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((r[1] & 3) << 8) + r[2]
    
    def read_voltage_average(self, channel: int, samples: int = 3) -> float:
        """전압 평균값 읽기 (샘플 수 최적화)"""
        if not HARDWARE_AVAILABLE:
            return 2.5  # 기본값
        
        total = sum(self.read_adc(channel) * 5.0 / 1024.0 for _ in range(samples))
        return total / samples
    
    def read_dht_sensor(self, max_retries: int = 2) -> Tuple[Optional[float], Optional[float]]:
        """DHT 센서 읽기 (재시도 횟수 최적화)"""
        if not HARDWARE_AVAILABLE or not self.dht_sensor:
            return 25.0, 60.0  # 기본값
        
        for attempt in range(max_retries):
            try:
                humidity = self.dht_sensor.humidity
                temperature = self.dht_sensor.temperature
                
                if humidity is not None and temperature is not None:
                    return temperature, humidity
            except RuntimeError as err:
                logger.warning(f'DHT 센서 읽기 오류 ({attempt+1}/{max_retries}): {err}')
                if attempt < max_retries - 1:
                    time.sleep(1)  # 대기 시간 단축
        
        return None, None
    
    def calculate_rs(self, voltage: float) -> float:
        if voltage >= 4.9 or voltage <= 0.1:
            return -1
        rs = ((5.0 * self.config.RLOAD) / voltage) - self.config.RLOAD
        return max(0.1, rs)
    
    def calculate_co2(self, voltage: float, humidity: Optional[float] = None) -> float:
        if self.ro_value <= 0:
            return 400
        
        rs = self.calculate_rs(voltage)
        if rs <= 0:
            return 400
        
        ratio = rs / self.ro_value
        
        if humidity is not None and humidity > 60:
            humidity_factor = 1.0 + (humidity - 60) * 0.005
            ratio *= humidity_factor
        
        co2_ppm = self.config.CO2_CURVE_A * math.pow(ratio, self.config.CO2_CURVE_B) * 100
        
        if co2_ppm < 350:
            co2_ppm = 350 + (4.0 - ratio) * 50
        elif co2_ppm > 5000:
            co2_ppm = 5000
        
        return co2_ppm
    
    def calculate_gas(self, adc_value: int, gas_type: str) -> float:
        if adc_value <= 0:
            return 0
        
        voltage = (adc_value / 1024.0) * 5.0
        rs = self.calculate_rs(voltage)
        if rs <= 0:
            return 0
        
        rzero = self.ro_value if self.ro_value > 0 else 64.13
        ratio = rs / rzero
        
        gas_params = {
            "NO2": (self.config.NO2_PARA, self.config.NO2_PARB),
            "CO": (self.config.CO_PARA, self.config.CO_PARB),
            "NH3": (self.config.NH3_PARA, self.config.NH3_PARB)
        }
        
        if gas_type in gas_params:
            para, parb = gas_params[gas_type]
            concentration = para * math.pow(ratio, -parb)
            return max(0, concentration)
        
        return 0
    
    def read_all_sensors(self) -> Dict[str, Any]:
        """모든 센서 읽기 (캐시 활용)"""
        current_time = time.time()
        
        # 캐시된 값이 유효한지 확인
        if (self._last_readings and 
            current_time - self._last_readings.get('timestamp', 0) < self._cache_timeout):
            return self._last_readings
        
        # 센서 값 읽기
        temperature, humidity = self.read_dht_sensor()
        
        # ADC 값들 읽기
        ldr_adc = self.read_adc(self.config.LDR_CHANNEL)
        mq_adc = self.read_adc(self.config.MQ_CHANNEL)
        
        # 조도 계산
        lux = (ldr_adc / 1024.0) * 1000 if ldr_adc > 0 else 0
        
        # 가스 농도 계산
        co2 = self.calculate_co2(mq_adc, humidity)
        co = self.calculate_gas(mq_adc, "CO")
        nh3 = self.calculate_gas(mq_adc, "NH3")
        no2 = self.calculate_gas(mq_adc, "NO2")
        
        sensor_data = {
            'temperature': temperature or 25.0,
            'humidity': humidity or 60.0,
            'lux': lux,
            'co2': co2,
            'co': co,
            'nh3': nh3,
            'no2': no2,
            'timestamp': current_time
        }
        
        # 캐시 업데이트
        self._last_readings = sensor_data
        
        return sensor_data
    
    def read_simple_gas_sensors(self):
        """간단한 가스 센서 읽기 (env_monitor_simple.py 방식)"""
        if not HARDWARE_AVAILABLE:
            # 각 가스별로 적정 범위의 기본값 설정
            return {
                'nh3': 15,    # 15ppm 정도
                'co2': 400,   # 400ppm 정도
                'no2': 20,    # 20ppb 정도
                'co': 5       # 5ppm 정도
            }
        
        try:
            # ADC 원시 값 읽기
            nh3_raw = self.read_adc(1)  # NH3_CHANNEL
            co2_raw = self.read_adc(2)  # CO2_CHANNEL
            no2_raw = self.read_adc(3)  # NO2_CHANNEL
            co_raw = self.read_adc(4)   # CO_CHANNEL
            
            # ADC 값을 실제 단위로 변환
            sensors = {
                'nh3': round((nh3_raw / 1023.0) * 50, 1),    # 0-50 ppm
                'co2': round((co2_raw / 1023.0) * 2000, 1),  # 0-2000 ppm
                'no2': round((no2_raw / 1023.0) * 200, 1),   # 0-200 ppb
                'co': round((co_raw / 1023.0) * 100, 1)      # 0-100 ppm
            }
            return sensors
        except Exception as e:
            logger.error(f"간단한 가스 센서 읽기 실패: {e}")
            return {
                'nh3': 15,
                'co2': 400,
                'no2': 20,
                'co': 5
            }
    
    def cleanup(self):
        """리소스 정리"""
        if self.spi:
            self.spi.close()


class DynamicDeviceController:
    """동적 설정을 지원하는 장치 제어"""
    
    def __init__(self, config, settings_manager):
        self.config = config
        self.settings_manager = settings_manager
        self.servo_position = 90
        self.led_status = "OFF"
        self.fan_status = False
        self.door_status = "닫힘"
        self.window_status = "닫힘"
        self._setup_gpio()
        self._setup_pwm()
    
    def _setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.config.MOTOR_A, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.config.MOTOR_B, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.config.LED_PIN, GPIO.OUT)
        GPIO.setup(self.config.SERVO_PIN, GPIO.OUT)
    
    def _setup_pwm(self):
        self.pwm_a = GPIO.PWM(self.config.MOTOR_A, self.config.FREQ)
        self.pwm_b = GPIO.PWM(self.config.MOTOR_B, self.config.FREQ)
        self.servo = GPIO.PWM(self.config.SERVO_PIN, 50)
        
        self.pwm_a.start(0)
        self.pwm_b.start(0)
        self.servo.start(0)
        
        self.set_servo_angle(90)
    
    def set_servo_angle(self, angle: int):
        angle = max(0, min(180, angle))
        duty = self.config.SERVO_MIN_DUTY + \
            (angle * (self.config.SERVO_MAX_DUTY - self.config.SERVO_MIN_DUTY) / 180.0)
        self.servo.ChangeDutyCycle(duty)
        time.sleep(0.5)
        self.servo.ChangeDutyCycle(0)
        self.servo_position = angle
    
    def control_led(self, lux):
        # 수면 시간 확인
        if self.settings_manager.is_sleep_time():
            if self.led_status != "OFF (수면시간)":
                old_status = self.led_status
                self.led_status = "OFF (수면시간)"
                print(f"LED {old_status} -> {self.led_status}")
            GPIO.output(self.config.LED_PIN, GPIO.LOW)
            return self.led_status
        
        # 자동/수동 모드에 따라 LED 기준값 계산
        threshold = self.settings_manager.get_led_threshold()
        
        if lux <= threshold:
            if self.led_status != "ON":
                old_status = self.led_status
                self.led_status = "ON"
                print(f"LED {old_status} -> {self.led_status}")
            GPIO.output(self.config.LED_PIN, GPIO.HIGH)
            return self.led_status
        else:
            if self.led_status != "OFF":
                old_status = self.led_status
                self.led_status = "OFF"
                print(f"LED {old_status} -> {self.led_status}")
            GPIO.output(self.config.LED_PIN, GPIO.LOW)
            return self.led_status
    
    def control_door(self, temp):
        open_temp = self.settings_manager.get_setting('doorOpenTemp', 25)
        close_temp = self.settings_manager.get_setting('doorCloseTemp', 15)
        
        # 히스테리시스 추가 (기준값 ±2°C)
        hysteresis = 2.0
        
        # 문이 열려있는 상태에서 닫힘 기준 확인
        if self.servo_position == 180:  # 문이 열려있을 때
            if temp <= (open_temp - hysteresis):  # 열림 기준보다 2도 낮아야 닫기
                self.set_servo_angle(0)
                old_status = self.door_status
                self.door_status = "닫힘"
                print(f"문 {old_status} -> {self.door_status}")
        else:  # 문이 닫혀있을 때
            if temp >= (close_temp + hysteresis):  # 닫힘 기준보다 2도 높아야 열기
                self.set_servo_angle(180)
                old_status = self.door_status
                self.door_status = "열림"
                print(f"문 {old_status} -> {self.door_status}")
    
    def control_servo(self, humidity):
        """서보 모터 제어 (창문) - 습도 기반"""
        if not HARDWARE_AVAILABLE:
            logger.info(f"서보 제어 (시뮬레이션): 습도 {humidity}%")
            return
        
        try:
            threshold = self.settings_manager.get_setting('servoThreshold', 60)
            hysteresis = 5.0  # 습도 히스테리시스 ±5%
            
            # 창문이 열려있는 상태에서 닫힘 기준 확인
            if self.servo_position == 90:  # 창문이 열려있을 때
                if humidity <= (threshold - hysteresis):  # 기준보다 5% 낮아야 닫기
                    self.set_servo_angle(0)
                    old_status = self.window_status
                    self.window_status = "닫힘"
                    print(f"창문 {old_status} -> {self.window_status}")
            else:  # 창문이 닫혀있을 때
                if humidity >= (threshold + hysteresis):  # 기준보다 5% 높아야 열기
                    self.set_servo_angle(90)
                    old_status = self.window_status
                    self.window_status = "열림"
                    print(f"창문 {old_status} -> {self.window_status}")
                
        except Exception as e:
            logger.error(f"서보 제어 실패: {e}")
    
    def control_fan(self, sensor_data):
        """팬 제어"""
        if not HARDWARE_AVAILABLE:
            logger.info(f"팬 제어 (시뮬레이션): CO2 {sensor_data.get('co2', 0):.1f}ppm")
            return False, "시뮬레이션"
        
        fan_needed = False
        reasons = []
        
        humidity_threshold = self.settings_manager.get_setting('fanHumidityThreshold', 75)
        co2_threshold = self.settings_manager.get_setting('fanCO2Threshold', 1000)
        co_threshold = self.settings_manager.get_setting('fanCOThreshold', 30)
        fan_speed = self.settings_manager.get_setting('fanSpeed', 60)
        
        if sensor_data.get('humidity', 0) >= humidity_threshold:
            fan_needed = True
            reasons.append(f"고습도")
        
        if sensor_data.get('co2', 0) > co2_threshold:
            fan_needed = True
            reasons.append(f"CO2높음")
        
        if sensor_data.get('co', 0) > co_threshold:
            fan_needed = True
            reasons.append(f"CO높음")
        
        try:
            if fan_needed:
                if not self.fan_status:
                    self.fan_status = True
                    print(f"팬 OFF -> ON")
                self.pwm_a.ChangeDutyCycle(fan_speed)
                return True, ", ".join(reasons)
            else:
                if self.fan_status:
                    self.fan_status = False
                    print(f"팬 ON -> OFF")
                self.pwm_a.ChangeDutyCycle(0)
                return False, ""
        except Exception as e:
            logger.error(f"팬 제어 실패: {e}")
            return False, f"제어 실패: {e}"
    
    def cleanup(self):
        self.pwm_a.ChangeDutyCycle(0)
        self.pwm_b.ChangeDutyCycle(0)
        self.servo.stop()
        self.pwm_a.stop()
        self.pwm_b.stop()
        GPIO.cleanup()


class WarmupManager:
    """센서 예열 관리"""
    
    def __init__(self, duration: int):
        self.duration = duration  # 예열 시간 (초)
        self.start_time = None
        self.is_warming = False
    
    def ask_warmup(self) -> bool:
        """예열 여부 선택"""
        # 사용자 입력 전에 API 차단 상태로 설정
        global latest_sensor_data
        latest_sensor_data['is_warming'] = True
        
        print("\n🔥 센서 예열 안내: 정확한 측정을 위해 30분간 예열을 권장합니다.")
        
        while True:
            choice = input("\n예열을 진행하시겠습니까? (y/n): ").strip().lower()
            if choice in ['y', 'yes', 'ㅛ']:
                return True
            elif choice in ['n', 'no', 'ㅜ']:
                print("\n⚠️  예열을 건너뜁니다. 초기 측정값이 부정확할 수 있습니다.\n")
                # 예열을 건너뛸 때도 정상 모드로 전환
                latest_sensor_data['is_warming'] = False
                return False
            else:
                print("잘못된 입력입니다. 'y' 또는 'n'을 입력해주세요.")
    
    def start_warmup(self):
        """예열 시작"""
        self.start_time = datetime.now()
        self.is_warming = True
        
        # 전역 변수 즉시 업데이트
        global latest_sensor_data
        latest_sensor_data['is_warming'] = True
        logger.info(f"센서 예열 시작 (예상 소요시간: {self.duration//60}분)")
    
    def get_progress(self) -> Tuple[int, int, bool]:
        """예열 진행률 반환 (경과 시간, 남은 시간, 완료 여부)"""
        if not self.is_warming or self.start_time is None:
            return 0, 0, True
        
        elapsed = int((datetime.now() - self.start_time).total_seconds())
        remaining = max(0, self.duration - elapsed)
        is_complete = elapsed >= self.duration
        
        return elapsed, remaining, is_complete
    
    def print_progress(self, sensor_data: Optional[Dict[str, Any]] = None):
        """예열 진행 상황 출력"""
        elapsed, remaining, is_complete = self.get_progress()
        
        if is_complete:
            self.is_warming = False
            print("\n✅ 예열완료")
            logger.info("센서 예열 완료 - 정상 모니터링 시작")
            return
        
        progress_percent = (elapsed / self.duration) * 100
        elapsed_min = elapsed // 60
        remaining_min = remaining // 60
        
        # 10초마다만 출력
        if elapsed % 10 == 0:
            print(f"🔥예열 {progress_percent:.0f}% ({elapsed_min}분/{remaining_min}분)")
    
    def complete_warmup(self):
        """예열 완료 처리"""
        self.is_warming = False
        
        # 전역 변수 업데이트
        global latest_sensor_data
        latest_sensor_data['is_warming'] = False
        
        print("\n✅ 모니터링 시작\n")


class DynamicEnvMonitorSystem:
    """동적 설정을 지원하는 환경 모니터링 시스템"""
    
    def __init__(self):
        self.config = EnvConfig()
        
        db_config = {
            'host': '192.168.30.111',
            'port': 3306,
            'user': 'rasberry',
            'password': 'mariadb',
            'database': 'team_db'
        }
        
        self.db_manager = DatabaseManager(db_config)
        self.sensor_reader = EnvSensorReader(self.config)
        
        # 설정 관리자 초기화
        self.settings_manager = EnvSettingsManager(self.db_manager, self.config.FARM_NUM)
        
        # 동적 설정 로드
        self.settings_manager.load_settings_from_db()
        
        # 동적 설정을 사용하는 컨트롤러로 교체
        self.device_controller = DynamicDeviceController(self.config, self.settings_manager)
        self.warmup_manager = WarmupManager(self.config.WARMUP_DURATION)
        
        logger.info("동적 환경 모니터링 시스템 초기화 완료")
    
    def read_sensors(self, use_simple_mode: bool = False) -> Optional[Dict[str, Any]]:
        """센서 데이터 읽기 (고급 모드 또는 간단 모드 선택 가능)"""
        logger.debug(f"센서 읽기 시작 - 간단 모드: {use_simple_mode}")
        
        temp, hum = self.sensor_reader.read_dht_sensor()
        logger.debug(f"DHT 센서 읽기 결과: temp={temp}, hum={hum}")
        
        if temp is None or hum is None:
            logger.warning("온습도 센서 오류")
            return None
        
        lux = self.sensor_reader.read_adc(self.config.LDR_CHANNEL)
        logger.debug(f"LDR 센서 읽기 결과: lux={lux}")
        
        if use_simple_mode:
            # 간단 모드: env_monitor_simple.py 방식
            gas_data = self.sensor_reader.read_simple_gas_sensors()
            return {
                'temperature': temp,
                'humidity': hum,
                'lux': lux,
                'co2': gas_data['co2'],
                'no2': gas_data['no2'],
                'co': gas_data['co'],
                'nh3': gas_data['nh3']
            }
        else:
            # 고급 모드: 기존 방식 (센서 특성곡선 사용)
            mq_voltage = self.sensor_reader.read_voltage_average(self.config.MQ_CHANNEL)
            co2 = self.sensor_reader.calculate_co2(mq_voltage, hum)
            
            mq_adc = self.sensor_reader.read_adc(self.config.MQ_CHANNEL)
            no2 = self.sensor_reader.calculate_gas(mq_adc, "NO2")
            co = self.sensor_reader.calculate_gas(mq_adc, "CO")
            nh3 = self.sensor_reader.calculate_gas(mq_adc, "NH3")
            
            return {
                'temperature': temp,
                'humidity': hum,
                'lux': lux,
                'co2': co2,
                'no2': no2,
                'co': co,
                'nh3': nh3
            }
    
    def check_dangers(self, sensor_data: Dict[str, Any], is_warming: bool = False):
        """동적 설정을 사용한 위험 알림 체크 (예열 중일 때는 저장하지 않음)"""
        if is_warming:
            logger.info("예열 중이므로 위험 알림을 저장하지 않습니다.")
            return
            
        temp = sensor_data.get('temperature')
        if temp:
            temp_high_alert = self.settings_manager.get_setting('tempHighAlert', 35)
            temp_low_alert = self.settings_manager.get_setting('tempLowAlert', 10)
            
            if temp >= temp_high_alert:
                self.db_manager.save_danger_notice(
                    f'🌡️ 온도가 {temp:.1f}°C로 너무 높습니다.', 
                    '온도', self.config.FARM_NUM)
            elif temp <= temp_low_alert:
                self.db_manager.save_danger_notice(
                    f'🌡️ 온도가 {temp:.1f}°C로 너무 낮습니다.', 
                    '온도', self.config.FARM_NUM)
        
        hum = sensor_data.get('humidity')
        if hum:
            humidity_high_alert = self.settings_manager.get_setting('humidityHighAlert', 85)
            humidity_low_alert = self.settings_manager.get_setting('humidityLowAlert', 30)
            
            if hum >= humidity_high_alert:
                self.db_manager.save_danger_notice(
                    f'💧 습도가 {hum:.1f}%로 너무 높습니다.', 
                    '습도', self.config.FARM_NUM)
            elif hum <= humidity_low_alert:
                self.db_manager.save_danger_notice(
                    f'💧 습도가 {hum:.1f}%로 너무 낮습니다.', 
                    '습도', self.config.FARM_NUM)
        
        co2_alert = self.settings_manager.get_setting('co2Alert', 2000)
        if sensor_data.get('co2', 0) > co2_alert:
            self.db_manager.save_danger_notice(
                f'⚠️ CO2 농도가 {sensor_data["co2"]:.1f}ppm으로 너무 높습니다.', 
                'CO2', self.config.FARM_NUM)
        
        co_alert = self.settings_manager.get_setting('coAlert', 50)
        if sensor_data.get('co', 0) > co_alert:
            self.db_manager.save_danger_notice(
                f'⚠️ CO 농도가 {sensor_data["co"]:.3f}ppm으로 위험합니다.', 
                'CO', self.config.FARM_NUM)
        
        nh3_alert = self.settings_manager.get_setting('nh3Alert', 25)
        if sensor_data.get('nh3', 0) > nh3_alert:
            self.db_manager.save_danger_notice(
                f'⚠️ 암모니아 농도가 {sensor_data["nh3"]:.3f}ppm으로 높습니다.', 
                'NH3', self.config.FARM_NUM)
    
    def control_devices(self, sensor_data: Dict[str, Any]):
        """동적 설정을 사용한 장치 제어"""
        led_status = self.device_controller.control_led(sensor_data['lux'])
        
        temp = sensor_data.get('temperature')
        if temp is not None:
            self.device_controller.control_door(temp)
        
        humidity = sensor_data.get('humidity')
        if humidity is not None:
            self.device_controller.control_servo(humidity)
        
        fan_active, fan_reason = self.device_controller.control_fan(sensor_data)
        if fan_active:
            logger.info(f"팬 가동: {fan_reason}")
        
        return led_status, fan_active
    
    def print_status(self, sensor_data: Dict[str, Any]):
        timestamp = time.strftime("%H:%M")
        print(f"[{timestamp}] {sensor_data['temperature']:.1f}°C {sensor_data['humidity']:.0f}% "
              f"CO2:{sensor_data['co2']:.0f} CO:{sensor_data['co']:.1f} NH3:{sensor_data['nh3']:.1f}")
    
    def run(self):
        """메인 실행 루프 (설정 자동 리로드 포함)"""
        global latest_sensor_data  # 전역 변수 선언을 함수 시작 부분에 한 번만
        
        logger.info("="*60)
        logger.info("동적 환경 모니터링 시스템 시작")
        logger.info("="*60)
        
        # 예열 여부 선택
        need_warmup = self.warmup_manager.ask_warmup()
        
        if need_warmup:
            self.warmup_manager.start_warmup()
        
        loop_count = 0
        
        try:
            while True:
                # 설정 자동 리로드 (5분마다)
                if self.settings_manager.should_reload_settings():
                    self.settings_manager.load_settings_from_db()
                
                # 예열 중인지 확인
                if self.warmup_manager.is_warming:
                    # 예열 중일 때는 전역 변수에 예열 상태만 업데이트
                    latest_sensor_data['is_warming'] = True
                    logger.debug(f"예열 중 - is_warming 설정: {latest_sensor_data['is_warming']}")
                    
                    # 예열 중에도 공기질 센서는 읽어야 함 (정확한 측정을 위해)
                    temp, hum = self.sensor_reader.read_dht_sensor()
                    if temp is not None and hum is not None:
                        # 공기질 센서 읽기 (예열 중에도 필요)
                        mq_voltage = self.sensor_reader.read_voltage_average(self.config.MQ_CHANNEL)
                        co2 = self.sensor_reader.calculate_co2(mq_voltage, hum)
                        
                        mq_adc = self.sensor_reader.read_adc(self.config.MQ_CHANNEL)
                        no2 = self.sensor_reader.calculate_gas(mq_adc, "NO2")
                        co = self.sensor_reader.calculate_gas(mq_adc, "CO")
                        nh3 = self.sensor_reader.calculate_gas(mq_adc, "NH3")
                        
                        simple_data = {
                            'temperature': temp,
                            'humidity': hum,
                            'co2': co2,
                            'no2': no2,
                            'co': co,
                            'nh3': nh3
                        }
                        self.warmup_manager.print_progress(simple_data)
                    else:
                        self.warmup_manager.print_progress()
                    
                    _, _, is_complete = self.warmup_manager.get_progress()
                    if is_complete:
                        self.warmup_manager.complete_warmup()
                    
                    time.sleep(1)
                    continue
                
                # 센서 모드 설정 확인
                use_simple_mode = self.settings_manager.get_setting('useSimpleSensorMode', False)
                sensor_data = self.read_sensors(use_simple_mode)
                
                if sensor_data is None:
                    logger.warning("센서 데이터 읽기 실패 - 재시도 중...")
                    time.sleep(2)
                    continue
                
                logger.debug(f"센서 데이터 읽기 성공: {sensor_data}")
                
                # 전역 변수 업데이트
                latest_sensor_data = {
                    'temperature': round(sensor_data['temperature'], 1),
                    'humidity': round(sensor_data['humidity'], 1),
                    'lux': sensor_data['lux'],
                    'co2': round(sensor_data['co2'], 1),
                    'no2': round(sensor_data['no2'], 3),
                    'co': round(sensor_data['co'], 3),
                    'nh3': round(sensor_data['nh3'], 3),
                    'timestamp': datetime.now().isoformat(),
                    'is_warming': False
                }
                
                # 센서 히스토리 업데이트 (2초마다)
                if loop_count % 2 == 0:  # 2초마다 히스토리 업데이트
                    update_sensor_history(latest_sensor_data)
                    logger.debug(f"센서 히스토리 업데이트됨 - 온도: {latest_sensor_data['temperature']}, 히스토리 크기: {len(sensor_history['temperature'])}")
                
                # 정상 모니터링 모드
                self.check_dangers(sensor_data, is_warming=False)
                self.control_devices(sensor_data)
                
                if loop_count % 10 == 0:  # 10초마다 상태 출력
                    logger.debug(f"상태 출력 시도 - 센서 데이터: {sensor_data}")
                    self.print_status(sensor_data)
                
                # 5분마다 DB 저장 (예열 중이 아닐 때만)
                if loop_count % 300 == 0 and loop_count > 0:
                    db_data = {
                        'temperature': round(sensor_data['temperature'], 1),
                        'humidity': round(sensor_data['humidity'], 1),
                        'lux': sensor_data['lux'],
                        'no2': round(sensor_data['no2'], 3),
                        'co': round(sensor_data['co'], 3),
                        'co2': round(sensor_data['co2'], 1),
                        'nh3': round(sensor_data['nh3'], 3)
                    }
                    self.db_manager.save_farm_status(db_data, self.config.FARM_NUM)
                    loop_count = 0
                
                time.sleep(1)
                loop_count += 1
        
        except KeyboardInterrupt:
            logger.info("\n시스템 종료")
        
        finally:
            self.device_controller.cleanup()
            self.sensor_reader.spi.close()
            logger.info("정리 완료")


def main():
    global system_instance
    
    try:
        # Flask 서버를 별도 쓰레드로 시작
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Flask 서버 시작 (포트 5000)")
        
        # 동적 환경 모니터링 시스템 시작
        system_instance = DynamicEnvMonitorSystem()
        system_instance.run()
        
    except Exception as e:
        logger.error(f"시스템 오류: {e}", exc_info=True)
        raise
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
