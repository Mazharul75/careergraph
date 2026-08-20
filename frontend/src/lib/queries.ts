"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch } from "./api";
import type {
  Achievement,
  AdminUser,
  GoalProgress,
  Job,
  JobSummary,
  LearningPath,
  MatchResult,
  Resume,
  RankedCandidate,
  Skill,
  SkillProfile,
  SkillStatus,
  SystemStats,
  UserRole,
} from "./types";

export const keys = {
  resumes: ["resumes"] as const,
  resume: (id: string) => ["resumes", id] as const,
  skills: ["skills"] as const,
  profile: ["skills", "me"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["jobs", id] as const,
  match: (id: string) => ["jobs", id, "match"] as const,
  path: (id: string) => ["jobs", id, "learning-path"] as const,
  goal: ["goals", "current"] as const,
  achievements: ["goals", "achievements"] as const,
  candidates: (id: string) => ["jobs", id, "candidates"] as const,
  adminStats: ["admin", "stats"] as const,
  adminUsers: ["admin", "users"] as const,
};

/* -------------------------------------------------------------------------- resumes */

export function useResumes(): UseQueryResult<Resume[]> {
  return useQuery({
    queryKey: keys.resumes,
    queryFn: () => apiFetch<Resume[]>("/api/v1/resumes"),
    // Poll while anything is still being parsed, and stop once everything reaches a terminal
    // state. Polling forever would keep a tab making requests all day for no reason.
    refetchInterval: (query) => {
      const data = query.state.data as Resume[] | undefined;
      const working = data?.some((r) => r.status === "pending" || r.status === "processing");
      return working ? 2000 : false;
    },
  });
}

export function useUploadResume() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<Resume>("/api/v1/resumes", { method: "POST", body: form });
    },
    onSuccess: () => {
      // Parsing writes skills, so both lists are stale once an upload lands.
      void client.invalidateQueries({ queryKey: keys.resumes });
      void client.invalidateQueries({ queryKey: keys.profile });
    },
  });
}

/* --------------------------------------------------------------------------- skills */

export function useSkillCatalogue(): UseQueryResult<Skill[]> {
  return useQuery({
    queryKey: keys.skills,
    queryFn: () => apiFetch<Skill[]>("/api/v1/skills"),
    // Reference data seeded by migration — it does not change while the app is open.
    staleTime: Infinity,
  });
}

export function useSkillProfile(): UseQueryResult<SkillProfile> {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => apiFetch<SkillProfile>("/api/v1/skills/me"),
    refetchInterval: 5000, // the worker writes suggestions after a resume parses
  });
}

function invalidateEverythingScoreRelated(client: ReturnType<typeof useQueryClient>) {
  // A profile change moves every match score and every learning path, so those caches are
  // stale by definition. Invalidating broadly is correct here and cheap at this scale.
  void client.invalidateQueries({ queryKey: keys.profile });
  void client.invalidateQueries({ queryKey: keys.jobs });
}

export function useUpdateSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ skillId, status }: { skillId: string; status: SkillStatus }) =>
      apiFetch(`/api/v1/skills/me/${skillId}`, { method: "PATCH", body: { status } }),
    onSuccess: () => invalidateEverythingScoreRelated(client),
  });
}

export function useAddSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      apiFetch("/api/v1/skills/me", { method: "POST", body: { skill_id: skillId } }),
    onSuccess: () => invalidateEverythingScoreRelated(client),
  });
}

export function useConfirmAllSkills() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/api/v1/skills/me/confirm-all", { method: "POST" }),
    onSuccess: () => invalidateEverythingScoreRelated(client),
  });
}

/* ----------------------------------------------------------------------------- jobs */

export function useJobs(): UseQueryResult<JobSummary[]> {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: () => apiFetch<JobSummary[]>("/api/v1/jobs"),
  });
}

export function useJob(id: string): UseQueryResult<Job> {
  return useQuery({ queryKey: keys.job(id), queryFn: () => apiFetch<Job>(`/api/v1/jobs/${id}`) });
}

export function useCreateJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      title: string;
      description: string;
      company?: string;
      location?: string;
      is_public?: boolean;
    }) => apiFetch<Job>("/api/v1/jobs", { method: "POST", body: input }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export function useDeleteJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.jobs }),
  });
}

/* ------------------------------------------------------------- matching and planning */

