import { useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useApp } from '../state'

export function Layout({ children }: { children: ReactNode }) {
  const { t, lang, setLang, meta, online, user, logout, alerts } = useApp()
  const [menuOpen, setMenuOpen] = useState(false)
  const loc = useLocation()
  const wide = loc.pathname.startsWith('/dashboard') || loc.pathname.startsWith('/admin')

  return (
    <div className={`app ${wide ? 'app-wide' : ''}`}>
      <header className="topbar">
        <Link to="/" className="brand" onClick={() => setMenuOpen(false)}>
          <img src="/icon.svg" alt="" width={28} height={28} />
          <span>
            <strong>{t('appName')}</strong>
            <small>{t('tagline')}</small>
          </span>
        </Link>
        <div className="topbar-actions">
          <button className="btn btn-lang" onClick={() => setLang(lang === 'te' ? 'en' : 'te')} aria-label="Change language / భాష మార్చండి">
            {t('langToggle')}
          </button>
          <button className="btn btn-icon" aria-expanded={menuOpen} aria-label={t('menu')} onClick={() => setMenuOpen((v) => !v)}>
            ☰
          </button>
        </div>
        {menuOpen && (
          <nav className="menu" onClick={() => setMenuOpen(false)}>
            <NavLink to="/dashboard">{t('navDashboard')}</NavLink>
            <NavLink to="/admin">{t('navAdmin')}</NavLink>
            {user ? (
              <>
                <span className="menu-user">
                  {t('loggedInAs')}: <strong>{user.name || user.username}</strong> ({user.role})
                </span>
                <button className="btn btn-link" onClick={logout}>
                  {t('logout')}
                </button>
              </>
            ) : (
              <NavLink to="/login">{t('navLogin')}</NavLink>
            )}
          </nav>
        )}
      </header>

      {meta?.is_simulated && <div className="banner banner-info">{t('simulatedBanner')}</div>}
      {!online && <div className="banner banner-warn">{t('offline')}</div>}

      <main className="content">{children}</main>

      <footer className="footer muted small">{t('footer')}</footer>

      <nav className="bottomnav" aria-label="Main">
        <NavLink to="/" end>
          <span aria-hidden="true">₹</span>
          {t('navPrices')}
        </NavLink>
        <NavLink to="/markets">
          <span aria-hidden="true">⇄</span>
          {t('navMarkets')}
        </NavLink>
        <NavLink to="/ask">
          <span aria-hidden="true">🎙</span>
          {t('navAsk')}
        </NavLink>
        <NavLink to="/alerts">
          <span aria-hidden="true">🔔</span>
          {t('navAlerts')}
          {alerts.length > 0 && <em className="dot-count">{alerts.length}</em>}
        </NavLink>
      </nav>
    </div>
  )
}
