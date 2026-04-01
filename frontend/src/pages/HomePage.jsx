import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/api";
import { useAuth } from "../context/AuthContext";
import Recorder from "../components/Recorder";
import NoteCard from "../components/NoteCard";
import NoteModal from "../components/NoteModal";

export default function HomePage() {
  const { user, logout } = useAuth();
  const userId = user?.id;

  const [notes, setNotes] = useState([]);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [error, setError] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [activeNote, setActiveNote] = useState(null);

  const header = useMemo(() => {
    const email = user?.email || "";
    return email ? `Logged in as ${email}` : "Logged in";
  }, [user]);

  async function fetchNotes() {
    if (!userId) return;
    setError(null);
    setLoadingNotes(true);
    try {
      const res = await api.get("/notes/list", { params: { user_id: userId } });
      setNotes(res.data?.notes || res.data || []);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to load notes";
      setError(msg);
    } finally {
      setLoadingNotes(false);
    }
  }

  useEffect(() => {
    fetchNotes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function runSearch() {
    if (!userId) return;
    const q = (searchQuery || "").trim();
    if (!q) {
      setSearchResults(null);
      return;
    }

    setError(null);
    setSearching(true);
    try {
      const res = await api.get("/notes/search", {
        params: { user_id: userId, q, top_k: 20 },
      });
      setSearchResults(res.data || []);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Search failed";
      setError(msg);
    } finally {
      setSearching(false);
    }
  }

  async function createNoteFromBlob(blob) {
    if (!userId) return;

    const form = new FormData();
    form.append("audio", blob, `recording-${Date.now()}.webm`);

    await api.post("/notes/create", form, {
      params: { user_id: userId },
      headers: { "Content-Type": "multipart/form-data" },
    });

    await fetchNotes();
  }

  async function openNote(note) {
    if (!note?.id || !userId) return;
    setError(null);
    try {
      const res = await api.get(`/notes/${note.id}`, {
        params: { user_id: userId },
      });
      setActiveNote(res.data);
      setModalOpen(true);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to open note";
      setError(msg);
    }
  }

  async function deleteNote(note) {
    if (!note?.id || !userId) return;
    setError(null);
    try {
      await api.delete(`/notes/${note.id}`, { params: { user_id: userId } });
      setModalOpen(false);
      setActiveNote(null);
      await fetchNotes();
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to delete note";
      setError(msg);
    }
  }

  async function updateNote(noteId, patch) {
    if (!noteId || !userId) return;
    setError(null);
    try {
      const res = await api.patch(`/notes/${noteId}`, patch, {
        params: { user_id: userId },
      });
      setActiveNote(res.data);
      await fetchNotes();
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to update note";
      setError(msg);
      throw err;
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <div className="max-w-5xl mx-auto p-4">
        <header className="flex items-center justify-between gap-3 py-2">
          <div>
            <div className="text-xl font-semibold">Urdu Voice Notes</div>
            <div className="text-sm text-zinc-400">{header}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
          >
            Sign out
          </button>
        </header>

        <main className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
            <div className="text-white font-semibold">Record</div>
            <div className="text-sm text-zinc-400 mt-1">
              Tap to start, tap to stop.
            </div>
            <div className="mt-4">
              <Recorder onCreate={createNoteFromBlob} />
            </div>
          </section>

          <section className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="text-white font-semibold">Your notes</div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={fetchNotes}
                  className="text-sm text-zinc-300 hover:text-white"
                >
                  Refresh
                </button>
              </div>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runSearch();
                }}
                placeholder="Semantic search your notes…"
                className="flex-1 rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-700"
              />
              {searchResults ? (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    setSearchResults(null);
                  }}
                  className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
                >
                  Clear
                </button>
              ) : null}
              <button
                type="button"
                onClick={runSearch}
                disabled={searching}
                className="rounded-lg bg-white text-black px-3 py-2 disabled:opacity-50"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>

            {error ? (
              <div className="mt-3 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
                {String(error)}
              </div>
            ) : null}

            <div className="mt-4 space-y-3">
              {loadingNotes ? (
                <div className="text-sm text-zinc-400">Loading…</div>
              ) : searchResults !== null ? (
                searchResults.length ? (
                  searchResults.map((n) => (
                    <NoteCard key={n.id} note={n} onOpen={openNote} />
                  ))
                ) : (
                  <div className="text-sm text-zinc-500">No matches.</div>
                )
              ) : notes.length ? (
                notes.map((n) => (
                  <NoteCard key={n.id} note={n} onOpen={openNote} />
                ))
              ) : (
                <div className="text-sm text-zinc-500">
                  No notes yet. Record one.
                </div>
              )}
            </div>
          </section>
        </main>

        <NoteModal
          open={modalOpen}
          note={activeNote}
          onClose={() => setModalOpen(false)}
          onDelete={deleteNote}
          onUpdate={updateNote}
        />
      </div>
    </div>
  );
}
