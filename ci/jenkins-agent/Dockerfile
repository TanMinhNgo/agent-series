FROM python:3.12-slim-trixie

ARG NODE_MAJOR=22

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl docker.io git gnupg openjdk-21-jre-headless \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/jenkins/agent /opt/jenkins-agent

COPY ci/jenkins-agent/entrypoint.sh /usr/local/bin/jenkins-agent-entrypoint
RUN chmod 0555 /usr/local/bin/jenkins-agent-entrypoint

ENV JENKINS_AGENT_WORKDIR=/home/jenkins/agent
WORKDIR /home/jenkins/agent
ENTRYPOINT ["/usr/local/bin/jenkins-agent-entrypoint"]
