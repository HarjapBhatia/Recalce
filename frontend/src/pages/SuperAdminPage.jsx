import React, { useState, useEffect } from 'react';
import TopNav from '../components/TopNav';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { StaggeredTextReveal } from '../components/ui/StaggeredTextReveal';
import { WarmBeam } from '../components/ui/WarmBeam';
import { useAuth } from '../context/AuthContext';
import styles from './WorkspacePage.module.css';

const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const BASE = rawBase.endsWith('/api/v1') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api/v1`

export default function SuperAdminPage() {
  const { token } = useAuth();
  const [overview, setOverview] = useState({ organizations: 0, admins: 0, analysts: 0, total_batches: 0 });
  const [orgs, setOrgs] = useState([]);
  const [batches, setBatches] = useState([]);
  const [activeTab, setActiveTab] = useState('orgs');

  useEffect(() => {
    if (!token) return;
    const fetchData = async () => {
      try {
        const headers = { Authorization: `Bearer ${token}` };
        const [resOverview, resOrgs, resBatches] = await Promise.all([
          fetch(`${BASE}/superadmin/overview`,      { headers }),
          fetch(`${BASE}/superadmin/organizations`, { headers }),
          fetch(`${BASE}/superadmin/batches`,       { headers })
        ]);
        if (resOverview.ok) setOverview(await resOverview.json());
        if (resOrgs.ok)     setOrgs(await resOrgs.json());
        if (resBatches.ok)  setBatches(await resBatches.json());
      } catch (e) {
        console.error('SuperAdmin fetch error:', e);
      }
    };
    fetchData();
  }, [token]);

  const handleTransfer = async (batchId, targetOrgId) => {
    try {
      const res = await fetch(`${BASE}/superadmin/batches/${batchId}/transfer`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body:    JSON.stringify({ target_organization_id: targetOrgId })
      });
      if (res.ok) {
        const resBatches = await fetch(`${BASE}/superadmin/batches`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (resBatches.ok) setBatches(await resBatches.json());
      }
    } catch (e) {
      console.error('Transfer error:', e);
    }
  };

  return (
    <div className={styles.pageWrapper}>
      <WarmBeam />
      <TopNav />
      <main className={styles.main}>
        <div className={styles.pageHeader}>
          <div>
            <StaggeredTextReveal text="Super Admin Console" className={styles.pageTitle} />
            <p className={styles.pageSubtitle}>Global oversight and cross-tenant batch reallocation.</p>
          </div>
        </div>

        {/* Global Metrics */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '16px' }}>
          <SpotlightCard style={{ padding: '24px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--on-surface-variant)' }}>Total Organizations</div>
            <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--primary-container)' }}>{overview.organizations}</div>
          </SpotlightCard>
          <SpotlightCard style={{ padding: '24px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--on-surface-variant)' }}>Platform Admins</div>
            <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--primary-container)' }}>{overview.admins}</div>
          </SpotlightCard>
          <SpotlightCard style={{ padding: '24px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--on-surface-variant)' }}>Platform Analysts</div>
            <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--primary-container)' }}>{overview.analysts}</div>
          </SpotlightCard>
          <SpotlightCard style={{ padding: '24px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--on-surface-variant)' }}>Total Batches</div>
            <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--primary-container)' }}>{overview.total_batches}</div>
          </SpotlightCard>
        </div>

        <div style={{ display: 'flex', gap: '16px', borderBottom: '1px solid var(--outline-variant)' }}>
          <button
            onClick={() => setActiveTab('orgs')}
            style={{
              padding: '12px 16px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'orgs' ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeTab === 'orgs' ? 'var(--primary)' : 'var(--on-surface-variant)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Organizations
          </button>
          <button
            onClick={() => setActiveTab('batches')}
            style={{
              padding: '12px 16px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'batches' ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeTab === 'batches' ? 'var(--primary)' : 'var(--on-surface-variant)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Global Batch Control
          </button>
        </div>

        {activeTab === 'orgs' && (
          <SpotlightCard style={{ padding: '24px' }}>
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                  <th style={{ padding: '12px 8px' }}>Organization</th>
                  <th style={{ padding: '12px 8px' }}>Slug</th>
                  <th style={{ padding: '12px 8px' }}>Admins</th>
                  <th style={{ padding: '12px 8px' }}>Analysts</th>
                  <th style={{ padding: '12px 8px' }}>Batches</th>
                  <th style={{ padding: '12px 8px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map(o => (
                  <tr key={o.id} style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                    <td style={{ padding: '12px 8px', fontWeight: 600 }}>{o.name}</td>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-mono)' }}>{o.slug}</td>
                    <td style={{ padding: '12px 8px' }}>{o.admin_count}</td>
                    <td style={{ padding: '12px 8px' }}>{o.analyst_count}</td>
                    <td style={{ padding: '12px 8px' }}>{o.batch_count}</td>
                    <td style={{ padding: '12px 8px' }}>
                      <span style={{ color: o.is_active ? '#2e7d32' : '#c62828', fontWeight: 600, fontSize: '12px' }}>
                        {o.is_active ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </td>
                  </tr>
                ))}
                {orgs.length === 0 && (
                  <tr>
                    <td colSpan="6" style={{ padding: '24px', textAlign: 'center', color: 'var(--on-surface-variant)' }}>
                      No organizations found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </SpotlightCard>
        )}

        {activeTab === 'batches' && (
          <SpotlightCard style={{ padding: '24px' }}>
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                  <th style={{ padding: '12px 8px' }}>Batch ID</th>
                  <th style={{ padding: '12px 8px' }}>Uploaded At</th>
                  <th style={{ padding: '12px 8px' }}>Status</th>
                  <th style={{ padding: '12px 8px' }}>Current Organization</th>
                  <th style={{ padding: '12px 8px' }}>Transfer To</th>
                </tr>
              </thead>
              <tbody>
                {batches.map(b => (
                  <tr key={b.batch_id} style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-mono)' }}>{b.batch_id.split('-')[0]}</td>
                    <td style={{ padding: '12px 8px' }}>{new Date(b.uploaded_at).toLocaleString()}</td>
                    <td style={{ padding: '12px 8px' }}>{b.status}</td>
                    <td style={{ padding: '12px 8px' }}>
                      {orgs.find(o => o.id === b.organization_id)?.name || 'Unknown'}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <select
                        value={b.organization_id || ""}
                        onChange={(e) => {
                          if (e.target.value !== b.organization_id && window.confirm("Are you sure you want to transfer this batch? All current assignments will be lost.")) {
                            handleTransfer(b.batch_id, e.target.value);
                          }
                        }}
                        style={{ padding: '4px 8px', border: '1px solid var(--outline-variant)', borderRadius: '4px', maxWidth: '200px' }}
                      >
                        {orgs.map(o => (
                          <option key={o.id} value={o.id}>{o.name}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
                {batches.length === 0 && (
                  <tr>
                    <td colSpan="5" style={{ padding: '24px', textAlign: 'center', color: 'var(--on-surface-variant)' }}>
                      No batches found across the platform.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </SpotlightCard>
        )}

      </main>
    </div>
  );
}
