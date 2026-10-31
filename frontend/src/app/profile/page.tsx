"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { NEW_TAG, TagList, TagSheet, tagToDraft } from "@/components/TagManager";
import { PlusIcon } from "@/components/icons";
import { api } from "@/lib/api";
import type {
  Country,
  CustomTag,
  CustomTagDraft,
  Profile,
  SourceInfo,
} from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function ProfilePage() {
  const { email, loading: authLoading } = useAuth();
  const [tags, setTags] = useState<CustomTag[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [sourceWeights, setSourceWeights] = useState<Record<string, number>>({});
  const [collectorKeywords, setCollectorKeywords] = useState<string[]>([]);
  const [keywordDraft, setKeywordDraft] = useState("");
  const [sourceSearch, setSourceSearch] = useState("");
  const [collectorSave, setCollectorSave] = useState<"saved" | "saving" | "error">("saved");
  const [collectorReady, setCollectorReady] = useState(false);
  const [worker, setWorker] = useState<Awaited<ReturnType<typeof api.workerStatus>> | null>(null);
  const [workerBusy, setWorkerBusy] = useState(false);
  const [collectorError, setCollectorError] = useState<string | null>(null);
  const [clearingSignals, setClearingSignals] = useState(false);
  const [clearSignalsMessage, setClearSignalsMessage] = useState<string | null>(null);
  const [clearSignalsError, setClearSignalsError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CustomTag | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CustomTagDraft>(NEW_TAG);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!email) return;
    void (async () => {
      try {
        setTags(await api.customTags());
        const [c, s, p] = await Promise.all([
          api.countries(undefined, true),
          api.sources(),
          api.profile(),
        ]);
        setCountries(c);
        setSources(s);
        setProfile(p);
        setSourceWeights(Object.fromEntries(s.map((item) => [item.id, p.collector_source_weights?.[item.id] ?? 5])));
        setCollectorKeywords(p.collector_keywords ?? []);
        setCollectorReady(true);
        void api.workerStatus().then(setWorker).catch(() => setWorker(null));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load tags");
      }
    })();
  }, [email]);

  useEffect(() => {
    if (!email) return;
    let active = true;
    const poll = async () => {
      try {
        const status = await api.workerStatus();
        if (active) setWorker(status);
      } catch {
        if (active) setWorker(null);
      }
    };
    const timer = window.setInterval(() => void poll(), 15_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [email]);

  useEffect(() => {
    if (!collectorReady) return;
    const timer = window.setTimeout(async () => {
      setCollectorSave("saving");
      setCollectorError(null);
      try {
        const updated = await api.updateProfile({
          collector_source_weights: sourceWeights,
          collector_keywords: collectorKeywords,
        });
        setProfile(updated);
        setCollectorSave("saved");
      } catch (err) {
        setCollectorSave("error");
        setCollectorError(err instanceof Error ? err.message : "Could not save collector settings");
      }
    }, 600);
    return () => window.clearTimeout(timer);
  }, [collectorReady, sourceWeights, collectorKeywords]);

  async function toggleCollector() {
    setWorkerBusy(true);
    setCollectorError(null);
    try {
      if (!worker?.running) {
        await api.startWorker();
        window.setTimeout(() => void api.workerStatus().then(setWorker).catch(() => setWorker(null)), 1500);
      } else if (worker.paused) {
        await api.resumeWorker();
        setWorker({ ...worker, paused: false });
      } else {
        await api.pauseWorker();
        setWorker({ ...worker, paused: true });
      }
    } catch (err) {
      setCollectorError(err instanceof Error ? err.message : "Could not change collector state");
    } finally {
      setWorkerBusy(false);
    }
  }

  async function clearCollectedSignals() {
    const confirmed = window.confirm(
      "Permanently delete every collected signal, its history, saved/muted state, notification deliveries, and raw source records? Your collector settings, tags, and radars will stay. A fresh full collection pass will be queued. This cannot be undone.",
    );
    if (!confirmed) return;

    setClearingSignals(true);
    setClearSignalsError(null);
    setClearSignalsMessage(null);
    try {
      const result = await api.clearAllSignals();
      setClearSignalsMessage(
        `Cleared ${result.deleted_signals.toLocaleString()} signals and ${result.deleted_source_events.toLocaleString()} source records. A fresh collection pass is queued.`,
      );
      void api.workerStatus().then(setWorker).catch(() => setWorker(null));
    } catch (err) {
      setClearSignalsError(
        err instanceof Error ? err.message : "Could not clear collected signals",
      );
    } finally {
      setClearingSignals(false);
    }
  }

  function applyPreset(preset: "balanced" | "social" | "x") {
    setSourceWeights(Object.fromEntries(sources.map((source) => {
      const isSocial = source.type === "SOCIAL" || source.type === "COMMUNITY";
      const isX = source.id.toLowerCase().includes("x_") || source.id.toLowerCase() === "x";
      const value = preset === "balanced" ? 5 : preset === "social" ? (isSocial ? 10 : 0) : (isX ? 10 : 0);
      return [source.id, value];
    })));
  }

  function addCollectorKeyword() {
    const value = keywordDraft.trim();
    if (!value || collectorKeywords.some((item) => item.toLowerCase() === value.toLowerCase())) return;
    if (collectorKeywords.length >= 30) {
      setCollectorError("You can add up to 30 search phrases.");
      return;
    }
    setCollectorKeywords([...collectorKeywords, value]);
    setKeywordDraft("");
  }

  function startCreate() {
    setEditing(null);
    setDraft(NEW_TAG);
    setOpen(true);
  }

  function startEdit(tag: CustomTag) {
    setEditing(tag);
    setDraft(tagToDraft(tag));
    setOpen(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await api.updateCustomTag(editing.id, draft);
      } else {
        await api.createCustomTag(draft);
      }
      setTags(await api.customTags());
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save tag");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this custom tag?")) return;
    try {
      await api.deleteCustomTag(id);
      setTags(await api.customTags());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete tag");
    }
  }

  if (authLoading) return <p className="muted">Loading…</p>;

  if (!email) {
    return (
      <div className="empty" role="status" aria-live="polite">
        <div className="empty-title">Cannot reach the local API</div>
        <p className="empty-text">
          Custom tags, radars and notifications live in your local database.
          Start the collector with <code className="mono">docker compose up</code>{" "}
          and reload.
        </p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="section-title">
        Collector control
        <div className="spacer" />
        <span className={`collector-state ${worker?.running && !worker.paused ? "is-running" : ""}`}>
          <span className="statusbar-dot" />
          {!worker ? "Checking…" : !worker.running ? "Offline" : worker.paused ? "Paused" : worker.collection_state === "idle" ? "Collector active · scheduled" : "Collecting now"}
        </span>
      </div>

      <section className="panel collector-panel" aria-label="Collector settings">
        <div className="collector-head">
          <div>
            <h2 className="panel-title">Choose where the collector spends its time</h2>
            <p className="muted text-sm">0 turns a source off. 5 uses its normal check interval; 10 checks about twice as often, while 1 checks about five times less often. Some sources update every few minutes; slower sources and rate limits are respected.</p>
          </div>
          <button className={`btn ${worker?.running && !worker.paused ? "btn-ghost" : "btn-primary"}`} disabled={workerBusy} onClick={() => void toggleCollector()} type="button">
            {workerBusy ? "Updating…" : !worker?.running ? "Start collector" : worker.paused ? "Resume collection" : "Pause collection"}
          </button>
        </div>
        {worker?.running && worker.last_collection_completed_at && (
          <p className="collector-last-run">Collector heartbeat {worker.heartbeat_age_seconds != null ? `${Math.round(worker.heartbeat_age_seconds)}s ago` : "active"} · next source check {worker.next_source_check_at ? `around ${new Date(worker.next_source_check_at).toLocaleTimeString()}` : "when available"} · last cycle {new Date(worker.last_collection_completed_at).toLocaleTimeString()}, {worker.last_collection_result?.signals_created ?? 0} new signals</p>
        )}
        {worker && !worker.running && <p className="collector-hint">The API is available, but the background collector is offline. Start it here and keep the app open.</p>}

        <div className="collector-presets" aria-label="Collection presets">
          <span className="field-label">Quick setup</span>
          <button className="chip" onClick={() => applyPreset("balanced")} type="button">Balanced</button>
          <button className="chip" onClick={() => applyPreset("social")} type="button">Social networks</button>
          <button className="chip" onClick={() => applyPreset("x")} type="button">Only X</button>
        </div>

        <div className="field collector-keywords">
          <label className="field-label" htmlFor="collector-keyword">Focus phrases</label>
          <p className="muted text-sm">When set, only matching posts are saved as signals. Leave empty to collect broadly.</p>
          <div className="collector-keyword-entry">
            <input id="collector-keyword" value={keywordDraft} maxLength={80} placeholder="e.g. battery breakthrough" onChange={(event) => setKeywordDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addCollectorKeyword(); } }} />
            <button className="btn btn-sm" onClick={addCollectorKeyword} type="button">Add phrase</button>
          </div>
          {collectorKeywords.length > 0 && <div className="collector-keyword-list">{collectorKeywords.map((term) => <button key={term} className="chip" aria-label={`Remove ${term}`} onClick={() => setCollectorKeywords(collectorKeywords.filter((item) => item !== term))} type="button">{term}<span aria-hidden="true"> ×</span></button>)}</div>}
        </div>

        <div className="collector-source-toolbar">
          <div><span className="field-label">Sources</span><span className="muted text-sm"> {Object.values(sourceWeights).filter((weight) => weight > 0).length} enabled</span></div>
          <input className="collector-source-search" aria-label="Find a source" value={sourceSearch} placeholder="Find source" onChange={(event) => setSourceSearch(event.target.value)} />
        </div>
        <div className="collector-source-list">
          {sources.filter((source) => source.name.toLowerCase().includes(sourceSearch.toLowerCase()) || source.id.toLowerCase().includes(sourceSearch.toLowerCase())).map((source) => {
            const weight = sourceWeights[source.id] ?? 5;
            return <div className="collector-source-row" key={source.id} data-disabled={weight === 0}>
              <div className="collector-source-name"><strong>{source.name}</strong><span className="muted">{source.status === "OFFLINE" ? "Needs access" : source.type.toLowerCase()}</span></div>
              <input aria-label={`${source.name} collection priority`} type="range" min={0} max={10} step={1} value={weight} onChange={(event) => setSourceWeights({ ...sourceWeights, [source.id]: Number(event.target.value) })} />
              <output>{weight === 0 ? "Off" : weight}</output>
            </div>;
          })}
          {sources.length > 0 && !sources.some((source) => source.name.toLowerCase().includes(sourceSearch.toLowerCase()) || source.id.toLowerCase().includes(sourceSearch.toLowerCase())) && <p className="muted text-sm">No sources match that search.</p>}
        </div>
        <div className="collector-footer">
          <span className="muted text-sm" role="status" aria-live="polite">{collectorSave === "saving" ? "Saving settings…" : collectorSave === "error" ? "Could not save" : "Settings saved"}</span>
          {collectorError && <span className="statusbar-error" role="alert">{collectorError}</span>}
          {worker?.last_collection_error && <span className="statusbar-error">Last cycle issue: {worker.last_collection_error}</span>}
        </div>
      </section>

      <section className="panel" aria-label="Reset collected signal data">
        <div className="collector-head">
          <div>
            <h2 className="panel-title">Reset collected data</h2>
            <p className="muted text-sm">
              Clear all signals, their histories and the source records used for duplicate detection. Your tags, radars and collector settings stay. The collector will make a fresh full pass.
            </p>
          </div>
          <button
            className="btn btn-sm btn-danger"
            disabled={clearingSignals}
            onClick={() => void clearCollectedSignals()}
            type="button"
          >
            {clearingSignals ? "Clearing…" : "Delete all collected signals"}
          </button>
        </div>
        {clearSignalsMessage && <p className="text-sm" role="status" aria-live="polite">{clearSignalsMessage}</p>}
        {clearSignalsError && <p className="text-sm statusbar-error" role="alert" aria-live="assertive">{clearSignalsError}</p>}
      </section>

      <div className="section-title">
        Custom tags
        <div className="spacer" />
        <button className="btn btn-sm btn-primary" onClick={startCreate} type="button">
          <PlusIcon size={13} /> New tag
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert" aria-live="assertive">{error}</div>}

      <TagList tags={tags} onEdit={startEdit} onDelete={remove} />

      {open && (
        <TagSheet
          draft={draft}
          onChange={setDraft}
          onClose={() => setOpen(false)}
          onSave={save}
          countries={countries}
          sources={sources}
          saving={saving}
        />
      )}

      <div className="section-title">Account</div>
      <div className="panel">
        <div className="row">
          <span className="muted text-sm">Signed in as</span>
          <strong>{email}</strong>
        </div>
        <div className="row" style={{ marginTop: "var(--s3)" }}>
          <Link className="btn" href="/settings">
            Notification &amp; theme settings
          </Link>
          <Link className="btn btn-ghost" href="/radars">
            My radars
          </Link>
        </div>
      </div>
    </>
  );
}
