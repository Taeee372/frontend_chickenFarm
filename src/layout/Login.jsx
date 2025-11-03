import { useState } from 'react'
import Input from '../common/Input'
import Button from '../common/Button'
import styles from './Login.module.css'
import { useNavigate } from 'react-router-dom'
import { memberAPI } from '../services/api'
import { useAlert } from '../context/AlertContext'

const Login = () => {
  const nav = useNavigate();
  const { showCustomAlert } = useAlert();

  const [loginDate, setLoginDate] = useState({
    'memId': '',
    'memPw': ''
  });

  const handleLoginData = (e) => {
    setLoginDate({
      ...loginDate,
      [e.target.name]: e.target.value
    });
  }

  const login = async () => {
    try {
      const response = await memberAPI.login(loginDate);
      console.log('로그인 응답:', response);

      if (response && response.memId) {
        const loginInfo = {
          'memId': response.memId,
          'name': response.name,
          'role': response.role
        };

        sessionStorage.setItem('loginInfo', JSON.stringify(loginInfo));

        if (response.role === 'ADMIN') {
          await showCustomAlert('환영합니다.');
          nav('/home');
          setLoginDate({ 'memId': '', 'memPw': '' });
        }
      } else {
        await showCustomAlert('ID 혹은 비밀번호가 잘못 입력되었습니다.');
      }
    } catch (err) {
      console.error('로그인 오류:', err);
      if (err.response) {
        if (err.response.status === 401) {
          await showCustomAlert('ID 혹은 비밀번호가 잘못 입력되었습니다.');
        } else if (err.response.status === 404) {
          await showCustomAlert('로그인 서비스를 찾을 수 없습니다. 서버 상태를 확인해주세요.');
        } else {
          await showCustomAlert('로그인 중 오류가 발생했습니다.');
        }
      } else if (err.request) {
        await showCustomAlert('서버에 연결할 수 없습니다. 네트워크를 확인해주세요.');
      } else {
        await showCustomAlert('로그인 중 오류가 발생했습니다.');
      }
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.title}>Smart Farm</div>
      <div className={styles.form_div}>
        <div className={styles.input_div}>
          <Input
            size='500px'
            height='45px'
            placeholder='아이디 또는 전화번호'
            name='memId'
            value={loginDate.memId}
            onChange={e => handleLoginData(e)}
            className={styles.input}
            onKeyDown={e => {
              if (e.key === 'Enter') login()
            }}
          />
          {
            loginDate.memId && (
              <Button
                className={styles.input_inButton}
                size='10px'
                title='x'
                onClick={() => {
                  setLoginDate({
                    ...loginDate,
                    'memId': ''
                  })
                }}
              />
            )
          }
        </div>
        <div className={styles.input_div}>
          <Input
            size='500px'
            height='45px'
            placeholder='비밀번호'
            name='memPw'
            value={loginDate.memPw}
            onChange={e => handleLoginData(e)}
            className={styles.input}
            type='password'
            onKeyDown={e => {
              if (e.key === 'Enter') login()
            }}
          />
          {
            loginDate.memPw && (
              <Button
                className={styles.input_inButton}
                size='10px'
                title='x'
                onClick={() => {
                  setLoginDate({
                    ...loginDate,
                    'memPw': ''
                  })
                }}
              />
            )
          }
        </div>
        <div className={styles.button_div}>
          <Button
            title='로그인'
            className={styles.button}
            size='500px'
            height='45px'
            onClick={() => {
              login()
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default Login