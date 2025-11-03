"""
양계장 무게 측정 시스템 - 모이통 소비량 및 개별 닭 무게 (개선 버전)
- 데이터베이스 구조에 최적화
- REC_AGE 자동 계산
- 인덱스 최적화 고려
- 에러 처리 강화
"""

import mysql.connector
import time
import RPi.GPIO as GPIO
import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List
from contextlib import contextmanager
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('weight_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class WeightConfig:
    """무게 센서 설정"""
    WEIGHT_DOUT_PIN: int = 5
    WEIGHT_SCK_PIN: int = 6
    
    MIN_FEED_CONSUMPTION_THRESHOLD: float = 2.0
    CALIBRATION_FACTOR: int = 397
    WEIGHT_DRIFT_RATE: float = -0.05
    
    FARM_NUM: int = 1


@dataclass
class WeightState:
    """무게 시스템 상태"""
    session_feed_consumption: float = 0.0
    last_feed_weight: Optional[float] = None
    is_weight_stable: bool = False
    
    tare_offset: float = 0.0
    
    last_weight_calibration_time: float = 0.0
    weight_drift_samples: List[Tuple[float, float]] = field(default_factory=list)
    calculated_drift_rate: float = 0.0
    drift_rate_locked: bool = False
    
    # 무게별 드리프트율 보정 테이블
    weight_drift_table: Dict[float, float] = field(default_factory=dict)
    drift_calibration_weight: float = 0.0  # 드리프트 측정 시 사용한 무게
    
    weight_readings_buffer: List[float] = field(default_factory=list)
    
    chicken_weight_buffer: List[float] = field(default_factory=list)
    chicken_weight_stable: bool = False
    chicken_measurement_start_time: float = 0.0


class DatabaseManager:
    """데이터베이스 연결 관리 (개선 버전)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._ensure_tables_exist()
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = mysql.connector.connect(**self.config)
            yield conn
        except mysql.connector.Error as err:
            logger.error(f'데이터베이스 연결 오류: {err}')
            yield None
        finally:
            if conn:
                conn.close()
    
    def _ensure_tables_exist(self):
        """필요한 테이블들이 존재하는지 확인"""
        with self.get_connection() as conn:
            if not conn:
                logger.error("데이터베이스 연결 실패 - 테이블 확인 불가")
                return
            
            try:
                cursor = conn.cursor()
                
                # 필수 테이블 존재 확인
                required_tables = [
                    'CHICKEN_FARM', 'CHICKEN', 'CHICKEN_BATCH', 
                    'FARM_MANAGEMENT', 'chicken_weight_history'
                ]
                
                for table in required_tables:
                    cursor.execute(f"SHOW TABLES LIKE '{table}'")
                    if not cursor.fetchone():
                        logger.error(f"필수 테이블 '{table}'이 존재하지 않습니다!")
                        raise Exception(f"테이블 '{table}' 누락")
                
                logger.info("모든 필수 테이블 확인 완료")
                cursor.close()
                
            except mysql.connector.Error as err:
                logger.error(f'테이블 확인 오류: {err}')
                raise
    
    def save_feed_consumption(self, feed_consumption: float, farm_num: int) -> bool:
        """모이 소비량 저장 (개선 버전)"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            try:
                cursor = conn.cursor()
                sql = """
                INSERT INTO FARM_MANAGEMENT(
                    FEED_CONSUMPTION_G, WATER_CONSUMPTION_ML, FARM_NUM, REC_TIME
                ) VALUES(%s, 0, %s, NOW())
                """
                cursor.execute(sql, (feed_consumption, farm_num))
                conn.commit()
                logger.info(f"모이 소비량 저장: {feed_consumption}g (농장 {farm_num})")
                return True
            except mysql.connector.Error as err:
                logger.error(f'모이 소비량 저장 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def get_active_chickens(self, farm_num: int, batch_id: str = None) -> List[Dict[str, Any]]:
        """활성 닭 목록 조회 (배치별 필터링 가능)"""
        with self.get_connection() as conn:
            if not conn:
                return []
            
            try:
                cursor = conn.cursor(dictionary=True)
                
                if batch_id:
                    sql = """
                    SELECT 
                        c.CHICKEN_ID, 
                        c.RAW_WEIGHT, 
                        c.AGE, 
                        c.GROWTH_STAGE, 
                        c.BATCH_ID,
                        c.HEALTH_STATUS,
                        cb.ENTRY_DATE,
                        cb.CURRENT_COUNT
                    FROM CHICKEN c
                    LEFT JOIN CHICKEN_BATCH cb ON c.BATCH_ID = cb.BATCH_ID
                    WHERE c.FARM_NUM = %s AND c.BATCH_ID = %s
                    ORDER BY c.CHICKEN_ID
                    """
                    cursor.execute(sql, (farm_num, batch_id))
                    logger.info(f"농장 {farm_num}, 배치 {batch_id}에서 활성 닭 조회")
                else:
                    sql = """
                    SELECT 
                        c.CHICKEN_ID, 
                        c.RAW_WEIGHT, 
                        c.AGE, 
                        c.GROWTH_STAGE, 
                        c.BATCH_ID,
                        c.HEALTH_STATUS,
                        cb.ENTRY_DATE,
                        cb.CURRENT_COUNT
                    FROM CHICKEN c
                    LEFT JOIN CHICKEN_BATCH cb ON c.BATCH_ID = cb.BATCH_ID
                    WHERE c.FARM_NUM = %s
                    ORDER BY c.CHICKEN_ID
                    """
                    cursor.execute(sql, (farm_num,))
                    logger.info(f"농장 {farm_num}에서 모든 활성 닭 조회")
                
                chickens = cursor.fetchall()
                logger.info(f"조회된 닭 수: {len(chickens)}마리")
                return chickens
            except mysql.connector.Error as err:
                logger.error(f'닭 목록 조회 오류: {err}')
                return []
            finally:
                cursor.close()
    
    def get_available_batches(self, farm_num: int) -> List[Dict[str, Any]]:
        """농장의 사용 가능한 배치 목록 조회"""
        with self.get_connection() as conn:
            if not conn:
                return []
            
            try:
                cursor = conn.cursor(dictionary=True)
                sql = """
                SELECT DISTINCT 
                    cb.BATCH_ID,
                    cb.ENTRY_DATE,
                    cb.INITIAL_COUNT,
                    cb.CURRENT_COUNT,
                    cb.SHIPMENT_STATUS,
                    COUNT(c.CHICKEN_ID) as chicken_count
                FROM CHICKEN_BATCH cb
                LEFT JOIN CHICKEN c ON cb.BATCH_ID = c.BATCH_ID AND c.FARM_NUM = %s
                WHERE cb.FARM_NUM = %s
                GROUP BY cb.BATCH_ID, cb.ENTRY_DATE, cb.INITIAL_COUNT, cb.CURRENT_COUNT, cb.SHIPMENT_STATUS
                ORDER BY cb.BATCH_ID
                """
                cursor.execute(sql, (farm_num, farm_num))
                batches = cursor.fetchall()
                logger.info(f"농장 {farm_num}에서 {len(batches)}개 배치 조회")
                return batches
            except mysql.connector.Error as err:
                logger.error(f'배치 목록 조회 오류: {err}')
                return []
            finally:
                cursor.close()
    
    def update_chicken_weight(self, chicken_id: int, weight: float) -> bool:
        """개별 닭 무게 업데이트 (개선 버전)"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            try:
                cursor = conn.cursor()
                sql = """
                UPDATE CHICKEN 
                SET RAW_WEIGHT = %s 
                WHERE CHICKEN_ID = %s
                """
                cursor.execute(sql, (weight, chicken_id))
                
                if cursor.rowcount == 0:
                    logger.warning(f"닭 ID {chicken_id}를 찾을 수 없습니다")
                    return False
                
                conn.commit()
                logger.info(f"닭 ID {chicken_id} 무게 업데이트: {weight}g")
                return True
            except mysql.connector.Error as err:
                logger.error(f'닭 무게 업데이트 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def save_chicken_weight_history(self, chicken_id: int, weight: float) -> bool:
        """닭 무게 이력 저장 (REC_AGE 자동 계산)"""
        with self.get_connection() as conn:
            if not conn:
                return False
            
            try:
                cursor = conn.cursor()
                # REC_AGE를 현재 나이로 자동 계산
                sql = """
                INSERT INTO chicken_weight_history(CHICKEN_ID, RAW_WEIGHT, REC_TIME, REC_AGE)
                SELECT %s, %s, NOW(), AGE 
                FROM CHICKEN 
                WHERE CHICKEN_ID = %s
                """
                cursor.execute(sql, (chicken_id, weight, chicken_id))
                conn.commit()
                logger.debug(f"닭 ID {chicken_id} 무게 이력 저장: {weight}g")
                return True
            except mysql.connector.Error as err:
                logger.error(f'무게 이력 저장 오류: {err}')
                return False
            finally:
                cursor.close()
    
    def get_chicken_weight_history(self, chicken_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """닭 무게 이력 조회"""
        with self.get_connection() as conn:
            if not conn:
                return []
            
            try:
                cursor = conn.cursor(dictionary=True)
                sql = """
                SELECT 
                    HISTORY_ID,
                    RAW_WEIGHT,
                    REC_TIME,
                    REC_AGE
                FROM chicken_weight_history
                WHERE CHICKEN_ID = %s
                ORDER BY REC_TIME DESC
                LIMIT %s
                """
                cursor.execute(sql, (chicken_id, limit))
                history = cursor.fetchall()
                return history
            except mysql.connector.Error as err:
                logger.error(f'무게 이력 조회 오류: {err}')
                return []
            finally:
                cursor.close()
    
    def get_farm_statistics(self, farm_num: int) -> Dict[str, Any]:
        """농장 통계 정보 조회"""
        with self.get_connection() as conn:
            if not conn:
                return {}
            
            try:
                cursor = conn.cursor(dictionary=True)
                
                # 닭 통계
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_chickens,
                        AVG(RAW_WEIGHT) as avg_weight,
                        MIN(RAW_WEIGHT) as min_weight,
                        MAX(RAW_WEIGHT) as max_weight,
                        COUNT(CASE WHEN HEALTH_STATUS = 'HEALTHY' THEN 1 END) as healthy_count
                    FROM CHICKEN 
                    WHERE FARM_NUM = %s
                """, (farm_num,))
                
                chicken_stats = cursor.fetchone()
                
                # 최근 모이 소비량
                cursor.execute("""
                    SELECT SUM(FEED_CONSUMPTION_G) as total_feed_consumption
                    FROM FARM_MANAGEMENT 
                    WHERE FARM_NUM = %s 
                    AND DATE(REC_TIME) = CURDATE()
                """, (farm_num,))
                
                feed_stats = cursor.fetchone()
                
                return {
                    'chicken_stats': chicken_stats,
                    'feed_stats': feed_stats
                }
            except mysql.connector.Error as err:
                logger.error(f'농장 통계 조회 오류: {err}')
                return {}
            finally:
                cursor.close()


class WeightSensor:
    """HX711 무게 센서 (개선 버전)"""
    
    def __init__(self, config: WeightConfig):
        self.config = config
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.WEIGHT_DOUT_PIN, GPIO.IN)
        GPIO.setup(config.WEIGHT_SCK_PIN, GPIO.OUT)
        logger.info(f"HX711 센서 초기화 완료 (DOUT: {config.WEIGHT_DOUT_PIN}, SCK: {config.WEIGHT_SCK_PIN})")
    
    def read_raw(self) -> Optional[int]:
        """원시 데이터 읽기"""
        GPIO.output(self.config.WEIGHT_SCK_PIN, GPIO.LOW)
        
        # 데이터 준비 대기
        for _ in range(100):
            if not GPIO.input(self.config.WEIGHT_DOUT_PIN):
                break
            time.sleep(0.01)
        else:
            logger.warning("센서 데이터 준비 시간 초과")
            return None
        
        # 24비트 데이터 읽기
        data = 0
        for _ in range(24):
            GPIO.output(self.config.WEIGHT_SCK_PIN, GPIO.HIGH)
            data = data << 1
            if GPIO.input(self.config.WEIGHT_DOUT_PIN):
                data |= 1
            GPIO.output(self.config.WEIGHT_SCK_PIN, GPIO.LOW)
        
        # 채널 및 게인 설정
        GPIO.output(self.config.WEIGHT_SCK_PIN, GPIO.HIGH)
        GPIO.output(self.config.WEIGHT_SCK_PIN, GPIO.LOW)
        
        # 2의 보수 처리
        if data & 0x800000:
            data -= 0x1000000
        
        return data
    
    def read_average(self, samples: int = 10, tare_offset: float = 0) -> Optional[float]:
        """평균값 읽기"""
        readings = []
        for _ in range(samples):
            reading = self.read_raw()
            if reading is not None:
                readings.append(reading)
            time.sleep(0.01)
        
        if not readings:
            logger.warning("유효한 센서 데이터 없음")
            return None
        
        avg_raw = sum(readings) / len(readings)
        weight_grams = (avg_raw - tare_offset) / self.config.CALIBRATION_FACTOR
        return max(0, weight_grams)
    
    def tare(self) -> Optional[float]:
        """영점 조정"""
        logger.info("무게센서 영점 조정 중...")
        
        readings = []
        for _ in range(20):
            reading = self.read_raw()
            if reading is not None:
                readings.append(reading)
            time.sleep(0.1)
        
        if readings:
            tare_offset = sum(readings) / len(readings)
            logger.info(f"영점 조정 완료: {tare_offset:.0f}")
            return tare_offset
        else:
            logger.error("영점 조정 실패")
            return None


