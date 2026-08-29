/**
 * API response types, mirroring the backend Pydantic schemas.
 *
 * Hand-written rather than generated from the OpenAPI document. At this size the generator
 * plus its build step costs more than it saves, and these read better than generated output.
 * The trade is real: a backend change that is not mirrored here will only surface at runtime,
 * so the integration points are kept few and obvious.
 */

export type UserRole = "job_seeker" | "recruiter" | "admin";
export type ParseStatus = "pending" | "processing" | "complete" | "failed";
export type SkillStatus = "suggested" | "confirmed" | "rejected" | "learning";
export type SkillSource = "extracted" | "manual";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  email_verified: boolean;
  /** False for a Google-only account — nothing to change a password to. */
  has_password: boolean;
}

/** What POST /auth/register returns: the account plus, in local/CI only, the raw
 * verification token that would otherwise only ever reach a real inbox. */
export interface RegisterResult extends User {
  dev_verification_token: string | null;
}

export interface ForgotPasswordResult {
  dev_reset_token: string | null;
}

export interface Skill {
  id: string;
  canonical_name: string;
  slug: string;
  category: string;
  difficulty: number;
}

export interface UserSkill {
  skill: Skill;
  source: SkillSource;
  status: SkillStatus;
  proficiency: number | null;
  occurrences: number;
}

export interface SkillProfile {
  confirmed: UserSkill[];
  suggested: UserSkill[];
  /** Skills the user does not have yet and is actively working on. */
  learning: UserSkill[];
  total_confirmed: number;
  total_suggested: number;
  total_learning: number;
}

export interface Resume {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: ParseStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSkill {
  skill: Skill;
  importance: number;
}

export interface Job {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  description: string;
  is_public: boolean;
  created_by: string;
  required_skills: JobSkill[];
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  is_public: boolean;
  created_by: string;
  skill_count: number;
  created_at: string;
}

export interface SkillGap {
  skill_id: string;
  canonical_name: string;
  importance: number;
}

export interface MatchResult {
  job_id: string;
  score: number;
  skill_coverage: number;
  semantic_similarity: number;
  /** False while a resume or job is still awaiting its embedding; the score will change. */
  semantic_available: boolean;
  matched: SkillGap[];
  missing: SkillGap[];
  total_required: number;
}

export interface PathStep {
  order: number;
  skill_id: string;
  canonical_name: string;
  slug: string;
  difficulty: number;
  /** False when the graph inferred this step; the job description never named it. */
  directly_required: boolean;
  unlocked_by: string[];
}

export interface LearningPath {
  steps: PathStep[];
  step_count: number;
  total_effort: number;
  unreachable: string[];
}

/* ------------------------------------------------------------------- career goals */

/** A required skill, plus whether the user is currently working on it. */
export interface GoalSkillGap extends SkillGap {
  is_learning: boolean;
}

export interface GoalProgress {
  id: string;
  job: JobSummary;
  created_at: string;
  achieved_at: string | null;
  /** The match score frozen at the moment the goal was set. Never changes. */
  baseline_score: number;
  current_score: number;
  /** current_score - baseline_score. Negative is possible and honest. */
  delta: number;
  /** Progress toward the achievement threshold, 0-100, for the progress bar. */
  readiness: number;
  is_achievable_now: boolean;
  matched: GoalSkillGap[];
  missing: GoalSkillGap[];
  learning_count: number;
  semantic_available: boolean;
}

export interface Achievement {
  id: string;
  job: JobSummary;
  baseline_score: number;
  created_at: string;
  achieved_at: string | null;
}

/* --------------------------------------------------------------- candidate ranking */

export interface RankedCandidate {
  user_id: string;
  full_name: string | null;
  score: number;
  skill_coverage: number;
  semantic_similarity: number;
  matched: GoalSkillGap[];
  missing: GoalSkillGap[];
  has_resume: boolean;
}

/* -------------------------------------------------------------------------- admin */

export interface SystemStats {
  total_users: number;
  job_seekers: number;
  recruiters: number;
  admins: number;
  inactive_users: number;
  total_jobs: number;
  public_jobs: number;
  total_resumes: number;
  resumes_pending: number;
  resumes_failed: number;
  active_goals: number;
  achieved_goals: number;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  skill_count: number;
  resume_count: number;
}

export interface SkillPath extends LearningPath {
  /** Least-effort chain from something you already know to the target skill. */
  shortest_route: string[];
}

export interface SkillEdge {
  prerequisite_id: string;
  skill_id: string;
}

export interface SkillGraphData {
  skills: Skill[];
  edges: SkillEdge[];
}
