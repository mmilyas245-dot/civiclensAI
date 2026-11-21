"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  Clock3,
  ImageOff,
  Inbox,
  LogOut,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import {
  AdminReport,
  AdminStatus,
  STATUSES,
  adminFetch,
  clearToken,
  formatId,
  fullDate,
  getToken,
  shortAddress,
  timeAgo,
} from "../lib";

type Folder = "All" | AdminStatus;

const severityDot: Record<string, string> = {
  Low: "bg-emerald-400",
  Medium: "bg-amber-400",
  High: "bg-orange-400",
  Critical: "bg-red-500",
};

const severityBadge: Record<string, string> = {
  Low: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
  Medium: "border-amber-400/20 bg-amber-400/10 text-amber-300",
  High: "border-orange-400/20 bg-orange-400/10 text-orange-300",
  Critical: "border-red-400/20 bg-red-400/10 text-red-300",
};

const statusBadge: Record<AdminStatus, string> = {
  Pending: "bg-amber-400/10 text-amber-300",
  "In Progress": "bg-fuchsia-400/10 text-fuchsia-300",
  Resolved: "bg-emerald-400/10 text-emerald-300",
};

const statusButton: Record<AdminStatus, string> = {
  Pending: "border-amber-400/40 bg-amber-400/15 text-amber-200",
  "In Progress": "border-fuchsia-400/40 bg-fuchsia-400/15 text-fuchsia-200",
  Resolved: "border-emerald-400/40 bg-emerald-400/15 text-emerald-200",
};

function StatusIcon({ status }: { status: Folder }) {
  if (status === "Pending") return <Clock3 className="h-4 w-4" />;
  if (status === "In Progress") return <CircleDot className="h-4 w-4" />;
  if (status === "Resolved") return <CheckCircle2 className="h-4 w-4" />;
  return <Inbox className="h-4 w-4" />;
}

