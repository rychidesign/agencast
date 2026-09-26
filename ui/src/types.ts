// Tvary odpovědí `agencast serve` podle docs/spec/api.md (0.9.0).

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
  /** Jen u `available: false`. */
  reason?: string;
  last_run?: LastRunRef | null;
}

/** `GET /projects` (0.9.0: `projects_root`, `writable`). */
export interface ProjectList {
  projects: ProjectRef[];
  registry: string;
  /** Výchozí kořen nových projektů (`<projects_root>/<jméno>`). */
  projects_root: string;
  /** Jen v režimu registru s právem zápisu; jinak GUI nabízí příkaz pro CLI. */
  writable: boolean;
}

/** `last_run` v `GET /projects` a u scénářů = první položka `…/runs` zúžená. */
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
  /** Typy kroků hlavního seznamu v pořadí souboru. */
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

/** Strojový stav běhu (api.md „Stav běhu: `state`“). */
export type RunState = "queued" | "running" | "interrupted" | "succeeded" | "failed" | "cancelled" | "dry_run";

export interface RunListItem {
  run_id: string;
  /** Text pro člověka (`failed (<třída> v <krok>)`); stav je `state`. */
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

/** `interrupted` jen v GUI: krok bez konce v běhu, který už neběží. */
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
  /** Složka kroku ve složce běhu (`steps/02-ton/steps/01-kontrola`), bez lomítka na konci. */
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

/** `GET …/runs/<id>/steps/<cesta>`. */
export interface RunStepDetail extends RunStep {
  events: RunEvent[];
  output: unknown;
  files: string[];
}

export interface Run extends RunListItem {
  steps?: RunStep[];
  files?: string[];
  /** Strom kroků ze snímku scénáře (`tree_source: snapshot`), jinak ze současného souboru. */
  tree?: Step[];
  callees?: Record<string, Step[]>;
  tree_source?: "snapshot" | "current";
}

export interface Spend {
  day: string;
  total_usd: number;
  runs: { run_id: string; cost_usd: number; finished_at: string }[];
}

/** Jedna událost z events.jsonl (docs/spec/run-record.md), v `RunStepDetail.events`. */
export type RunEvent = { ts: string; type: string; step?: string } & Record<string, unknown>;
