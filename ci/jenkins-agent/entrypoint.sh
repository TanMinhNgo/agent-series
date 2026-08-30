#!/bin/sh
set -eu

: "${JENKINS_URL:?JENKINS_URL is required}"
: "${JENKINS_AGENT_NAME:?JENKINS_AGENT_NAME is required}"
: "${JENKINS_SECRET:?JENKINS_SECRET is required}"

agent_jar=/opt/jenkins-agent/agent.jar
case "$JENKINS_URL" in
  https://*|http://host.docker.internal:8080|http://jenkins:8080) ;;
  *) echo "JENKINS_URL must use HTTPS or an approved local controller URL." >&2; exit 1 ;;
esac
curl --fail --silent --show-error --max-redirs 0 \
  "${JENKINS_URL%/}/jnlpJars/agent.jar" --output "$agent_jar"

exec java -jar "$agent_jar" \
  -url "$JENKINS_URL" \
  -secret "$JENKINS_SECRET" \
  -name "$JENKINS_AGENT_NAME" \
  -workDir "${JENKINS_AGENT_WORKDIR:-/home/jenkins/agent}"
