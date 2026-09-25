/**
 * SatQuery AI - Auth & Account Management TypeScript models.
 *
 * Mirrors the v1 FastAPI contracts under `/api/v1/auth/*`.
 */

export type AccountType = "student" | "researcher" | "gis_analyst" | "organization";
export type OrgType = "government" | "defense" | "private";
export type Role = "user" | "analyst" | "admin";
export type VerificationPurpose = "register" | "password_change";

// ---------------------------------------------------------------------------
// User / session models
// ---------------------------------------------------------------------------

export interface StudentProfile {
  institution: string;
  course: string;
  year_of_study: number;
}

export interface ResearcherProfile {
  institution: string;
  research_field: string;
  orcid: string;
  profile_link: string;
}

export interface GisAnalystProfile {
  employer: string;
  job_title: string;
  years_experience: number;
  primary_tools: string;
}

export interface OrganizationProfile {
  org_name: string;
  org_type: OrgType;
  official_domain: string;
  admin_name: string;
  admin_email: string;
  team_size: number;
  intended_use: string;
}

export type ProfileRecord =
  | StudentProfile
  | ResearcherProfile
  | GisAnalystProfile
  | OrganizationProfile
  | Record<string, never>;

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  account_type: AccountType;
  org_type: OrgType | null;
  active: boolean;
  email_verified: boolean;
  mfa_enabled: boolean;
  mfa_required: boolean;
  inactivity_timeout_minutes: number;
  password_changed_at: string | null;
  profile: ProfileRecord;
  settings?: Record<string, unknown>;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  session_id: string;
  expires_at: string;
}

export interface Session {
  session_id: string;
  device_label: string;
  ip_address: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

// ---------------------------------------------------------------------------
// Registration request/response models
// ---------------------------------------------------------------------------

export interface BaseRegistration {
  password: string;
  confirm_password: string;
}

export interface StudentRegistration extends BaseRegistration {
  account_type: "student";
  full_name: string;
  email: string;
  institution: string;
  course: string;
  year_of_study: number;
}

export interface ResearcherRegistration extends BaseRegistration {
  account_type: "researcher";
  full_name: string;
  email: string;
  institution: string;
  research_field: string;
  orcid?: string;
  profile_link?: string;
}

export interface GisAnalystRegistration extends BaseRegistration {
  account_type: "gis_analyst";
  full_name: string;
  email: string;
  employer: string;
  job_title: string;
  years_experience: number;
  primary_tools: string;
}

export interface OrganizationRegistration extends BaseRegistration {
  account_type: "organization";
  org_name: string;
  org_type: OrgType;
  official_domain: string;
  admin_name: string;
  admin_email: string;
  team_size: number;
  intended_use: string;
}

export type RegistrationPayload =
  | StudentRegistration
  | ResearcherRegistration
  | GisAnalystRegistration
  | OrganizationRegistration;

export interface RegisterResponse {
  user: User;
  requires_email_verification: true;
  email: string;
  verification_expires_in_minutes: number;
  verification_purpose: VerificationPurpose;
  demo_code?: string;
}

// ---------------------------------------------------------------------------
// Email verification
// ---------------------------------------------------------------------------

export interface VerifyEmailRequest {
  email: string;
  code: string;
}

export interface VerifyEmailResponse extends AuthTokens {
  user: User;
}

export interface ResendVerificationRequest {
  email: string;
}

export interface ResendVerificationResponse {
  ok: boolean;
  message: string;
  demo_code?: string;
}

// ---------------------------------------------------------------------------
// Login / MFA
// ---------------------------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export type LoginResponse =
  | (AuthTokens & { user: User })
  | {
      mfa_required: true;
      mfa_token: string;
      email: string;
      expires_in_seconds: number;
    }
  | {
      mfa_setup_required: true;
      mfa_token: string;
      email: string;
      user: User;
    };

export interface MfaChallengeRequest {
  mfa_token: string;
  code: string;
}

export interface MfaChallengeResponse extends AuthTokens {
  user: User;
}

export interface MfaSetupResponse {
  secret: string;
  otpauth_url: string;
  expires_in_seconds: number;
  hint: string;
}

export interface MfaVerifyRequest {
  code: string;
}

export interface MfaVerifyResponse {
  ok: boolean;
  mfa_enabled: boolean;
  message?: string;
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export interface SessionsResponse {
  sessions: Session[];
}

export interface RevokeAllResponse {
  ok: boolean;
  revoked_count: number;
}

// ---------------------------------------------------------------------------
// Password change
// ---------------------------------------------------------------------------

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface ChangePasswordResponse {
  ok: boolean;
  password_change_id: string;
  expires_in_minutes: number;
  message: string;
  demo_code?: string;
}

export interface ChangePasswordVerifyRequest {
  password_change_id: string;
  otp_code: string;
}

export interface ChangePasswordVerifyResponse {
  ok: boolean;
  revoked_sessions: number;
  message: string;
}

// ---------------------------------------------------------------------------
// Heartbeat / inactivity
// ---------------------------------------------------------------------------

export interface HeartbeatResponse {
  ok: boolean;
  last_seen_at: string;
  expires_at: string;
  inactivity_timeout_minutes: number;
}

export interface InactivityTimeoutUpdate {
  inactivity_timeout_minutes: number;
}

export interface InactivityTimeoutResponse {
  inactivity_timeout_minutes: number;
  options: number[];
}

export interface ApiErrorBody {
  detail: string;
  code?: string;
  error?: boolean;
}

// ---------------------------------------------------------------------------
// WebSocket security notifications
// ---------------------------------------------------------------------------

export type NotificationEvent =
  | { type: "session_revoked"; session_id: string; ts: string }
  | { type: "password_changed"; except_session_id?: string; ts: string }
  | { type: "account_deleted"; ts: string };

export type SessionRevokedReason = "revoked" | "expired" | "inactive" | "password_changed";

// ---------------------------------------------------------------------------
// Auto-logout / idle configuration
// ---------------------------------------------------------------------------

/** User-selectable inactivity windows (minutes). Never an option for the UI. */
export const INACTIVITY_OPTIONS = [5, 15, 30, 60] as const;

export type InactivityOption = (typeof INACTIVITY_OPTIONS)[number];

export interface IdleConfig {
  /** Effective timeout in minutes for the current user. */
  timeoutMinutes: number;
  /** Seconds before timeout at which the (non-dismissible) warning shows. */
  warningLeadSeconds: number;
  /** Maximum allowed window; Government/Defense orgs clamp to 15. */
  maxTimeoutMinutes: number;
  /** True for government/defense organization accounts (no "Never"). */
  governmentTier: boolean;
  /** Options the user may select in Settings. */
  selectableOptions: number[];
}

export interface AuthError {
  status: number;
  code?: string;
  message: string;
}