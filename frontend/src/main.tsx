import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = import.meta.env.VITE_API_URL ?? `${window.location.protocol}//${window.location.hostname}:8000/api`;

type Application = {
  id: number; company: string; role: string; location: string | null;
  current_status: string; latest_update_at: string;
};
type ReviewItem = {
  email_id: number; subject: string; sender: string; status: string;
  received_at: string; confidence: number; evidence: string[];
};
type AcceptedItem = {
  email_id: number; subject: string; sender: string; status: string; received_at: string;
  accepted_at: string; application_id: number | null; company: string | null; role: string | null;
};
type Metrics = {
  total_applications: number; needs_review: number; by_status: Record<string, number>;
  accepted_by_status: Record<string, number>; human_reviewed: number; human_agreement_rate: number; human_corrections: number;
};

const statuses = ["APPLICATION_RECEIVED", "UNDER_REVIEW", "ASSESSMENT", "INTERVIEW", "NEXT_ROUND", "OFFER", "REJECTED", "ACTION_REQUIRED", "UNKNOWN"];

function label(value: string) { return value.replaceAll("_", " ").toLowerCase(); }

function App() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [accepted, setAccepted] = useState<AcceptedItem[]>([]);
  const [metrics, setMetrics] = useState<Metrics>({ total_applications: 0, needs_review: 0, by_status: {}, accepted_by_status: {}, human_reviewed: 0, human_agreement_rate: 0, human_corrections: 0 });
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [pendingRemoval, setPendingRemoval] = useState<ReviewItem | null>(null);
  const [removalError, setRemovalError] = useState("");

  async function refresh() {
    const [apps, queue, acceptedItems, stats] = await Promise.all([
      fetch(`${API}/applications`).then(r => r.json()),
      fetch(`${API}/review-queue`).then(r => r.json()),
      fetch(`${API}/accepted-emails`).then(r => r.json()),
      fetch(`${API}/metrics`).then(r => r.json()),
    ]);
    setApplications(apps); setReviews(queue); setAccepted(acceptedItems); setMetrics(stats);
  }
  useEffect(() => { refresh().catch(console.error); }, []);

  const visible = useMemo(() => applications.filter(item =>
    `${item.company} ${item.role}`.toLowerCase().includes(query.toLowerCase()) &&
    (!stateFilter || item.current_status === stateFilter) &&
    (!dateFilter || item.latest_update_at.slice(0, 10) >= dateFilter)
  ), [applications, query, stateFilter, dateFilter]);

  const visibleReviews = useMemo(() => reviews.filter(item =>
    (!stateFilter || item.status === stateFilter) &&
    (!dateFilter || item.received_at.slice(0, 10) >= dateFilter)
  ), [reviews, stateFilter, dateFilter]);

  useEffect(() => {
    setReviewIndex(index => Math.min(index, Math.max(visibleReviews.length - 1, 0)));
  }, [visibleReviews.length]);

  const currentReview = visibleReviews[reviewIndex];

  async function correct(emailId: number, status: string) {
    setBusy(true);
    try {
      await fetch(`${API}/emails/${emailId}/correction`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ status })
      });
      await refresh();
    } finally { setBusy(false); }
  }

  function requestRemoval(item: ReviewItem) {
    setRemovalError("");
    setPendingRemoval(item);
  }

  async function removeEmail() {
    if (!pendingRemoval) return;
    setBusy(true);
    setRemovalError("");
    try {
      const response = await fetch(`${API}/emails/${pendingRemoval.email_id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`Remove failed (${response.status})`);
      await refresh();
      setPendingRemoval(null);
    } catch {
      setRemovalError("The email could not be removed. Please try again.");
    } finally { setBusy(false); }
  }

  async function acceptEmail(item: ReviewItem) {
    setBusy(true);
    try {
      const response = await fetch(`${API}/emails/${item.email_id}/accept`, { method: "POST" });
      if (!response.ok) throw new Error(`Accept failed (${response.status})`);
      await refresh();
    } finally { setBusy(false); }
  }

  return <>
    <main className="site-shell">
    <header className="topbar">
      <div className="wordmark">internship<br /><span>signal</span></div>
      <nav aria-label="Dashboard sections"><span>Pipeline</span><span>Review desk</span><span>Insights</span></nav>
      <button className="refresh" onClick={() => refresh()} disabled={busy}>{busy ? "Updating..." : "Refresh data"}</button>
    </header>

    <section className="hero">
      <div className="hero-copy">
        <p className="eyebrow">YOUR APPLICATION UNIVERSE</p>
        <h1>Make every<br /><em>signal</em> count.</h1>
        <p className="hero-text">A considered home for every application update, with room for your judgment where it matters.</p>
      </div>
      <div className="hero-art" aria-hidden="true">
        <span className="hero-orb hero-orb--large"></span><span className="hero-orb hero-orb--small"></span>
        <span className="hero-stamp">LIVE<br />PIPELINE</span><span className="hero-arrow">↘</span>
      </div>
    </section>

    <section className="metrics" aria-label="Application summary">
      <article><strong>{metrics.total_applications}</strong><span>tracked applications</span></article>
      <article><strong>{metrics.needs_review}</strong><span>waiting for you</span></article>
      <article><strong>{metrics.by_status.INTERVIEW ?? 0}</strong><span>interviews ahead</span></article>
      <article><strong>{metrics.by_status.OFFER ?? 0}</strong><span>offers received</span></article>
    </section>

    <section className="insights" aria-label="Pipeline insights">
      <div className="insights-head"><div><p className="eyebrow">AT A GLANCE</p><h2>Pipeline by status</h2></div>
        <p>{metrics.human_reviewed ? `${Math.round(metrics.human_agreement_rate * 100)}% of your reviewed decisions agreed with the model` : "Review decisions will measure model agreement."}</p>
      </div>
      <div className="insight-charts">
        <div><p className="chart-title">All tracked applications</p><div className="status-chart" role="img" aria-label="Application count by status">
          {statuses.filter(status => (metrics.by_status[status] ?? 0) > 0).map(status => {
            const count = metrics.by_status[status] ?? 0;
            const max = Math.max(...Object.values(metrics.by_status), 1);
            return <div className="chart-row" key={status}><span>{label(status)}</span><div className="chart-track"><i className={`chart-${status.toLowerCase()}`} style={{ width: `${(count / max) * 100}%` }} /></div><strong>{count}</strong></div>;
          })}
          {!Object.keys(metrics.by_status).length && <p className="chart-empty">Your status distribution will appear after the first email is processed.</p>}
        </div></div>
        <div className="accepted-chart"><p className="chart-title">Accepted activity</p><div className="status-chart" role="img" aria-label="Accepted email count by confirmed status">
          {statuses.filter(status => (metrics.accepted_by_status[status] ?? 0) > 0).map(status => {
            const count = metrics.accepted_by_status[status] ?? 0;
            const max = Math.max(...Object.values(metrics.accepted_by_status), 1);
            return <div className="chart-row" key={status}><span>{label(status)}</span><div className="chart-track"><i className={`chart-${status.toLowerCase()}`} style={{ width: `${(count / max) * 100}%` }} /></div><strong>{count}</strong></div>;
          })}
          {!Object.keys(metrics.accepted_by_status).length && <p className="chart-empty">Accept a Review Desk decision to build this chart.</p>}
        </div></div>
      </div>
    </section>

    <section className="filters" aria-label="Dashboard filters">
      <p className="filter-title">Find your flow</p>
      <label className="filter-field"><span>Application state</span>
        <select value={stateFilter} onChange={event => setStateFilter(event.target.value)}>
          <option value="">All states</option>
          {statuses.map(status => <option key={status} value={status}>{label(status)}</option>)}
        </select>
      </label>
      <label className="filter-field"><span>On or after</span>
        <input type="date" value={dateFilter} onChange={event => setDateFilter(event.target.value)} />
      </label>
      <button className="clear-filters" type="button" onClick={() => { setStateFilter(""); setDateFilter(""); }}>Clear filters</button>
    </section>

    <section className="workspace">
      <div className="panel applications">
        <div className="panel-head"><div><p className="eyebrow">APPLICATIONS</p><h2>Your pipeline</h2></div>
          <input aria-label="Search applications" placeholder="Search company or role" value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        {visible.length === 0 ? <div className="empty"><h3>No signals yet</h3><p>Import a sample email or connect Gmail to start the pipeline.</p></div> :
          <div className="app-list">{visible.map(item => <article className="app-card" key={item.id}>
            <div className="monogram">{item.company.slice(0, 2).toUpperCase()}</div>
            <div><h3>{item.company}</h3><p>{item.role}</p></div>
            <span className={`status ${item.current_status.toLowerCase()}`}>{label(item.current_status)}</span>
            <time>{new Date(item.latest_update_at).toLocaleDateString()}</time>
          </article>)}</div>}
      </div>

      <aside className="panel review">
        <div className="panel-head"><div><p className="eyebrow">YOUR CALL</p><h2>Review desk</h2></div><span className="queue-count">{visibleReviews.length}</span></div>
        {!currentReview ? <div className="empty compact"><h3>No matching reviews</h3><p>Clear the filters or wait for ambiguous predictions.</p></div> : <>
          <article className="review-card" key={currentReview.email_id}>
            <p className="confidence">{Math.round(currentReview.confidence * 100)}% confidence</p>
            <h3>{currentReview.subject || "No subject"}</h3><p>{currentReview.sender}</p>
            <time>{new Date(currentReview.received_at).toLocaleDateString()}</time>
            <small>{currentReview.evidence.join(" · ")}</small>
            <div className="review-actions">
              <select aria-label="Correct status" defaultValue={currentReview.status} disabled={busy} onChange={e => correct(currentReview.email_id, e.target.value)}>
                {statuses.map(status => <option key={status} value={status}>{label(status)}</option>)}
              </select>
              <button className="accept-email" type="button" disabled={busy} onClick={() => acceptEmail(currentReview)}>Accept</button>
              <button className="remove-email" type="button" disabled={busy} onClick={() => requestRemoval(currentReview)}>Remove from tracker</button>
            </div>
          </article>
          <nav className="review-navigation" aria-label="Review item navigation">
            <button type="button" onClick={() => setReviewIndex(index => Math.max(0, index - 1))} disabled={busy || reviewIndex === 0}>← Previous</button>
            <span>{reviewIndex + 1} / {visibleReviews.length}</span>
            <button type="button" onClick={() => setReviewIndex(index => Math.min(visibleReviews.length - 1, index + 1))} disabled={busy || reviewIndex === visibleReviews.length - 1}>Next →</button>
          </nav>
        </>}
      </aside>
    </section>

    <section className="panel accepted-panel" aria-label="Accepted email history">
      <div className="panel-head"><div><p className="eyebrow">DECISIONS KEPT</p><h2>Accepted activity</h2></div><span className="accepted-note">Accepted emails stay here after leaving Review Desk</span></div>
      {!accepted.length ? <div className="empty compact"><h3>No accepted emails yet</h3><p>Use Accept in Review Desk to confirm a prediction and keep its record here.</p></div> :
        <div className="accepted-list">{accepted.map(item => <article className="accepted-card" key={item.email_id}>
          <div><p className="accepted-status">{label(item.status)}</p><h3>{item.subject || "No subject"}</h3><p>{item.company ? `${item.company} · ${item.role}` : item.sender}</p></div>
          <time>Accepted {new Date(item.accepted_at).toLocaleDateString()}</time>
        </article>)}</div>}
    </section>
    </main>
    {pendingRemoval && <div className="confirmation-backdrop" role="presentation" onMouseDown={() => !busy && setPendingRemoval(null)}>
      <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="remove-dialog-title" onMouseDown={event => event.stopPropagation()}>
        <p className="eyebrow">REMOVE FROM TRACKER</p>
        <h2 id="remove-dialog-title">Remove this email?</h2>
        <p><strong>{pendingRemoval.subject || "This email"}</strong> will be removed from the dashboard and ignored in future Gmail syncs.</p>
        <p className="confirmation-note">This does not delete the email from Gmail. Future emails from this exact sender will be ignored.</p>
        {removalError && <p className="confirmation-error" role="alert">{removalError}</p>}
        <div className="confirmation-actions">
          <button type="button" className="cancel-removal" disabled={busy} onClick={() => setPendingRemoval(null)}>Keep email</button>
          <button type="button" className="confirm-removal" disabled={busy} onClick={removeEmail}>{busy ? "Removing..." : "Remove from tracker"}</button>
        </div>
      </section>
    </div>}
  </>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
