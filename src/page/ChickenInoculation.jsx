import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import styles from './ChickenInoculation.module.css'
import { inoculationAPI, batchAPI } from '../services/api'
import { useAlert } from '../context/AlertContext'

const ChickenInoculation = () => {
  const navigate = useNavigate()
  const { showCustomAlert } = useAlert()

  const [batches, setBatches] = useState([])
  const [selectedBatch, setSelectedBatch] = useState('')
  const [chickens, setChickens] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [selectedVaccine, setSelectedVaccine] = useState('ND')
  const [selectedIds, setSelectedIds] = useState([])

  // 컴포넌트 마운트 시 배치 목록 로드
  useEffect(() => {
    loadBatches()
    console.log('실제 데이터베이스 연결을 시도합니다...')
  }, [])

  // 배치 선택 시 닭 목록 로드
  useEffect(() => {
    if (selectedBatch) {
      loadChickensByBatch(selectedBatch)
      console.log(`배치 ${selectedBatch}의 실제 데이터를 로드합니다...`)
    }
  }, [selectedBatch])

  // 배치 목록 로드
  const loadBatches = async () => {
    try {
      setLoading(true)
      setError(null)
      console.log('배치 데이터 로드 시작...')
      
      // batchAPI.getBatchInfo() 사용
      const batchesData = await batchAPI.getBatchInfo()
      console.log('배치 데이터 응답:', batchesData)
      
      if (batchesData && Array.isArray(batchesData)) {
        setBatches(batchesData)
        if (batchesData.length > 0) {
          setSelectedBatch(batchesData[0].batchId)
        }
        console.log('배치 데이터 로드 성공:', batchesData.length, '건')
      } else if (batchesData && batchesData.success && Array.isArray(batchesData.data)) {
        setBatches(batchesData.data)
        if (batchesData.data.length > 0) {
          setSelectedBatch(batchesData.data[0].batchId)
        }
        console.log('배치 데이터 로드 성공 (data 속성):', batchesData.data.length, '건')
      } else {
        console.log('배치 데이터가 없거나 실패:', batchesData)
        setBatches([])
      }
    } catch (err) {
      console.error('배치 로드 오류:', err)
      setError('배치 정보를 불러오는데 실패했습니다.')
      setBatches([])
    } finally {
      setLoading(false)
    }
  }

  // 개발용 더미 데이터 로드
  const loadDummyData = () => {
    console.log('더미 데이터를 로드합니다...')
    const dummyBatches = [
      {
        batchId: '2025-001',
        entryDate: '2024-12-01T00:00:00',
        initialCount: 100,
        currentCount: 98,
        shipmentStatus: false,
        farmNum: 1
      },
      {
        batchId: '2025-002',
        entryDate: '2024-12-15T00:00:00',
        initialCount: 80,
        currentCount: 80,
        shipmentStatus: false,
        farmNum: 1
      },
      {
        batchId: '2025-003',
        entryDate: '2025-01-01T00:00:00',
        initialCount: 120,
        currentCount: 120,
        shipmentStatus: false,
        farmNum: 2
      }
    ]
    
    setBatches(dummyBatches)
    setSelectedBatch('2025-001')
    loadDummyChickensByBatch('2025-001')
    console.log('더미 데이터 로드 완료:', { batches: dummyBatches.length })
  }

  // 더미 데이터에서 배치별 닭 목록 로드
  const loadDummyChickensByBatch = (batchId) => {
    console.log(`배치 ${batchId}의 더미 닭 데이터를 로드합니다...`)
    const dummyChickens = [
      { chickenId: 1, batchId: '2025-001', age: 45, rawWeight: 1.8, growthStage: 'FINISHER', healthStatus: 'HEALTHY', nd: true, hpai: true, ibd: true, ib: true },
      { chickenId: 2, batchId: '2025-001', age: 45, rawWeight: 1.9, growthStage: 'FINISHER', healthStatus: 'HEALTHY', nd: true, hpai: true, ibd: true, ib: false },
      { chickenId: 3, batchId: '2025-001', age: 45, rawWeight: 1.7, growthStage: 'FINISHER', healthStatus: 'HEALTHY', nd: true, hpai: true, ibd: true, ib: true },
      { chickenId: 4, batchId: '2025-002', age: 30, rawWeight: 1.4, growthStage: 'GROWER', healthStatus: 'HEALTHY', nd: true, hpai: true, ibd: true, ib: false },
      { chickenId: 5, batchId: '2025-002', age: 30, rawWeight: 1.5, growthStage: 'GROWER', healthStatus: 'HEALTHY', nd: true, hpai: false, ibd: true, ib: false },
      { chickenId: 6, batchId: '2025-003', age: 15, rawWeight: 1.0, growthStage: 'CHICK', healthStatus: 'HEALTHY', nd: true, hpai: false, ibd: true, ib: false },
      { chickenId: 7, batchId: '2025-003', age: 15, rawWeight: 1.1, growthStage: 'CHICK', healthStatus: 'HEALTHY', nd: true, hpai: false, ibd: false, ib: false },
      { chickenId: 8, batchId: '2025-003', age: 15, rawWeight: 0.9, growthStage: 'CHICK', healthStatus: 'HEALTHY', nd: false, hpai: false, ibd: true, ib: false }
    ]
    
    const filteredChickens = dummyChickens.filter(chicken => chicken.batchId === batchId)
    setChickens(filteredChickens)
    console.log(`배치 ${batchId}의 닭 데이터 로드 완료:`, filteredChickens.length, '마리')
    console.log('로드된 닭 데이터:', filteredChickens)
  }

  // 배치별 닭 목록 로드
  const loadChickensByBatch = async (batchId) => {
    try {
      setLoading(true)
      const chickensData = await inoculationAPI.getChickensByBatch(batchId)
      setChickens(chickensData)
    } catch (err) {
      console.error('닭 목록 로드 오류:', err)
      console.log('백엔드 연결 실패, 더미 데이터를 사용합니다.')
      loadDummyChickensByBatch(batchId)
    } finally {
      setLoading(false)
    }
  }

  const vaccineOptions = [
    { value: 'ND', label: '뉴캣슬병 (ND)', schedule: '1일령, 7-10일령, 21-28일령, 60-70일령' },
    { value: 'HPAI', label: '조류인플루엔자 (HPAI)', schedule: '3-4주령, 12-16주령' },
    { value: 'IBD', label: '감보로병 (IBD)', schedule: '10-14일령, 21-28일령' },
    { value: 'IB', label: '전염성 기관지염 (IB)', schedule: '1일령, 14-21일령, 35-42일령' },
  ]

  const completedChickens = chickens.filter(c => c[selectedVaccine.toLowerCase()])
  const pendingChickens = chickens.filter(c => !c[selectedVaccine.toLowerCase()])

  // 전체 선택/해제 (수정됨: chickenId 사용)
  const handleSelectAll = (e, isPending) => {
    const targetChickens = isPending ? pendingChickens : completedChickens
    if (e.target.checked) {
      const newIds = [...selectedIds, ...targetChickens.map(c => c.chickenId)]
      setSelectedIds([...new Set(newIds)])
      console.log('전체 선택:', newIds)
    } else {
      const targetIds = targetChickens.map(c => c.chickenId)
      setSelectedIds(selectedIds.filter(id => !targetIds.includes(id)))
      console.log('전체 해제')
    }
  }

  // 개별 선택/해제 (수정됨: chickenId 사용)
  const handleSelectOne = (chickenId) => {
    if (selectedIds.includes(chickenId)) {
      const newIds = selectedIds.filter(id => id !== chickenId)
      setSelectedIds(newIds)
      console.log('선택 해제:', chickenId, '현재 선택:', newIds)
    } else {
      const newIds = [...selectedIds, chickenId]
      setSelectedIds(newIds)
      console.log('선택 추가:', chickenId, '현재 선택:', newIds)
    }
  }

  const handleMarkCompleted = async () => {
    if (selectedIds.length === 0) {
      await showCustomAlert('접종할 개체를 선택해주세요.')
      return
    }

    console.log('접종 완료 처리 시작:', selectedIds)

    try {
      setLoading(true)

      // 실제 백엔드 연결 시도
      const inoculationData = {
        chickenIds: selectedIds,
        vaccineType: selectedVaccine,
        vaccinationMethod: '음수 투여',
        vaccinatedBy: '관리자',
        notes: `${selectedVaccine} 백신 접종 완료`,
        vaccinationDate: new Date().toISOString()
      }

      console.log('백엔드 전송 데이터:', inoculationData)

      await inoculationAPI.performBatchInoculation(inoculationData)
      await loadChickensByBatch(selectedBatch)
      setSelectedIds([])
      await showCustomAlert('예방접종이 성공적으로 완료되었습니다.')

    } catch (err) {
      console.error('백엔드 연결 실패, 더미 데이터로 처리:', err)
      // 백엔드 연결 실패 시 더미 데이터로 처리
      const updatedChickens = chickens.map(c =>
        selectedIds.includes(c.chickenId) ? { ...c, [selectedVaccine.toLowerCase()]: true } : c
      )
      console.log('업데이트된 닭 데이터:', updatedChickens)
      setChickens(updatedChickens)
      setSelectedIds([])
      await showCustomAlert('예방접종이 성공적으로 완료되었습니다. (더미 데이터)')
    } finally {
      setLoading(false)
    }
  }

  const handleMarkPending = async () => {
    if (selectedIds.length === 0) {
      await showCustomAlert('미완료 처리할 개체를 선택해주세요.')
      return
    }

    console.log('미완료 처리 시작:', selectedIds)

    try {
      setLoading(true)

      // 백엔드 API 호출
      const deleteData = {
        chickenIds: selectedIds,
        vaccineType: selectedVaccine
      }

      console.log('백엔드 전송 데이터:', deleteData)

      await inoculationAPI.deleteInoculation(deleteData)
      await loadChickensByBatch(selectedBatch)
      setSelectedIds([])
      await showCustomAlert('예방접종 상태가 미완료로 변경되었습니다.')

    } catch (err) {
      console.error('백엔드 연결 실패, 더미 데이터로 처리:', err)
      // 백엔드 연결 실패 시 더미 데이터로 처리
      const updatedChickens = chickens.map(c =>
        selectedIds.includes(c.chickenId) ? { ...c, [selectedVaccine.toLowerCase()]: false } : c
      )
      console.log('업데이트된 닭 데이터:', updatedChickens)
      setChickens(updatedChickens)
      setSelectedIds([])
      await showCustomAlert('예방접종 상태가 미완료로 변경되었습니다. (더미 데이터)')
    } finally {
      setLoading(false)
    }
  }

  const selectedVaccineInfo = vaccineOptions.find(v => v.value === selectedVaccine)
  const selectedBatchInfo = Array.isArray(batches) && batches.length > 0 ? batches.find(b => b.batchId === selectedBatch) : null

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>로딩 중...</div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>예방 접종</h2>

        <div className={styles.batchSelector}>
          <label className={styles.batchLabel}>배치 선택</label>
          <select
            className={styles.batchSelect}
            value={selectedBatch}
            onChange={(e) => {
              setSelectedBatch(e.target.value)
              setSelectedIds([])
            }}
          >
            {Array.isArray(batches) ? batches.filter(batch => batch.currentCount > 0).map(batch => (
              <option key={batch.batchId} value={batch.batchId}>
                {batch.batchId} (입식일: {new Date(batch.entryDate).toLocaleDateString()}, {batch.currentCount}마리)
              </option>
            )) : <option value="">배치 데이터가 없습니다</option>}
          </select>
        </div>

        <div className={styles.vaccineSelector}>
          <label className={styles.vaccineLabel}>접종 질병 선택</label>
          <select
            className={styles.vaccineSelect}
            value={selectedVaccine}
            onChange={(e) => {
              setSelectedVaccine(e.target.value)
              setSelectedIds([])
            }}
          >
            {vaccineOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <div className={styles.vaccineSchedule}>
            📅 접종 스케줄: {selectedVaccineInfo.schedule}
          </div>
        </div>

        <div className={styles.statsCards}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>배치 전체</div>
            <div className={styles.statValue}>{chickens.length}마리</div>
          </div>
          <div className={`${styles.statCard} ${styles.pending}`}>
            <div className={styles.statLabel}>접종 예정</div>
            <div className={styles.statValue}>{pendingChickens.length}마리</div>
          </div>
          <div className={`${styles.statCard} ${styles.completed}`}>
            <div className={styles.statLabel}>접종 완료</div>
            <div className={styles.statValue}>{completedChickens.length}마리</div>
          </div>
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.leftControls}>
          <button
            className={styles.btnSchedule}
            onClick={() => navigate('/home/inoculation-schedule')}
          >
            📅 접종 스케줄 보기
          </button>
          <button
            className={styles.btnList}
            onClick={() => navigate('/home/inoculation-list')}
          >
            📋 접종 리스트 보기
          </button>
          <div className={styles.selectInfo}>
            {selectedIds.length > 0 && (
              <span>{selectedIds.length}개 항목 선택됨</span>
            )}
          </div>
        </div>
        <div className={styles.actionButtons}>
          <button
            className={styles.btnComplete}
            onClick={handleMarkCompleted}
            disabled={selectedIds.length === 0}
          >
            ✓ 접종 완료 처리
          </button>
          <button
            className={styles.btnPending}
            onClick={handleMarkPending}
            disabled={selectedIds.length === 0}
          >
            ↺ 미완료 처리
          </button>
        </div>
      </div>

      <div className={styles.splitView}>
        {/* 접종 예정 */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>⏱ 접종 예정 ({pendingChickens.length}마리)</h3>
            <input
              type="checkbox"
              checked={pendingChickens.length > 0 && pendingChickens.every(c => selectedIds.includes(c.chickenId))}
              onChange={(e) => handleSelectAll(e, true)}
              className={styles.checkboxLarge}
            />
          </div>
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.checkboxCol}></th>
                  <th>개체 번호</th>
                  <th>일령</th>
                  <th>체중 (kg)</th>
                </tr>
              </thead>
              <tbody>
                {pendingChickens.map(chicken => (
                  <tr
                    key={chicken.chickenId}
                    className={selectedIds.includes(chicken.chickenId) ? styles.selected : ''}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(chicken.chickenId)}
                        onChange={() => handleSelectOne(chicken.chickenId)}
                      />
                    </td>
                    <td className={styles.tag}>C-{chicken.chickenId.toString().padStart(3, '0')}</td>
                    <td>{chicken.age}일</td>
                    <td>{chicken.rawWeight ? chicken.rawWeight.toFixed(2) : '0.00'}</td>
                  </tr>
                ))}
                {pendingChickens.length === 0 && (
                  <tr>
                    <td colSpan="4" className={styles.emptyMessage}>
                      모든 개체가 접종을 완료했습니다 ✓
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 접종 완료 */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>✓ 접종 완료 ({completedChickens.length}마리)</h3>
            <input
              type="checkbox"
              checked={completedChickens.length > 0 && completedChickens.every(c => selectedIds.includes(c.chickenId))}
              onChange={(e) => handleSelectAll(e, false)}
              className={styles.checkboxLarge}
            />
          </div>
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.checkboxCol}></th>
                  <th>개체 번호</th>
                  <th>일령</th>
                  <th>체중 (kg)</th>
                </tr>
              </thead>
              <tbody>
                {completedChickens.map(chicken => (
                  <tr
                    key={chicken.chickenId}
                    className={selectedIds.includes(chicken.chickenId) ? styles.selected : ''}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(chicken.chickenId)}
                        onChange={() => handleSelectOne(chicken.chickenId)}
                      />
                    </td>
                    <td className={styles.tag}>C-{chicken.chickenId.toString().padStart(3, '0')}</td>
                    <td>{chicken.age}일</td>
                    <td>{chicken.rawWeight ? chicken.rawWeight.toFixed(2) : '0.00'}</td>
                  </tr>
                ))}
                {completedChickens.length === 0 && (
                  <tr>
                    <td colSpan="4" className={styles.emptyMessage}>
                      아직 접종을 완료한 개체가 없습니다
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChickenInoculation