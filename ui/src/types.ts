// Tvary odpovědí `agencast serve` podle docs/spec/api.md (0.6.0).

export interface ErrorItem {
  message: string;
  file?: string;
  step?: string;
  field?: string;
  line?: number;
}

export interface ProjectRef {
  name: string;
  root: string;
  available: boolean;
}

export interface IoSpec {
  type?: string;
  required?: boolean;
  default?: unknown;
  description?: string;
}

export interface ScenarioSummary {
  name: string;
  etag: string;
  description: string;
  inputs: Record<string, IoSpec> | null;
  outputs: Record<string, IoSpec> | null;
  callable: boolean;
  steps_count: number;
  errors: ErrorItem[];
}

export interface AgentSummary {
  name: string;
  etag: string;
  description: string;
  model: string;
  model_id: string | null;
  skills: string[];
  mcp: unknown;
  tools: unknown;
  errors: ErrorItem[];
}

export interface SkillSummary {
  name: string;
  etag: string;
  description: string;
  errors: ErrorItem[];
}

export interface McpServer {
  name: string;
  type: string;
  agents: string[] | null;
  tools: string[] | null;
  scenarios: string[] | null;
}

export interface Project {
  name: string;
  root: string;
  models: Record<string, string>;
  limits: Record<string, number | string | null>;
  scenarios: ScenarioSummary[];
  agents: AgentSummary[];
  skills: SkillSummary[];
  mcp_servers: McpServer[];
  links: Record<"scenario_agent" | "scenario_scenario" | "agent_skill" | "agent_server", [string, string][]>;
  env: Record<string, boolean>;
  errors: ErrorItem[];
}

export type StepType =
  | "ask" | "task" | "jev" | "image" | "parallel" | "switch" | "call" | "set" | "fail" | "output";

export interface Step {
  nn: number;
  address: (string | number)[];
  id: string;
  type: StepType | null;
  when: string | null;
  fields: Record<string, unknown>;
  refs: string[];
  agent?: string;
  call?: string;
  branches?: Record<string, Step[]>;
  cases?: Record<string, Step[]>;
  default?: Step[] | null;
}

export interface Scenario extends ScenarioSummary {
  steps: Step[];
}

export interface FileDoc {
  path: string;
  etag: string;
  text: string;
  errors: ErrorItem[];
  data?: unknown;
  frontmatter?: Record<string, unknown>;
  body?: string;
}

export interface RunListItem {
  run_id: string;
  status: string;
  cost_usd?: number | null;
  duration_s?: number | null;
  callback?: string;
  scenario?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  current_step?: string | null;
  steps_total?: number | null;
}

export type StepStatus = "running" | "succeeded" | "failed" | "cancelled" | "skipped";

export interface RunStep {
  step: string;
  kind: StepType;
  status: StepStatus;
  branch?: string | null;
  started_at?: string;
  finished_at?: string;
  duration_s?: number;
  cost_usd?: number | null;
  reason_code?: string;
  reason?: string;
}

export interface Run extends RunListItem {
  steps?: RunStep[];
  files?: string[];
}

export interface Spend {
  day: string;
  total_usd: number;
  runs: { run_id: string; cost_usd: number; finished_at: string }[];
}

/** Jedna událost z events.jsonl (docs/spec/run-record.md). */
export type RunEvent = { ts: string; type: string; step?: string } & Record<string, unknown>;