class WeightMonitorSystem:
    """무게 측정 시스템 (개선 버전)"""
    
    def __init__(self):
        self.config = WeightConfig()
        self.state = WeightState()
        
        db_config = {
            'host': '192.168.30.111',
            'port': 3306,
            'user': 'rasberry',
            'password': 'mariadb',
            'database': 'team_db',
            'autocommit': False,
            'charset': 'utf8mb4'
        }
        
        self.db_manager = DatabaseManager(db_config)
        self.sensor = WeightSensor(self.config)
        
        logger.info("무게 측정 시스템 초기화 완료")
    
    def get_drift_rate_for_weight(self, weight: float) -> float:
        """무게에 따른 드리프트율 계산"""
        if not self.state.weight_drift_table:
            # 드리프트 테이블이 없으면 기본값 사용
            return self.state.calculated_drift_rate or self.config.WEIGHT_DRIFT_RATE
        
        # 가장 가까운 무게의 드리프트율 찾기
        closest_weight = min(self.state.weight_drift_table.keys(), 
                           key=lambda x: abs(x - weight))
        
        # 선형 보간으로 정확한 드리프트율 계산
        weights = sorted(self.state.weight_drift_table.keys())
        
        if weight <= weights[0]:
            return self.state.weight_drift_table[weights[0]]
        elif weight >= weights[-1]:
            return self.state.weight_drift_table[weights[-1]]
        else:
            # 선형 보간
            for i in range(len(weights) - 1):
                if weights[i] <= weight <= weights[i + 1]:
                    w1, w2 = weights[i], weights[i + 1]
                    d1, d2 = self.state.weight_drift_table[w1], self.state.weight_drift_table[w2]
                    
                    # 선형 보간 공식
                    ratio = (weight - w1) / (w2 - w1)
                    return d1 + ratio * (d2 - d1)
        
        return self.state.calculated_drift_rate or self.config.WEIGHT_DRIFT_RATE
    
    def calibrate_drift(self):
        """드리프트율 측정 (무게별 보정)"""
        print(f"\n{'='*60}")
        print("드리프트율 측정 시작")
        print("="*60)
        print("1. 단일 무게로 드리프트 측정")
        print("2. 여러 무게로 드리프트 테이블 생성")
        print("3. 기존 드리프트 테이블 보기")
        print("="*60)
        
        choice = input("선택 (1-3) >>> ").strip()
        
        if choice == '1':
            self._calibrate_single_weight_drift()
        elif choice == '2':
            self._calibrate_weight_drift_table()
        elif choice == '3':
            self._show_drift_table()
        else:
            print("올바른 선택이 아닙니다.")
    
    def _calibrate_single_weight_drift(self):
        """단일 무게로 드리프트 측정"""
        print(f"\n{'='*60}")
        print("단일 무게 드리프트율 측정")
        print("모이통을 저울에 올려주세요.")
        print("약 90초간 무게 변화를 측정합니다.")
        print("="*60)
        
        user_input = input("\n측정 시작? (y/n) >>> ").lower().strip()
        if user_input != 'y':
            logger.info("드리프트율 측정 건너뛰기")
            return
        
        print("\n초기 무게 확인 중...")
        initial_readings = []
        for i in range(5):
            weight = self.sensor.read_average(tare_offset=self.state.tare_offset)
            if weight:
                initial_readings.append(weight)
                print(f"  측정 {i+1}: {weight:.2f}g")
            time.sleep(0.5)
        
        if not initial_readings:
            logger.error("초기 무게 측정 실패")
            return
        
        avg_weight = sum(initial_readings) / len(initial_readings)
        print(f"\n초기 평균 무게: {avg_weight:.2f}g")
        print("\n측정 중... (90초)")
        print("모이통을 움직이지 마세요!\n")
        
        drift_samples = []
        start_time = time.time()
        
        while time.time() - start_time < 90:
            if time.time() - start_time >= len(drift_samples) * 2:
                weight = self.sensor.read_average(tare_offset=self.state.tare_offset)
                if weight and weight > 0:
                    drift_samples.append((time.time(), weight))
                    print(f"[{len(drift_samples)}/45] {weight:.2f}g", end='\r')
            time.sleep(0.1)
        
        print("\n\n드리프트율 계산 중...")
        
        if len(drift_samples) < 10:
            logger.error("샘플 부족으로 드리프트율 계산 불가")
            return
        
        # 선형 회귀로 드리프트율 계산
        start_t = drift_samples[0][0]
        times = [t - start_t for t, w in drift_samples]
        weights = [w for t, w in drift_samples]
        
        n = len(times)
        sum_t = sum(times)
        sum_w = sum(weights)
        sum_tw = sum(t * w for t, w in zip(times, weights))
        sum_t2 = sum(t * t for t in times)
        
        drift_rate = (n * sum_tw - sum_t * sum_w) / (n * sum_t2 - sum_t * sum_t)
        
        print(f"\n{'='*60}")
        print(f"무게: {avg_weight:.2f}g")
        print(f"드리프트율: {drift_rate:.4f} g/s ({drift_rate * 60:.2f} g/min)")
        print(f"측정 샘플 수: {len(drift_samples)}개")
        
        if drift_rate < 0:
            print(f"⚠️  센서가 시간이 지날수록 무게를 과소측정합니다")
            print(f"   (90초당 약 {abs(drift_rate * 90):.2f}g 무게가 감소)")
        elif drift_rate > 0:
            print(f"⚠️  센서가 시간이 지날수록 무게를 과대측정합니다")
            print(f"   (90초당 약 {drift_rate * 90:.2f}g 무게가 증가)")
        else:
            print(f"✅ 센서 드리프트가 거의 없습니다")
        
        print("="*60)
        
        if abs(drift_rate) < 1.0:
            apply = input("\n적용? (y/n) >>> ").lower().strip()
            if apply == 'y':
                self.state.calculated_drift_rate = drift_rate
                self.state.drift_rate_locked = True
                self.state.drift_calibration_weight = avg_weight
                logger.info(f"드리프트율 적용: {drift_rate:.4f} g/s (무게: {avg_weight:.2f}g)")
                print(f"✅ 드리프트율이 적용되었습니다: {drift_rate:.4f} g/s")
            else:
                print("드리프트율 적용을 건너뛰었습니다.")
        else:
            logger.warning("드리프트율이 너무 큽니다. 센서 상태를 확인하세요.")
            print("❌ 드리프트율이 너무 큽니다. 센서 상태를 확인하세요.")
    
    def _calibrate_weight_drift_table(self):
        """여러 무게로 드리프트 테이블 생성"""
        print(f"\n{'='*60}")
        print("무게별 드리프트 테이블 생성")
        print("여러 무게에서 드리프트율을 측정합니다.")
        print("="*60)
        
        weights_to_test = []
        print("\n측정할 무게들을 입력하세요 (예: 12,24,36):")
        weight_input = input("무게 (g) >>> ").strip()
        
        try:
            weights_to_test = [float(w.strip()) for w in weight_input.split(',')]
            weights_to_test.sort()
        except ValueError:
            print("올바른 형식으로 입력하세요 (예: 12,24,36)")
            return
        
        print(f"\n측정할 무게: {weights_to_test}")
        confirm = input("계속? (y/n) >>> ").lower().strip()
        if confirm != 'y':
            return
        
        drift_table = {}
        
        for i, target_weight in enumerate(weights_to_test):
            print(f"\n{'='*60}")
            print(f"[{i+1}/{len(weights_to_test)}] 무게 {target_weight}g 드리프트 측정")
            print(f"{target_weight}g 무게추를 저울에 올려주세요.")
            print("="*60)
            
            input("준비 후 Enter >>> ")
            
            # 30초간 측정 (짧은 버전)
            print("측정 중... (30초)")
            drift_samples = []
            start_time = time.time()
            
            while time.time() - start_time < 30:
                if time.time() - start_time >= len(drift_samples) * 2:
                    weight = self.sensor.read_average(tare_offset=self.state.tare_offset)
                    if weight and weight > 0:
                        drift_samples.append((time.time(), weight))
                        print(f"[{len(drift_samples)}/15] {weight:.2f}g", end='\r')
                time.sleep(0.1)
            
            print("\n드리프트율 계산 중...")
            
            if len(drift_samples) >= 5:
                # 선형 회귀로 드리프트율 계산
                start_t = drift_samples[0][0]
                times = [t - start_t for t, w in drift_samples]
                weights = [w for t, w in drift_samples]
                
                n = len(times)
                sum_t = sum(times)
                sum_w = sum(weights)
                sum_tw = sum(t * w for t, w in zip(times, weights))
                sum_t2 = sum(t * t for t in times)
                
                if n * sum_t2 - sum_t * sum_t != 0:
                    drift_rate = (n * sum_tw - sum_t * sum_w) / (n * sum_t2 - sum_t * sum_t)
                    drift_table[target_weight] = drift_rate
                    print(f"✅ 무게 {target_weight}g: 드리프트율 {drift_rate:.4f} g/s")
                else:
                    print(f"❌ 무게 {target_weight}g: 드리프트율 계산 실패")
            else:
                print(f"❌ 무게 {target_weight}g: 샘플 부족")
        
        if drift_table:
            print(f"\n{'='*60}")
            print("드리프트 테이블 생성 완료:")
            print("="*60)
            for weight, drift in sorted(drift_table.items()):
                print(f"무게 {weight:6.1f}g: {drift:8.4f} g/s ({drift*60:6.2f} g/min)")
            print("="*60)
            
            apply = input("\n테이블을 적용하시겠습니까? (y/n) >>> ").lower().strip()
            if apply == 'y':
                self.state.weight_drift_table = drift_table
                self.state.drift_rate_locked = True
                logger.info(f"무게별 드리프트 테이블 적용: {len(drift_table)}개 무게")
                print("✅ 무게별 드리프트 테이블이 적용되었습니다!")
            else:
                print("드리프트 테이블 적용을 건너뛰었습니다.")
        else:
            print("❌ 유효한 드리프트 데이터가 없습니다.")
    
    def _show_drift_table(self):
        """기존 드리프트 테이블 보기"""
        print(f"\n{'='*60}")
        print("현재 드리프트 테이블:")
        print("="*60)
        
        if self.state.weight_drift_table:
            for weight, drift in sorted(self.state.weight_drift_table.items()):
                print(f"무게 {weight:6.1f}g: {drift:8.4f} g/s ({drift*60:6.2f} g/min)")
        else:
            print("드리프트 테이블이 없습니다.")
        
        if self.state.drift_calibration_weight > 0:
            print(f"\n단일 무게 드리프트율:")
            print(f"무게 {self.state.drift_calibration_weight:.1f}g: {self.state.calculated_drift_rate:.4f} g/s")
        
        print("="*60)
    
    def is_stable(self, buffer: List[float], threshold: float = 1.0) -> bool:
        """무게 안정성 판단"""
        if len(buffer) < 5:
            return False
        recent = buffer[-5:]
        return (max(recent) - min(recent)) <= threshold
    
    def track_feed_consumption(self):
        """모이 소비량 추적 (개선 버전)"""
        current_weight = self.sensor.read_average(tare_offset=self.state.tare_offset)
        
        if current_weight is None:
            return 0
        
        # 드리프트 보정 (모이 소비량 추적용, 무게별 드리프트율 사용)
        drift_rate = self.get_drift_rate_for_weight(current_weight)
        if self.state.last_weight_calibration_time > 0:
            elapsed = time.time() - self.state.last_weight_calibration_time
            # 드리프트 보정: 센서가 시간이 지날수록 무게를 과소측정하므로 보정값을 더함
            if drift_rate < 0:  # 음수 드리프트율 (센서가 무게를 과소측정)
                current_weight -= drift_rate * elapsed  # 음수를 빼면 양수가 됨
            else:  # 양수 드리프트율 (센서가 무게를 과대측정)
                current_weight -= drift_rate * elapsed  # 양수를 빼서 보정
        
        self.state.weight_readings_buffer.append(current_weight)
        if len(self.state.weight_readings_buffer) > 8:
            self.state.weight_readings_buffer.pop(0)
        
        self.state.is_weight_stable = self.is_stable(self.state.weight_readings_buffer)
        
        # 기준점 설정
        if self.state.last_feed_weight is None:
            if self.state.is_weight_stable:
                self.state.last_feed_weight = current_weight
                self.state.last_weight_calibration_time = time.time()
                logger.info(f"모이 기준점 설정: {current_weight:.1f}g")
            return 0
        
        # 소비량 계산
        if current_weight < self.state.last_feed_weight - self.config.MIN_FEED_CONSUMPTION_THRESHOLD:
            consumption = self.state.last_feed_weight - current_weight
            self.state.session_feed_consumption += consumption
            self.state.last_feed_weight = current_weight
            self.state.last_weight_calibration_time = time.time()
            logger.info(f"모이 소비: {consumption:.1f}g (누적: {self.state.session_feed_consumption:.1f}g)")
            return consumption
        
        # 보충 감지
        elif current_weight > self.state.last_feed_weight + 10.0:
            logger.info(f"모이 보충 감지: {self.state.last_feed_weight:.1f}g → {current_weight:.1f}g")
            self.state.last_feed_weight = current_weight
            self.state.last_weight_calibration_time = time.time()
        
        return 0
    
    def measure_chicken_weight(self) -> Optional[float]:
        """닭 무게 측정 (개선 버전)"""
        current_weight = self.sensor.read_average(tare_offset=self.state.tare_offset)
        
        if current_weight is None:
            return None
        
        if self.state.chicken_measurement_start_time == 0:
            self.state.chicken_measurement_start_time = time.time()
        
        # 드리프트 보정 (무게별 드리프트율 사용)
        drift_rate = self.get_drift_rate_for_weight(current_weight)
        elapsed = time.time() - self.state.chicken_measurement_start_time
        
        # 드리프트 보정: 센서가 시간이 지날수록 무게를 과소측정하므로 보정값을 더함
        if drift_rate < 0:  # 음수 드리프트율 (센서가 무게를 과소측정)
            compensated = current_weight - drift_rate * elapsed  # 음수를 빼면 양수가 됨
        else:  # 양수 드리프트율 (센서가 무게를 과대측정)
            compensated = current_weight - drift_rate * elapsed  # 양수를 빼서 보정
        
        logger.info(f"원시 무게: {current_weight:.2f}g, 드리프트율: {drift_rate:.4f}g/s, 경과시간: {elapsed:.1f}s, 보정후: {compensated:.2f}g")
        
        self.state.chicken_weight_buffer.append(compensated)
        if len(self.state.chicken_weight_buffer) > 8:
            self.state.chicken_weight_buffer.pop(0)
        
        self.state.chicken_weight_stable = self.is_stable(self.state.chicken_weight_buffer, 2.0)
        
        if self.state.chicken_weight_stable and len(self.state.chicken_weight_buffer) >= 5:
            return sum(self.state.chicken_weight_buffer) / len(self.state.chicken_weight_buffer)
        
        return None
    
    def measure_all_chickens(self, batch_id: str = None):
        """모든 닭 무게 측정 (배치별 선택 가능)"""
        # 배치 선택
        if batch_id is None:
            batches = self.db_manager.get_available_batches(self.config.FARM_NUM)
            
            if not batches:
                logger.warning("사용 가능한 배치가 없습니다")
                return
            
            print(f"\n{'='*60}")
            print("사용 가능한 배치 목록:")
            print("="*60)
            
            for i, batch in enumerate(batches):
                entry_date = batch['ENTRY_DATE'].strftime('%Y-%m-%d') if batch['ENTRY_DATE'] else 'N/A'
                shipment_status = "출하완료" if batch['SHIPMENT_STATUS'] else "사육중"
                print(f"{i+1}. 배치 ID: {batch['BATCH_ID']}")
                print(f"   입식일: {entry_date}")
                print(f"   초기 수: {batch['INITIAL_COUNT']}마리")
                print(f"   현재 수: {batch['CURRENT_COUNT']}마리")
                print(f"   실제 닭 수: {batch['chicken_count']}마리")
                print(f"   상태: {shipment_status}")
                print()
            
            print("0. 모든 배치 측정")
            print("="*60)
            
            while True:
                try:
                    choice = input("배치를 선택하세요 (번호 입력) >>> ").strip()
                    if choice == '0':
                        batch_id = None
                        break
                    elif choice.isdigit() and 1 <= int(choice) <= len(batches):
                        batch_id = batches[int(choice)-1]['BATCH_ID']
                        break
                    else:
                        print("올바른 번호를 입력하세요.")
                except (ValueError, IndexError):
                    print("올바른 번호를 입력하세요.")
        
        # 선택된 배치의 닭들 조회
        chickens = self.db_manager.get_active_chickens(self.config.FARM_NUM, batch_id)
        
        if not chickens:
            if batch_id:
                logger.warning(f"배치 {batch_id}에 측정할 닭이 없습니다")
            else:
                logger.warning("측정할 닭이 없습니다")
            return
        
        # 농장 통계 출력
        stats = self.db_manager.get_farm_statistics(self.config.FARM_NUM)
        if stats.get('chicken_stats'):
            cs = stats['chicken_stats']
            print(f"\n{'='*60}")
            if batch_id:
                print(f"농장 {self.config.FARM_NUM} - 배치 {batch_id} 통계")
            else:
                print(f"농장 {self.config.FARM_NUM} 전체 통계")
            print(f"총 닭 수: {cs['total_chickens']}마리")
            print(f"평균 무게: {cs['avg_weight']:.1f}g")
            print(f"무게 범위: {cs['min_weight']:.1f}g ~ {cs['max_weight']:.1f}g")
            print(f"건강한 닭: {cs['healthy_count']}마리")
            print("="*60)
        
        logger.info(f"\n{'='*60}")
        if batch_id:
            logger.info(f"배치 {batch_id} 닭 무게 측정 (총 {len(chickens)}마리)")
        else:
            logger.info(f"전체 닭 무게 측정 (총 {len(chickens)}마리)")
        logger.info(f"{'='*60}")
        
        measured_count = 0
        skipped_count = 0
        
        for idx, chicken in enumerate(chickens):
            chicken_id = chicken['CHICKEN_ID']
            current_weight = chicken.get('RAW_WEIGHT', 0)
            health_status = chicken.get('HEALTH_STATUS', 'UNKNOWN')
            chicken_batch_id = chicken.get('BATCH_ID', 'N/A')
            
            print(f"\n[{idx+1}/{len(chickens)}] 닭 ID: {chicken_id}")
            print(f"배치 ID: {chicken_batch_id}")
            print(f"이전 무게: {current_weight:.1f}g")
            print(f"건강 상태: {health_status}")
            
            user_input = input("준비 후 Enter (s=건너뛰기, q=종료, h=이력보기) >>> ").lower()
            
            if user_input == 'q':
                break
            elif user_input == 's':
                skipped_count += 1
                continue
            elif user_input == 'h':
                # 무게 이력 조회
                history = self.db_manager.get_chicken_weight_history(chicken_id, 5)
                if history:
                    print(f"\n닭 {chicken_id} 최근 무게 이력:")
                    for h in history:
                        print(f"  {h['REC_TIME']}: {h['RAW_WEIGHT']:.1f}g (나이: {h['REC_AGE']}일)")
                else:
                    print("무게 이력이 없습니다.")
                continue
            
            # 측정 시작
            self.state.chicken_weight_buffer = []
            self.state.chicken_weight_stable = False
            self.state.chicken_measurement_start_time = 0
            
            print("측정 중... (최대 30초)")
            start = time.time()
            measured = None
            
            while time.time() - start < 30:
                weight = self.measure_chicken_weight()
                if weight:
                    measured = weight
                    print(f"\n측정 완료: {measured:.1f}g")
                    break
                
                if self.state.chicken_weight_buffer:
                    current = self.state.chicken_weight_buffer[-1]
                    status = "안정됨" if self.state.chicken_weight_stable else "안정화중"
                    print(f"  {current:.1f}g | {status}   ", end='\r')
                
                time.sleep(0.5)
            
            if measured:
                # DB 업데이트
                if self.db_manager.update_chicken_weight(chicken_id, measured):
                    self.db_manager.save_chicken_weight_history(chicken_id, measured)
                    measured_count += 1
                    print(f"✅ 닭 {chicken_id} 무게 업데이트 완료")
                else:
                    print(f"❌ 닭 {chicken_id} 무게 업데이트 실패")
            else:
                logger.warning(f"닭 {chicken_id} 측정 실패")
        
        print(f"\n{'='*60}")
        if batch_id:
            print(f"배치 {batch_id} 측정 완료: {measured_count}마리 측정, {skipped_count}마리 건너뛰기")
        else:
            print(f"전체 측정 완료: {measured_count}마리 측정, {skipped_count}마리 건너뛰기")
        print("="*60)
    
    def run_feed_monitor(self):
        """모이 소비량 모니터링 (개선 버전)"""
        logger.info("="*60)
        logger.info("모이 소비량 모니터링 시작")
        logger.info("="*60)
        
        tare = self.sensor.tare()
        if tare:
            self.state.tare_offset = tare
        else:
            logger.error("영점 조정 실패 - 모니터링 중단")
            return
        
        self.calibrate_drift()
        
        print("\n명령어:")
        print("  t: 영점 재조정")
        print("  w: 닭 무게 측정")
        print("  s: 통계 보기")
        print("  q: 종료\n")
        
        accumulated_consumption = 0.0
        loop_count = 0
        
        try:
            while True:
                consumption = self.track_feed_consumption()
                accumulated_consumption += consumption
                
                if loop_count % 5 == 0:
                    weight = self.state.last_feed_weight or 0
                    stable = "O" if self.state.is_weight_stable else "X"
                    drift = self.state.calculated_drift_rate or self.config.WEIGHT_DRIFT_RATE
                    print(f"[{time.strftime('%H:%M:%S')}] 모이: {weight:.1f}g (안정:{stable}) | "
                          f"세션 소비: {self.state.session_feed_consumption:.1f}g | "
                          f"드리프트: {drift:.4f}g/s")
                
                # 10분마다 DB 저장
                if loop_count % 600 == 0 and accumulated_consumption > 0:
                    if self.db_manager.save_feed_consumption(accumulated_consumption, self.config.FARM_NUM):
                        print(f"✅ 모이 소비량 저장: {accumulated_consumption:.1f}g")
                        accumulated_consumption = 0.0
                    else:
                        print(f"❌ 모이 소비량 저장 실패: {accumulated_consumption:.1f}g")
                
                time.sleep(1)
                loop_count += 1
        
        except KeyboardInterrupt:
            logger.info("\n모니터링 종료")
            if accumulated_consumption > 0:
                if self.db_manager.save_feed_consumption(accumulated_consumption, self.config.FARM_NUM):
                    print(f"✅ 최종 모이 소비량 저장: {accumulated_consumption:.1f}g")
                else:
                    print(f"❌ 최종 모이 소비량 저장 실패: {accumulated_consumption:.1f}g")
    
    def run_interactive(self):
        """대화형 모드 (개선 버전)"""
        logger.info("="*60)
        logger.info("무게 측정 시스템 (대화형) - 개선 버전")
        logger.info("="*60)
        
        tare = self.sensor.tare()
        if tare:
            self.state.tare_offset = tare
        else:
            logger.error("영점 조정 실패")
            return
        
        while True:
            print("\n" + "="*60)
            print("1. 드리프트 측정")
            print("2. 모이 소비량 모니터링 시작")
            print("3. 개별 닭 무게 측정 (배치 선택)")
            print("4. 개별 닭 무게 측정 (전체)")
            print("5. 영점 재조정")
            print("6. 농장 통계 보기")
            print("7. 닭 무게 이력 조회")
            print("8. 배치 목록 보기")
            print("9. 드리프트율 상태 확인")
            print("10. 종료")
            print("="*60)
            
            choice = input("선택 >>> ").strip()
            
            if choice == '1':
                self.calibrate_drift()
            elif choice == '2':
                self.run_feed_monitor()
            elif choice == '3':
                # 배치 선택하여 측정
                self.measure_all_chickens()
                print("\n모이통을 다시 올려주세요")
                input("준비 후 Enter >>> ")
                tare = self.sensor.tare()
                if tare:
                    self.state.tare_offset = tare
            elif choice == '4':
                # 전체 닭 측정
                self.measure_all_chickens(batch_id=None)
                print("\n모이통을 다시 올려주세요")
                input("준비 후 Enter >>> ")
                tare = self.sensor.tare()
                if tare:
                    self.state.tare_offset = tare
            elif choice == '5':
                tare = self.sensor.tare()
                if tare:
                    self.state.tare_offset = tare
                    print("✅ 영점 조정 완료")
                else:
                    print("❌ 영점 조정 실패")
            elif choice == '6':
                stats = self.db_manager.get_farm_statistics(self.config.FARM_NUM)
                if stats:
                    cs = stats.get('chicken_stats', {})
                    fs = stats.get('feed_stats', {})
                    
                    print(f"\n농장 {self.config.FARM_NUM} 통계:")
                    print(f"총 닭 수: {cs.get('total_chickens', 0)}마리")
                    print(f"평균 무게: {cs.get('avg_weight', 0):.1f}g")
                    print(f"무게 범위: {cs.get('min_weight', 0):.1f}g ~ {cs.get('max_weight', 0):.1f}g")
                    print(f"건강한 닭: {cs.get('healthy_count', 0)}마리")
                    print(f"오늘 모이 소비량: {fs.get('total_feed_consumption', 0):.1f}g")
                else:
                    print("통계 조회 실패")
            elif choice == '7':
                chicken_id = input("닭 ID 입력 >>> ").strip()
                if chicken_id.isdigit():
                    history = self.db_manager.get_chicken_weight_history(int(chicken_id), 10)
                    if history:
                        print(f"\n닭 {chicken_id} 무게 이력:")
                        for h in history:
                            print(f"  {h['REC_TIME']}: {h['RAW_WEIGHT']:.1f}g (나이: {h['REC_AGE']}일)")
                    else:
                        print("무게 이력이 없습니다.")
                else:
                    print("올바른 닭 ID를 입력하세요.")
            elif choice == '8':
                # 배치 목록 보기
                batches = self.db_manager.get_available_batches(self.config.FARM_NUM)
                if batches:
                    print(f"\n{'='*60}")
                    print(f"농장 {self.config.FARM_NUM} 배치 목록:")
                    print("="*60)
                    
                    for batch in batches:
                        entry_date = batch['ENTRY_DATE'].strftime('%Y-%m-%d') if batch['ENTRY_DATE'] else 'N/A'
                        shipment_status = "출하완료" if batch['SHIPMENT_STATUS'] else "사육중"
                        print(f"배치 ID: {batch['BATCH_ID']}")
                        print(f"  입식일: {entry_date}")
                        print(f"  초기 수: {batch['INITIAL_COUNT']}마리")
                        print(f"  현재 수: {batch['CURRENT_COUNT']}마리")
                        print(f"  실제 닭 수: {batch['chicken_count']}마리")
                        print(f"  상태: {shipment_status}")
                        print()
                else:
                    print("사용 가능한 배치가 없습니다.")
            elif choice == '9':
                # 현재 드리프트율 상태 확인
                print(f"\n{'='*60}")
                print("현재 드리프트율 상태:")
                print("="*60)
                
                if self.state.weight_drift_table:
                    print("✅ 무게별 드리프트 테이블 적용됨:")
                    for weight, drift in sorted(self.state.weight_drift_table.items()):
                        print(f"   무게 {weight:6.1f}g: {drift:8.4f} g/s ({drift*60:6.2f} g/min)")
                elif self.state.drift_rate_locked:
                    drift_rate = self.state.calculated_drift_rate
                    print(f"✅ 단일 무게 드리프트율 적용됨: {drift_rate:.4f} g/s ({drift_rate * 60:.2f} g/min)")
                    print(f"   측정 무게: {self.state.drift_calibration_weight:.1f}g")
                    if drift_rate < 0:
                        print(f"⚠️  센서가 시간이 지날수록 무게를 과소측정합니다")
                        print(f"   (1분당 약 {abs(drift_rate * 60):.2f}g 무게가 감소)")
                    elif drift_rate > 0:
                        print(f"⚠️  센서가 시간이 지날수록 무게를 과대측정합니다")
                        print(f"   (1분당 약 {drift_rate * 60:.2f}g 무게가 증가)")
                    else:
                        print(f"✅ 센서 드리프트가 거의 없습니다")
                else:
                    default_drift = self.config.WEIGHT_DRIFT_RATE
                    print(f"❌ 드리프트율 미적용 (기본값 사용: {default_drift:.4f} g/s)")
                    print("드리프트율 측정을 권장합니다.")
                
                print(f"영점 오프셋: {self.state.tare_offset:.0f}")
                print("="*60)
            elif choice == '10':
                break


def main():
    try:
        system = WeightMonitorSystem()
        system.run_interactive()
    except Exception as e:
        logger.error(f"시스템 오류: {e}", exc_info=True)
        raise
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