export default function AdminDashboard() {
  const router = useRouter();

  const [reports, setReports] = useState<AdminReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");

  const [folder, setFolder] = useState<Folder>("All");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [severity, setSeverity] = useState("All");
  const [sort, setSort] = useState<"newest" | "priority">("newest");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const logout = useCallback(() => {
    clearToken();
    router.replace("/admin");
  }, [router]);

  // Fetch every report from the backend. The server decides whether the
  // saved token is valid; a 401 sends the user back to the login page.
  const loadReports = useCallback(async () => {
    try {
      const res = await adminFetch("/admin/reports");

      if (res.status === 401 || res.status === 503) {
        logout();
        return;
      }

      const data = await res.json();

      if (!res.ok || !data?.success) {
        setError(data?.error || "Could not load reports.");
        return;
      }

      setReports(data.reports);
      setError(null);
    } catch {
      setError("Could not reach the CivicLens server.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [logout]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/admin");
      return;
    }

    adminFetch("/admin/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.success) {
          logout();
          return;
        }
        setUsername(data.username);
        loadReports();
      })
      .catch(() => {
        setError("Could not reach the CivicLens server.");
        setLoading(false);
      });

    // New reports show up on their own, like new mail.
    const timer = setInterval(loadReports, 30000);
    return () => clearInterval(timer);
  }, [router, logout, loadReports]);

  const counts = useMemo(() => {
    const result: Record<Folder, number> = {
      All: reports.length,
      Pending: 0,
      "In Progress": 0,
      Resolved: 0,
    };
    reports.forEach((r) => {
      if (r.status in result) result[r.status] += 1;
    });
    return result;
  }, [reports]);

  const categories = useMemo(
    () => Array.from(new Set(reports.map((r) => r.category))).sort(),
    [reports]
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/^#/, "");

    const list = reports.filter((r) => {
      if (folder !== "All" && r.status !== folder) return false;
      if (category !== "All" && r.category !== category) return false;
      if (severity !== "All" && r.severity !== severity) return false;
      if (!q) return true;

      const haystack = [
        formatId(r.report_id),
        String(r.report_id),
        r.problem,
        r.category,
        r.status,
        r.severity,
        r.address || "",
        r.responsible_department,
        r.description,
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(q);
    });

    return list.sort((a, b) =>
      sort === "priority"
        ? b.priority_score - a.priority_score ||
          b.created_at.localeCompare(a.created_at)
        : b.created_at.localeCompare(a.created_at)
    );
  }, [reports, folder, category, severity, query, sort]);

  const selected = reports.find((r) => r.report_id === selectedId) || null;

  const changeStatus = async (
    report: AdminReport,
    status: AdminStatus,
    note: string
  ): Promise<string | null> => {
    try {
      const res = await adminFetch(
        `/admin/reports/${report.report_id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status, note }),
        }
      );

      if (res.status === 401) {
        logout();
        return "Session expired. Please sign in again.";
      }

      const data = await res.json().catch(() => null);

      if (!res.ok || !data?.success) {
        return data?.error || "Could not update the status.";
      }

      setReports((prev) =>
        prev.map((r) =>
          r.report_id === data.report.report_id ? data.report : r
        )
      );

      return null;
    } catch {
      return "Could not reach the CivicLens server.";
    }
  };

  const hasFilters =
    query !== "" || category !== "All" || severity !== "All";

  return (
    <div className="flex h-dvh flex-col bg-[#050816] text-slate-100">
      {/* TOP BAR */}
      <header className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-300">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div className="hidden sm:block">
            <div className="text-sm font-bold leading-tight">
              Civic<span className="text-fuchsia-300">Lens</span> Admin
            </div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-600">
              Report inbox
            </div>
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-xl items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 focus-within:border-fuchsia-400/50">
          <Search className="h-4 w-4 shrink-0 text-slate-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by ID, location, category, status..."
            className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-slate-600"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="text-slate-500 hover:text-slate-200"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <button
          onClick={() => {
            setRefreshing(true);
            loadReports();
          }}
          className="rounded-lg p-2 text-slate-400 transition hover:bg-white/5 hover:text-white"
          aria-label="Refresh"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
        </button>

        <div className="hidden items-center gap-3 md:flex">
          <span className="text-xs text-slate-500">{username}</span>
          <button
            onClick={logout}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 transition hover:border-fuchsia-400/40 hover:text-fuchsia-200"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
        <button
          onClick={logout}
          className="rounded-lg p-2 text-slate-400 hover:text-white md:hidden"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* SIDEBAR FOLDERS (large screens) */}
        <aside className="hidden w-56 shrink-0 border-r border-white/10 p-3 lg:block">
          <nav className="space-y-1">
            {(["All", ...STATUSES] as Folder[]).map((f) => (
              <button
                key={f}
                onClick={() => setFolder(f)}
                className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm transition ${
                  folder === f
                    ? "bg-fuchsia-400/15 font-semibold text-fuchsia-200"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`}
              >
                <span className="flex items-center gap-3">
                  <StatusIcon status={f} />
                  {f === "All" ? "All reports" : f}
                </span>
                <span className="text-xs">{counts[f]}</span>
              </button>
            ))}
          </nav>

          <div className="mt-6 rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11px] leading-5 text-slate-500">
            Click a report to read it, view the photo and change its status.
            The list refreshes automatically every 30 seconds.
          </div>
        </aside>

        {/* LIST */}
        <section
          className={`min-h-0 w-full flex-col border-r border-white/10 md:w-[400px] md:shrink-0 ${
            selected ? "hidden md:flex" : "flex"
          }`}
        >
          {/* folder chips (small screens) */}
          <div className="flex gap-2 overflow-x-auto border-b border-white/10 p-3 lg:hidden">
            {(["All", ...STATUSES] as Folder[]).map((f) => (
              <button
                key={f}
                onClick={() => setFolder(f)}
                className={`shrink-0 rounded-full border px-3 py-1.5 text-xs transition ${
                  folder === f
                    ? "border-fuchsia-400/40 bg-fuchsia-400/15 text-fuchsia-200"
                    : "border-white/10 text-slate-400"
                }`}
              >
                {f === "All" ? "All" : f} · {counts[f]}
              </button>
            ))}
          </div>

          {/* filters */}
          <div className="flex flex-wrap items-center gap-2 border-b border-white/10 p-3">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-[#0a1223] px-2 py-2 text-xs text-slate-300 outline-none"
              aria-label="Filter by category"
            >
              <option value="All">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="rounded-lg border border-white/10 bg-[#0a1223] px-2 py-2 text-xs text-slate-300 outline-none"
              aria-label="Filter by severity"
            >
              <option value="All">Any severity</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>

            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as "newest" | "priority")}
              className="rounded-lg border border-white/10 bg-[#0a1223] px-2 py-2 text-xs text-slate-300 outline-none"
              aria-label="Sort"
            >
              <option value="newest">Newest first</option>
              <option value="priority">Highest priority</option>
            </select>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {loading && (
              <div className="p-6 text-center text-sm text-slate-500">
                Loading reports...
              </div>
            )}

            {error && (
              <div className="m-3 flex items-start gap-2 rounded-xl border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-300">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            {!loading && visible.length === 0 && (
              <div className="p-8 text-center text-sm text-slate-500">
                {reports.length === 0
                  ? "No reports yet. Reports submitted on the public site will appear here."
                  : "No reports match your search or filters."}
                {hasFilters && (
                  <button
                    onClick={() => {
                      setQuery("");
                      setCategory("All");
                      setSeverity("All");
                    }}
                    className="mt-3 block w-full text-xs text-fuchsia-300 hover:underline"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            )}

            {visible.map((r) => {
              const unread = r.status === "Pending";
              return (
                <button
                  key={r.report_id}
                  onClick={() => setSelectedId(r.report_id)}
                  className={`block w-full border-b border-white/5 px-4 py-3.5 text-left transition ${
                    r.report_id === selectedId
                      ? "bg-fuchsia-400/10"
                      : "hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${severityDot[r.severity]}`}
                      title={`${r.severity} severity`}
                    />
                    <span className="font-mono text-[11px] text-fuchsia-300">
                      {formatId(r.report_id)}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusBadge[r.status]}`}
                    >
                      {r.status}
                    </span>
                    <span className="ml-auto shrink-0 text-[11px] text-slate-600">
                      {timeAgo(r.created_at)}
                    </span>
                  </div>

                  <div
                    className={`mt-1.5 truncate text-sm ${
                      unread ? "font-semibold text-white" : "text-slate-300"
                    }`}
                  >
                    {r.problem}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-500">
                    {r.category} · {shortAddress(r)}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="border-t border-white/10 px-4 py-2 text-[11px] text-slate-600">
            Showing {visible.length} of {reports.length}
          </div>
        </section>

        {/* READING PANE */}
        <section
          className={`min-h-0 min-w-0 flex-1 ${
            selected ? "block" : "hidden md:block"
          }`}
        >
          {selected ? (
            <ReportDetail
              key={selected.report_id}
              report={selected}
              onBack={() => setSelectedId(null)}
              onChangeStatus={changeStatus}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-slate-600">
              <Inbox className="h-10 w-10" />
              <div className="text-sm">Select a report to read it</div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ReportDetail({
  report,
  onBack,
  onChangeStatus,
}: {
  report: AdminReport;
  onBack: () => void;
  onChangeStatus: (
    report: AdminReport,
    status: AdminStatus,
    note: string
  ) => Promise<string | null>;
}) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState<AdminStatus | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [photoIndex, setPhotoIndex] = useState(0);
  const [photo, setPhoto] = useState<{ key: string; url: string | null }>({
    key: "",
    url: null,
  });

  const hasPhotos = report.photo_count > 0;
  const photoKey = `${report.report_id}:${photoIndex}`;

  // The photo is protected, so it is fetched with the login token and
  // shown from a temporary blob URL.
  useEffect(() => {
    if (!hasPhotos) return;

    let cancelled = false;
    let objectUrl: string | null = null;

    adminFetch(`/admin/reports/${report.report_id}/photo?n=${photoIndex}`)
      .then((res) => (res.ok ? res.blob() : null))
      .then((blob) => {
        if (cancelled) return;
        objectUrl = blob ? URL.createObjectURL(blob) : null;
        setPhoto({ key: photoKey, url: objectUrl });
      })
      .catch(() => {
        if (!cancelled) setPhoto({ key: photoKey, url: null });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [report.report_id, hasPhotos, photoIndex, photoKey]);

  const photoUrl = photo.key === photoKey ? photo.url : null;
  const photoLoading = hasPhotos && photo.key !== photoKey;

  const apply = async (status: AdminStatus) => {
    if (status === report.status || saving) return;

    setSaving(status);
    setActionError(null);

    const error = await onChangeStatus(report, status, note);

    setSaving(null);

    if (error) setActionError(error);
    else setNote("");
  };

  const { latitude, longitude } = report.location || {};
  const hasCoords =
    typeof latitude === "number" && typeof longitude === "number";
  const fullAddress = report.address || report.location?.address;

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <div className="border-b border-white/10 px-5 py-4">
        <button
          onClick={onBack}
          className="mb-3 flex items-center gap-1 text-xs text-slate-400 hover:text-white md:hidden"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to inbox
        </button>

        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-fuchsia-300">
            {formatId(report.report_id)}
          </span>
          <span
            className={`rounded-full border px-2.5 py-1 text-[10px] font-medium ${severityBadge[report.severity]}`}
          >
            {report.severity}
          </span>
          <span
            className={`rounded-full px-2.5 py-1 text-[10px] font-medium ${statusBadge[report.status]}`}
          >
            {report.status}
          </span>
          {(report.report_count ?? 1) > 1 && (
            <span className="flex items-center gap-1 rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-[10px] font-medium text-violet-300">
              <Users className="h-3 w-3" />
              {report.report_count} citizen reports
            </span>
          )}
        </div>

        <h2 className="mt-2 text-xl font-bold leading-snug">
          {report.problem}
        </h2>
        <div className="mt-1 text-xs text-slate-500">
          Reported {fullDate(report.created_at)} · {timeAgo(report.created_at)}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* status actions */}
        <div className="border-b border-white/10 px-5 py-4">
          <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-600">
            Update status
          </div>

          <div className="flex flex-wrap gap-2">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => apply(s)}
                disabled={saving !== null}
                className={`rounded-xl border px-4 py-2 text-xs font-medium transition disabled:opacity-60 ${
                  report.status === s
                    ? statusButton[s]
                    : "border-white/10 text-slate-400 hover:border-white/25 hover:text-white"
                }`}
              >
                {saving === s ? "Saving..." : s}
              </button>
            ))}
          </div>

          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={300}
            placeholder="Optional note saved with the next status change"
            className="mt-3 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs outline-none placeholder:text-slate-600 focus:border-fuchsia-400/50"
          />

          {actionError && (
            <div className="mt-3 rounded-xl border border-red-400/20 bg-red-400/5 px-3 py-2 text-xs text-red-300">
              {actionError}
            </div>
          )}
        </div>

        <div className="space-y-6 px-5 py-5">
          {/* photo */}
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-600">
              Submitted photo
            </div>

            {hasPhotos ? (
              <>
                <div className="flex min-h-48 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black/30">
                  {photoUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={photoUrl}
                      alt={report.problem}
                      className="max-h-[420px] w-full object-contain"
                    />
                  ) : photoLoading ? (
                    <span className="text-xs text-slate-600">
                      Loading photo...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 text-xs text-slate-600">
                      <ImageOff className="h-4 w-4" />
                      Photo could not be loaded
                    </span>
                  )}
                </div>

                {report.photo_count > 1 && (
                  <div className="mt-2 flex gap-2">
                    {Array.from({ length: report.photo_count }).map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setPhotoIndex(i)}
                        className={`h-8 w-8 rounded-lg border text-xs ${
                          i === photoIndex
                            ? "border-fuchsia-400/50 bg-fuchsia-400/15 text-fuchsia-200"
                            : "border-white/10 text-slate-500 hover:text-white"
                        }`}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center gap-2 rounded-2xl border border-dashed border-white/10 p-5 text-xs text-slate-600">
                <ImageOff className="h-4 w-4" />
                No photo was stored for this report.
              </div>
            )}
          </div>

          {/* key facts */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Fact label="Category" value={report.category} />
            <Fact label="Severity" value={report.severity} />
            <Fact
              label="Priority"
              value={`${report.priority_score}/10`}
            />
            <Fact label="Department" value={report.responsible_department} />
          </div>

          {/* location */}
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-600">
              Location
            </div>
            <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-fuchsia-300" />
              <div className="min-w-0 text-sm">
                <div className="break-words">
                  {fullAddress || "Address not available"}
                </div>
                {hasCoords && (
                  <>
                    <div className="mt-1 font-mono text-xs text-slate-500">
                      {latitude.toFixed(5)}, {longitude.toFixed(5)}
                    </div>
                    <a
                      href={`https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-1 text-xs text-fuchsia-300 hover:underline"
                    >
                      Open in OpenStreetMap
                      <ArrowUpRight className="h-3 w-3" />
                    </a>
                  </>
                )}
              </div>
            </div>
          </div>

          <TextBlock title="Description" text={report.description} />
          <TextBlock title="Risk" text={report.risk} />
          <TextBlock
            title="Recommended action"
            text={report.recommended_action}
          />
          {report.additional_information && (
            <TextBlock
              title="Added by later citizen reports"
              text={report.additional_information}
            />
          )}

          {/* history */}
          {report.status_history && report.status_history.length > 0 && (
            <div>
              <div className="mb-3 text-[10px] uppercase tracking-widest text-slate-600">
                History
              </div>
              <ol className="space-y-3 border-l border-white/10 pl-4">
                {report.status_history
                  .slice()
                  .reverse()
                  .map((h, i) => (
                    <li key={i} className="relative text-xs">
                      <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-fuchsia-400" />
                      <div className="text-slate-300">
                        <span className="font-medium">{h.status}</span>
                        {h.by && (
                          <span className="text-slate-500"> · {h.by}</span>
                        )}
                      </div>
                      <div className="text-slate-600">{fullDate(h.at)}</div>
                      {h.note && (
                        <div className="mt-0.5 text-slate-400">{h.note}</div>
                      )}
                    </li>
                  ))}
              </ol>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <div className="text-[10px] uppercase tracking-widest text-slate-600">
        {label}
      </div>
      <div className="mt-1 break-words text-sm font-medium">{value}</div>
    </div>
  );
}

function TextBlock({ title, text }: { title: string; text: string }) {
  if (!text) return null;

  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-widest text-slate-600">
        {title}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-7 text-slate-300">
        {text}
      </p>
    </div>
  );
}
