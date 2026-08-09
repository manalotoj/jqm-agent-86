import { useState } from "react";
import {
  useSessions,
  useCreateSession,
  useUpdateSession,
  useDeleteSession,
} from "../hooks/useSessions";

export default function SessionList() {
  const { data: sessions, isLoading, error } = useSessions();
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();
  const [newTitle, setNewTitle] = useState("");

  if (isLoading) return <p>Loading sessions...</p>;
  if (error) return <p style={{ color: "red" }}>Error: {(error as Error).message}</p>;

  return (
    <div>
      <h2>Sessions</h2>

      <div style={{ marginBottom: "16px" }}>
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New session title"
        />
        <button
          onClick={() => {
            createSession.mutate({ title: newTitle || null });
            setNewTitle("");
          }}
          disabled={createSession.isPending}
        >
          Create Session
        </button>
      </div>

      <ul>
        {sessions?.map((session) => (
          <li key={session.id} style={{ marginBottom: "8px" }}>
            <strong>{session.title || session.id}</strong>
            <button
              onClick={() => {
                const newName = prompt("Rename session:", session.title ?? "");
                if (newName !== null) {
                  updateSession.mutate({ sessionId: session.id, body: { title: newName } });
                }
              }}
              style={{ marginLeft: "8px" }}
            >
              Rename
            </button>
            <button
              onClick={() => {
                if (confirm("Delete this session?")) {
                  deleteSession.mutate(session.id);
                }
              }}
              style={{ marginLeft: "8px" }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}