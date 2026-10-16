/**
 * src/components/TopNav.jsx
 *
 * Institutional navigation bar — Linear/Stripe style.
 * Layout: Logo (left) · Nav links (centre) · User context (right)
 * Height: 56px, single hairline border at bottom.
 */

import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import styles from './TopNav.module.css';

function AvatarInitials({ name }) {
  const initials = name
    ? name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()
    : '?';
  return <span className={styles.avatar}>{initials}</span>;
}

const ROLE_LABELS = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Admin',
  ANALYST: 'Analyst',
};

const ROLE_COLOURS = {
  SUPER_ADMIN: { bg: 'var(--primary)', color: '#fff', hoverBg: '#b36b00' },
  ADMIN:       { bg: 'var(--primary-container)', color: 'var(--on-primary-container)', hoverBg: '#ffd580' },
  ANALYST:     { bg: 'var(--surface-container-high)', color: 'var(--on-surface-variant)', hoverBg: '#e6e6e6' },
};

export default function TopNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleColour = user ? ROLE_COLOURS[user.role] ?? ROLE_COLOURS.ANALYST : null;

  /* Build nav links based on role */
  const navLinks = [];
  if (user?.role === 'SUPER_ADMIN') {
    navLinks.push({ to: '/superadmin', label: 'Overview' });
    navLinks.push({ to: '/workspace', label: 'Workspace' });
  } else if (user?.role === 'ADMIN') {
    navLinks.push({ to: '/admin', label: 'Admin Portal' });
    navLinks.push({ to: '/workspace', label: 'Workspace' });
  } else if (user?.role === 'ANALYST') {
    navLinks.push({ to: '/workspace', label: 'Workspace' });
  }

  return (
    <nav className={`${styles.nav} ${isScrolled ? styles.navScrolled : ''}`} role="navigation" aria-label="Main navigation">
      <div className={styles.inner}>

        {/* Left — brand */}
        <Link to="/" className={styles.brand}>
          Recalce
        </Link>

        {/* Centre — page links */}
        {navLinks.length > 0 && (
          <div className={styles.links} role="menubar">
            {navLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                role="menuitem"
                className={`${styles.link} ${pathname === to || pathname.startsWith(to + '/') ? styles.linkActive : ''}`}
              >
                {label}
              </Link>
            ))}
          </div>
        )}

        {/* Spacer */}
        <div className={styles.spacer} />

        {/* Right — user context */}
        {user && (
          <div className={styles.userSection}>
            {/* Org name (if not Super Admin) */}
            {user.org_name && (
              <span className={styles.orgName}>{user.org_name}</span>
            )}

            {/* Interactive Role pill */}
            <div 
              className={styles.rolePill}
              style={{ '--pill-bg': roleColour.bg, '--pill-color': roleColour.color, '--pill-hover': roleColour.hoverBg }}
              title={`Logged in as ${ROLE_LABELS[user.role]}`}
            >
              <div className={styles.rolePillDot} />
              <span className={styles.rolePillText}>{ROLE_LABELS[user.role] ?? user.role}</span>
            </div>

            {/* Avatar */}
            <AvatarInitials name={user.full_name} />

            {/* Logout */}
            <button
              onClick={handleLogout}
              className={styles.logoutBtn}
              aria-label="Sign out"
              title="Sign out"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

