#!/usr/bin/env python3
"""
================================================================================
inject_faults.py - Injeção EXTERNA de falhas
================================================================================
As principais falhas (5% erros, 3% slow) já são injetadas internamente pelo
worker. Este script complementa com falhas de INFRAESTRUTURA, controladas
manualmente, para validar a capacidade diagnóstica em cenários adversos:

    - pause:     pausa o container por X segundos (simula GC stop-the-world)
    - kill:      mata um container (testa detecção de outage)
    - latency:   injeta latência de rede via tc (Linux-only)
    - cpu-stress: aplica stress CPU em um container
    - restart:   reinicia o worker (testa pickup de novos traces)

Uso:
    python inject_faults.py --env A --action pause   --target worker --duration 10
    python inject_faults.py --env A --action latency --target worker --ms 500 --duration 30
    python inject_faults.py --env B --action kill    --target worker
================================================================================
"""

import argparse
import subprocess
import time
import sys


def run(cmd, check=True):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def container_name(env: str, target: str) -> str:
    """env=A target=worker -> env-a-worker"""
    return f"env-{env.lower()}-{target}"


def action_pause(name: str, duration: int):
    print(f"Pausando {name} por {duration}s...")
    run(["docker", "pause", name])
    time.sleep(duration)
    run(["docker", "unpause", name])
    print(f"  {name} retomado")


def action_kill(name: str):
    print(f"Matando {name}...")
    run(["docker", "kill", name])
    print(f"  {name} foi morto. Use 'docker compose up -d' para restaurar.")


def action_restart(name: str):
    print(f"Reiniciando {name}...")
    run(["docker", "restart", name])


def action_latency(name: str, ms: int, duration: int):
    """Adiciona latência de rede usando tc dentro do container."""
    print(f"Adicionando {ms}ms de latência de rede em {name} por {duration}s...")
    # tc precisa de NET_ADMIN; assumimos cap_add ou privileged
    cmd_install = ["docker", "exec", name, "sh", "-c",
                   "command -v tc >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq iproute2)"]
    try:
        run(cmd_install, check=False)
    except Exception:
        pass

    add = ["docker", "exec", name, "tc", "qdisc", "add", "dev", "eth0",
           "root", "netem", "delay", f"{ms}ms"]
    rem = ["docker", "exec", name, "tc", "qdisc", "del", "dev", "eth0", "root"]
    try:
        run(add)
        time.sleep(duration)
    finally:
        run(rem, check=False)
    print(f"  latência removida")


def action_cpu_stress(name: str, duration: int):
    """Stress CPU usando 'yes' loops dentro do container."""
    print(f"Aplicando CPU stress em {name} por {duration}s...")
    pid = run(["docker", "exec", "-d", name, "sh", "-c",
               f"yes > /dev/null & yes > /dev/null & yes > /dev/null & sleep {duration}; pkill -f 'yes'"],
              check=False)
    time.sleep(duration + 2)
    print(f"  stress finalizado")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, choices=["A", "B"])
    ap.add_argument("--target", required=True,
                    choices=["api", "worker", "otel-collector", "jaeger", "prometheus"])
    ap.add_argument("--action", required=True,
                    choices=["pause", "kill", "restart", "latency", "cpu-stress"])
    ap.add_argument("--duration", type=int, default=10)
    ap.add_argument("--ms", type=int, default=200,
                    help="Latência adicional em ms (action=latency)")
    args = ap.parse_args()

    name = container_name(args.env, args.target)
    print(f"Container alvo: {name}")
    print(f"Ação: {args.action}")
    print()

    if args.action == "pause":
        action_pause(name, args.duration)
    elif args.action == "kill":
        action_kill(name)
    elif args.action == "restart":
        action_restart(name)
    elif args.action == "latency":
        action_latency(name, args.ms, args.duration)
    elif args.action == "cpu-stress":
        action_cpu_stress(name, args.duration)

    print("\nInjeção concluída.")


if __name__ == "__main__":
    sys.exit(main() or 0)
