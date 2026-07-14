export type RunStatus = "QUEUED" | "RUNNING" | "SOLVED" | "FAILED" | "TIMEOUT";
export type IndexStatus = "PENDING" | "INDEXING" | "READY" | "FAILED";

export interface Step {
  id: string;
  step_number: number;
  agent_name: string | null;
  thought: string | null;
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
  duration_ms: number | null;
  pr_number: number | null;
  pr_url: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RunDetail extends RunSummary {
  issue_body: string;
  baseline_tests: Record<string, any> | null;
  final_tests: Record<string, any> | null;
  error_message: string | null;
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
  type: "setup" | "think" | "act" | "observe" | string;
  step?: number;
  agent_name?: string;
  thought?: string;
  tool?: string | null;
  args?: Record<string, any> | null;
  observation?: string;
  duration_ms?: number;
  token_count?: number;
  status?: string;
  baseline?: Record<string, any>;
  branch?: string;
}
