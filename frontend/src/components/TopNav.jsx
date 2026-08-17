import styles from './TopNav.module.css'

export default function TopNav() {
  return (
    <nav className={styles.nav}>
      <div className={styles.inner}>
        <a href="#" className={styles.logo}>
          <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1", color: 'var(--primary-container)', fontSize: '22px' }}>dataset</span>
          <span className={styles.wordmark}>Recalce</span>
        </a>
        <div className={styles.links}>
          <a href="#" className={styles.activeLink}>Dashboard</a>
        </div>
      </div>
    </nav>
  )
}
