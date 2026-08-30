#!/bin/sh
set -eu

: "${JENKINS_URL:?JENKINS_URL is required}"
: "${JENKINS_AGENT_NAME:?JENKINS_AGENT_NAME is required}"
: "${JENKINS_SECRET:?JENKINS_SECRET is required}"

agent_jar=/opt/jenkins-agent/agent.jar
curl --fail --silent --show-error --location "${JENKINS_URL%/}/jnlpJars/agent.jar" --output "$agent_jar"

exec java -jar "$agent_jar" \
  -url "$JENKINS_URL" \
  -secret "$JENKINS_SECRET" \
  -name "$JENKINS_AGENT_NAME" \
  -workDir "${JENKINS_AGENT_WORKDIR:-/home/jenkins/agent}"
