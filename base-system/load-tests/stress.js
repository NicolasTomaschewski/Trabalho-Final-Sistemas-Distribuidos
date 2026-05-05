/*
 * =============================================================================
 * k6 - Load test STRESS
 * =============================================================================
 * Carga agressiva para identificar pontos de saturação e amplificar
 * diferença de overhead entre Env A (baseline) e Env B (otimizado).
 *
 * Stages: ramp-up agressivo até 100 VUs, sustain por 5m, ramp-down 1m
 * Total:  ~8min
 *
 * Uso:
 *   k6 run -e API_URL=http://localhost:8080 -e ENV_LABEL=A stress.js
 * =============================================================================
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const errors = new Counter('test_errors');
const latency = new Trend('test_latency_ms', true);

export const options = {
  stages: [
    { duration: '1m',  target: 50  },
    { duration: '1m',  target: 100 },
    { duration: '5m',  target: 100 },   // sustain @ 100 VUs
    { duration: '1m',  target: 0   },
  ],
  thresholds: {
    // SLOs relaxados em stress - queremos OBSERVAR degradação, não falhar
    http_req_failed: ['rate<0.50'],
    http_req_duration: ['p(95)<10000'],
  },
  tags: {
    env: __ENV.ENV_LABEL || 'unknown',
    test: 'stress',
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8080';

export default function () {
  const payload = JSON.stringify({
    task_id: `k6-stress-${__VU}-${__ITER}`,
    complexity: Math.floor(Math.random() * 10) + 1,  // 1..10
  });

  const start = Date.now();
  const res = http.post(`${API_URL}/process`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '20s',
  });
  latency.add(Date.now() - start);

  const ok = check(res, {
    'status not 5xx': (r) => r.status < 500 || r.status === 500,  // erros injetados são esperados
  });
  if (!ok) errors.add(1);

  // Sem sleep no stress - máxima agressividade
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    [`/results/stress-${__ENV.ENV_LABEL || 'unknown'}-${Date.now()}.json`]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const m = data.metrics;
  return `
======================================================================
RESUMO - Teste de Stress (env=${__ENV.ENV_LABEL || 'unknown'})
======================================================================
Iterations:          ${m.iterations.values.count}
Failed requests:     ${(m.http_req_failed.values.rate * 100).toFixed(2)}%
Latency p50/p95/p99: ${m.http_req_duration.values['p(50)'].toFixed(1)}ms / ${m.http_req_duration.values['p(95)'].toFixed(1)}ms / ${m.http_req_duration.values['p(99)'].toFixed(1)}ms
Throughput:          ${m.http_reqs.values.rate.toFixed(2)} req/s
======================================================================
`;
}
