/*
 * =============================================================================
 * k6 - Load test BÁSICO
 * =============================================================================
 * Carga leve para validação funcional e baseline.
 *
 * Padrão: 10 VUs por 1 minuto
 *
 * Uso:
 *   k6 run -e API_URL=http://localhost:8080 -e ENV_LABEL=A basic.js
 * =============================================================================
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// Métricas customizadas - exportadas no resumo final do k6
const errors = new Counter('test_errors');
const latency = new Trend('test_latency_ms', true);

export const options = {
  vus: 10,
  duration: '1m',
  thresholds: {
    // SLOs do experimento
    http_req_failed: ['rate<0.20'],      // <20% de erros (5% inj + 2% inj api + ruído)
    http_req_duration: ['p(95)<3000'],   // p95 < 3s (slow injection é 2.5s)
  },
  // Tags aplicadas a todas as métricas - permitem segregar A vs B
  tags: {
    env: __ENV.ENV_LABEL || 'unknown',
    test: 'basic',
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8080';

export default function () {
  const payload = JSON.stringify({
    task_id: `k6-${__VU}-${__ITER}`,
    complexity: Math.floor(Math.random() * 5) + 1,  // 1..5
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: '15s',
  };

  const start = Date.now();
  const res = http.post(`${API_URL}/process`, payload, params);
  latency.add(Date.now() - start);

  const ok = check(res, {
    'status 200': (r) => r.status === 200,
    'has task_id': (r) => {
      try { return JSON.parse(r.body).task_id !== undefined; }
      catch (e) { return false; }
    },
  });

  if (!ok) errors.add(1);

  sleep(Math.random() * 0.5 + 0.1);  // 100..600ms entre iterações
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    [`/results/basic-${__ENV.ENV_LABEL || 'unknown'}-${Date.now()}.json`]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const m = data.metrics;
  return `
======================================================================
RESUMO - Teste Básico (env=${__ENV.ENV_LABEL || 'unknown'})
======================================================================
Iterations:          ${m.iterations.values.count}
Failed requests:     ${(m.http_req_failed.values.rate * 100).toFixed(2)}%
Latency p50/p95/p99: ${m.http_req_duration.values['p(50)'].toFixed(1)}ms / ${m.http_req_duration.values['p(95)'].toFixed(1)}ms / ${m.http_req_duration.values['p(99)'].toFixed(1)}ms
Throughput:          ${m.http_reqs.values.rate.toFixed(2)} req/s
======================================================================
`;
}
