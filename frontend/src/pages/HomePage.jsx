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

  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatNoteSources, setChatNoteSources] = useState([]);

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

  async function sendChat() {
    if (!userId) return;
    const text = (chatInput || "").trim();
    if (!text) return;

    setChatError(null);
    setChatSending(true);
    setChatInput("");
    setChatNoteSources([]);
    setChatMessages((prev) => [...prev, { role: "user", text }]);

    try {
      const res = await api.post(
        "/notes/answer",
        { question: text, top_k: 8 },
        { params: { user_id: userId } },
      );

      const answer = res?.data?.answer || "";
      const noteSources = res?.data?.note_sources || [];

      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: answer || "(No answer returned)" },
      ]);
      setChatNoteSources(Array.isArray(noteSources) ? noteSources : []);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Chat failed";
      setChatError(msg);
    } finally {
      setChatSending(false);
    }
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

        <main className="mt-6 space-y-6">
          <section className="bg-zinc-950 border border-zinc-800 rounded-xl p-6">
            <div className="text-center">
              <div className="text-white font-semibold">Record</div>
              <div className="text-sm text-zinc-400 mt-1">
                Tap to start, tap to stop.
              </div>
            </div>
            <div className="mt-5 flex justify-center">
              <Recorder onCreate={createNoteFromBlob} />
            </div>
          </section>

          <section className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="text-white font-semibold">Your notes</div>
              <button
                type="button"
                onClick={fetchNotes}
                className="text-sm text-zinc-300 hover:text-white"
              >
                Refresh
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

          <section className="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
            <div className="text-white font-semibold">Ask your notes</div>
            <div className="text-sm text-zinc-400 mt-1">
              Ask like a chatbot: “Did I record anything about …?”
            </div>

            {chatError ? (
              <div className="mt-3 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
                {String(chatError)}
              </div>
            ) : null}

            {chatMessages.length ? (
              <div className="mt-4 space-y-3">
                {chatMessages.map((m, idx) => (
                  <div
                    key={idx}
                    className={
                      m.role === "user"
                        ? "ml-auto max-w-[85%] rounded-2xl bg-white text-black px-4 py-2"
                        : "mr-auto max-w-[85%] rounded-2xl bg-zinc-900 border border-zinc-800 px-4 py-2 text-zinc-200"
                    }
                  >
                    <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 text-sm text-zinc-500">
                No questions yet.
              </div>
            )}

            {chatNoteSources?.length ? (
              <div className="mt-4">
                <div className="text-xs text-zinc-500">Matched notes</div>
                <div className="mt-2 space-y-2">
                  {chatNoteSources.slice(0, 5).map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => openNote(n)}
                      className="w-full text-left rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
                    >
                      <div className="font-medium">{n.title || "Untitled"}</div>
                      <div className="text-xs text-zinc-400 line-clamp-2 mt-1">
                        {n.english_text || n.urdu_text_corrected || ""}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-4 flex items-center gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") sendChat();
                }}
                placeholder='Ask: "Did I record anything about gym?"'
                className="flex-1 rounded-full bg-zinc-900 border border-zinc-800 px-4 py-3 text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-700"
              />
              <button
                type="button"
                onClick={sendChat}
                disabled={chatSending}
                className="rounded-full bg-white text-black px-5 py-3 disabled:opacity-50"
              >
                {chatSending ? "…" : "Send"}
              </button>
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
