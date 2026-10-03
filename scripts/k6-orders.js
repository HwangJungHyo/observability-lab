import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';

// The runner supplies one run ID shared by all virtual users.
const PROFILE = __ENV.PROFILE || 'smoke';
const RUN_ID = __ENV.RUN_ID || '';
const BASE_URL = (__ENV.BASE_URL || 'http://order-api:8080').replace(/\/$/, '');
if (!/^[A-Za-z0-9_-]{1,40}$/.test(RUN_ID)) {
  throw new Error('RUN_ID must contain 1-40 letters, digits, underscores or hyphens');
}

// Labels are fixed and low cardinality. Transitions are reported separately.
const profiles = {
  smoke: [{ label: 'steady_1', seconds: 30, target: 1 }],
  steps: [
    { label: 'steady_1', seconds: 60, target: 1 },
    { label: 'ramp_3', seconds: 10, target: 3 },
    { label: 'steady_3', seconds: 60, target: 3 },
    { label: 'ramp_5', seconds: 10, target: 5 },
    { label: 'steady_5', seconds: 60, target: 5 },
  ],
  spike: [
    { label: 'before_1', seconds: 30, target: 1 },
    { label: 'ramp_10', seconds: 1, target: 10 },
    { label: 'peak_10', seconds: 30, target: 10 },
    { label: 'ramp_down', seconds: 1, target: 1 },
    { label: 'recovery_1', seconds: 60, target: 1 },
  ],
  // Run only after 5 VUs were shown to be stable in the steps profile.
  soak: [
    { label: 'ramp_5', seconds: 10, target: 5 },
    { label: 'steady_5', seconds: 300, target: 5 },
  ],
};
if (!Object.prototype.hasOwnProperty.call(profiles, PROFILE)) {
  throw new Error('PROFILE must be smoke, steps, spike or soak');
}
const phases = profiles[PROFILE];
const businessFailed = new Rate('business_failed');
const phaseMetrics = {};
for (const phase of phases) {
  phaseMetrics[phase.label] = {
    requests: new Counter(`orders_${phase.label}_requests`),
    failed: new Rate(`orders_${phase.label}_failed`),
    duration: new Trend(`orders_${phase.label}_duration_ms`, true),
  };
}

http.setResponseCallback(http.expectedStatuses(201));
export const options = {
  scenarios: {
    orders: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: phases.map(p => ({ duration: `${p.seconds}s`, target: p.target })),
      gracefulRampDown: '6s',
      gracefulStop: '6s',
    },
  },
  // Training stop rules, not a production SLO. These use cumulative metrics.
  thresholds: {
    business_failed: [
      'rate==0',
      { threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '30s' },
    ],
    http_req_duration: [
      { threshold: 'p(95)<1000', abortOnFail: true, delayAbortEval: '30s' },
    ],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
  tags: { run_id: RUN_ID, profile: PROFILE },
};

function phaseAt(seconds) {
  let end = 0;
  for (const phase of phases) {
    end += phase.seconds;
    if (seconds < end) return phase;
  }
  return phases[phases.length - 1];
}

let loggedFailures = 0; // Per VU: avoid flooding the generator's output.
export default function () {
  // Assign a request to the phase in which it starts, even if it finishes later.
  const phase = phaseAt(exec.instance.currentTestRunDuration / 1000);
  const requestId = `${RUN_ID}-${__VU}-${__ITER}`;
  const response = http.post(`${BASE_URL}/orders`, JSON.stringify({ amount: 10000 }), {
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
    timeout: '5s',
    redirects: 0,
    tags: { name: 'POST /orders', phase: phase.label },
  });
  let body = null;
  try { body = response.json(); } catch (_) { /* Empty or non-JSON is a failure. */ }
  const passed = check(response, {
    'HTTP 201': r => r.status === 201,
    'order confirmed with IDs': () => Boolean(
      body && body.status === 'confirmed' && body.amount === 10000 &&
      typeof body.order_id === 'string' && body.order_id.length > 0 &&
      typeof body.payment_id === 'string' && body.payment_id.length > 0
    ),
  }, { phase: phase.label });
  businessFailed.add(!passed);
  phaseMetrics[phase.label].requests.add(1);
  phaseMetrics[phase.label].failed.add(!passed);
  phaseMetrics[phase.label].duration.add(response.timings.duration);

  // IDs go to sample logs, not request-level metric labels.
  if (__ITER === 0 || (!passed && loggedFailures < 3)) {
    console.log(JSON.stringify({
      event: 'request_sample', run_id: RUN_ID, phase: phase.label,
      request_id: requestId, trace_id: response.headers['X-Trace-Id'] || '',
      http_status: response.status, duration_ms: response.timings.duration,
      passed, error_code: response.error_code || 0,
    }));
    if (!passed) loggedFailures += 1;
  }
  sleep(0.2); // Each VU waits after a response; this does not set a fixed RPS.
}

export function handleSummary(data) {
  const values = name => data.metrics[name] ? data.metrics[name].values : {};
  const phasesReport = phases.map(p => {
    const n = values(`orders_${p.label}_requests`).count || 0;
    const failed = values(`orders_${p.label}_failed`);
    return {
      phase: p.label, planned_seconds: p.seconds, target_vus: p.target,
      completed_requests: n,
      failed_requests: failed.passes || 0, // Rate's true samples mean failures.
      failure_rate: n ? failed.rate : null,
      request_duration_ms: values(`orders_${p.label}_duration_ms`),
    };
  });
  const report = {
    run_id: RUN_ID, profile: PROFILE, base_url: BASE_URL,
    test_configuration: {
      expected_application_cpus_each: 0.5,
      expected_application_memory_mib_each: 512,
      generator_cpus: 1, generator_memory_mib: 512,
      stop_rules: 'After 30s: cumulative failure rate >= 5% or HTTP p95 >= 1000ms',
      limits_verified_by_script: false,
    },
    planned_seconds: phases.reduce((sum, p) => sum + p.seconds, 0),
    finished_utc: new Date().toISOString(), phases: phasesReport,
    notes: [
      'Phase is assigned at request start; ramp-down may drain for up to 6 seconds.',
      'HTTP duration excludes connection setup; do not equate it with curl time_total.',
      'Raw points include request timestamps and status; request IDs are sampled in console logs.',
    ],
    k6: data,
  };
  let text = `\nRUN_ID=${RUN_ID}\nPROFILE=${PROFILE}\n`;
  for (const p of phasesReport) {
    text += `${p.phase}: requests=${p.completed_requests} failed=${p.failed_requests}` +
      ` avg_ms=${p.request_duration_ms.avg ?? 'n/a'}` +
      ` p95_ms=${p.request_duration_ms['p(95)'] ?? 'n/a'}\n`;
  }
  const serialized = JSON.stringify(report, null, 2);
  return { stdout: text, [`${RUN_ID}.summary.json`]: serialized };
}
