"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch } from "./api";
import type {
  Job,
  JobSummary,
  LearningPath,
  MatchResult,
  Resume,
  Skill,
  SkillProfile,
  SkillStatus,
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
