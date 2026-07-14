import type {
  GitHubIssue,
  PaginatedGitHubIssues,
  RunSummary,
  RunDetail,
  Repository,
  Stats,
} from "../types";

export type { GitHubIssue, PaginatedGitHubIssues, RunSummary, RunDetail, Repository, Stats };

export interface PaginatedRuns {
  items: RunSummary[];
  total: number;
  page: number;
  page_size: number;
}
