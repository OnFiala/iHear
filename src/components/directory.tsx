"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, Plus, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { api, dateLabel } from "@/lib/client/api";
import { difficulties, type Patient } from "@/lib/types";
import { Header, Footer, ErrorBox, Loading, Status } from "./shared";

const pageSize = 25;

export function ClinicDirectory() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [version, setVersion] = useState(0);
  const filterCount = [status, difficulty, followUp].filter(Boolean).length;
  const hasQuery = Boolean(q.trim() || filterCount);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        await api("/api/session");
        const result = await api<{ patients: Patient[] }>(
          `/api/patients?${new URLSearchParams({ q, status, difficulty, followUp })}`,
        );
        if (active) {
          setPatients(result.patients);
          setError("");
          setHasLoaded(true);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setLoading(false);
      }
    }, q ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [q, status, difficulty, followUp, version]);
  useEffect(() => {
    const id = setInterval(() => setVersion((v) => v + 1), 8000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => { setPage(1); }, [q, status, difficulty, followUp, sort]);

  const ordered = [...patients].sort((a, b) => {
    const byName = a.displayName.localeCompare(b.displayName, "en", { sensitivity: "base" });
    if (sort === "followUp") return a.followUpDate.localeCompare(b.followUpDate) || byName;
    if (sort === "moments") return (b.eventCount || 0) - (a.eventCount || 0) || byName;
    return byName || a.id.localeCompare(b.id);
  });
  const pageCount = Math.max(1, Math.ceil(ordered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visible = ordered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  function clearFilters() {
    setQ(""); setStatus(""); setDifficulty(""); setFollowUp("");
  }

  return (
    <>
      <Header clinic />
      <main tabIndex={-1} id="main" className="clinic-main clinic-directory page-width">
        <div className="page-title-row clinic-directory-header">
          <h1>Patients</h1>
          <Link href="/clinic/patients/new" className="button small"><Plus size={18} />New patient</Link>
        </div>

        <section className="directory-search" aria-label="Find a patient">
          <div className="directory-toolbar">
            <label className="search-box">
              <span>Search patient records</span>
              <span className="search-input">
                <Search size={20} aria-hidden />
                <input type="search" placeholder="Name, note or listening moment…" aria-label="Search patients and event content" aria-describedby="search-scope" maxLength={200} value={q} onChange={(e) => setQ(e.target.value)} />
              </span>
            </label>
            <button className={`button secondary directory-filter-toggle${filterCount ? " active" : ""}`} aria-expanded={filtersOpen} aria-controls="directory-filters" onClick={() => setFiltersOpen(!filtersOpen)}>
              <SlidersHorizontal size={17} />Filters{filterCount > 0 && <span className="filter-count">{filterCount}</span>}
            </button>
          </div>
          <div className="directory-search-meta">
            <p id="search-scope">Search across names, notes and listening moments.</p>
            {hasQuery && <button className="text-button" onClick={clearFilters}><X size={15} />Clear search & filters</button>}
          </div>
          {filtersOpen && <div className="filter-row" id="directory-filters">
            <label><span>Result status</span><select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any result</option><option value="ready">Analysed</option><option value="queued">Queued</option><option value="analysing">Analysing</option><option value="failed">Failed</option>
            </select></label>
            <label><span>Reported difficulty</span><select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="">Any difficulty</option>{difficulties.map((d) => <option key={d}>{d}</option>)}
            </select></label>
            <label className="date-filter"><span>Follow-up date</span><input type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} /></label>
          </div>}
        </section>

        {error && <div className="directory-error"><ErrorBox message={error} /><button className="button secondary small" disabled={loading} onClick={() => setVersion((v) => v + 1)}><RefreshCw size={16} />{loading ? "Trying again…" : "Try again"}</button></div>}
        <div className="list-heading clinic-list-heading">
          <div className="directory-result-summary">
            <strong>{hasLoaded ? `${patients.length} ${patients.length === 1 ? "patient" : "patients"}${hasQuery ? " found" : ""}` : "Patient list"}</strong>
            <span className="directory-live-state" aria-live="polite">{error ? (hasLoaded ? "Showing last loaded results" : "Couldn’t load patients") : loading ? "Updating…" : "Updates automatically"}</span>
          </div>
          <label className="directory-sort"><span>Sort by</span><select value={sort} onChange={(e) => setSort(e.target.value)}><option value="name">Name A–Z</option><option value="followUp">Follow-up date</option><option value="moments">Most moments</option></select></label>
        </div>

        {loading && (!hasLoaded || patients.length === 0) ? <Loading label="Loading patients…" /> : error && patients.length === 0 ? null : patients.length === 0 ? (
          <section className="empty-state compact clinic-empty-state">
            <Search size={25} aria-hidden />
            <h2>{hasQuery ? "No matching patients" : "No patients yet"}</h2>
            <p>{hasQuery ? "Try a name, a word from a note or a listening situation. You can type just the start of a word." : "Create a synthetic patient profile to begin."}</p>
            {hasQuery ? <button className="button secondary" onClick={clearFilters}>Clear search & filters</button> : <Link className="button" href="/clinic/patients/new"><Plus size={18} />New patient</Link>}
          </section>
        ) : (
          <div className="patient-grid clinic-patient-list" aria-busy={loading}>
            <div className="clinic-patient-columns" aria-hidden="true"><span>Patient</span><span>Follow-up</span><span>Moments</span><span>Latest result</span><span /></div>
            {visible.map((p) => (
              <Link className="patient-card clinic-patient-row" href={`/clinic/patients/${p.id}`} key={p.id}>
                <span className="clinic-patient-identity">
                  <span className="avatar sage" aria-hidden>{p.displayName.trim().split(/\s+/).map((n) => n[0]).slice(0, 2).join("")}</span>
                  <span className="clinic-patient-name"><strong>{p.displayName}</strong><small>{p.aids.side === "bilateral" ? "Both ears" : p.aids.side === "left" ? "Left ear" : "Right ear"}{p.note && <span className="directory-note"> · {p.note}</span>}</small></span>
                </span>
                <span className="clinic-patient-followup"><CalendarDays size={14} aria-hidden /><span>{dateLabel(p.followUpDate)}</span></span>
                <span className="clinic-patient-count">{p.eventCount || 0}<span className="mobile-field-label">{p.eventCount === 1 ? "moment" : "moments"}</span></span>
                <span className="clinic-patient-status">{p.latestStatus ? <Status value={p.latestStatus} /> : <span className="caption">No moments</span>}</span>
                <ArrowRight className="clinic-patient-arrow" size={17} aria-hidden />
              </Link>
            ))}
          </div>
        )}
        {pageCount > 1 && <nav className="directory-pagination" aria-label="Patient list pages"><span>{(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, patients.length)} of {patients.length}</span><div><button className="button secondary small" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17} />Previous</button><button className="button secondary small" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>Next<ChevronRight size={17} /></button></div></nav>}
        <p className="directory-demo-note">Illustrative demo · Use synthetic patient information only.</p>
      </main>
      <Footer />
    </>
  );
}
