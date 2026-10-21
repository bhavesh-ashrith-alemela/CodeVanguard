import { test, expect } from '@playwright/test';

test.describe('Git History Secret Detection Flow', () => {
  const repoId = 'repo-secrets-101';
  const findingId = 'finding-secret-aws';

  test.beforeEach(async ({ page }) => {
    // 1. Mock session authentication
    await page.route('/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 1,
            username: 'sec-analyst',
            github_login: 'sec-analyst',
            role: 'user'
          }
        })
      });
    });

    // 2. Mock repositories list
    await page.route('/api/repos', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repositories: [
            {
              id: repoId,
              full_name: 'octocat/secret-vault',
              default_branch: 'main',
              scan_enabled: true
            }
          ]
        })
      });
    });

    // 3. Mock single repository details
    await page.route(`/api/repos/${repoId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repository: {
            id: repoId,
            full_name: 'octocat/secret-vault',
            default_branch: 'main',
            scan_enabled: true
          },
          installation: {
            id: 'inst-1',
            account_login: 'octocat'
          },
          scans: []
        })
      });
    });

    // 4. Mock findings listing with secret findings
    await page.route(`/api/repos/${repoId}/findings*`, async (route) => {
      const url = new URL(route.request().url());
      const isSecretOnly = url.searchParams.get('is_secret') === 'true' || url.searchParams.get('scanner') === 'secret';

      const allFindings = [
        {
          id: findingId,
          repo_id: repoId,
          fingerprint: 'fp-secret-aws-1234',
          rule_id: 'SECRET_AWS_KEY',
          severity: 'high',
          title: 'AWS Access Key ID',
          detector: 'AWS Access Key ID',
          filepath: 'config/aws.py',
          line_number: 14,
          first_seen_commit: 'c0ffee1234567890abcdef1234567890abcdef12',
          commit_sha: 'c0ffee1234567890abcdef1234567890abcdef12',
          first_seen_at: new Date().toISOString(),
          last_seen_at: new Date().toISOString(),
          state: 'open',
          is_secret: true,
          still_in_head: false,
          masked_secret: 'AKIA...2A',
          code_snippet: '14: AWS_KEY = "AKIA...2A"',
          fix_title: 'Rotate Exposed Credential Immediately',
          fix_description: 'Rotate this credential immediately; removing it from code or history is secondary.'
        },
        {
          id: 'finding-sqli-02',
          repo_id: repoId,
          fingerprint: 'fp-sqli-5678',
          rule_id: 'B608',
          severity: 'high',
          title: 'SQL Injection vulnerability',
          filepath: 'db/users.py',
          line_number: 28,
          first_seen_commit: 'deadbeef1234567890abcdef1234567890abcdef12',
          first_seen_at: new Date().toISOString(),
          last_seen_at: new Date().toISOString(),
          state: 'open',
          is_secret: false,
          code_snippet: '28: cursor.execute(query)'
        }
      ];

      const returnedFindings = isSecretOnly
        ? allFindings.filter(f => f.is_secret)
        : allFindings;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          findings: returnedFindings,
          total_count: returnedFindings.length,
          page: 1,
          per_page: 15
        })
      });
    });

    // 5. Mock history scan trigger
    await page.route(`/api/repos/${repoId}/scan/history`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'queued',
          scan_id: 'scan-history-123',
          repo_id: repoId,
          trigger: 'history'
        })
      });
    });

    // 6. Mock scan polling
    await page.route('/api/scan/scan-history-123', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          scan: {
            id: 'scan-history-123',
            status: 'completed',
            progress: 'completed',
            total_issues: 1
          }
        })
      });
    });
  });

  test('Secrets filter and Rotate First checklist drawer', async ({ page }) => {
    // Navigate to Findings page
    await page.goto(`/repos/${repoId}/findings`);

    // Verify both findings rendered initially
    await expect(page.locator('text=AWS Access Key ID')).toBeVisible();
    await expect(page.locator('text=SQL Injection vulnerability')).toBeVisible();

    // Click the dedicated Secrets filter button
    const secretsFilterBtn = page.locator('button:has-text("Secrets")');
    await expect(secretsFilterBtn).toBeVisible();
    await secretsFilterBtn.click();

    // Verify only the secret finding is displayed
    await expect(page.locator('text=AWS Access Key ID')).toBeVisible();
    await expect(page.locator('text=AKIA...2A')).toBeVisible();
    await expect(page.locator('text=HISTORY ONLY')).toBeVisible();

    // Click on the secret row to open side panel drawer
    await page.locator('text=AWS Access Key ID').click();

    // Verify Rotate First checklist is rendered with 4 steps
    await expect(page.locator('text=Rotate First Checklist')).toBeVisible();
    await expect(page.locator('text=Revoke in Provider Console')).toBeVisible();
    await expect(page.locator('text=Rotate Production Secrets')).toBeVisible();
    await expect(page.locator('text=Audit Provider Logs')).toBeVisible();
    await expect(page.locator('text=Purge from Git History')).toBeVisible();
    await expect(page.locator('text=git filter-repo')).toBeVisible();
    await expect(page.locator('text=force-push')).toBeVisible();
  });

  test('Settings page history scan trigger', async ({ page }) => {
    // Navigate to Settings page
    await page.goto(`/repos/${repoId}/settings`);

    // Verify Git History Secret Detection card is visible
    await expect(page.locator('text=Git History Secret Detection')).toBeVisible();

    const runHistoryScanBtn = page.locator('button:has-text("Run full history scan")');
    await expect(runHistoryScanBtn).toBeVisible();
    await runHistoryScanBtn.click();

    // Verify status transition or completion
    await expect(page.locator('text=View Secret Findings')).toBeVisible({ timeout: 5000 });
  });
});