export function useMatch(jobId: string): UseQueryResult<MatchResult> {
  return useQuery({
    queryKey: keys.match(jobId),
    queryFn: () => apiFetch<MatchResult>(`/api/v1/jobs/${jobId}/match`),
    // Re-poll while the semantic half is missing: the worker is still embedding, and the score
    // will change once it lands. Stop as soon as it is available.
    refetchInterval: (query) => {
      const data = query.state.data as MatchResult | undefined;
      return data && !data.semantic_available ? 4000 : false;
    },
  });
}

export function useLearningPath(jobId: string): UseQueryResult<LearningPath> {
  return useQuery({
    queryKey: keys.path(jobId),
    queryFn: () => apiFetch<LearningPath>(`/api/v1/jobs/${jobId}/learning-path`),
  });
}

/* ------------------------------------------------------------------- career goals */

export function useCurrentGoal(): UseQueryResult<GoalProgress | null> {
  return useQuery({
    queryKey: keys.goal,
    // The endpoint returns null rather than 404 when no goal is set, because having no goal
    // is a normal state for a new account — not an error the UI should have to catch.
    queryFn: () => apiFetch<GoalProgress | null>("/api/v1/goals/current"),
  });
}

export function useAchievements(): UseQueryResult<Achievement[]> {
  return useQuery({
    queryKey: keys.achievements,
    queryFn: () => apiFetch<Achievement[]>("/api/v1/goals/achievements"),
  });
}

export function useSetGoal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      apiFetch<GoalProgress>("/api/v1/goals", { method: "POST", body: { job_id: jobId } }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.goal }),
  });
}

export function useAbandonGoal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) =>
      apiFetch<void>(`/api/v1/goals/${goalId}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.goal }),
  });
}

export function useAchieveGoal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) =>
      apiFetch<Achievement>(`/api/v1/goals/${goalId}/achieve`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goal });
      void client.invalidateQueries({ queryKey: keys.achievements });
    },
  });
}

export function useStartLearning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      apiFetch("/api/v1/skills/me/learning", { method: "POST", body: { skill_id: skillId } }),
    // Both the goal and the profile change: the goal gains an in-progress flag, the profile
    // gains a learning entry. The score deliberately does not move.
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goal });
      void client.invalidateQueries({ queryKey: keys.profile });
    },
  });
}

export function useMarkLearned() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      apiFetch(`/api/v1/skills/me/${skillId}`, { method: "PATCH", body: { status: "confirmed" } }),
    // This is the one that moves the number, so every score-bearing cache is stale.
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goal });
      void client.invalidateQueries({ queryKey: keys.profile });
      void client.invalidateQueries({ queryKey: keys.jobs });
    },
  });
}

/* --------------------------------------------------------------- candidate ranking */

export function useCandidates(jobId: string, enabled: boolean): UseQueryResult<RankedCandidate[]> {
  return useQuery({
    queryKey: keys.candidates(jobId),
    queryFn: () => apiFetch<RankedCandidate[]>(`/api/v1/jobs/${jobId}/candidates`),
    // Only recruiters who own the posting may call this; asking as anyone else is a
    // guaranteed 403/404, so the query is not even issued.
    enabled,
  });
}

/* -------------------------------------------------------------------------- admin */

export function useSystemStats(enabled: boolean): UseQueryResult<SystemStats> {
  return useQuery({
    queryKey: keys.adminStats,
    queryFn: () => apiFetch<SystemStats>("/api/v1/admin/stats"),
    enabled,
  });
}

export function useAdminUsers(enabled: boolean): UseQueryResult<AdminUser[]> {
  return useQuery({
    queryKey: keys.adminUsers,
    queryFn: () => apiFetch<AdminUser[]>("/api/v1/admin/users"),
    enabled,
  });
}

export function useSetUserActive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      apiFetch<AdminUser>(`/api/v1/admin/users/${userId}/active`, {
        method: "PATCH",
        body: { is_active: isActive },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.adminUsers });
      void client.invalidateQueries({ queryKey: keys.adminStats });
    },
  });
}

export function useSetUserRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      apiFetch<AdminUser>(`/api/v1/admin/users/${userId}/role`, {
        method: "PATCH",
        body: { role },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.adminUsers });
      void client.invalidateQueries({ queryKey: keys.adminStats });
    },
  });
}
