import React, { use, useEffect, useState } from 'react'
import styles from './ChickenManagement.module.css'
import Input from '../common/Input'
import Button from '../common/Button'
import ChickenList from './ChickenList'
import { apiClient } from '../services/api'
import { useAlert } from '../context/AlertContext'

const ChickenManagement = () => {
  const { showCustomAlert, showCustomConfirm } = useAlert();
  //양계장 번호 조회
  const [farmNumList, setFarmNumList] = useState([]);

  //화면 다시 그리기
  const [reload, setReload] = useState(0);

  //출하를 위한 체크박스
  const [checkedBatches, setCheckedBatches] = useState([]);

  //전체 체크박스
  const [isAllChecked, setIsAllChecked] = useState(false);

  //배치 번호 넘기기
  const [selectedBatchId, setSelectedBatchId] = useState('');

  //폐사 처리된 배치 보기 여부
  const [showDeadBatches, setShowDeadBatches] = useState(false);
  
  //축사 정보 저장
  const [farmName, setFarmName] = useState('');

  //배치 정보 저장
  const [batch, setBatch] = useState({
    'farmNum' : '',
    'entryDate' : '',
    'initialCount' : ''
  });

  //불러온 배치 정보 담을 변수
  const [batchInfo, setBatchInfo] = useState([]);

  const [errorMsg, setErrorMsg] = useState({
    'farmNameError' : '',
    'farmNumError' : '',
    'entryDateError' : '',
    'initialCountError' : ''
  });

  const regex = /^[0-9]+$/; //정수 정규식

  //화면에 띄울 배치
  const displayBatchInfo = 
  showDeadBatches 
  ? 
  batchInfo.filter(batch => batch.currentCount === 0) //폐사 처리된 배치
  :
  batchInfo.filter(batch => batch.currentCount > 0); //살아 있는 배치

  // 체크박스 선택/해제
  const handleCheckbox = (e) => {
    if (e.target.checked) {
      // 체크 추가
      setCheckedBatches([...checkedBatches, e.target.value]);
    } else {
      // 이미 체크된 경우 제거
      setCheckedBatches(checkedBatches.filter(batchId => batchId !== e.target.value));
      setIsAllChecked(false);
    }
  }

  //전체 체크박스 선택/해제 (살아있는 배치 중에서)
  const handleCheckedAll = (e) => {
    if(e.target.checked){
      const allBatchIds = displayBatchInfo
                          .filter(batch => batch.currentCount !== 0)
                          .map(batch => String(batch.batchId));
      setCheckedBatches(allBatchIds);
      setIsAllChecked(true)
    }
    else {
      setCheckedBatches([]);
      setIsAllChecked(false);
    }
  }

  const handleShipment = async () => {
  if (checkedBatches.length === 0) {
    await showCustomAlert('출하할 배치를 선택해주세요.');
    return;
  }

  const confirmed = await showCustomConfirm(`선택한 ${checkedBatches.length}개 배치를 출하 처리하시겠습니까?`);
  if(!confirmed){
    return ;
  }

  apiClient.put('/api/batch/shipment', { batchIdList: checkedBatches })
    .then(async res => {
      await showCustomAlert('출하가 완료되었습니다.');
      setCheckedBatches([]);  // 체크박스 초기화
      setIsAllChecked(false);
      setReload(reload + 1)
    })
    .catch(async e => {
      console.log(e);
      await showCustomAlert('출하 처리 중 오류가 발생했습니다.');
    });
}

  //배치 정보 변경 시 체크박스 초기화
  useEffect(() => {
    setCheckedBatches([]);
    setIsAllChecked(false);
  }, [showDeadBatches])

  //양계장 번호 조회
  useEffect(() => {
    apiClient.get('/api/farm/num-list')
    .then(res => setFarmNumList(res.data))
    .catch(e => console.log(e));
  }, [])

  //배치 정보 불러오기
  useEffect(() => {
    apiClient.get('/api/batch/info')
    .then(res => {
      setBatchInfo(res.data);
    })
    .catch(e => console.log(e));
  }, [reload])

  //양계장 등록
  const regFarmName = async () => {
    if(farmName === ''){
      setErrorMsg({
        ...errorMsg,
        'farmNameError' : '양계장 이름을 입력해주세요.'
      })
      return ;
    }
    apiClient.post(`/api/farm`, {farmName : farmName})
    .then(async res => {
      await showCustomAlert('양계장 등록이 완료되었습니다.');
      setFarmName('');
      changeReload();
    })
    .catch(e => {
      console.log(e)
    });
  }

  //배치 & 개체 동시 등록
  const regBatchAndChickens = async () => {
    const newErrors = {
      farmNumError: batch.farmNum === '' ? '양계장을 선택해주세요.' : '',
      entryDateError: batch.entryDate === '' ? '입식일을 선택해주세요.' : '',
      initialCountError: batch.initialCount === '' || batch.initialCount < 1 ? '닭 개체 수를 입력해주세요.' :
                        !regex.test(batch.initialCount) ? '숫자를 입력해주세요.' : ''
    };

    setErrorMsg({
      ...errorMsg,
      ...newErrors
    });

    //에러가 하나라도 있으면 등록 중단
    if(Object.values(newErrors).some(error => error !== '')){
      return ;
    }

    apiClient.post('/api/batch', batch)
    .then(async res => {
      await showCustomAlert('배치 등록이 완료되었습니다.');
      setBatch({
        'farmNum' : '',
        'entryDate' : '',
        'initialCount' : ''
      });
      changeReload();
    })
    .catch(e => {
      console.log(e)
    });
  }

  //배치 인풋에 입력한 값으로 변경
  const handleBatch = (e) => {
    setBatch({
      ...batch,
      [e.target.name] : e.target.value
    })
  }

  const changeReload = () => {
    setReload(reload + 1);
  }

  return (
    <div className={styles.container}>
      <h2>개체 관리</h2>
      <div>
        <h3>양계장 등록</h3>
        <div className={styles.farm_reg}>
          <span>양계장 이름</span>
          <div className={styles.valid}>
            <Input 
              value={farmName} 
              onChange={(e) => {
                setFarmName(e.target.value);
                setErrorMsg({
                  ...errorMsg,
                  'farmNameError' : e.target.value === '' ? '양계장 이름을 입력해주세요.' : ''
                })
              }}
              size='150px'
              height='30px'
              onKeyDown={e => {
                if(e.key === 'Enter') regFarmName()
              }}
              />
              <p className={styles.error}>{errorMsg.farmNameError}</p>
          </div>
          <Button 
            size='80px'
            height='30px'
            color='green'
            title='등록'
            onClick={() => regFarmName()}
          />
        </div>
      </div>
      <div>
        <h3>배치 등록</h3>
        <div className={styles.batch_reg}>
          <div className={styles.input_group}>
            <span>양계장</span>
            <div className={styles.valid}>
              <select
                name='farmNum'
                value={batch.farmNum}
                onChange={(e) => {
                  handleBatch(e);
                  setErrorMsg({
                  ...errorMsg,
                  'farmNumError' : e.target.value === '' ? '양계장을 선택해주세요.' : ''
                  })
                }}
              >
                <option value=''>선택</option>
                {
                  farmNumList.map((farm, i) => {
                    return (
                      <option key={i} value={farm.farmNum}>{farm.farmNum} - {farm.farmName}</option>
                    )
                  })
                }
              </select>
              <p className={styles.error}>{errorMsg.farmNumError}</p>
            </div>
          </div>
          <div className={styles.input_group}>
            <span>입식일</span>
           <div className={styles.valid}>
              <Input 
                size='140px'
                height='30px'
                type='date'
                name='entryDate'
                value={batch.entryDate}
                onChange={(e) => {
                  handleBatch(e);
                  setErrorMsg({
                  ...errorMsg,
                  'entryDateError' 
                  : e.target.value === '' ? '입식일을 선택해주세요.' : ''
                  })
                }}
              />
              <p className={styles.error}>{errorMsg.entryDateError}</p>
           </div>
          </div>
          <div className={styles.input_group}>
            <span>닭 개체 수</span>
            <div className={styles.valid}>
              <Input 
                size='140px'
                height='30px'
                name='initialCount'
                value={batch.initialCount}
                onChange={(e) => {
                  handleBatch(e)
                  setErrorMsg({
                  ...errorMsg,
                  'initialCountError' 
                  : e.target.value === '' ? '닭 개체 수를 입력해주세요' :
                    !regex.test(e.target.value) ? '숫자를 입력해주세요.' : ''
                })
                }}
              />
              <p className={styles.error}>{errorMsg.initialCountError}</p>
            </div>
          </div>
          <Button 
            size='80px'
            height='30px'
            color='green'
            title='등록' 
            onClick={() => regBatchAndChickens()}
          />
        </div>
      </div>
      <div>
        <h3>배치 목록</h3>
        <div className={styles.batch_list}>
          <span>
            <input 
              type="checkbox" 
              checked={isAllChecked}
              onChange={e => handleCheckedAll(e)}
            /> 전체 선택
          </span>
          {
            displayBatchInfo.length === 0 
            ?
            <table className={styles.table}>
              <colgroup>
                <col width='*%'/>
                <col width='19%'/>
                <col width='19%'/>
                <col width='18%'/>
                <col width='18%'/>
                <col width='10%'/>
              </colgroup>
              <thead>
                <tr>
                  <td>양계장 번호</td>
                  <td>배치 번호</td>
                  <td>입식일</td>
                  <td>초기 닭의 수</td>
                  <td>현재 닭의 수</td>
                  <td>출하</td>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td colSpan={6} style={{backgroundColor : 'white'}}>
                    {showDeadBatches ? '폐사 처리된 배치가 없습니다.' : '배치가 존재하지 않습니다.'}
                  </td>
                </tr>
              </tbody>
            </table>
            :
            <table className={styles.table}>
              <colgroup>
                <col width='*%'/>
                <col width='19%'/>
                <col width='19%'/>
                <col width='18%'/>
                <col width='18%'/>
                <col width='10%'/>
              </colgroup>
            <thead>
              <tr>
                <td>양계장 번호</td>
                <td>배치 번호</td>
                <td>입식일</td>
                <td>초기 닭의 수</td>
                <td>현재 닭의 수</td>
                <td>출하</td>
              </tr>
            </thead>
            <tbody>
              {
                displayBatchInfo.map((batch, i) => {
                  return (
                    <tr 
                      key={i} 
                      onClick={() => setSelectedBatchId(batch.batchId)}
                      className={batch.currentCount === 0 ? styles.dead_color : ''}
                    >
                      <td>{batch.farmNum}</td>
                      <td>{batch.batchId}</td>
                      <td>{batch.entryDate}</td>
                      <td>{batch.initialCount}</td>
                      <td>{batch.currentCount}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input 
                          type='checkbox'
                          value={batch.batchId}
                          checked={checkedBatches.includes(String(batch.batchId))}
                          onChange={(e) => handleCheckbox(e)}
                          disabled={showDeadBatches}
                        />
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </table>
          }
          <div className={styles.btn_div}>
            <Button 
              size='120px'
              height='30px'
              color='gray'
              title={showDeadBatches ? '돌아가기' : '폐사 처리된 배치'}
              onClick={() => setShowDeadBatches(!showDeadBatches)}
            />
            <Button 
              size='80px'
              height='30px'
              color='green'
              title='출하' 
              onClick={handleShipment}
            />
          </div>
        </div>
      </div>
      {
        selectedBatchId && <ChickenList batchId={selectedBatchId} changeReload={changeReload} reload={reload}/>
      }
    </div>
  )
}

export default ChickenManagement