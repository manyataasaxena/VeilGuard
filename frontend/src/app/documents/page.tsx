"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import TopNav from "@/components/TopNav";
import { API_BASE, clearSession, getSavedUser, getToken, UserInfo } from "@/lib/api";

interface DocItem {
  id: string;
  filename: string;
  allowed_roles: string[];
  total_pages: number;
  status: string;
}

const ALL_ROLES = ["ADMIN", "FINANCE", "HR", "INTERN"];

export default function DocumentsPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [file, setFile] = useState<File | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(["ADMIN", "FINANCE"]);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  const fetchDocs = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.push("/");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/docs/list`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        clearSession();
        router.push("/");
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch documents");
      const data = await res.json();
      setDocs(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not load documents";
      setFeedback({ type: "err", msg });
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const saved = getSavedUser();
    const token = getToken();
    if (!saved || !token) {
      router.push("/");
      return;
    }
    setUser(saved);
    fetchDocs();
  }, [router, fetchDocs]);

  function toggleRole(role: string) {
    if (role === "ADMIN") return;
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    const token = getToken();
    if (!token) return;

    setFeedback(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("allowed_roles", selectedRoles.join(","));

      const res = await fetch(`${API_BASE}/docs/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }
      setFeedback({
        type: "ok",
        msg: `Indexed "${data.filename}" (${data.total_pages} pages) for [${data.allowed_roles.join(", ")}]`,
      });
      setFile(null);
      await fetchDocs();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setFeedback({ type: "err", msg });
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(docId: string, filename: string) {
    const token = getToken();
    if (!token) return;
    setDeletingId(docId);
    setFeedback(null);
    try {
      const res = await fetch(`${API_BASE}/docs/${docId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Delete failed");
      }
      setFeedback({ type: "ok", msg: `Removed "${filename}" and its vector chunks.` });
      await fetchDocs();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setFeedback({ type: "err", msg });
    } finally {
      setDeletingId(null);
    }
  }

  const isAdmin = user?.role === "ADMIN";

  return (
    <div className="min-h-screen flex flex-col bg-[#151619] text-[#F5F5F2]">
      <TopNav user={user} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 space-y-8">
        <div className="border-b border-white/10 pb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-widest text-[#C6F432]">
              Knowledge Perimeter / SQL-Level RBAC
            </p>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white mt-1">
              Document &amp; Access Matrix
            </h1>
          </div>
          <div className="font-mono text-xs text-white/60">
            VISIBLE TO ROLE <span className="text-[#C6F432] font-semibold">{user?.role}</span>: {docs.length} FILES
          </div>
        </div>

        {feedback && (
          <div
            className={`p-3.5 border font-mono text-xs ${
              feedback.type === "ok"
                ? "bg-[#182015] border-[#C6F432]/50 text-[#E8F8B3]"
                : "bg-[#2A1416] border-[#EF4444]/60 text-[#FCA5A5]"
            }`}
          >
            {feedback.msg}
          </div>
        )}

        <section className="bg-[#1B1C20] border border-white/10 border-t-white/20 p-6">
          {!isAdmin ? (
            <div className="flex items-center justify-between gap-4 font-mono text-xs">
              <span className="text-white/75">
                UPLOAD RESTRICTED: Role <strong className="text-white">{user?.role}</strong> has read-only access to authorized documents.
              </span>
              <span className="px-2.5 py-1 border border-white/15 text-white/50">READ-ONLY</span>
            </div>
          ) : (
            <form onSubmit={handleUpload} className="space-y-5">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <h2 className="font-mono text-xs uppercase tracking-wider text-white">
                  Ingest New Compliance PDF
                </h2>
                <span className="font-mono text-[11px] text-white/50">
                  CHUNKING + 384-DIM PGVECTOR + TSVECTOR
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-end">
                <div className="lg:col-span-5 space-y-2">
                  <label className="block font-mono text-[11px] uppercase text-white/60">
                    Select PDF File
                  </label>
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="w-full text-xs font-mono text-white/80 bg-[#121316] border border-white/15 p-2 file:mr-3 file:py-1 file:px-3 file:border-0 file:bg-[#C6F432] file:text-[#151619] file:font-semibold file:cursor-pointer"
                  />
                </div>

                <div className="lg:col-span-4 space-y-2">
                  <label className="block font-mono text-[11px] uppercase text-white/60">
                    Authorized Roles
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {ALL_ROLES.map((role) => {
                      const active = selectedRoles.includes(role);
                      return (
                        <button
                          key={role}
                          type="button"
                          onClick={() => toggleRole(role)}
                          className={`px-2.5 py-1.5 font-mono text-xs border transition-colors cursor-pointer ${
                            active
                              ? "bg-[#C6F432] text-[#151619] border-[#C6F432] font-semibold"
                              : "bg-[#121316] text-white/60 border-white/15 hover:border-white/40"
                          }`}
                        >
                          {role}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="lg:col-span-3 flex justify-end">
                  <button
                    type="submit"
                    disabled={!file || uploading}
                    className="w-full px-4 py-2.5 bg-[#C6F432] text-[#151619] font-mono text-xs font-bold uppercase tracking-wider disabled:opacity-40 cursor-pointer"
                  >
                    {uploading ? "INDEXING PDF..." : "UPLOAD & INDEX ->"}
                  </button>
                </div>
              </div>
            </form>
          )}
        </section>

        <section className="bg-[#1B1C20] border border-white/10 overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/10 bg-[#121316] font-mono text-[11px] uppercase tracking-wider text-white/55">
                <th className="py-3.5 px-4">Document</th>
                <th className="py-3.5 px-4">Pages</th>
                <th className="py-3.5 px-4">Status</th>
                {ALL_ROLES.map((r) => (
                  <th key={r} className="py-3.5 px-3 text-center">
                    {r}
                  </th>
                ))}
                {isAdmin && <th className="py-3.5 px-4 text-right">Action</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10 text-xs">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center font-mono text-white/50">
                    LOADING DOCUMENTS...
                  </td>
                </tr>
              ) : docs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center font-mono text-white/50">
                    NO DOCUMENTS ACCESSIBLE FOR ROLE [{user?.role}].
                  </td>
                </tr>
              ) : (
                docs.map((doc) => (
                  <tr key={doc.id} className="hover:bg-white/[0.02]">
                    <td className="py-3.5 px-4 font-medium text-white">{doc.filename}</td>
                    <td className="py-3.5 px-4 font-mono text-white/70">{doc.total_pages}</td>
                    <td className="py-3.5 px-4 font-mono">
                      <span className="px-2 py-0.5 text-[10px] border border-[#C6F432]/40 text-[#C6F432] bg-[#C6F432]/10">
                        {doc.status}
                      </span>
                    </td>
                    {ALL_ROLES.map((r) => {
                      const allowed = doc.allowed_roles.includes(r);
                      return (
                        <td key={r} className="py-3.5 px-3 text-center font-mono text-[10px]">
                          {allowed ? (
                            <span className="px-2 py-0.5 bg-[#C6F432]/15 text-[#C6F432] border border-[#C6F432]/35">
                              ALLOW
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 bg-white/5 text-white/30 border border-white/10">
                              LOCKED
                            </span>
                          )}
                        </td>
                      );
                    })}
                    {isAdmin && (
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          disabled={deletingId === doc.id}
                          className="font-mono text-[11px] px-2.5 py-1 border border-[#EF4444]/40 text-[#FCA5A5] hover:bg-[#EF4444]/15 cursor-pointer disabled:opacity-40"
                        >
                          {deletingId === doc.id ? "..." : "DELETE"}
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  );
}