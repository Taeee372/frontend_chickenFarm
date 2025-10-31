import React, { useState, useEffect } from "react";
import styles from "./Diary.module.css";
import { getNotesByDate, insertNote, updateNote, deleteNote } from "../api/noteApi";
import { useAlert } from '../context/AlertContext';

const Diary = () => {
  const { showCustomAlert, showCustomConfirm } = useAlert();
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [entries, setEntries] = useState([]);
  const [viewMode, setViewMode] = useState('day'); // 'day', 'week', 'month'

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [newEntry, setNewEntry] = useState({
    content: "",
  });

  // 로그인된 사용자 ID (임시로 하드코딩, 실제로는 로그인 정보에서 가져와야 함)
  const memId = sessionStorage.getItem('loginInfo')
    ? JSON.parse(sessionStorage.getItem('loginInfo')).memId
    : 'admin';

  // 날짜 변경 시 또는 뷰모드 변경 시 일지 조회
  useEffect(() => {
    fetchNotesByDateRange();
  }, [selectedDate, viewMode]);

  // 날짜 범위 계산
  const getDateRange = () => {
    const today = new Date(selectedDate);
    let startDate, endDate;

    if (viewMode === 'day') {
      startDate = selectedDate;
      endDate = selectedDate;
    } else if (viewMode === 'week') {
      // 오늘 기준 최근 7일
      const weekStart = new Date(today);
      weekStart.setDate(today.getDate() - 6);
      startDate = weekStart.toISOString().split('T')[0];
      endDate = selectedDate;
    } else if (viewMode === 'month') {
      // 오늘 기준 최근 30일
      const monthStart = new Date(today);
      monthStart.setDate(today.getDate() - 29);
      startDate = monthStart.toISOString().split('T')[0];
      endDate = selectedDate;
    }

    return { startDate, endDate };
  };

  // 날짜 범위에 따른 일지 조회
  const fetchNotesByDateRange = async () => {
    try {
      const { startDate, endDate } = getDateRange();

      if (viewMode === 'day') {
        const data = await getNotesByDate(memId, selectedDate);
        setEntries(data);
      } else {
        // 일주일/월간의 경우 범위 내 모든 데이터 조회
        const allData = [];
        const start = new Date(startDate);
        const end = new Date(endDate);

        for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
          const dateStr = d.toISOString().split('T')[0];
          const data = await getNotesByDate(memId, dateStr);
          allData.push(...data);
        }

        setEntries(allData);
      }
    } catch (error) {
      console.error('일지 조회 실패:', error);
      setEntries([]);
    }
  };

  const handleAddEntry = async () => {
    if (editingId) {
      // 수정 모드
      try {
        const noteData = {
          noteNum: editingId,
          content: newEntry.content,
        };
        const result = await updateNote(noteData);

        if (result.success) {
          await showCustomAlert(result.message);
          fetchNotesByDateRange(); // 목록 새로고침
          setEditingId(null);
        } else {
          await showCustomAlert(result.message);
        }
      } catch (error) {
        await showCustomAlert('일지 수정에 실패했습니다.');
        console.error(error);
      }
    } else {
      // 추가 모드
      try {
        const noteData = {
          memId: memId,
          content: newEntry.content,
        };
        const result = await insertNote(noteData);

        if (result.success) {
          await showCustomAlert(result.message);
          fetchNotesByDateRange(); // 목록 새로고침
        } else {
          await showCustomAlert(result.message);
        }
      } catch (error) {
        await showCustomAlert('일지 추가에 실패했습니다.');
        console.error(error);
      }
    }
    setNewEntry({
      content: "",
    });
    setShowForm(false);
  };

  const handleEdit = (entry) => {
    setNewEntry({
      content: entry.content,
    });
    setEditingId(entry.noteNum);
    setShowForm(true);
  };

  const handleDelete = async (noteNum) => {
    const confirmed = await showCustomConfirm("이 기록을 삭제하시겠습니까?");
    if (confirmed) {
      try {
        const result = await deleteNote(noteNum);

        if (result.success) {
          await showCustomAlert(result.message);
          fetchNotesByDateRange(); // 목록 새로고침
        } else {
          await showCustomAlert(result.message);
        }
      } catch (error) {
        await showCustomAlert('일지 삭제에 실패했습니다.');
        console.error(error);
      }
    }
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingId(null);
    setNewEntry({
      content: "",
    });
  };

  const filteredEntries = entries;

  const getViewModeLabel = () => {
    const { startDate, endDate } = getDateRange();
    if (viewMode === 'day') {
      return `${selectedDate} 기록`;
    } else if (viewMode === 'week') {
      return `${startDate} ~ ${endDate} (최근 7일)`;
    } else {
      return `${startDate} ~ ${endDate} (최근 30일)`;
    }
  };

  return (
    <div className={styles.container}>
      <h2>관찰 일지</h2>
      <div className={styles.header}>
        <div className={styles.headerRight}>
          <div className={styles.viewModeButtons}>
            <button
              className={`${styles.viewModeButton} ${viewMode === 'day' ? styles.active : ''}`}
              onClick={() => setViewMode('day')}
            >
              일간
            </button>
            <button
              className={`${styles.viewModeButton} ${viewMode === 'week' ? styles.active : ''}`}
              onClick={() => setViewMode('week')}
            >
              주간
            </button>
            <button
              className={`${styles.viewModeButton} ${viewMode === 'month' ? styles.active : ''}`}
              onClick={() => setViewMode('month')}
            >
              월간
            </button>
          </div>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className={styles.datePicker}
          />
          <button
            className={styles.addButton}
            onClick={() => setShowForm(!showForm)}
          >
            + 기록 추가
          </button>
        </div>
      </div>

      {showForm && (
        <div className={styles.formCard}>
          <h3 className={styles.formTitle}>{editingId ? "관찰 기록 수정" : "새 관찰 기록"}</h3>
          <div className={styles.formGroup}>
            <label>관찰 내용</label>
            <textarea
              value={newEntry.content}
              onChange={(e) => setNewEntry({ ...newEntry, content: e.target.value })}
              placeholder="상세 내용을 입력하세요"
              className={styles.textarea}
              rows={4}
            />
          </div>
          <div className={styles.formActions}>
            <button className={styles.cancelButton} onClick={handleCancel}>
              취소
            </button>
            <button className={styles.saveButton} onClick={handleAddEntry}>
              {editingId ? "수정" : "저장"}
            </button>
          </div>
        </div>
      )}

      <div className={styles.entriesContainer}>
        <div className={styles.entriesHeader}>
          <h3 className={styles.entriesTitle}>
            {getViewModeLabel()} ({filteredEntries.length}건)
          </h3>
        </div>

        {filteredEntries.length === 0 ? (
          <div className={styles.emptyState}>
            <p>📝 이 날짜에 등록된 기록이 없습니다.</p>
          </div>
        ) : (
          <div className={styles.entriesList}>
            {filteredEntries.map((entry) => (
              <div key={entry.noteNum} className={styles.entryCard}>
                <div className={styles.entryContent}>
                  {entry.content}
                </div>
                <div className={styles.entryFooter}>
                  <div className={styles.entryFooterLeft}>
                    <span>📅 {new Date(entry.recTime).toLocaleString('ko-KR')}</span>
                  </div>
                  <div className={styles.entryActions}>
                    <button
                      className={styles.editButton}
                      onClick={() => handleEdit(entry)}
                    >
                      수정
                    </button>
                    <button
                      className={styles.deleteButton}
                      onClick={() => handleDelete(entry.noteNum)}
                    >
                      삭제
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Diary;
