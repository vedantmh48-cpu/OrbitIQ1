/**
 * Typed v1 auth API. All calls hit the new `/api/v1/auth/*` backend.
 */
import { api, ApiError } from "./client";
import type {
  ChangePasswordRequest,
  ChangePasswordResponse,
  ChangePasswordVerifyRequest,
  ChangePasswordVerifyResponse,
  HeartbeatResponse,
  InactivityTimeoutResponse,
  InactivityTimeoutUpdate,
  LoginRequest,
  LoginResponse,
  MfaChallengeRequest,
  MfaChallengeResponse,
  MfaSetupResponse,
  MfaVerifyRequest,
  MfaVerifyResponse,
  RegisterResponse,
  RegistrationPayload,
  ResendVerificationResponse,
  RevokeAllResponse,
  SessionsResponse,
  VerifyEmailResponse,
} from "../types/auth";

const AUTH = "/api/v1/auth";

/** Thrown when login needs a follow-up step (MFA). Carries the server body. */
export class AuthStepRequired extends Error {
  body: LoginResponse;
  constructor(body: LoginResponse) {
    super("Additional authentication step required.");
    this.body = body;
  }
}

export async function register(params: RegistrationPayload): Promise<RegisterResponse> {
  return api.post<RegisterResponse>(`${AUTH}/register`, params, { auth: false });
}

export async function verifyEmail(email: string, code: string): Promise<VerifyEmailResponse> {
  return api.post<VerifyEmailResponse>(`${AUTH}/verify-email`, { email, code }, { auth: false });
}

export async function resendVerification(email: string): Promise<ResendVerificationResponse> {
  return api.post<ResendVerificationResponse>(`${AUTH}/verify-email/resend`, { email }, { auth: false });
}

export async function login(params: LoginRequest): Promise<LoginResponse> {
  return api.post<LoginResponse>(`${AUTH}/login`, params, { auth: false });
}

export async function mfaChallenge(params: MfaChallengeRequest): Promise<MfaChallengeResponse> {
  return api.post<MfaChallengeResponse>(`${AUTH}/mfa/challenge`, params, { auth: false });
}

/** Load the current user profile (used to restore/sync the session). */
export async function apiGetMe() {
  return api.get<import("../types/auth").User>("/api/users/me");
}

export async function logout(refreshToken: string): Promise<{ ok: boolean }> {
  return api.post(`${AUTH}/logout`, { refresh_token: refreshToken }, { auth: true });
}

export async function heartbeat(): Promise<HeartbeatResponse> {
  return api.post<HeartbeatResponse>(`${AUTH}/heartbeat`, {}, { auth: true });
}

export async function listSessions(): Promise<SessionsResponse> {
  return api.get<SessionsResponse>(`${AUTH}/sessions`);
}

export async function revokeSession(sessionId: string): Promise<{ ok: boolean }> {
  return api.del(`${AUTH}/sessions/${encodeURIComponent(sessionId)}`);
}

export async function revokeAllSessions(): Promise<RevokeAllResponse> {
  return api.post<RevokeAllResponse>(`${AUTH}/sessions/revoke-all`);
}

export async function changePassword(params: ChangePasswordRequest): Promise<ChangePasswordResponse> {
  return api.post<ChangePasswordResponse>(`${AUTH}/change-password`, params);
}

export async function changePasswordVerify(
  params: ChangePasswordVerifyRequest
): Promise<ChangePasswordVerifyResponse> {
  return api.post<ChangePasswordVerifyResponse>(`${AUTH}/change-password/verify`, params);
}

export async function mfaSetup(): Promise<MfaSetupResponse> {
  return api.post<MfaSetupResponse>(`${AUTH}/mfa/setup`);
}

export async function mfaVerify(params: MfaVerifyRequest): Promise<MfaVerifyResponse> {
  return api.post<MfaVerifyResponse>(`${AUTH}/mfa/verify`, params);
}

export async function mfaDisable(params: MfaVerifyRequest): Promise<MfaVerifyResponse> {
  return api.post<MfaVerifyResponse>(`${AUTH}/mfa/disable`, params);
}

export async function setInactivityTimeout(
  minutes: number
): Promise<InactivityTimeoutResponse> {
  const body: InactivityTimeoutUpdate = { inactivity_timeout_minutes: minutes };
  return api.put<InactivityTimeoutResponse>(`${AUTH}/inactivity-timeout`, body);
}

export function errorCode(err: unknown): string | undefined {
  return err instanceof ApiError ? err.code : undefined;
}

export { ApiError };