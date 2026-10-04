export type RunStatus =
  | "QUEUED" | "PREPARING" | "ANALYZING" | "PLANNING" | "IMPLEMENTING"
  | "VALIDATING" | "AWAITING_APPROVAL" | "CHANGES_REQUESTED" | "PR_CREATING"
  | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMED_OUT" | "REJECTED"
  | "RUNNING" | "SOLVED" | "TIMEOUT";
export type IndexStatus = "PENDING" | "INDEXING" | "READY" | "FAILED";

export interface Step {
  id: string;
  step_number: number;
  agent_name: string | null;
  tool_name: string | null;
  tool_args: Record<string, any> | null;
  observation: string | null;
  duration_ms: number | null;
  token_count: number | null;
  created_at: string;
}

export interface RunSummary {
  id: string;
  repository_id: string;
  issue_number: number;
  issue_title: string;
  source: string;
  external_issue_key: string | null;
  external_issue_url: string | null;
  status: RunStatus;
  model: string;
  total_steps: number;
  model_requests: number;
  total_tokens: number;
  estimated_cost: number | null;
  tool_counts: Record<string, number>;
  duration_ms: number | null;
  pr_number: number | null;
  pr_url: string | null;
  created_at: string;
  completed_at: string | null;
  state_version: number;
  event_sequence: number;
  approval_status: string;
  pr_status: string;
  cancellation_requested_at: string | null;
  heartbeat_at: string | null;
  phase_started_at: string | null;
  phase_timestamps: Record<string, string>;
}

export interface RunDetail extends RunSummary {
  issue_body: string;
  baseline_tests: Record<string, any> | null;
  final_tests: Record<string, any> | null;
  error_message: string | null;
  patch_diff: string | null;
  review_summary: Record<string, any> | null;
  approval_comment: string | null;
  remote_branch: string | null;
  commit_sha: string | null;
  steps: Step[];
}

export interface Repository {
  id: string;
  owner: string;
  name: string;
  installation_id: number | null;
  index_status: IndexStatus;
  last_indexed_sha: string | null;
  files_indexed: number;
  indexing_progress: number;
  index_error: string | null;
  config: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface GitHubIssueLabel {
  name: string;
  color: string | null;
}

export interface GitHubIssue {
  number: number;
  title: string;
  body: string;
  state: "open" | "closed" | string;
  author: string | null;
  labels: GitHubIssueLabel[];
  html_url: string;
  created_at: string;
  updated_at: string;
}

export interface PaginatedGitHubIssues {
  items: GitHubIssue[];
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface Stats {
  total_runs: number;
  solved: number;
  failed: number;
  in_progress: number;
  success_rate: number;
  avg_steps: number;
  avg_duration_ms: number;
  recent: RunSummary[];
}

export interface LiveStep {
  run_id: string;
  sequence?: number;
  type: "setup" | "think" | "act" | "observe" | string;
  step?: number;
  agent_name?: string;
  tool?: string | null;
  args?: Record<string, any> | null;
  observation?: string;
  duration_ms?: number;
  token_count?: number;
  status?: string;
  baseline?: Record<string, any>;
  branch?: string;
}
