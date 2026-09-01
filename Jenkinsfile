pipeline {
  agent { label 'agent-series-ci' }
  parameters {
    string(name: 'GIT_URL', defaultValue: '', description: 'Repository URL sent by GitHub Actions')
    string(name: 'GIT_SHA', defaultValue: '', description: 'Immutable commit SHA sent by GitHub Actions')
    string(name: 'GIT_REF', defaultValue: '', description: 'Source branch/ref')
  }
  environment {
    IMAGE_TAG = "${params.GIT_SHA.take(12)}"
    REPORTS_DIR = 'reports'
  }
  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '10'))
  }
  stages {
    stage('Validate trigger') {
      steps {
        script {
          if (!params.GIT_URL?.trim() || !params.GIT_SHA?.trim()) {
            error('GIT_URL and GIT_SHA are required.')
          }
        }
      }
    }
    stage('Checkout exact commit') {
      steps {
        deleteDir()
        checkout([$class: 'GitSCM', branches: [[name: params.GIT_SHA]], userRemoteConfigs: [[url: params.GIT_URL, credentialsId: 'github-read-token']]])
        sh 'test "$(git rev-parse HEAD)" = "$GIT_SHA"'
      }
    }
    stage('Test and coverage') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          docker rm -f agent-series-ci-postgres >/dev/null 2>&1 || true
          docker run -d --name agent-series-ci-postgres -e POSTGRES_DB=agent_series -e POSTGRES_USER=agent -e POSTGRES_PASSWORD=agent -p 55432:5432 pgvector/pgvector:pg16
          until docker exec agent-series-ci-postgres pg_isready -U agent -d agent_series; do sleep 2; done
          python3.12 -m venv .ci-venv
          .ci-venv/bin/python -m pip install --require-hashes --requirement requirements-ci.lock
          mkdir -p "$REPORTS_DIR"
          DATABASE_URL=postgresql+psycopg://agent:agent@host.docker.internal:55432/agent_series .ci-venv/bin/python -m alembic upgrade head
          DATABASE_URL=postgresql+psycopg://agent:agent@host.docker.internal:55432/agent_series .ci-venv/bin/python -m coverage run -m pytest -q --junitxml="$REPORTS_DIR/backend-junit.xml"
          .ci-venv/bin/python -m coverage xml -o "$REPORTS_DIR/backend-coverage.xml"
          cd frontend
          npm ci --ignore-scripts
          npm run format:check
          npm run lint
          npm run build
        '''
      }
    }
    stage('OWASP dependency check') {
      steps {
        withCredentials([string(credentialsId: 'nvd-api-key', variable: 'NVD_API_KEY')]) {
          sh '''#!/usr/bin/env bash
            set -euo pipefail
            mkdir -p "$REPORTS_DIR/owasp"
            docker volume create agent-series-owasp-data >/dev/null
            args=(--scan /src --out /report --format ALL --failOnCVSS 7)
            if [[ -n "$NVD_API_KEY" ]]; then args+=(--nvdApiKey "$NVD_API_KEY"); fi
            docker run --rm \
              -v "$PWD:/src" \
              -v "$PWD/$REPORTS_DIR/owasp:/report" \
              -v agent-series-owasp-data:/usr/share/dependency-check/data \
              owasp/dependency-check:12.2.2 "${args[@]}"
          '''
        }
      }
    }
    stage('SonarQube quality gate') {
      steps {
        script {
          def scannerHome = tool 'SonarScanner'
          withSonarQubeEnv('SonarQube') { sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectVersion=${params.GIT_SHA}" }
        }
      }
    }
    stage('Wait for SonarQube gate') {
      steps { timeout(time: 10, unit: 'MINUTES') { waitForQualityGate abortPipeline: true } }
    }
    stage('Trivy source and config') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          mkdir -p "$REPORTS_DIR/trivy"
          docker run --rm -v "$PWD:/src" aquasec/trivy:0.58.0 fs --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output /src/$REPORTS_DIR/trivy/fs.json /src
          docker run --rm -v "$PWD:/src" aquasec/trivy:0.58.0 config --exit-code 1 --severity HIGH,CRITICAL --format json --output /src/$REPORTS_DIR/trivy/config.json /src
        '''
      }
    }
    stage('Build Docker images') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          docker build --target api -t agent-series-api:$IMAGE_TAG -f Dockerfile.backend .
          docker build --target worker -t agent-series-worker:$IMAGE_TAG -f Dockerfile.backend .
          docker build -t agent-series-frontend:$IMAGE_TAG -f frontend/Dockerfile frontend
          printf 'POSTGRES_PASSWORD=validation-only\n' > .ci.env
          APP_ENV_FILE=.ci.env docker compose -f docker-compose.prod.yml config > "$REPORTS_DIR/docker-compose.rendered.yml"
          docker image inspect agent-series-api:$IMAGE_TAG agent-series-worker:$IMAGE_TAG agent-series-frontend:$IMAGE_TAG > "$REPORTS_DIR/docker-images.json"
        '''
      }
    }
    stage('Trivy Docker images') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          for image in agent-series-api:$IMAGE_TAG agent-series-worker:$IMAGE_TAG agent-series-frontend:$IMAGE_TAG; do
            safe_name=$(echo "$image" | tr ':/' '__')
            docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:/src" aquasec/trivy:0.58.0 image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/src/$REPORTS_DIR/trivy/${safe_name}.json" "$image"
          done
        '''
      }
    }
    stage('Push verified images to Docker Hub') {
      when { expression { params.GIT_REF == 'main' } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', usernameVariable: 'DOCKERHUB_USERNAME', passwordVariable: 'DOCKERHUB_TOKEN')]) {
          sh '''#!/usr/bin/env bash
            set -euo pipefail
            trap 'docker logout >/dev/null 2>&1 || true' EXIT

            printf '%s' "$DOCKERHUB_TOKEN" | docker login --username "$DOCKERHUB_USERNAME" --password-stdin

            for service in api worker frontend; do
              local_image="agent-series-${service}:$IMAGE_TAG"
              remote_image="${DOCKERHUB_USERNAME}/agent-series-${service}"

              docker tag "$local_image" "${remote_image}:sha-${GIT_SHA}"
              docker push "${remote_image}:sha-${GIT_SHA}"
              docker tag "$local_image" "${remote_image}:latest"
              docker push "${remote_image}:latest"
            done
          '''
        }
      }
    }
  }
  post {
    always {
      sh 'docker rm -f agent-series-ci-postgres >/dev/null 2>&1 || true'
      junit allowEmptyResults: true, testResults: 'reports/backend-junit.xml'
      archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**/*'
    }
  }
}
