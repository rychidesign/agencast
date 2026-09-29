// Shapes of `agencast serve` responses per docs/spec/api.md (0.9.0).

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
  counts: { scenarios: number; agents: number };
  spend_today_usd: number;
  /** Only for `available: false`. */
  reason?: string;
  last_run?: LastRunRef | null;
}

/** `GET /projects` (0.9.0: `projects_root`, `writable`). */
export interface ProjectList {
  projects: ProjectRef[];
  registry: string;
  /** Default root for new projects (`<projects_root>/<name>`). */
  projects_root: string;
  /** Only in registry mode with write permission; otherwise the GUI offers a CLI command. */
  writable: boolean;
}

/** `last_run` in `GET /projects` and on scenarios = the first item of `…/runs`, narrowed down. */
export interface LastRunRef {
  run_id: string;
  state: RunState;
  started_at: string | null;
  finished_at: string | null;
  cost_usd: number | null;
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
  /** Step types of the main list in file order. */
  types: (StepType | null)[];
  last_run: LastRunRef | null;
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
  links: Record<"scenario_agent" | "scenario_scenario" | "agent_skill" | "agent_server", [string, string][]>
    & { scenario_step_agent: [string, string, string][] };
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

/** Machine-readable run state (api.md "Run state: `state`"). */
export type RunState = "queued" | "running" | "interrupted" | "succeeded" | "failed" | "cancelled" | "dry_run";

export interface RunListItem {
  run_id: string;
  /** Human-readable text (`failed (<class> in <step>)`); the machine state is `state`. */
  status: string;
  state: RunState;
  cost_usd?: number | null;
  duration_s?: number | null;
  callback?: string;
  scenario?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  current_step?: string | null;
  steps_total?: number | null;
  fake?: boolean | null;
  queue_position?: number | null;
  current_nn?: number | null;
  steps_done?: number | null;
}

/** `interrupted` only in the GUI: a step without an end in a run that is no longer running. */
export type StepStatus = "running" | "succeeded" | "failed" | "cancelled" | "skipped" | "interrupted";

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
  nn?: number | null;
  /** Step folder inside the run folder (`steps/02-tone/steps/01-check`), without a trailing slash. */
  dir?: string | null;
  error?: { class: string; message: string } | null;
  continued?: boolean;
  default_used?: boolean;
  calls?: RunCall[];
  turns?: number;
  tool_calls?: number;
  answers?: Record<string, unknown>;
}

export interface RunCall {
  attempt: number;
  alias: string | null;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  finish_reason: string | null;
  structured_output: string | null;
  duration_s: number | null;
}

/** `GET …/runs/<id>/steps/<path>`. */
export interface RunStepDetail extends RunStep {
  events: RunEvent[];
  output: unknown;
  files: string[];
}

export interface Run extends RunListItem {
  steps?: RunStep[];
  files?: string[];
  /** Step tree from the scenario snapshot (`tree_source: snapshot`), otherwise from the current file. */
  tree?: Step[];
  callees?: Record<string, Step[]>;
  tree_source?: "snapshot" | "current";
}

export interface Spend {
  day: string;
  total_usd: number;
  runs: { run_id: string; cost_usd: number; finished_at: string }[];
}

/** One event from events.jsonl (docs/spec/run-record.md), in `RunStepDetail.events`. */
export type RunEvent = { ts: string; type: string; step?: string } & Record<string, unknown>;
