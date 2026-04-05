import React, { useEffect, useMemo, useState } from "react";

export default function NoteModal({ open, note, onClose, onDelete, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState(null);
  const [title, setTitle] = useState("");
  const [tagsText, setTagsText] = useState("");

  const initialTagsText = useMemo(() => {
    const tags = Array.isArray(note?.tags) ? note.tags : [];
    return tags.join(", ");
  }, [note]);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") onClose?.();
    }
    if (open) window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    setEditing(false);
    setSaving(false);
    setEditError(null);
    setTitle(note?.title || "");
    setTagsText(initialTagsText);
  }, [open, note, initialTagsText]);

  if (!open) return null;

  async function onSave() {
    if (!note?.id) return;
    setEditError(null);
    setSaving(true);
    try {
      const tags = tagsText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      await onUpdate?.(note.id, {
        title: title || null,
        tags,
      });
      setEditing(false);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to update note";
      setEditError(msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="text-white font-semibold">
            {note?.title || "Note"}
          </div>
          <button
            className="text-zinc-300 hover:text-white"
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        <div className="p-4 space-y-4">
          {editError ? (
            <div className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
              {String(editError)}
            </div>
          ) : null}

          {editing ? (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-zinc-500">Title</div>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="mt-1 w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-700"
                  placeholder="Optional"
                />
              </div>
              <div>
                <div className="text-xs text-zinc-500">
                  Tags (comma separated)
                </div>
                <input
                  value={tagsText}
                  onChange={(e) => setTagsText(e.target.value)}
                  className="mt-1 w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-700"
                  placeholder="work, ideas, personal"
                />
              </div>
            </div>
          ) : null}

          {note?.urdu_text_corrected ? (
            <div>
              <div className="text-xs text-zinc-500">Urdu (corrected)</div>
              <div className="mt-1 text-zinc-200 whitespace-pre-wrap">
                {note.urdu_text_corrected}
              </div>
            </div>
          ) : null}

          {note?.urdu_text_roman ? (
            <div>
              <div className="text-xs text-zinc-500">Roman Urdu</div>
              <div className="mt-1 text-zinc-200 whitespace-pre-wrap">
                {note.urdu_text_roman}
              </div>
            </div>
          ) : null}

          {note?.urdu_text ? (
            <div>
              <div className="text-xs text-zinc-500">Urdu (raw)</div>
              <div className="mt-1 text-zinc-200 whitespace-pre-wrap">
                {note.urdu_text}
              </div>
            </div>
          ) : null}

          {note?.english_text ? (
            <div>
              <div className="text-xs text-zinc-500">English</div>
              <div className="mt-1 text-zinc-200 whitespace-pre-wrap">
                {note.english_text}
              </div>
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-3 pt-2">
            {editing ? (
              <button
                className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
                type="button"
                onClick={() => setEditing(false)}
                disabled={saving}
              >
                Cancel
              </button>
            ) : (
              <button
                className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
                type="button"
                onClick={() => setEditing(true)}
              >
                Edit
              </button>
            )}

            {editing ? (
              <button
                className="rounded-lg bg-white text-black px-3 py-2"
                type="button"
                onClick={onSave}
                disabled={saving}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            ) : null}

            <button
              className="rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-zinc-200 hover:border-zinc-600"
              type="button"
              onClick={onClose}
            >
              Done
            </button>
            <button
              className="rounded-lg bg-red-600 text-white px-3 py-2"
              type="button"
              onClick={() => onDelete?.(note)}
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
