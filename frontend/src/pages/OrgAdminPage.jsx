import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import TopNav from '../components/TopNav';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { StaggeredTextReveal } from '../components/ui/StaggeredTextReveal';
import { WarmBeam } from '../components/ui/WarmBeam';
import { useAuth } from '../context/AuthContext';
import styles from './WorkspacePage.module.css';

const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const BASE = rawBase.endsWith('/api/v1') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api/v1`;

export default function OrgAdminPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('team');
  const [analysts, setAnalysts] = useState([]);
  const [batches, setBatches] = useState([]);
  const [newAnalyst, setNewAnalyst] = useState({ full_name: '', email: '', password: '' });
  const [createError, setCreateError] = useState(null);
  const [createSuccess, setCreateSuccess] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  // Selected Analyst for batch assignment view
  const [selectedAnalystFilter, setSelectedAnalystFilter] = useState('all');
  const [batchSearch, setBatchSearch] = useState('');

  useEffect(() => {
    if (!token) return;
    fetchAnalysts();
    fetchBatches();
  }, [token]);

  const fetchAnalysts = async () => {
    try {
      const res = await fetch(`${BASE}/admin/analysts`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) setAnalysts(await res.json());
    } catch (e) {
      console.error('Fetch analysts error:', e);
    }
  };

  const fetchBatches = async () => {
    try {
      const res = await fetch(`${BASE}/admin/batches`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) setBatches(await res.json());
    } catch (e) {
      console.error('Fetch batches error:', e);
    }
  };

  const handleCreateAnalyst = async (e) => {
    e.preventDefault();
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const res = await fetch(`${BASE}/admin/analysts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(newAnalyst)
      });
      if (res.ok) {
        setNewAnalyst({ full_name: '', email: '', password: '' });
        setCreateSuccess('Analyst account created successfully.');
        fetchAnalysts();
      } else {
        const err = await res.json();
        setCreateError(err.detail || 'Failed to create analyst.');
      }
    } catch (e) {
      setCreateError('Network error. Please try again.');
    }
  };

  const handleDeleteAnalyst = async (analyst) => {
    if (!window.confirm(`Are you sure you want to remove analyst "${analyst.full_name}" (${analyst.email})? Any batches assigned to them will be unassigned.`)) {
      return;
    }
    setActionMessage(null);
    try {
      const res = await fetch(`${BASE}/admin/analysts/${analyst.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setActionMessage(`Analyst ${analyst.full_name} removed successfully.`);
        fetchAnalysts();
        fetchBatches();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to remove analyst.');
      }
    } catch (e) {
      alert('Network error while removing analyst.');
    }
  };

  const handleAssignment = async (batchId, analystId, isPublic) => {
    try {
      const res = await fetch(`${BASE}/admin/batches/${batchId}/assignment`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ assigned_analyst_id: analystId || null, is_org_public: isPublic })
      });
      if (res.ok) fetchBatches();
    } catch (e) {
      console.error('Assignment error:', e);
    }
  };

  const onlyAnalysts = analysts.filter(a => a.role === 'ANALYST');

  // Filter batches by analyst filter and batch ID search
  const displayedBatches = batches.filter(b => {
    if (batchSearch.trim()) {
      const q = batchSearch.trim().toLowerCase();
      if (!b.batch_id.toLowerCase().includes(q)) return false;
    }
    if (selectedAnalystFilter === 'all') return true;
    if (selectedAnalystFilter === 'unassigned') return !b.assigned_analyst_id && !b.is_org_public;
    if (selectedAnalystFilter === 'public') return b.is_org_public;
    return b.assigned_analyst_id === selectedAnalystFilter;
  });

  return (
    <div className={styles.pageWrapper}>
      <WarmBeam />
      <TopNav />
      <main className={styles.main}>
        <div className={styles.pageHeader}>
          <div>
            <StaggeredTextReveal text="Organization Admin" className={styles.pageTitle} />
            <p className={styles.pageSubtitle}>
              Manage analysts, assign reconciliation batches, and run reconciliations.
            </p>
          </div>
          <Link
            to="/workspace"
            style={{
              padding: '10px 18px',
              background: 'var(--primary-container)',
              color: 'var(--on-primary-container)',
              borderRadius: '8px',
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: '14px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>play_circle</span>
            Run Recon in Workspace
          </Link>
        </div>

        {actionMessage && (
          <div style={{
            padding: '12px 16px',
            background: '#e8f5e9',
            border: '1px solid #a5d6a7',
            borderRadius: '8px',
            color: '#2e7d32',
            fontSize: '14px',
            marginBottom: '16px'
          }}>
            {actionMessage}
          </div>
        )}

        <div style={{ display: 'flex', gap: '16px', borderBottom: '1px solid var(--outline-variant)', marginBottom: '24px' }}>
          <button
            onClick={() => setActiveTab('team')}
            style={{
              padding: '12px 16px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'team' ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeTab === 'team' ? 'var(--primary)' : 'var(--on-surface-variant)',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Team Roster ({analysts.length})
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
            Batch Assignment ({batches.length})
          </button>
        </div>

        {activeTab === 'team' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
            <SpotlightCard style={{ padding: '24px' }}>
              <h3 style={{ marginBottom: '16px', fontWeight: 600 }}>Analysts &amp; Administrators</h3>
              <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                    <th style={{ padding: '12px 8px' }}>Name</th>
                    <th style={{ padding: '12px 8px' }}>Email</th>
                    <th style={{ padding: '12px 8px' }}>Role</th>
                    <th style={{ padding: '12px 8px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {analysts.map(u => (
                    <tr key={u.id} style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                      <td style={{ padding: '12px 8px', fontWeight: 500 }}>{u.full_name}</td>
                      <td style={{ padding: '12px 8px', color: 'var(--on-surface-variant)' }}>{u.email}</td>
                      <td style={{ padding: '12px 8px' }}>
                        <span style={{
                          fontSize: '11px',
                          padding: '4px 8px',
                          background: u.role === 'ADMIN' ? 'var(--primary-container)' : 'var(--surface-container-high)',
                          borderRadius: '4px',
                          fontWeight: 650
                        }}>
                          {u.role}
                        </span>
                      </td>
                      <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                        {u.role === 'ANALYST' ? (
                          <button
                            onClick={() => handleDeleteAnalyst(u)}
                            style={{
                              padding: '6px 12px',
                              background: 'transparent',
                              border: '1px solid var(--outline-variant)',
                              borderRadius: '6px',
                              color: '#d32f2f',
                              fontSize: '12px',
                              fontWeight: 600,
                              cursor: 'pointer'
                            }}
                            title="Remove analyst from organization"
                          >
                            Remove
                          </button>
                        ) : (
                          <span style={{ fontSize: '12px', color: 'var(--on-surface-variant)' }}>Org Admin</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {analysts.length === 0 && (
                    <tr>
                      <td colSpan="4" style={{ padding: '24px', textAlign: 'center', color: 'var(--on-surface-variant)' }}>
                        No team members found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </SpotlightCard>

            <SpotlightCard style={{ padding: '24px' }}>
              <h3 style={{ marginBottom: '4px', fontWeight: 600 }}>Provision Analyst</h3>
              <p style={{ fontSize: '13px', color: 'var(--on-surface-variant)', marginBottom: '16px' }}>
                Create a new analyst account in your organization. They can then sign in at <strong>/login</strong>.
              </p>

              {createError && (
                <div style={{ padding: '10px 12px', background: '#ffebee', border: '1px solid #ef9a9a', borderRadius: '6px', color: '#c62828', fontSize: '13px', marginBottom: '12px' }}>
                  {createError}
                </div>
              )}
              {createSuccess && (
                <div style={{ padding: '10px 12px', background: '#e8f5e9', border: '1px solid #a5d6a7', borderRadius: '6px', color: '#2e7d32', fontSize: '13px', marginBottom: '12px' }}>
                  {createSuccess}
                </div>
              )}

              <form onSubmit={handleCreateAnalyst} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <input
                  type="text" placeholder="Full Name" required
                  value={newAnalyst.full_name}
                  onChange={e => setNewAnalyst({ ...newAnalyst, full_name: e.target.value })}
                  style={{ padding: '8px 12px', border: '1px solid var(--outline-variant)', borderRadius: '4px', background: 'transparent', color: 'inherit' }}
                />
                <input
                  type="email" placeholder="Email Address" required
                  value={newAnalyst.email}
                  onChange={e => setNewAnalyst({ ...newAnalyst, email: e.target.value })}
                  style={{ padding: '8px 12px', border: '1px solid var(--outline-variant)', borderRadius: '4px', background: 'transparent', color: 'inherit' }}
                />
                <input
                  type="password" placeholder="Temporary Password (min 8 chars)" required minLength={8}
                  value={newAnalyst.password}
                  onChange={e => setNewAnalyst({ ...newAnalyst, password: e.target.value })}
                  style={{ padding: '8px 12px', border: '1px solid var(--outline-variant)', borderRadius: '4px', background: 'transparent', color: 'inherit' }}
                />
                <button
                  type="submit"
                  style={{ padding: '10px', background: 'var(--primary-container)', color: 'var(--on-primary-container)', border: 'none', borderRadius: '4px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Create Account
                </button>
              </form>
            </SpotlightCard>
          </div>
        )}

        {activeTab === 'batches' && (
          <SpotlightCard style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 600 }}>Batch Assignment &amp; Visibility</h3>
                <p style={{ fontSize: '13px', color: 'var(--on-surface-variant)', margin: '4px 0 0 0' }}>
                  Search by Batch ID, filter by analyst, and manage batch visibility.
                </p>
              </div>

              {/* Search & Filter Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <span className="material-symbols-outlined" style={{ position: 'absolute', left: '10px', fontSize: '18px', color: 'var(--on-surface-variant)', pointerEvents: 'none' }}>
                    search
                  </span>
                  <input
                    type="text"
                    placeholder="Search batch ID..."
                    value={batchSearch}
                    onChange={(e) => setBatchSearch(e.target.value)}
                    style={{
                      padding: '6px 12px 6px 34px',
                      border: '1px solid var(--outline-variant)',
                      borderRadius: '6px',
                      background: 'var(--surface)',
                      color: 'inherit',
                      fontSize: '13px',
                      width: '200px'
                    }}
                  />
                  {batchSearch && (
                    <button
                      onClick={() => setBatchSearch('')}
                      style={{
                        position: 'absolute',
                        right: '8px',
                        background: 'none',
                        border: 'none',
                        color: 'var(--on-surface-variant)',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Analyst Filter */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <label style={{ fontSize: '13px', color: 'var(--on-surface-variant)', fontWeight: 500 }}>Analyst:</label>
                  <select
                    value={selectedAnalystFilter}
                    onChange={(e) => setSelectedAnalystFilter(e.target.value)}
                    style={{ padding: '6px 12px', border: '1px solid var(--outline-variant)', borderRadius: '6px', background: 'var(--surface)', color: 'inherit', fontSize: '13px' }}
                  >
                    <option value="all">All Batches ({batches.length})</option>
                    <option value="public">Org Public Batches</option>
                    <option value="unassigned">Unassigned (Private)</option>
                    {onlyAnalysts.map(a => (
                      <option key={a.id} value={a.id}>
                        {a.full_name} ({batches.filter(b => b.assigned_analyst_id === a.id).length})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                  <th style={{ padding: '12px 8px' }}>Batch ID</th>
                  <th style={{ padding: '12px 8px' }}>Uploaded At</th>
                  <th style={{ padding: '12px 8px' }}>Status</th>
                  <th style={{ padding: '12px 8px' }}>Visibility Mode</th>
                  <th style={{ padding: '12px 8px' }}>Assign to Analyst</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {displayedBatches.map(b => (
                  <tr key={b.batch_id} style={{ borderBottom: '1px solid var(--outline-variant)' }}>
                    <td style={{ padding: '12px 8px', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {b.batch_id.split('-')[0]}
                    </td>
                    <td style={{ padding: '12px 8px', color: 'var(--on-surface-variant)' }}>
                      {new Date(b.uploaded_at).toLocaleString()}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <span style={{
                        fontSize: '11px',
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontWeight: 650,
                        background: b.status === 'COMPLETE' ? '#e8f5e9' : 'var(--surface-container-high)',
                        color: b.status === 'COMPLETE' ? '#2e7d32' : 'inherit'
                      }}>
                        {b.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <select
                        value={b.is_org_public ? "public" : "private"}
                        onChange={(e) => handleAssignment(b.batch_id, b.assigned_analyst_id, e.target.value === 'public')}
                        style={{ padding: '6px 10px', border: '1px solid var(--outline-variant)', borderRadius: '6px', background: 'var(--surface)', color: 'inherit', fontSize: '13px' }}
                      >
                        <option value="public">Org Public (All Analysts)</option>
                        <option value="private">Assigned Analyst Only</option>
                      </select>
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <select
                        value={b.assigned_analyst_id || ""}
                        onChange={(e) => handleAssignment(b.batch_id, e.target.value, b.is_org_public)}
                        style={{
                          padding: '6px 10px',
                          border: '1px solid var(--outline-variant)',
                          borderRadius: '6px',
                          background: 'var(--surface)',
                          color: 'inherit',
                          fontSize: '13px',
                          minWidth: '170px'
                        }}
                      >
                        <option value="">-- No Analyst Assigned --</option>
                        {onlyAnalysts.map(a => (
                          <option key={a.id} value={a.id}>{a.full_name}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                      <Link
                        to="/workspace"
                        style={{
                          fontSize: '12px',
                          color: 'var(--primary)',
                          textDecoration: 'none',
                          fontWeight: 600,
                          padding: '6px 10px',
                          borderRadius: '4px',
                          background: 'var(--surface-container-high)'
                        }}
                      >
                        Open Batch
                      </Link>
                    </td>
                  </tr>
                ))}
                {displayedBatches.length === 0 && (
                  <tr>
                    <td colSpan="6" style={{ padding: '32px', textAlign: 'center', color: 'var(--on-surface-variant)' }}>
                      No batches match the selected filter.
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
