import React, { useState, useEffect, useMemo } from "react";
import axios from "axios";
import Button from "../../common/Button";
import PageTitle from "../../common/cctv/PageTitle";
import Modal from "../../common/Modal";
import styles from "./Alarms.module.css";
import { useAlert } from '../../context/AlertContext';

 const API_BASE = "http://192.168.30.71:5000";
// const API_BASE = "http://192.168.31.229:5000";
const LIMIT = 100;
const noCache = () => ({ params: { _t: Date.now() } });

// 상태 변환
const statusToFlags = (status) => {
  switch (status) {
    case "dangerous":
      return { IS_DANGEROUS: true, IS_MANAGED: false, IS_EXCLUDED: false };
    case "managed":
      return { IS_DANGEROUS: false, IS_MANAGED: true, IS_EXCLUDED: false };
    case "excluded":
      return { IS_DANGEROUS: false, IS_MANAGED: false, IS_EXCLUDED: true };
    default:
      return { IS_DANGEROUS: false, IS_MANAGED: true, IS_EXCLUDED: false };
  }
};

const flagsToStatus = ({ IS_DANGEROUS, IS_MANAGED, IS_EXCLUDED }) =>
  IS_DANGEROUS ? "dangerous" : IS_MANAGED ? "managed" : IS_EXCLUDED ? "excluded" : "managed";

const norm = (s) => (s || "").toString().trim().toLowerCase();

