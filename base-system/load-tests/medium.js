/*
 * =============================================================================
 * k6 - Load test MÉDIO
 * =============================================================================
 * Carga sustentada com ramp-up. Cenário principal do experimento.
 *
 * Stages: 0 -> 30 VUs em 1m, manter 30 VUs por 3m, ramp-down em 30s
 * Total:  ~5min, ~9000 requisições esperadas
 *
 * Uso:
 *   k6 run -e API_URL=http://localhost:8080 -e ENV_LABEL=A medium.js
 * =============================================================================
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const errors = new Counter('test_errors');
const slowRequests = new Counter('test_slow_requests');
const latency = new Trend('test_latency_ms', true);

export const options = {
  stages: [
    { duration: '1m',  target: 30 },   // ramp-up
    { duration: '3m',  target: 30 },   // sustain
    { duration: '30s', target: 0  },   // ramp-down
  ],
  thresholds: {
    http_req_failed: ['rate<0.20'],
    http_req_duration: ['p(95)<5000'],
  },
  tags: {
    env: __ENV.ENV_LABEL || 'unknown',
    test: 'medium',
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8080';

export default function () {
  const payload = JSON.stringify({
    task_id: `k6-medium-${__VU}-${__ITER}`,
    complexity: Math.floor(Math.random() * 7) + 2,  // 2..8
  });

  const start = Date.now();
  const res = http.post(`${API_URL}/process`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '15s',
  });
  const elapsed = Date.now() - start;
  latency.add(elapsed);

  if (elapsed > 2000) slowRequests.add(1);

  const ok = check(res, {
    'status 200': (r) => r.status === 200,
  });
  if (!ok) errors.add(1);

  sleep(Math.random() * 0.3 + 0.05);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    [`/results/medium-${__ENV.ENV_LABEL || 'unknown'}-${Date.now()}.json`]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const m = data.metrics;
  return `
======================================================================
RESUMO - Teste Médio (env=${__ENV.ENV_LABEL || 'unknown'})
======================================================================
Iterations:          ${m.iterations.values.count}
Failed requests:     ${(m.http_req_failed.values.rate * 100).toFixed(2)}%
Slow requests (>2s): ${m.test_slow_requests ? m.test_slow_requests.values.count : 0}
Latency p50/p95/p99: ${m.http_req_duration.values['p(50)'].toFixed(1)}ms / ${m.http_req_duration.values['p(95)'].toFixed(1)}ms / ${m.http_req_duration.values['p(99)'].toFixed(1)}ms
Throughput:          ${m.http_reqs.values.rate.toFixed(2)} req/s
======================================================================
`;
}
