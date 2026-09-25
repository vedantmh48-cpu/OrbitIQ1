import type { ReactNode } from "react";

/** Type declarations for the shared UI kit `ui.jsx`. */
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  variant?: "primary" | "ghost" | "danger";
}

export function Spinner(props: { className?: string; label?: string }): React.ReactElement;
export function Button(props: ButtonProps): React.ReactElement;
export function Skeleton(props: { className?: string; lines?: number }): React.ReactElement;
export function Card(props: { children?: ReactNode; className?: string; hover?: boolean }): React.ReactElement;
export function StatCard(props: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
  accent?: string;
  className?: string;
}): React.ReactElement;
export function EmptyState(props: {
  icon?: ReactNode;
  title: string;
  message?: string;
  action?: ReactNode;
  className?: string;
}): React.ReactElement;
export function Badge(props: { children?: ReactNode; color?: "accent" | "green" | "amber" | "red" | "slate" }): React.ReactElement;
export function SimulatedBadge(props: { simulated?: boolean }): React.ReactElement;
export function Alert(props: { type?: "error" | "warn" | "info" | "success"; title?: string; children?: ReactNode }): React.ReactElement;
export function SectionTitle(props: { icon?: ReactNode; children?: ReactNode; className?: string }): React.ReactElement;
export function Toggle(props: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }): React.ReactElement;