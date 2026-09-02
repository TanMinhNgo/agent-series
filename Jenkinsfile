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
            data_volume=agent-series-owasp-data
            ready_marker=/usr/share/dependency-check/data/.agent-series-nvd-ready
            docker volume create "$data_volume" >/dev/null

            update_args=(--updateonly --nvdMaxRetryCount 20 --nvdValidForHours 24)
            if [[ -n "$NVD_API_KEY" ]]; then update_args+=(--nvdApiKey "$NVD_API_KEY"); fi

            update_nvd_cache() {
              docker run --rm \
                -v "$data_volume:/usr/share/dependency-check/data" \
                owasp/dependency-check:12.2.2 "${update_args[@]}"
            }

            cache_is_verified() {
              docker run --rm --entrypoint /bin/sh \
                -v "$data_volume:/usr/share/dependency-check/data" \
                owasp/dependency-check:12.2.2 \
                -c "test -f '$ready_marker'"
            }

            mark_cache_verified() {
              docker run --rm --entrypoint /bin/sh \
                -v "$data_volume:/usr/share/dependency-check/data" \
                owasp/dependency-check:12.2.2 \
                -c "touch '$ready_marker'"
            }

            if update_nvd_cache; then
              mark_cache_verified
            elif cache_is_verified; then
              echo 'NVD is temporarily unavailable; scanning with the last verified NVD cache.' >&2
            else
              echo 'NVD update failed before a complete cache was created; refusing an incomplete security scan.' >&2
              exit 1
            fi

            # CI agent only shares the Docker socket, not its workspace, with the
            # Docker host. Copy the committed manifest/lockfiles into a scanner
            # container instead of bind-mounting $PWD (which becomes an empty /src).
            scan_container="$(docker create --entrypoint /bin/sh \
              -v "$data_volume:/usr/share/dependency-check/data" \
              owasp/dependency-check:12.2.2 \
              -c 'mkdir -p /src/frontend /report; tail -f /dev/null')"
            cleanup_scan_container() {
              if [[ -n "${scan_container:-}" ]]; then docker rm -f "$scan_container" >/dev/null 2>&1 || true; fi
            }
            trap cleanup_scan_container EXIT
            docker start "$scan_container" >/dev/null
            docker cp requirements.txt "$scan_container:/src/requirements.txt"
            docker cp requirements-ci.lock "$scan_container:/src/requirements-ci.lock"
            docker cp frontend/package-lock.json "$scan_container:/src/frontend/package-lock.json"
            docker exec "$scan_container" /usr/share/dependency-check/bin/dependency-check.sh \
              --scan /src/requirements.txt \
              --scan /src/requirements-ci.lock \
              --scan /src/frontend/package-lock.json \
              --out /report --format ALL --failOnCVSS 7 --noupdate
            docker cp "$scan_container:/report/." "$REPORTS_DIR/owasp"
            cleanup_scan_container
            scan_container=''
            trap - EXIT
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
          scan_container="$(docker create --entrypoint /bin/sh aquasec/trivy:0.58.0 -c 'mkdir -p /src /report; tail -f /dev/null')"
          cleanup_scan_container() {
            if [[ -n "${scan_container:-}" ]]; then docker rm -f "$scan_container" >/dev/null 2>&1 || true; fi
          }
          trap cleanup_scan_container EXIT
          docker start "$scan_container" >/dev/null
          git archive --format=tar HEAD | docker cp - "$scan_container:/src"

          scan_status=0
          docker exec "$scan_container" trivy fs --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output /report/fs.json /src || scan_status=$?
          docker exec "$scan_container" trivy config --exit-code 1 --severity HIGH,CRITICAL --format json --output /report/config.json /src || scan_status=$?
          docker cp "$scan_container:/report/." "$REPORTS_DIR/trivy"
          exit "$scan_status"
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
          mkdir -p "$REPORTS_DIR/trivy"
          scan_container="$(docker create --entrypoint /bin/sh -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.58.0 -c 'mkdir -p /report; tail -f /dev/null')"
          cleanup_scan_container() {
            if [[ -n "${scan_container:-}" ]]; then docker rm -f "$scan_container" >/dev/null 2>&1 || true; fi
          }
          trap cleanup_scan_container EXIT
          docker start "$scan_container" >/dev/null

          scan_status=0
          for image in agent-series-api:$IMAGE_TAG agent-series-worker:$IMAGE_TAG agent-series-frontend:$IMAGE_TAG; do
            safe_name=$(echo "$image" | tr ':/' '__')
            docker exec "$scan_container" trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/report/${safe_name}.json" "$image" || scan_status=$?
          done
          docker cp "$scan_container:/report/." "$REPORTS_DIR/trivy"
          exit "$scan_status"
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
