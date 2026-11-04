import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../state'
import { Card, ErrorBox } from '../components/common'

export function LoginPage() {
  const { t, login, user, logout } = useApp()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) {
    return (
      <div className="page">
        <Card title={t('loginTitle')}>
          <p>
            {t('loggedInAs')}: <strong>{user.name || user.username}</strong> ({user.role})
          </p>
          <div className="row-inline">
            <button className="btn btn-primary" onClick={() => nav(user.role === 'admin' ? '/admin' : '/dashboard')}>
              {user.role === 'admin' ? t('navAdmin') : t('navDashboard')}
            </button>
            <button className="btn btn-secondary" onClick={logout}>
              {t('logout')}
            </button>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="page">
      <Card title={t('loginTitle')}>
        <form
          className="stack"
          onSubmit={async (e) => {
            e.preventDefault()
            setErr(null)
            setBusy(true)
            try {
              const u = await login(username.trim(), password)
              nav(u.role === 'admin' ? '/admin' : '/dashboard')
            } catch (ex) {
              setErr((ex as Error).message)
            } finally {
              setBusy(false)
            }
          }}
        >
          <label className="field">
            <span>{t('username')}</span>
            <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="field">
            <span>{t('password')}</span>
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {err && <ErrorBox error={err} />}
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {t('login')}
          </button>
        </form>
        <p className="hint">{t('demoAccounts')}</p>
      </Card>
    </div>
  )
}
