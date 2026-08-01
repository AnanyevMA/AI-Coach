import os
import re
from pathlib import Path
import pytest

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


BASE_DIR = Path(__file__).resolve().parent.parent
DEPLOY_DIR = BASE_DIR / "deploy"
DOCS_DIR = BASE_DIR / "docs"

NGINX_CONF = DEPLOY_DIR / "nginx_production.conf"
PROMETHEUS_YML = DEPLOY_DIR / "prometheus.yml"
DEPLOY_SCRIPT = DEPLOY_DIR / "selectel_yandex_cloud_deploy.sh"
GRAFANA_DASHBOARD = DEPLOY_DIR / "grafana_dashboard.json"
SECURITY_REPORT = DOCS_DIR / "security" / "final_security_and_compliance_report.md"


# ==============================================================================
# 1. DEPLOYMENT DIRECTORY & FILES EXISTENCE SUITE
# ==============================================================================
class TestDeployDirectoryFilesExistence:
    """Test suite to verify that deploy/ directory and mandatory deployment files exist."""

    def test_deploy_directory_exists(self):
        """Verify deploy/ directory exists in project root."""
        assert DEPLOY_DIR.exists(), f"Deploy directory missing at {DEPLOY_DIR}"
        assert DEPLOY_DIR.is_dir(), f"{DEPLOY_DIR} is not a directory"

    def test_required_deploy_files_exist(self):
        """Verify required deployment files exist inside deploy/ directory."""
        required_files = [
            NGINX_CONF,
            PROMETHEUS_YML,
            DEPLOY_SCRIPT,
            GRAFANA_DASHBOARD
        ]
        for file_path in required_files:
            assert file_path.exists(), f"Required deployment file missing: {file_path.name}"
            assert file_path.is_file(), f"Path is not a file: {file_path.name}"
            assert file_path.stat().st_size > 0, f"File is empty: {file_path.name}"

    def test_security_report_file_exists(self):
        """Verify final security and compliance audit report exists in docs/security/."""
        assert SECURITY_REPORT.exists(), f"Security report missing at {SECURITY_REPORT}"
        assert SECURITY_REPORT.is_file(), f"Security report path is not a file: {SECURITY_REPORT}"
        assert SECURITY_REPORT.stat().st_size > 1000, "Security report file is unexpectedly small"


