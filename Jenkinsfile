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
          .ci-venv/bin/python -m pip install --only-binary :all: --require-hashes --requirement requirements-ci.lock
          mkdir -p "$REPORTS_DIR"
          DATABASE_URL=postgresql+psycopg://agent:agent@host.docker.internal:55432/agent_series .ci-venv/bin/python -m alembic upgrade head
          DATABASE_URL=postgresql+psycopg://agent:agent@host.docker.internal:55432/agent_series .ci-venv/bin/python -m coverage run -m pytest -q --junitxml="$REPORTS_DIR/backend-junit.xml"
          .ci-venv/bin/python -m coverage xml -o "$REPORTS_DIR/backend-coverage.xml"
          cd frontend
          npm ci --ignore-scripts
          npm run format:check
          npm run lint
          npm run test:coverage
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
    stage('Prepare Trivy database') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          trivy_cache_volume=agent-series-trivy-cache
          trivy_cache_dir=/root/.cache/trivy
          ready_marker="$trivy_cache_dir/.agent-series-vuln-db-ready"
          docker volume create "$trivy_cache_volume" >/dev/null

          cache_is_verified() {
            docker run --rm --entrypoint /bin/sh \
              -v "$trivy_cache_volume:$trivy_cache_dir" \
              aquasec/trivy:0.74.0 \
              -c "test -f '$ready_marker' && test -f '$trivy_cache_dir/db/trivy.db'"
          }

          if docker run --rm \
            -v "$trivy_cache_volume:$trivy_cache_dir" \
            aquasec/trivy:0.74.0 image \
            --db-repository ghcr.io/aquasecurity/trivy-db:2 \
            --db-repository mirror.gcr.io/aquasec/trivy-db:2 \
            --download-db-only; then
            docker run --rm --entrypoint /bin/sh \
              -v "$trivy_cache_volume:$trivy_cache_dir" \
              aquasec/trivy:0.74.0 \
              -c "touch '$ready_marker'"
          elif cache_is_verified; then
            echo 'Trivy DB update is temporarily unavailable; scanning with the last verified DB cache.' >&2
          else
            echo 'Trivy DB update failed before a verified cache was available; refusing an incomplete vulnerability scan.' >&2
            exit 1
          fi
        '''
      }
    }
    stage('Trivy source and config') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          mkdir -p "$REPORTS_DIR/trivy"
          trivy_cache_volume=agent-series-trivy-cache
          scan_container="$(docker create --entrypoint /bin/sh -v "$trivy_cache_volume:/root/.cache/trivy" aquasec/trivy:0.74.0 -c 'mkdir -p /src /report; tail -f /dev/null')"
          cleanup_scan_container() {
            if [[ -n "${scan_container:-}" ]]; then docker rm -f "$scan_container" >/dev/null 2>&1 || true; fi
          }
          trap cleanup_scan_container EXIT
          docker start "$scan_container" >/dev/null
          git archive --format=tar HEAD | docker cp - "$scan_container:/src"

          scan_status=0
          docker exec "$scan_container" trivy fs --skip-db-update --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output /report/fs.json /src || scan_status=$?
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
          # AWS t3.small is amd64; build the images natively so the exact
          # artifacts scanned here run on the deployment VM.
          docker build --target api -t agent-series-api:$IMAGE_TAG -f Dockerfile.backend .
          docker build --target worker -t agent-series-worker:$IMAGE_TAG -f Dockerfile.backend .
          docker build -t agent-series-frontend:$IMAGE_TAG -f frontend/Dockerfile frontend
          printf 'POSTGRES_PASSWORD=validation-only\n' > .ci.env
          # The CI agent exposes only the Docker CLI, without the Compose plugin.
          # Its workspace cannot be bind-mounted into sibling Docker containers,
          # so copy the compose inputs into a dedicated Compose CLI container.
          compose_container="$(docker create --entrypoint /bin/sh docker/compose:1.29.2 -c 'mkdir -p /work /report; tail -f /dev/null')"
          cleanup_compose_container() {
            if [[ -n "${compose_container:-}" ]]; then docker rm -f "$compose_container" >/dev/null 2>&1 || true; fi
          }
          trap cleanup_compose_container EXIT
          docker start "$compose_container" >/dev/null
          git archive --format=tar HEAD | docker cp - "$compose_container:/work"
          docker cp .ci.env "$compose_container:/work/.ci.env"
          docker exec \
            -e APP_ENV_FILE=.ci.env \
            -e POSTGRES_PASSWORD=validation-only \
            -e IMAGE_TAG="$IMAGE_TAG" \
            "$compose_container" sh -c 'cd /work && docker-compose -f docker-compose.prod.yml config > /report/docker-compose.rendered.yml'
          docker cp "$compose_container:/report/docker-compose.rendered.yml" "$REPORTS_DIR/docker-compose.rendered.yml"
          cleanup_compose_container
          compose_container=''
          trap - EXIT
          docker image inspect agent-series-api:$IMAGE_TAG agent-series-worker:$IMAGE_TAG agent-series-frontend:$IMAGE_TAG > "$REPORTS_DIR/docker-images.json"
        '''
      }
    }
    stage('Trivy Docker images') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail
          mkdir -p "$REPORTS_DIR/trivy"
          trivy_cache_volume=agent-series-trivy-cache
          scan_container="$(docker create --entrypoint /bin/sh -v /var/run/docker.sock:/var/run/docker.sock -v "$trivy_cache_volume:/root/.cache/trivy" aquasec/trivy:0.74.0 -c 'mkdir -p /report; tail -f /dev/null')"
          cleanup_scan_container() {
            if [[ -n "${scan_container:-}" ]]; then docker rm -f "$scan_container" >/dev/null 2>&1 || true; fi
          }
          trap cleanup_scan_container EXIT
          docker start "$scan_container" >/dev/null

          scan_status=0
          for image in agent-series-api:$IMAGE_TAG agent-series-worker:$IMAGE_TAG agent-series-frontend:$IMAGE_TAG; do
            safe_name=$(echo "$image" | tr ':/' '__')
            docker exec "$scan_container" trivy image --skip-db-update --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --format json --output "/report/${safe_name}.json" "$image" || scan_status=$?
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

            retry_registry() {
              local attempt=1
              until "$@"; do
                if (( attempt >= 3 )); then return 1; fi
                echo 'Docker Hub request failed; retrying...' >&2
                sleep "$((attempt * 5))"
                ((attempt++))
              done
            }
            login_registry() {
              printf '%s' "$DOCKERHUB_TOKEN" | docker login --username "$DOCKERHUB_USERNAME" --password-stdin
            }
            retry_registry login_registry

            for service in api worker frontend; do
              local_image="agent-series-${service}:$IMAGE_TAG"
              remote_image="${DOCKERHUB_USERNAME}/agent-series-${service}"

              docker tag "$local_image" "${remote_image}:sha-${GIT_SHA}"
              retry_registry docker push "${remote_image}:sha-${GIT_SHA}"
              docker tag "$local_image" "${remote_image}:latest"
              retry_registry docker push "${remote_image}:latest"
            done
          '''
        }
      }
    }
    stage('Deploy backend to AWS') {
      when { expression { params.GIT_REF == 'main' } }
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: 'aws-deploy-key', keyFileVariable: 'AWS_SSH_KEY', usernameVariable: 'AWS_SSH_USER'),
          string(credentialsId: 'aws-deploy-host', variable: 'AWS_DEPLOY_HOST'),
          file(credentialsId: 'aws-known-hosts', variable: 'AWS_KNOWN_HOSTS')
        ]) {
          sh '''#!/usr/bin/env bash
            set -euo pipefail
            remote_dir=agent-series
            target="$AWS_SSH_USER@$AWS_DEPLOY_HOST"
            ssh_args=(-i "$AWS_SSH_KEY" -o "UserKnownHostsFile=$AWS_KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
            scp_args=(-i "$AWS_SSH_KEY" -o "UserKnownHostsFile=$AWS_KNOWN_HOSTS" -o StrictHostKeyChecking=yes)

            ssh "${ssh_args[@]}" "$target" "install -d -m 700 '$remote_dir/backups'"
            scp "${scp_args[@]}" deploy/docker-compose.oci.yml deploy/Caddyfile "$target:$remote_dir/"
            ssh "${ssh_args[@]}" "$target" "set -euo pipefail
              cd '$remote_dir'
              test -f .env
              set -a; . ./.env; set +a
              export IMAGE_TAG='sha-$GIT_SHA'
              docker compose --env-file .env -f docker-compose.oci.yml pull api worker caddy
              docker compose --env-file .env -f docker-compose.oci.yml up -d postgres
              until docker compose --env-file .env -f docker-compose.oci.yml exec -T postgres pg_isready -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"; do sleep 2; done
              docker compose --env-file .env -f docker-compose.oci.yml exec -T postgres pg_dump -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" | gzip > 'backups/pre-$GIT_SHA.sql.gz'
              docker compose --env-file .env -f docker-compose.oci.yml run --rm api python -m alembic upgrade head
              docker compose --env-file .env -f docker-compose.oci.yml up -d --remove-orphans
              curl --fail --silent --show-error --retry 12 --retry-delay 5 \"https://\$BACKEND_DOMAIN/api/health\"
              printf '%s\\n' 'sha-$GIT_SHA' > .deployed-sha"
          '''
        }
      }
    }
    stage('Deploy frontend to Vercel') {
      when { expression { params.GIT_REF == 'main' } }
      steps {
        withCredentials([
          string(credentialsId: 'vercel-token', variable: 'VERCEL_TOKEN'),
          string(credentialsId: 'vercel-org-id', variable: 'VERCEL_ORG_ID'),
          string(credentialsId: 'vercel-project-id', variable: 'VERCEL_PROJECT_ID'),
          string(credentialsId: 'vercel-backend-origin', variable: 'VERCEL_BACKEND_ORIGIN')
        ]) {
          dir('frontend') {
            sh '''#!/usr/bin/env bash
              set -euo pipefail
              case "$VERCEL_BACKEND_ORIGIN" in https://*) ;; *) echo 'VERCEL_BACKEND_ORIGIN must be an HTTPS URL.' >&2; exit 1;; esac
              node -e 'const fs = require("fs"); const origin = process.env.VERCEL_BACKEND_ORIGIN.replace(/\\/$/, ""); const template = fs.readFileSync("vercel.json.template", "utf8"); if (!origin || !template.includes("__BACKEND_ORIGIN__")) process.exit(1); fs.writeFileSync("vercel.json", template.replace("__BACKEND_ORIGIN__", origin));'
              npx --yes vercel@59.17.0 --prod --yes --token "$VERCEL_TOKEN"
            '''
          }
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
