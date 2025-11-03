import { createContext, useContext, useState, useEffect, useRef } from "react";
import { sensorAPI, dangerNoticeAPI, envSettingsAPI } from "../services/api";

const AlertContext = createContext();

export const AlertProvider = ({ children }) => {
  const [alerts, setAlerts] = useState([]);
  const [customAlertDialog, setCustomAlertDialog] = useState(null); // 커스텀 alert 다이얼로그 상태
  const [customConfirmDialog, setCustomConfirmDialog] = useState(null); // 커스텀 confirm 다이얼로그 상태
  const [alertSettings, setAlertSettings] = useState({
    tempHighAlert: 35,
    tempLowAlert: 10,
    humidityHighAlert: 85,
    humidityLowAlert: 30,
    co2Alert: 2000,
    coAlert: 50,
    nh3Alert: 25,
    // 조도 및 수면시간 설정
    sleepModeEnabled: true,
    sleepStartHour: 22,
    sleepEndHour: 6,
    manualLedThreshold: 300
  });
  const lastSavedAlertsRef = useRef([]); // useRef를 사용하여 불필요한 리렌더링 없이 이전 상태를 기억

  // 커스텀 alert 함수 (위치 조정 가능)
  const showCustomAlert = (message) => {
    return new Promise((resolve) => {
      setCustomAlertDialog({
        message,
        onClose: () => {
          setCustomAlertDialog(null);
          resolve();
        }
      });
    });
  };

  // 커스텀 confirm 함수 (위치 조정 가능)
  const showCustomConfirm = (message) => {
    return new Promise((resolve) => {
      setCustomConfirmDialog({
        message,
        onConfirm: () => {
          setCustomConfirmDialog(null);
          resolve(true);
        },
        onCancel: () => {
          setCustomConfirmDialog(null);
          resolve(false);
        }
      });
    });
  };

  // DB에 위험 알림 저장
  const saveDangerNotice = async (alertList) => {
    // 이전 알림과 완전히 동일한 경우에만 중복 저장 방지
    const isSameAlerts =
      JSON.stringify(alertList.map((a) => a.message)) ===
      JSON.stringify(lastSavedAlertsRef.current.map((a) => a.message));

    if (isSameAlerts) {
      return;
    }

    try {
      const loginInfo = JSON.parse(sessionStorage.getItem("loginInfo") || "{}");
      const farmNum = loginInfo.farm_id || 1;

      // alerts가 비어있지 않은 경우에만 DB 저장
      if (alertList.length > 0) {
        for (const alert of alertList) {
          await dangerNoticeAPI.saveDangerNotice({
            noticeContent: alert.message,
            noticeCategory: alert.category,
            farmNum: farmNum,
          });
        }
        lastSavedAlertsRef.current = alertList; // useRef로 이전 알림 목록 업데이트
      }
    } catch (error) {
      // 에러 무시
    }
  };

  // 설정값 로드
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const result = await envSettingsAPI.getSettings();
        if (result.success && result.data) {
          setAlertSettings({
            tempHighAlert: result.data.tempHighAlert || 35,
            tempLowAlert: result.data.tempLowAlert || 10,
            humidityHighAlert: result.data.humidityHighAlert || 85,
            humidityLowAlert: result.data.humidityLowAlert || 30,
            co2Alert: result.data.co2Alert || 2000,
            coAlert: result.data.coAlert || 50,
            nh3Alert: result.data.nh3Alert || 25,
            sleepModeEnabled: result.data.sleepModeEnabled !== undefined ? result.data.sleepModeEnabled : true,
            sleepStartHour: result.data.sleepStartHour || 22,
            sleepEndHour: result.data.sleepEndHour || 6,
            manualLedThreshold: result.data.manualLedThreshold || 300
          });
        }
      } catch (error) {
        // 에러 무시
      }
    };
    
    loadSettings();
  }, []);

  // 수면시간 판단 함수
  const isSleepTime = () => {
    if (!alertSettings.sleepModeEnabled) return false;

    const now = new Date();
    const currentHour = now.getHours();
    const { sleepStartHour, sleepEndHour } = alertSettings;

    // 예: 22시 ~ 6시 (자정을 넘는 경우)
    if (sleepStartHour > sleepEndHour) {
      return currentHour >= sleepStartHour || currentHour < sleepEndHour;
    }
    // 예: 6시 ~ 22시 (일반적인 경우는 반대)
    return currentHour >= sleepStartHour && currentHour < sleepEndHour;
  };

  // ✅ 전역에서 센서 데이터 계속 받기
  useEffect(() => {
    let intervalId; // setInterval ID를 저장할 변수

    const fetchAndCheckSensors = async () => {
      try {
        const result = await sensorAPI.getRealtimeData();

        if (result.success && result.data) {
          const data = result.data;
          const newAlerts = [];

          // 비정상 감지 (백엔드 설정값 사용)
          if (data.temperature > alertSettings.tempHighAlert)
            newAlerts.push({ message: `🌡️ 온도가 ${data.temperature.toFixed(1)}°C로 너무 높습니다.`, category: "온도" });
          if (data.temperature < alertSettings.tempLowAlert)
            newAlerts.push({ message: `❄️ 온도가 ${data.temperature.toFixed(1)}°C로 너무 낮습니다.`, category: "온도" });
          if (data.humidity > alertSettings.humidityHighAlert)
            newAlerts.push({ message: `💧 습도가 ${data.humidity.toFixed(1)}%로 너무 높습니다.`, category: "습도" });
          if (data.humidity < alertSettings.humidityLowAlert)
            newAlerts.push({ message: `💧 습도가 ${data.humidity.toFixed(1)}%로 너무 낮습니다.`, category: "습도" });
          if (data.co2 > alertSettings.co2Alert)
            newAlerts.push({ message: `⚠️ CO2 농도가 ${data.co2.toFixed(1)}ppm으로 너무 높습니다.`, category: "CO2" });
          if (data.co > alertSettings.coAlert)
            newAlerts.push({ message: `⚠️ CO 농도가 ${data.co.toFixed(3)}ppm으로 위험합니다.`, category: "CO" });
          if (data.nh3 > alertSettings.nh3Alert)
            newAlerts.push({ message: `⚠️ 암모니아 농도가 ${data.nh3.toFixed(3)}ppm으로 높습니다.`, category: "NH3" });

          // 조도 알람 (수면시간 기반)
          const sleepTime = isSleepTime();
          const luxThreshold = alertSettings.manualLedThreshold;

          if (sleepTime) {
            // 수면시간: 조도가 높으면 알람
            if (data.lux > luxThreshold * 1.5) {
              newAlerts.push({ message: `💡 수면시간에 조도가 ${data.lux.toFixed(1)}lux로 너무 밝습니다.`, category: "조도" });
            } else if (data.lux > luxThreshold) {
              newAlerts.push({ message: `💡 수면시간에 조도가 ${data.lux.toFixed(1)}lux로 밝습니다.`, category: "조도" });
            }
          } else {
            // 활동시간: 조도가 낮으면 알람
            if (data.lux < luxThreshold * 0.5) {
              newAlerts.push({ message: `💡 활동시간에 조도가 ${data.lux.toFixed(1)}lux로 너무 어둡습니다.`, category: "조도" });
            } else if (data.lux < luxThreshold) {
              newAlerts.push({ message: `💡 활동시간에 조도가 ${data.lux.toFixed(1)}lux로 어둡습니다.`, category: "조도" });
            }
          }

          setAlerts(newAlerts); // 알림 목록 업데이트
          saveDangerNotice(newAlerts); // 업데이트된 새 알림 목록으로 DB 저장 함수 호출
        }
      } catch (error) {
        // 에러 무시
      }
    };

    fetchAndCheckSensors(); // 컴포넌트 마운트 시 최초 1회 실행
    intervalId = setInterval(fetchAndCheckSensors, 5000); // 5초마다 반복 실행

    return () => {
      clearInterval(intervalId); // 컴포넌트 언마운트 시 인터벌 정리
    };
  }, [alertSettings]); // alertSettings가 변경될 때마다 재실행

  return (
    <AlertContext.Provider value={{ alerts, setAlerts, showCustomAlert, showCustomConfirm }}>
      {children}
      {/* 커스텀 alert 다이얼로그 */}
      {customAlertDialog && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000
        }}>
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            padding: '24px',
            minWidth: '320px',
            maxWidth: '500px',
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.3)',
            position: 'relative',
            top: '-100px', // 이 값을 조정하면 alert의 위치가 변경됩니다 (양수: 아래로, 음수: 위로)
          }}>
            <div style={{
              fontSize: '16px',
              color: '#333',
              marginBottom: '24px',
              lineHeight: '1.5',
              whiteSpace: 'pre-wrap'
            }}>
              {customAlertDialog.message}
            </div>
            <button
              onClick={customAlertDialog.onClose}
              style={{
                width: '100%',
                padding: '12px',
                backgroundColor: '#3b82f6',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '15px',
                fontWeight: '600',
                cursor: 'pointer'
              }}
              onMouseOver={(e) => e.target.style.backgroundColor = '#2563eb'}
              onMouseOut={(e) => e.target.style.backgroundColor = '#3b82f6'}
            >
              확인
            </button>
          </div>
        </div>
      )}
      {/* 커스텀 confirm 다이얼로그 */}
      {customConfirmDialog && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000
        }}>
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            padding: '24px',
            minWidth: '320px',
            maxWidth: '500px',
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.3)',
            position: 'relative',
            top: '100px', // 이 값을 조정하면 confirm의 위치가 변경됩니다 (양수: 아래로, 음수: 위로)
          }}>
            <div style={{
              fontSize: '16px',
              color: '#333',
              marginBottom: '24px',
              lineHeight: '1.5',
              whiteSpace: 'pre-wrap'
            }}>
              {customConfirmDialog.message}
            </div>
            <div style={{
              display: 'flex',
              gap: '12px'
            }}>
              <button
                onClick={customConfirmDialog.onCancel}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: '#6b7280',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#4b5563'}
                onMouseOut={(e) => e.target.style.backgroundColor = '#6b7280'}
              >
                취소
              </button>
              <button
                onClick={customConfirmDialog.onConfirm}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#2563eb'}
                onMouseOut={(e) => e.target.style.backgroundColor = '#3b82f6'}
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 위험 알림 팝업 */}
      {alerts.length > 0 && (
        <div style={{
          position: 'fixed',
          bottom: '20px',
          right: '20px',
          zIndex: 9999,
          width: '350px',
          backgroundColor: '#fff',
          border: '2px solid #ef4444',
          borderRadius: '8px',
          padding: '16px',
          boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)'
        }}>
          <div style={{
            fontSize: '16px',
            fontWeight: '700',
            marginBottom: '12px',
            color: '#ef4444'
          }}>
            ⚠️ 위험 알림
          </div>
          <div>
            {alerts.map((alert, index) => {
              // 수치 추출 및 강조를 위한 함수
              const highlightNumbers = (text) => {
                return text.replace(/(\d+\.?\d*)/g, '<strong style="font-size: 16px; color: #b91c1c; text-decoration: underline; text-underline-offset: 3px;">$1</strong>');
              };
              
              return (
                <div key={index} style={{
                  padding: '12px',
                  backgroundColor: '#fef2f2',
                  borderRadius: '6px',
                  marginBottom: '10px',
                  fontSize: '15px',
                  color: '#dc2626',
                  borderLeft: '4px solid #ef4444',
                  lineHeight: '1.4'
                }}
                dangerouslySetInnerHTML={{ __html: highlightNumbers(alert.message) }}
                />
              );
            })}
          </div>
          <button
            onClick={() => setAlerts([])}
            style={{
              width: '100%',
              padding: '12px',
              backgroundColor: '#ef4444',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '600',
              cursor: 'pointer',
              marginTop: '12px'
            }}
          >
            확인
          </button>
        </div>
      )}
    </AlertContext.Provider>
  );
};

export const useAlert = () => useContext(AlertContext);

