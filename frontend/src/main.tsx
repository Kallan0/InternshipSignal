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
type Metrics = { total_applications: number; needs_review: number; by_status: Record<string, number> };

const statuses = ["APPLICATION_RECEIVED", "UNDER_REVIEW", "ASSESSMENT", "INTERVIEW", "NEXT_ROUND", "OFFER", "REJECTED", "ACTION_REQUIRED", "UNKNOWN"];

function label(value: string) { return value.replaceAll("_", " ").toLowerCase(); }

function App() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [metrics, setMetrics] = useState<Metrics>({ total_applications: 0, needs_review: 0, by_status: {} });
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewIndex, setReviewIndex] = useState(0);

  async function refresh() {
    const [apps, queue, stats] = await Promise.all([
      fetch(`${API}/applications`).then(r => r.json()),
      fetch(`${API}/review-queue`).then(r => r.json()),
      fetch(`${API}/metrics`).then(r => r.json()),
    ]);
    setApplications(apps); setReviews(queue); setMetrics(stats);
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

  async function removeEmail(item: ReviewItem) {
    if (!window.confirm(`Remove "${item.subject || "this email"}" from the tracker? It will not be imported again.`)) return;
    setBusy(true);
    try {
      const response = await fetch(`${API}/emails/${item.email_id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`Remove failed (${response.status})`);
      await refresh();
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

  return <main className="site-shell">
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
              <button className="remove-email" type="button" disabled={busy} onClick={() => removeEmail(currentReview)}>Remove from tracker</button>
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
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
