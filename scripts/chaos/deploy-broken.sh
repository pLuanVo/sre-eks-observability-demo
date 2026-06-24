#!/usr/bin/env bash
set -euo pipefail
echo "Deploying broken image to payment-service (triggers CrashLoopBackOff)..."
kubectl set image deployment/payment-service payment-service=busybox:latest -n demo
echo "Waiting for pods to crash..."
sleep 10
kubectl get pods -n demo -l app.kubernetes.io/name=payment-service