# ==============================================================================
# 2. NGINX PRODUCTION CONFIGURATION SUITE
# ==============================================================================
class TestNginxProductionConfiguration:
    """Test suite to validate production Nginx configuration (nginx_production.conf)."""

    @pytest.fixture(autouse=True)
    def load_nginx_content(self):
        assert NGINX_CONF.exists(), "nginx_production.conf missing"
        with open(NGINX_CONF, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_nginx_file_not_empty(self):
        """Verify nginx_production.conf is non-empty and has baseline content."""
        assert len(self.content) > 500, "nginx_production.conf content is too short"
        assert "AI Adaptive Coach v7.0" in self.content

    def test_nginx_worker_and_events_directives(self):
        """Verify Nginx worker processes, rlimit, and events block configuration."""
        assert "worker_processes  auto;" in self.content or "worker_processes auto;" in self.content
        assert "worker_rlimit_nofile" in self.content
        assert "events {" in self.content
        assert "worker_connections  4096;" in self.content or "worker_connections 4096;" in self.content
        assert "use epoll;" in self.content
        assert "multi_accept on;" in self.content

    def test_nginx_http_logging_and_performance(self):
        """Verify logging format with microsecond timings and performance optimizations."""
        assert "log_format  production" in self.content or "log_format production" in self.content
        assert "rt=$request_time" in self.content
        assert "uct=\"$upstream_connect_time\"" in self.content
        assert "urt=\"$upstream_response_time\"" in self.content
        assert "sendfile        on;" in self.content or "sendfile on;" in self.content
        assert "tcp_nopush      on;" in self.content or "tcp_nopush on;" in self.content
        assert "tcp_nodelay     on;" in self.content or "tcp_nodelay on;" in self.content
        assert "keepalive_timeout" in self.content
        assert "server_tokens off;" in self.content

    def test_nginx_body_size_limits(self):
        """Verify client_max_body_size is set to 50M for telemetric .FIT files."""
        assert "client_max_body_size 50M;" in self.content
        assert "client_body_buffer_size" in self.content

    def test_nginx_rate_limiting_zones(self):
        """Verify rate limiting zones for API, AI Coach engine, Auth, and Connections."""
        assert "limit_req_zone $binary_remote_addr zone=api_limit:" in self.content
        assert "limit_req_zone $binary_remote_addr zone=ai_limit:" in self.content
        assert "limit_req_zone $binary_remote_addr zone=auth_limit:" in self.content
        assert "limit_conn_zone $binary_remote_addr zone=conn_limit:" in self.content

    def test_nginx_gzip_compression(self):
        """Verify Gzip compression configuration and supported mime types."""
        assert "gzip on;" in self.content
        assert "gzip_comp_level" in self.content
        assert "application/json" in self.content
        assert "application/javascript" in self.content

    def test_nginx_upstream_block(self):
        """Verify upstream backend_api block targeting web:8000 container."""
        assert "upstream backend_api {" in self.content
        assert "server web:8000" in self.content
        assert "keepalive" in self.content

    def test_nginx_http_port_80_block(self):
        """Verify HTTP port 80 server block with Certbot challenge, healthcheck, and 301 HTTPS redirect."""
        assert "listen 80;" in self.content
        assert "location /.well-known/acme-challenge/" in self.content
        assert "location /nginx-health" in self.content
        assert "return 301 https://$host$request_uri;" in self.content

    def test_nginx_https_ssl_and_tls_settings(self):
        """Verify HTTPS port 443 server block with TLS 1.3 / TLS 1.2 and SSL certificate paths."""
        assert "listen 443 ssl" in self.content
        assert "ssl_certificate     /etc/nginx/ssl/fullchain.pem;" in self.content
        assert "ssl_certificate_key /etc/nginx/ssl/privkey.pem;" in self.content
        assert "ssl_dhparam         /etc/nginx/ssl/dhparam.pem;" in self.content
        assert "ssl_protocols TLSv1.3 TLSv1.2;" in self.content
        assert "ssl_prefer_server_ciphers off;" in self.content

    def test_nginx_owasp_security_headers(self):
        """Verify OWASP recommended security headers for 152-FZ PII protection."""
        assert "Strict-Transport-Security" in self.content
        assert "max-age=63072000" in self.content
        assert "includeSubDomains" in self.content
        assert "preload" in self.content

        assert "X-Frame-Options \"DENY\"" in self.content
        assert "X-Content-Type-Options \"nosniff\"" in self.content
        assert "X-XSS-Protection \"1; mode=block\"" in self.content
        assert "Referrer-Policy \"strict-origin-when-cross-origin\"" in self.content
        assert "Content-Security-Policy" in self.content
        assert "Permissions-Policy" in self.content

    def test_nginx_location_proxies(self):
        """Verify proxy locations for metrics, PWA, Coach Portal, AI Coach, and API root."""
        assert "location /metrics {" in self.content
        assert "location /pwa {" in self.content
        assert "location /pwa_static/ {" in self.content
        assert "location /coach {" in self.content
        assert "location /coach_static/ {" in self.content
        assert "location /api/v1/ai-coach/ {" in self.content
        assert "location / {" in self.content
        assert "proxy_pass http://backend_api" in self.content


# ==============================================================================
# 3. PROMETHEUS TELEMETRY CONFIGURATION SUITE
# ==============================================================================
class TestPrometheusConfiguration:
    """Test suite to validate Prometheus configuration (prometheus.yml)."""

    @pytest.fixture(autouse=True)
    def load_prometheus_content(self):
        assert PROMETHEUS_YML.exists(), "prometheus.yml missing"
        with open(PROMETHEUS_YML, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_prometheus_file_not_empty(self):
        """Verify prometheus.yml is non-empty and has valid structure."""
        assert len(self.content) > 200, "prometheus.yml content is too short"
        assert "global:" in self.content
        assert "scrape_configs:" in self.content

    def test_prometheus_global_config(self):
        """Verify global scraping intervals and timeout parameters."""
        assert "scrape_interval: 15s" in self.content
        assert "evaluation_interval: 15s" in self.content
        assert "scrape_timeout: 10s" in self.content

    def test_prometheus_external_labels(self):
        """Verify external labels for environment and cloud infrastructure identification."""
        assert "external_labels:" in self.content
        assert "environment: 'production'" in self.content
        assert "provider: 'selectel-yandex-cloud'" in self.content
        assert "app_name: 'ai-adaptive-coach-v7'" in self.content

    def test_prometheus_scrape_configs_backend(self):
        """Verify FastAPI backend metric scraper configuration."""
        assert "job_name: 'ai_coach_backend'" in self.content
        assert "metrics_path: '/metrics'" in self.content
        assert "web:8000" in self.content

    def test_prometheus_scrape_configs_nginx(self):
        """Verify Nginx proxy metric scraper configuration."""
        assert "job_name: 'nginx_proxy'" in self.content
        assert "nginx:80" in self.content

    def test_prometheus_scrape_configs_postgres(self):
        """Verify PostgreSQL metric exporter job configuration."""
        assert "job_name: 'postgres_db'" in self.content
        assert "postgres-exporter:9187" in self.content

    def test_prometheus_scrape_configs_redis(self):
        """Verify Redis metric exporter job configuration."""
        assert "job_name: 'redis_cache'" in self.content
        assert "redis-exporter:9121" in self.content

    def test_prometheus_yaml_validity(self):
        """Verify prometheus.yml syntax validity by parsing YAML (or structural validation)."""
        if HAS_YAML:
            parsed = yaml.safe_load(self.content)
            assert isinstance(parsed, dict)
            assert "global" in parsed
            assert "scrape_configs" in parsed
            assert len(parsed["scrape_configs"]) >= 4
            job_names = [sc["job_name"] for sc in parsed["scrape_configs"]]
            assert "ai_coach_backend" in job_names
            assert "nginx_proxy" in job_names
            assert "postgres_db" in job_names
            assert "redis_cache" in job_names
        else:
            # Fallback syntax assertion when PyYAML is not present
            assert self.content.count("job_name:") >= 4


# ==============================================================================
# 4. DEPLOYMENT SCRIPT SUITE
# ==============================================================================
class TestDeploymentScript:
    """Test suite to validate deployment script (selectel_yandex_cloud_deploy.sh)."""

    @pytest.fixture(autouse=True)
    def load_deploy_script_content(self):
        assert DEPLOY_SCRIPT.exists(), "selectel_yandex_cloud_deploy.sh missing"
        with open(DEPLOY_SCRIPT, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_deploy_script_not_empty(self):
        """Verify selectel_yandex_cloud_deploy.sh is non-empty."""
        assert len(self.content) > 500, "selectel_yandex_cloud_deploy.sh is too short"
        assert "AI Adaptive Coach v7.0" in self.content

    def test_deploy_script_shebang_and_strict_mode(self):
        """Verify bash shebang and strict execution flags (set -euo pipefail)."""
        lines = [line.strip() for line in self.content.splitlines() if line.strip()]
        assert lines[0].startswith("#!/usr/bin/env bash") or lines[0].startswith("#!/bin/bash")
        assert "set -euo pipefail" in self.content

    def test_deploy_script_root_privilege_check(self):
        """Verify script checks for root / sudo privileges ($EUID -ne 0)."""
        assert "EUID" in self.content
        assert "root privileges" in self.content.lower()

    def test_deploy_script_prerequisites_installation(self):
        """Verify system prerequisites installation steps (docker, certbot, openssl, jq)."""
        assert "apt-get install" in self.content
        assert "certbot" in self.content
        assert "openssl" in self.content
        assert "jq" in self.content

    def test_deploy_script_152_fz_aes_key_generation(self):
        """Verify 152-FZ secret key & AES-256 generation using openssl rand."""
        assert "openssl rand -hex 32" in self.content
        assert "AES_SECRET_KEY" in self.content
        assert "POSTGRES_PASSWORD" in self.content
        assert "REDIS_PASSWORD" in self.content
        assert "SECRET_KEY" in self.content

    def test_deploy_script_ssl_certbot_provisioning(self):
        """Verify SSL Certbot provisioning, self-signed fallback, and dhparam.pem generation."""
        assert "certbot certonly" in self.content
        assert "dhparam.pem" in self.content
        assert "openssl req -x509" in self.content

    def test_deploy_script_database_migrations(self):
        """Verify PostgreSQL health check wait loop and Alembic migration command."""
        assert "pg_isready" in self.content
        assert "alembic upgrade head" in self.content

    def test_deploy_script_docker_compose_up(self):
        """Verify Docker Compose up execution command."""
        assert "up -d" in self.content

    def test_deploy_script_ssl_renewal_cron(self):
        """Verify automated Certbot SSL renewal cron job configuration."""
        assert "crontab" in self.content
        assert "certbot renew" in self.content

    def test_deploy_script_post_deployment_verification(self):
        """Verify post-deployment HTTP health checks for /health, /metrics, /nginx-health."""
        assert "/health" in self.content
        assert "/metrics" in self.content
        assert "/nginx-health" in self.content


# ==============================================================================
# 5. SECURITY AND COMPLIANCE AUDIT REPORT SUITE
# ==============================================================================
class TestSecurityAndComplianceReport:
    """Test suite to validate the final security and compliance audit report."""

    @pytest.fixture(autouse=True)
    def load_report_content(self):
        assert SECURITY_REPORT.exists(), "final_security_and_compliance_report.md missing"
        with open(SECURITY_REPORT, "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_security_report_not_empty(self):
        """Verify final_security_and_compliance_report.md is comprehensive."""
        assert len(self.content) > 5000, "Security report content is unexpectedly short"
        assert "AI Adaptive Coach v7.0" in self.content

    def test_security_report_metadata(self):
        """Verify report metadata, audit date, version, status, and target standards."""
        assert "Итоговый отчёт по безопасности" in self.content or "Security & Compliance Audit Report" in self.content
        assert "APPROVED" in self.content or "Пройден" in self.content
        assert "152-ФЗ" in self.content
        assert "323-ФЗ" in self.content
        assert "38-ФЗ" in self.content
        assert "54-ФЗ" in self.content
        assert "OWASP" in self.content

    def test_security_report_152_fz_compliance(self):
        """Verify 152-FZ compliance analysis, UZ-2 rating, AES-256-GCM cipher, and breach notification sequence."""
        assert "152-ФЗ" in self.content
        assert "УЗ-2" in self.content
        assert "AES-256-GCM" in self.content
        assert "AES256GCMCipher" in self.content
        assert "24" in self.content and "72" in self.content  # Breach notification timelines

    def test_security_report_323_fz_compliance(self):
        """Verify 323-FZ compliance, medical disclaimer, and RedFlagsTriageEngine levels 1-3."""
        assert "323-ФЗ" in self.content
        assert "RedFlagsTriageEngine" in self.content
        assert "LEVEL 1" in self.content or "Level 1" in self.content
        assert "LEVEL 2" in self.content or "Level 2" in self.content
        assert "LEVEL 3" in self.content or "Level 3" in self.content
        assert "HARD_LOCK" in self.content or "Hard Lock" in self.content

    def test_security_report_38_54_fz_compliance(self):
        """Verify 38-FZ advertising erid marking and 54-FZ online cash register fiscal tags (1054, 1214, 1212, 1030)."""
        assert "38-ФЗ" in self.content
        assert "erid" in self.content
        assert "54-ФЗ" in self.content
        assert "1054" in self.content
        assert "1214" in self.content
        assert "1212" in self.content
        assert "1030" in self.content

    def test_security_report_gemini_api_security(self):
        """Verify Google Gemini API key security, masked key method, rate limiting, and prompt sanitization."""
        assert "Gemini" in self.content
        assert "get_masked_gemini_key" in self.content
        assert "RateLimiter" in self.content or "Rate Limit" in self.content
        assert "UUID" in self.content  # Anonymous profile tokenization

    def test_security_report_owasp_top_10_coverage(self):
        """Verify OWASP Top 10 coverage matrix (A01 through A10)."""
        assert "OWASP" in self.content
        for i in range(1, 11):
            category = f"A{i:02d}"
            assert category in self.content, f"OWASP category {category} missing from report"

    def test_security_report_audit_sign_off_checklist(self):
        """Verify final 10-point audit sign-off checklist and PASSED status indicators."""
        assert "PASSED" in self.content or "✅" in self.content
        assert "Audit Sign-off" in self.content or "чек-лист" in self.content.lower()
