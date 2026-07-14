import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import type { PaginatedGitHubIssues, PaginatedRuns, RunDetail, Repository, Stats } from "./apiTypes";

const API_URL = import.meta.env.VITE_API_URL || "";

export const api = axios.create({ baseURL: API_URL });

export function useStats() {
  return useQuery<Stats>({
    queryKey: ["stats"],
    queryFn: async () => (await api.get("/api/runs/stats")).data,
    refetchInterval: 5000,
  });
}

export function useRuns(params: { repository_id?: string; status?: string; page?: number } = {}) {
  return useQuery<PaginatedRuns>({
    queryKey: ["runs", params],
    queryFn: async () => (await api.get("/api/runs", { params })).data,
    refetchInterval: 5000,
  });
}

export function useRun(runId: string | undefined) {
  return useQuery<RunDetail>({
    queryKey: ["run", runId],
    queryFn: async () => (await api.get(`/api/runs/${runId}`)).data,
    enabled: !!runId,
  });
}

export function useRepositories() {
  return useQuery<Repository[]>({
    queryKey: ["repositories"],
    queryFn: async () => (await api.get("/api/repositories")).data,
    refetchInterval: 8000,
  });
}

export function useRepositoryIssues(
  repoId: string | undefined,
  params: { state?: string; page?: number; page_size?: number } = {}
) {
  return useQuery<PaginatedGitHubIssues>({
    queryKey: ["repository-issues", repoId, params],
    queryFn: async () => (await api.get(`/api/repositories/${repoId}/issues`, { params })).data,
    enabled: !!repoId,
    refetchInterval: 15000,
  });
}

export async function triggerManualRun(repo_id: string, issue_number: number) {
  return (await api.post("/api/runs/manual", { repo_id, issue_number })).data;
}

export async function stopRun(runId: string) {
  return (await api.post(`/api/runs/${runId}/stop`)).data;
}

export async function stopActiveRuns() {
  return (await api.post("/api/runs/stop-active")).data;
}

export async function deleteRun(runId: string) {
  return (await api.delete(`/api/runs/${runId}`)).data;
}

export async function deleteFailedRuns() {
  return (await api.delete("/api/runs/failed")).data;
}

export async function connectRepository(owner: string, name: string) {
  return (await api.post("/api/repositories", { owner, name })).data;
}

export async function reindexRepository(repoId: string) {
  return (await api.post(`/api/repositories/${repoId}/reindex`)).data;
}