/* =======================
   알람 리스트
======================= */
const AlarmList = () => {
  const { showCustomAlert, showCustomConfirm } = useAlert();
  const [alarms, setAlarms] = useState([]);
  const [dangerousObjects, setDangerousObjects] = useState([]);

  const dangerMap = useMemo(() => {
    const m = new Map();
    for (const obj of dangerousObjects || []) m.set(norm(obj.OBJECT_CODE), obj.OBJECT_NAME_KR);
    return m;
  }, [dangerousObjects]);

  const fetchDangerousObjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/dangerous_objects`, noCache());
      if (res.data.status === "success") setDangerousObjects(res.data.objects || []);
    } catch (e) {
      console.error("위험 객체 조회 실패:", e);
    }
  };

  const fetchAlarms = async () => {
    try {
      const res = await axios.get(`${API_BASE}/alarms_db`, { params: { limit: LIMIT, _t: Date.now() } });
      if (res.data.status === "success") setAlarms(res.data.alarms || []);
    } catch (e) {
      console.error("알람 조회 실패:", e);
    }
  };

  const deleteAlarm = async (alarmId) => {
    try {
      await axios.delete(`${API_BASE}/alarms/${alarmId}`, noCache());
      await fetchAlarms();
    } catch (e) {
      console.error("알람 삭제 실패:", e);
      await showCustomAlert("알람 삭제 실패");
    }
  };

  const getAlarmMessage = (labelRaw) => {
    const nameKr = dangerMap.get(norm(labelRaw));
    return nameKr ? `🚨 유해동물 ${nameKr}가 침입했습니다!!` : `${labelRaw} 감지`;
  };

  useEffect(() => {
    fetchDangerousObjects();
    fetchAlarms();
  }, []);

  useEffect(() => {
    const onDangerChanged = () => {
      fetchDangerousObjects();
      fetchAlarms();
    };
    window.addEventListener("dangerous-objects-updated", onDangerChanged);
    return () => window.removeEventListener("dangerous-objects-updated", onDangerChanged);
  }, []);

  return (
    <div className={styles.alarmListContainer}>
      <div className={styles.title_div}>
        <PageTitle title="알람리스트" size="83%" color="black" />
        <Button
          title="최신알람"
          color="pastelGreen"
          size="100px"
          height="36px"
          onClick={() => {
            fetchDangerousObjects();
            fetchAlarms();
          }}
        />
      </div>

      {alarms.length === 0 ? (
        <p>알람이 없습니다.</p>
      ) : (
        <ul className={styles.listReset}>
          {alarms.map((a) => (
            <li key={a.ALARM_ID} className={styles.alarmItem}>
              <span>
                {getAlarmMessage(a.OBJECT_LABEL)} - {new Date(a.DETECTED_AT).toLocaleString()}
              </span>
              <Button title="삭제" color="softGreen" size="60px" height="28px" onClick={() => deleteAlarm(a.ALARM_ID)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

/* =======================
   위험 객체 관리
======================= */
const DangerousObjects = () => {
  const [objects, setObjects] = useState([]);

  const fetchDangerousObjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/dangerous_objects`, noCache());
      if (res.data.status === "success") setObjects(res.data.objects || []);
    } catch (err) {
      console.error("위험 객체 조회 실패:", err);
    }
  };

  const updateDangerous = async (itemId, isDangerous) => {
    try {
      await axios.post(`${API_BASE}/dangerous_objects/${itemId}`, { is_dangerous: isDangerous });
      await fetchDangerousObjects();
      window.dispatchEvent(new CustomEvent("dangerous-objects-updated"));
    } catch (err) {
      console.error("위험 상태 변경 실패:", err);
      await showCustomAlert("위험 상태 변경 실패");
    }
  };

  useEffect(() => {
    fetchDangerousObjects();
  }, []);

  return (
    <div className={styles.warning_div}>
      <div className={styles.title_div}>
        <PageTitle title="위험 관리" size="70%" color="red" />
        <Button title="DB적용" onClick={fetchDangerousObjects} color="softRed" size="90px" height="36px" />
      </div>

      {objects.length === 0 ? (
        <p>위험 객체 없음</p>
      ) : (
        <ul className={styles.listReset}>
          {objects.map((obj) => (
            <li key={obj.ITEM_ID} className={styles.alarmItem}>
              <span>{obj.OBJECT_NAME_KR} ({obj.OBJECT_CODE})</span>
              <Button title="삭제" color="pastelRed" size="70px" height="32px" onClick={() => updateDangerous(obj.ITEM_ID, false)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

/* =======================
   관리 객체
======================= */
const ObjectManagement = () => {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState("view");
  const [addOpen, setAddOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [addForm, setAddForm] = useState({ code: "", name: "", status: "managed" });
  const [editStatus, setEditStatus] = useState("managed");

  const fetchObjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/objects`, noCache());
      if (res.data.status === "success") setList(res.data.objects || []);
    } catch (e) {
      console.error("objects 조회 실패:", e);
    }
  };

  useEffect(() => {
    fetchObjects();
  }, []);

  const onSelectRow = (row) => {
    setSelected(row);
    setMode("view");
    setEditStatus(flagsToStatus(row));
    setDetailModalOpen(true);
  };

  const onDelete = async () => {
    if (!selected) return;
    const confirmed = await showCustomConfirm("정말 삭제하시겠습니까?");
    if (!confirmed) return;
    try {
      const id = selected.ITEM_ID;
      const res = await axios.delete(`${API_BASE}/objects/${id}`, noCache());
      if (res.data.status === "success") {
        setSelected(null);
        setDetailModalOpen(false);
        await fetchObjects();
        window.dispatchEvent(new CustomEvent("dangerous-objects-updated"));
      } else {
        await showCustomAlert(res.data.message || "삭제 실패");
      }
    } catch (e) {
      console.error("삭제 실패:", e);
      await showCustomAlert("삭제 실패");
    }
  };

  const onEdit = () => {
    if (!selected) return;
    setEditStatus(flagsToStatus(selected));
    setMode("edit");
  };

const onSave = async () => {
  if (!selected) return;
  const id = selected.ITEM_ID;
  const flags = statusToFlags(editStatus);
  try {
    const payload = {
      OBJECT_CODE: selected.OBJECT_CODE,
      OBJECT_NAME_KR: selected.OBJECT_NAME_KR,
      ...flags,
    };
    const res = await axios.put(`${API_BASE}/objects/${id}`, payload);
    if (res.data.status === "success") {
      setMode("view");
      setDetailModalOpen(false);  // ✅ 모달 닫기 추가
      setSelected(null);          // 선택 초기화
      await fetchObjects();
      window.dispatchEvent(new CustomEvent("dangerous-objects-updated"));
    } else {
      await showCustomAlert(res.data.message || "수정 실패");
    }
  } catch (e) {
    console.error("수정 실패:", e);
    await showCustomAlert("수정 실패");
  }
};


  const onAddSave = async () => {
    const code = addForm.code.trim();
    const name = addForm.name.trim();
    if (!code || !name) {
      await showCustomAlert("OBJECT_CODE / OBJECT_NAME_KR을 입력하세요.");
      return;
    }
    const flags = statusToFlags(addForm.status);
    try {
      const res = await axios.post(`${API_BASE}/objects`, {
        OBJECT_CODE: code,
        OBJECT_NAME_KR: name,
        ...flags,
      });
      if (res.data.status === "success") {
        setAddOpen(false);
        setAddForm({ code: "", name: "", status: "managed" });
        await fetchObjects();
        window.dispatchEvent(new CustomEvent("dangerous-objects-updated"));
      } else {
        await showCustomAlert(res.data.message || "추가 실패");
      }
    } catch (e) {
      console.error("추가 실패:", e);
      await showCustomAlert("추가 실패");
    }
  };

  const handleDetailModalClose = () => {
    setDetailModalOpen(false);
    setSelected(null);
  };

  return (
    <div className={styles.object}>
      <div className={styles.title_div}>
        <PageTitle title="관리 객체" size="40%" color="skyblue"/>
        <Button title="추가" color="softBlue" size="70px" height="36px" onClick={() => setAddOpen(true)} />
        <Button title="DB적용" color="pastelBlue" size="90px" height="36px" onClick={fetchObjects}  />
      </div>

      {/* 리스트 */}
      <div className={styles.objList}>
        {list.length === 0 ? (
          <p>관리 객체 없음</p>
        ) : (
          <ul className={styles.listReset}>
            {list.map((row) => (
              <li
                key={row.ITEM_ID}
                className={`${styles.alarmItem} ${selected && selected.ITEM_ID === row.ITEM_ID ? styles.selected : ""}`}
                onClick={() => onSelectRow(row)}
                title="클릭하여 상세 보기"
              >
                <div className={styles.objRowText}>
                  <div className={styles.objCode}>{row.OBJECT_CODE}</div>
                  <div className={styles.objName}>{row.OBJECT_NAME_KR}</div>
                </div>
                <div
                  className={styles.objBadge}
                  style={{
                    color: row.IS_DANGEROUS ? "red" : row.IS_EXCLUDED ? "gray" : "yellow",
                  }}
                >
                  {row.IS_DANGEROUS ? "위험" : row.IS_EXCLUDED ? "제외" : "관리"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 추가 모달 */}
      <Modal title="관리 객체 추가" isOpen={addOpen} onClose={() => setAddOpen(false)} size="300px">
        <div className={styles.formGrid}>
          <label className={styles.formItem}>
            <div className={styles.formLabel}>객체ID</div>
            <input
              className={styles.input}
              value={addForm.code}
              onChange={(e) => setAddForm((p) => ({ ...p, code: e.target.value }))}
              placeholder="예: cat"
            />
          </label>
          <label className={styles.formItem}>
            <div className={styles.formLabel}>한글 등록명</div>
            <input
              className={styles.input}
              value={addForm.name}
              onChange={(e) => setAddForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="예: 고양이"
            />
          </label>
          <label className={styles.formItem}>
            <div className={styles.formLabel}>상태</div>
            <select
              className={styles.select}
              value={addForm.status}
              onChange={(e) => setAddForm((p) => ({ ...p, status: e.target.value }))}
            >
              <option value="dangerous">위험 알림 동물</option>
              <option value="managed">관리 대상 동물</option>
              <option value="excluded">관리 제외 대상</option>
            </select>
          </label>
        </div>
        <div className={styles.btnRow}>
          <Button title="저장" color="softGray" size="80px" height="36px" onClick={onAddSave} />
          <Button title="닫기" color="pastelGray" size="80px" height="36px" onClick={() => setAddOpen(false)} />
        </div>
      </Modal>

      {/* 상세 모달 */}
      <Modal title="객체 상세 정보" isOpen={detailModalOpen} onClose={handleDetailModalClose} size="300px">
        {selected && (
          <>
            <div className={styles.fieldRow}>
              <span className={styles.fieldLabel}>객채ID</span>
              <span className={styles.fieldValue}>{selected.OBJECT_CODE}</span>
            </div>
            <div className={styles.fieldRow}>
              <span className={styles.fieldLabel}>한글 등록 명</span>
              <span className={styles.fieldValue}>{selected.OBJECT_NAME_KR}</span>
            </div>
            <div className={styles.fieldRow}>
              {mode === "edit" ? (
                <select
                  className={`${styles.select} ${styles.fullWidth}`}
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                >
                  <option value="dangerous">위험 알림 동물</option>
                  <option value="managed">관리 대상 동물</option>
                  <option value="excluded">관리 제외 대상</option>
                </select>
              ) : (
                <>
                  <span className={styles.fieldLabel}>상태</span>
                  <b className={styles.fieldValue}>
                    {flagsToStatus(selected) === "dangerous"
                      ? "위험"
                      : flagsToStatus(selected) === "excluded"
                      ? "제외"
                      : "관리"}
                  </b>
                </>
              )}
            </div>
            <div className={styles.btnRow}>
              {mode === "edit" ? (
                <>
                  <Button title="저장" color="softGray" size="80px" height="36px" onClick={onSave} />
                  <Button title="취소" color="pastelGray" size="80px" height="36px" onClick={() => setMode("view")} />
                </>
              ) : (
                <>
                  <Button title="수정" color="softGray" size="80px" height="36px" onClick={onEdit} />
                  <Button title="삭제" color="pastelGray" size="80px" height="36px" onClick={onDelete} />
                </>
              )}
            </div>
          </>
        )}
      </Modal>
    </div>
  );
};

/* =======================
   페이지 통합
======================= */
const Alarms = () => {
  return (
    <div className={styles.container}>
      <div className={styles.left_div}>
        <AlarmList />
      </div>
      <div className={styles.right_div}>
        <DangerousObjects />
        <ObjectManagement />
      </div>
    </div>
  );
};

export default Alarms;
