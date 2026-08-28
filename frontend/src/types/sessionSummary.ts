export interface ActionItem {
  description: string;
  status: "open" | "done" | "abandoned";
  owner: string | null;
}

export interface ArtifactRef {
  name: string;
  artifact_type: "docx" | "pptx" | "xlsx" | "diagram" | "code" | "other";
  location: string;
}

export interface SessionSummary {
  id: string;
  session_id: string;
  user_id: string;
  title: string;
  date_range_start: string;
  date_range_end: string;
  one_line_summary: string;
  topics: string[];
  key_decisions: string[];
  action_items: ActionItem[];
  artifacts_generated: ArtifactRef[];
  open_questions: string[];
  tools_used: string[];
  tags: string[];
  continuation_context: string;
  created_at: string;
  updated_at: string;
}