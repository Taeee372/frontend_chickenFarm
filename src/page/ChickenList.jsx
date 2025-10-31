import React, { useEffect, useRef, useState } from 'react'
import styles from './ChickenList.module.css'
import { chickenAPI, apiClient } from '../services/api'
import Button from '../common/Button';
import { useAlert } from '../context/AlertContext'

const ChickenList = ({batchId, changeReload, reload}) => {
  const { showCustomAlert, showCustomConfirm } = useAlert();
  //닭 개체 정보 
  const [chickenInfo, setChickenInfo] = useState([]);

  //폐사 개체 선택을 위한 체크박스
  const [checkedChickenId, setCheckedChickenId] = useState([]);

  //전체, HEALTHY, SICK 체크박스
  const [isAllChecked, setIsAllChecked] = useState(false);
  const [isHealthyChecked, setIsHealthyChecked] = useState(false);
  const [isSickChecked, setIsSickChecked] = useState(false);

  const chickenIds = useRef([]); //모든 개체 아이디 저장

  //닭 개체 정보 조회
  useEffect(() => {
    if(batchId){
      setCheckedChickenId([]);
      setIsAllChecked(false);
      setIsHealthyChecked(false);
      setIsSickChecked(false);

      apiClient.get(`/api/chicken/${batchId}`)
      .then(res => {
        setChickenInfo(res.data);

        //살아있는 모든 개체 아이디 저장
        chickenIds.current = [];
        for(const chicken of res.data){
          if(chicken.healthStatus !== 'DEAD'){
            chickenIds.current.push(chicken.chickenId)
          }
        }
      })
      .catch(e => console.log(e));
    }
  }, [batchId, reload])

  //체크박스 선택/해제
  const handleCheckbox = (e) => {
    const chickenId = parseInt(e.target.value);

    if (e.target.checked) {
      //체크 추가
      setCheckedChickenId([...checkedChickenId, chickenId]);
    } else {
      //이미 체크된 경우 제거
      setCheckedChickenId(checkedChickenId.filter(id => id !== chickenId));
      setIsAllChecked(false);
      setIsHealthyChecked(false);
      setIsSickChecked(false);
    }
  }

  //전체 체크박스 선택/해제
  const handleCheckedAll = (e) => {
    if(e.target.checked){
      setCheckedChickenId(chickenIds.current);
      setIsAllChecked(true);
    }
    else {
      setCheckedChickenId([]);
      setIsAllChecked(false);
      
    }
    setIsHealthyChecked(false);
    setIsSickChecked(false);
  }

  //HEALTHY 체크박스 선택/해제
  const handleCheckedHealthy = (e) => {
    if(e.target.checked){
      const healthyIds = chickenInfo
                        .filter(chicken => chicken.healthStatus === 'HEALTHY')
                        .map(chicken => chicken.chickenId);
      setCheckedChickenId(healthyIds);
      setIsHealthyChecked(true);
    }
    else {
      setCheckedChickenId([]);
      setIsHealthyChecked(false);
    }
    setIsAllChecked(false);
    setIsSickChecked(false);
  }

  //SICK 체크박스 선택/해제
  const handleCheckedSick = (e) => {
    if(e.target.checked){
      const sickIds = chickenInfo
                      .filter(chicken => chicken.healthStatus === 'SICK')
                      .map(chicken => chicken.chickenId);
      setCheckedChickenId(sickIds);
      setIsSickChecked(true);
    }
    else{
      setCheckedChickenId([]);
      setIsSickChecked(false);
    }
    setIsAllChecked(false);
    setIsHealthyChecked(false);
  }

  //선택된 개체 폐사 처리
  const handleDeathProcess = async () => {
    if (checkedChickenId.length === 0){
      await showCustomAlert('폐사 처리할 개체를 선택해주세요.');
      return ;
    }

    const confirmed = await showCustomConfirm(`선택한 ${checkedChickenId.length}마리를 폐사 처리하시겠습니까?`);
    if(!confirmed){
      return ;
    }

    apiClient.put('/api/chicken/death', {batchId : batchId, chickenIdList : checkedChickenId})
    .then(async res => {
      await showCustomAlert('폐사 처리 완료');
      setCheckedChickenId([]);
      changeReload();
    })
    .catch(e => console.log(e));
  }

  //선택된 개체의 건강 상태 수정
  const handleHealthStatus = async () => {
    if (checkedChickenId.length === 0){
      await showCustomAlert('건강 상태를 변경할 개체를 선택해주세요.')
      return;
    }

    apiClient.put('/api/chicken/update-health', {chickenIdList : checkedChickenId})
    .then(async res => {
      await showCustomAlert('건강 상태 변경 완료');
      setCheckedChickenId([]);
      changeReload();
    })
    .catch(e => console.log(e));
  }


  if (!batchId || chickenInfo.length === 0) {
   return (
    <table className={styles.table}>
      <thead>
        <tr>
          <td>선택</td>
          <td>개체번호</td>
          <td>나이(일)</td>
          <td>성장단계</td>
          <td>몸무게</td>
          <td>건강상태</td>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td colSpan={6} style={{backgroundColor : 'white'}}>조회된 개체 정보가 없습니다.</td>
        </tr>
      </tbody>
     </table>
   )
  }

  return (
      <div className={styles.container}>
        <div className={styles.chicken_count}>
          <div>
            <div>{chickenInfo[0].batchDTO.initialCount}</div>
            <span>총 개체 수</span>
          </div>
          <div>
            <div>{chickenInfo[0].batchDTO.currentCount}</div>
            <span>현 개체 수</span>
          </div>
          <div>
            <div>{(chickenInfo[0].batchDTO.initialCount)-(chickenInfo[0].batchDTO.currentCount)}</div>
            <span>폐사 개체 수</span>
          </div>
          <div>
            <div>{chickenInfo[0].age}</div>
            <span>나이</span>
          </div>
        </div>
        <h3>배치 {batchId} 개체 목록</h3>
        <div className={styles.chicken_list}>
          <div className={styles.check_and_button}>
            <span>
              <input 
                type='checkbox'
                checked={isAllChecked}
                onChange={e => handleCheckedAll(e)}
              /> 전체선택
            </span>
            <span>
              <input 
                type='checkbox'
                checked={isHealthyChecked}
                onChange={e => handleCheckedHealthy(e)}
              /> HEALTHY
            </span>
            <span>
              <input 
                type='checkbox'
                checked={isSickChecked}
                onChange={e => handleCheckedSick(e)}
              /> SICK
            </span>
            <div className={styles.btn_div}>
              <Button 
                title='폐사 처리'
                size='110px'
                height='40px'
                color='red'
                onClick={() => handleDeathProcess()}
                />
              <Button 
                title='건강 상태 수정 HEALTHY ←→ SICK'
                size='150px'
                height='40px'
                color='green'
                onClick={() => handleHealthStatus()}
                />
            </div>
          </div>
         
          <table className={styles.table}>
            <thead>
              <tr>
                <td>선택</td>
                <td>개체번호</td>
                <td>나이(일)</td>
                <td>성장단계</td>
                <td>몸무게</td>
                <td>건강상태</td>
              </tr>
            </thead>
            <tbody>
              {
                chickenInfo.map((e, i) => {
                  return (
                    <tr 
                      key={i}
                      className={
                          e.healthStatus === 'DEAD' ? styles.dead_color :
                          e.healthStatus === 'SICK' ? styles.sick_color : 
                          ''
                      }
                   >
                      <td>
                         <input 
                            type='checkbox'
                            value={e.chickenId}
                            checked={checkedChickenId.includes(e.chickenId)}
                            onChange={(e) => handleCheckbox(e)}
                            disabled={e.healthStatus === 'DEAD'}
                          />
                      </td>
                      <td>{e.chickenId}</td>
                      <td>{e.age}</td>
                      <td>{e.growthStage}</td>
                      <td>{e.rawWeight}g</td>
                      <td>{e.healthStatus}</td>
                    </tr>
                  )
                })
              }
            </tbody>
          </table>
        </div>
      </div>
  )
}

export default ChickenList