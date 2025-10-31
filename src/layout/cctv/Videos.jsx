import React, { useEffect, useState } from "react";
import styles from "./Videos.module.css";
import Button from "../../common/Button";
import Modal from "../../common/Modal";
import { useAlert } from '../../context/AlertContext';

 const API_BASE = "http://192.168.30.71:5000";
// const API_BASE = "http://192.168.31.229:5000";

const Videos = () => {
  const { showCustomAlert } = useAlert();
  const [videos, setVideos] = useState([]);
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDbCleanupModalOpen, setIsDbCleanupModalOpen] = useState(false);
  const [fileToDelete, setFileToDelete] = useState(null);
  const [hasDeletedFiles, setHasDeletedFiles] = useState(false);

  const fetchVideos = () => {
    fetch(`${API_BASE}/videos_db`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "success") {
          setVideos(data.videos);
          // IS_READABLE=0인 파일이 있는지 확인
          const hasDeleted = data.videos.some(v => parseInt(v.IS_READABLE) === 0);
          setHasDeletedFiles(hasDeleted);
        }
      })
      .catch((err) => console.error("Fetch error:", err));
  };

  useEffect(() => {
    fetchVideos();
  }, []);

  const handleDelete = (fileName) => {
    setFileToDelete(fileName);
    setIsDeleteModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!fileToDelete) return;
    fetch(`${API_BASE}/videos/delete/${fileToDelete}`, { method: "POST" })
      .then((res) => res.json())
      .then(async (data) => {
        if (data.status === "success") {
          fetchVideos();
        } else {
          await showCustomAlert("삭제 실패: " + data.message);
        }
      })
      .catch(console.error)
      .finally(() => {
        setIsDeleteModalOpen(false);
        setFileToDelete(null);
      });
  };

  const handleDbCleanup = () => {
    setIsDbCleanupModalOpen(true);
  };

  const confirmDbCleanup = async () => {
    fetch(`${API_BASE}/videos/cleanup_deleted`, { method: "POST" })
      .then((res) => res.json())
      .then(async (data) => {
        if (data.status === "success") {
          // await showCustomAlert(`${data.deleted_count}개의 파일이 DB에서 삭제되었습니다.`);
          fetchVideos();
        } else {
          await showCustomAlert("정리 실패: " + data.message);
        }
      })
      .catch(async (err) => {
        console.error(err);
        await showCustomAlert("정리 중 오류 발생");
      })
      .finally(() => {
        setIsDbCleanupModalOpen(false);
      });
  };

  const handleDownload = () => {
    if (selectedVideo) {
      setIsModalOpen(true); // 모달 열기
    }
  };

  const confirmDownload = () => {
    if (selectedVideo) {
      window.open(`${API_BASE}/download/${selectedVideo.filename}`, "_blank");
    }
    setIsModalOpen(false);
  };

  return (
    <div className={styles.container}>
      <div className={styles.head_div}></div>

      <div className={styles.main_div}>
        {/* 왼쪽 리스트 */}
        <div className={styles.video_list}>
          <ul>
            {videos.map((v, index) => {
              const deleted = parseInt(v.IS_READABLE) === 0;
              const recording = index === 0 && (v.END_AT === null || v.END_AT === "-");
              const disabled = deleted || recording;
              return (
                <li
                  key={v.filename}
                  className={`${styles.list_item} ${
                    deleted ? styles.deleted : ""
                  } ${recording ? styles.recording : ""}`}
                >
                  <button
                    className={styles.video_btn}
                    onClick={() => !disabled && setSelectedVideo(v)}
                    disabled={disabled}
                  >
                    {v.filename}
                  </button>

                  {/* ✅ Button 컴포넌트로 교체 */}
                  <Button
                    title={deleted ? "불가" : recording ? "녹화중" : "삭제"}
                    size="80px"
                    fontSize="0.6rem"
                    height="30px"
                    color={deleted ? "softRed" : recording ? "gray" : "warmRed"}
                    onClick={() => !disabled && handleDelete(v.filename)}
                    disabled={disabled}
                  />
                </li>
              );
            })}
          </ul>
        </div>

        {/* 오른쪽 영상 */}
        <div className={styles.video_play}>
          {selectedVideo ? (
            <video
              src={selectedVideo.url}
              controls
              width="100%"
              height="100%"
              autoPlay
            />
          ) : (
            <div className={styles.placeholder}>
              ▶ 영상을 선택하면 이곳에 재생됩니다
            </div>
          )}
        </div>
      </div>

      {/* 항상 고정되는 영역 */}
      <div className={styles.controls_div}>
        <div className={styles.btn_group}>
          <Button
            title="닫기"
            size="100px"
            color="green"
            height="35px"
            onClick={() => setSelectedVideo(null)}
            disabled={!selectedVideo}
          />
          <Button
            title="내려받기"
            size="100px"
            color="green"
            height="35px"
            onClick={handleDownload}
            disabled={!selectedVideo}
          />
          <Button
            title="DB정리"
            size="100px"
            color="warmRed"
            height="35px"
            onClick={handleDbCleanup}
            disabled={!hasDeletedFiles}
          />
          <div className={styles.file_info}>
            {selectedVideo ? `📁 ${selectedVideo.filename}` : "📂 영상을 선택해주세요"}
          </div>
        </div>
        <div className={styles.details}>
          {selectedVideo ? (
            <table className={styles.detailsTable}>
              <tbody>
                <tr>
                  <td><b>카메라 ID</b></td>
                  <td><b>해상도</b></td>
                  <td><b>저장 시작</b></td>
                  <td><b>저장 종료</b></td>
                </tr>
                <tr>
                  <td>{selectedVideo.CAMERA_ID}</td>
                  <td>{selectedVideo.RESOLUTION}</td>
                  <td>{selectedVideo.SAVED_AT}</td>
                  <td>{selectedVideo.END_AT || "-"}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p className={styles.no_selection}>영상이 선택되지 않았습니다.</p>
          )}
        </div>
      </div>
      {/* 모달 추가 */}
      <Modal
        size="600px"
        title="파일 다운로드"
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      >
        <p>📂 {selectedVideo?.filename} 파일을 다운로드하시겠습니까?</p>
        <div style={{ display: "flex", gap: "10px", marginTop: "15px", width: '100%' , margin: 'auto'}}>
          <Button title="취소" width="0px" color="green" onClick={() => setIsModalOpen(false)} />
          <Button title="받기" width="160px" color="green" onClick={confirmDownload} />
        </div>
      </Modal>

      {/* 일반 삭제 모달 */}
      <Modal
        size="600px"
        title="파일 삭제"
        isOpen={isDeleteModalOpen}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setFileToDelete(null);
        }}
      >
        <p>🗑️ {fileToDelete} 파일을 삭제하시겠습니까?</p>
        <div style={{ display: "flex", gap: "10px", marginTop: "15px", width: '100%' , margin: 'auto'}}>
          <Button title="취소" width="0px" color="green" onClick={() => {
            setIsDeleteModalOpen(false);
            setFileToDelete(null);
          }} />
          <Button title="삭제" width="160px" color="warmRed" onClick={confirmDelete} />
        </div>
      </Modal>

      {/* DB 정리 모달 */}
      <Modal
        size="600px"
        title="DB 정리"
        isOpen={isDbCleanupModalOpen}
        onClose={() => setIsDbCleanupModalOpen(false)}
      >
        <p>🗑️ 이미 삭제된 모든 파일을 DB에서 삭제하시겠습니까?</p>
        <div style={{ display: "flex", gap: "10px", marginTop: "15px", width: '100%' , margin: 'auto'}}>
          <Button title="취소" width="0px" color="green" onClick={() => setIsDbCleanupModalOpen(false)} />
          <Button title="정리" width="160px" color="warmRed" onClick={confirmDbCleanup} />
        </div>
      </Modal>
    </div>
  );
};

export default Videos;
