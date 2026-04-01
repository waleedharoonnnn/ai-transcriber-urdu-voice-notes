import React from "react";

export default function NoteCard({ note, onOpen }) {
  const title = note?.title || "Untitled";
  const preview = note?.english_text || note?.urdu_text_corrected || "";
  const created = note?.created_at ? new Date(note.created_at) : null;

  return (
    <button
      type="button"
      onClick={() => onOpen?.(note)}
      className="w-full text-left bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-white font-semibold leading-tight">{title}</div>
          {created ? (
            <div className="text-xs text-zinc-500 mt-1">
              {created.toLocaleString()}
            </div>
          ) : null}
        </div>
        <div className="text-xs text-zinc-500">Open</div>
      </div>
      {preview ? (
        <div className="text-sm text-zinc-300 mt-3 line-clamp-3">{preview}</div>
      ) : (
        <div className="text-sm text-zinc-500 mt-3">No summary yet</div>
      )}
    </button>
  );
}
