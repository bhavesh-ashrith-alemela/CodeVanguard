import { test, expect } from '@playwright/test';

test.describe('CodeVanguard Golden Path E2E Journey', () => {
  const repoId = 'repo-golden-path-101';
  const prNumber = 42;
  const findingId = 'finding-golden-01';

  test.beforeEach(async ({ page }) => {
    // 1. Mock Authentication (/api/auth/me)
    await page.route('/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 1,
            username: 'vanguard-reviewer',
            github_login: 'vanguard-reviewer',
            avatar_url: 'https://avatars.githubusercontent.com/u/583231?v=4',
            role: 'user'
          }
        })
      });
    });

    // 2. Mock Repositories List
    await page.route('/api/repos', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repositories: [
            {
              id: repoId,
              full_name: 'vanguard-team/production-api',
              default_branch: 'main',
              scan_enabled: true,
              autofix_enabled: true
            }
          ]
        })
      });
    });

    // 3. Mock Repository Overview & Scans
    await page.route(`/api/repos/${repoId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repository: {
            id: repoId,
            full_name: 'vanguard-team/production-api',
            default_branch: 'main',
            scan_enabled: true,
            autofix_enabled: true,
            autofix_daily_quota: 20
          },
          installation: {
            id: 'inst-golden-1',
            account_login: 'vanguard-team'
          },
          scans: [
            {
              id: 'scan-base-01',
              branch: 'main',
              commit_sha: 'a1b2c3d4e5f6a1b2c3d4e5f6',
              status: 'completed',
              total_issues: 2,
              critical_count: 0,
              high_count: 2,
              medium_count: 0,
              low_count: 0,
              timestamp: new Date().toISOString()
            }
          ]
        })
      });
    });

    // 4. Mock Trend and Pull Requests endpoints
    await page.route(`/api/repos/${repoId}/trend`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          trend: [
            { scan_id: 'scan-base-01', commit_sha: 'a1b2c3d', timestamp: new Date().toISOString(), score: 84, critical: 0, high: 2, medium: 0, low: 0, total: 2 }
          ]
        })
      });
    });

    await page.route(`/api/repos/${repoId}/pulls`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pull_requests: [
            {
              pr_number: prNumber,
              title: 'Add payment webhook processor',
              branch: 'feature/payment-webhook',
              verdict: 'BLOCK',
              new_findings_count: 1,
              timestamp: new Date().toISOString()
            }
          ]
        })
      });
    });

    // 5. Mock PR Summary Facts (/api/repos/:id/pulls/:number/summary)
    await page.route(`/api/repos/${repoId}/pulls/${prNumber}/summary`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            id: 'summary-pr-42',
            repo_id: repoId,
            pr_number: prNumber,
            head_sha: 'f1e2d3c4b5a6',
            narrative: 'CodeVanguard blocked PR #42: 1 new High vulnerability detected (command injection).',
            facts: {
              version: 1,
              pr: {
                number: prNumber,
                head_sha: 'f1e2d3c4b5a6',
                base_sha: 'a1b2c3d4e5f6',
                title: 'Add payment webhook processor',
                author: 'developer-one',
                files_changed: 2,
                additions: 24,
                deletions: 3
              },
              categories_touched: ['auth', 'subprocess/exec'],
              findings: {
                new: [
                  {
                    finding_id: findingId,
                    fingerprint: 'fp_cmd_injection_42',
                    severity: 'high',
                    rule_id: 'B602:subprocess_popen_with_shell_equals_true',
                    message: 'Subprocess call with shell=True identified in webhook.py:32',
                    file: 'src/webhook.py',
                    line: 32,
                    has_verified_fix: true,
                    fix_attempt_id: 'fix-att-golden-1'
                  }
                ],
                fixed: [],
                existing_touched: [],
                hidden_existing_count: 2
              },
              dependency_changes: [],
              delta_since_previous_push: {
                new_count: 1,
                fixed_count: 0,
                delta_new: 1,
                delta_fixed: 0
              },
              verdict: 'block',
              reasons: [
                '1 new finding(s) meet or exceed repository block threshold (high).'
              ],
              actions: [
                {
                  priority: 2,
                  category: 'high_finding',
                  title: '[HIGH] Remediate B602:subprocess_popen_with_shell_equals_true in src/webhook.py:32',
                  description: 'Subprocess call with shell=True',
                  file: 'src/webhook.py',
                  line: 32
                }
              ]
            }
          }
        })
      });
    });

    // 6. Mock Findings List & Detail
    await page.route(new RegExp(`/api/repos/${repoId}/findings(\\?.*)?$`), async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          findings: [
            {
              id: findingId,
              repo_id: repoId,
              fingerprint: 'fp_cmd_injection_42',
              rule_id: 'B602:subprocess_popen_with_shell_equals_true',
              severity: 'high',
              title: 'Subprocess execution with shell=True',
              filepath: 'src/webhook.py',
              line_number: 32,
              code_snippet: '32: subprocess.run(f"verify {token}", shell=True)',
              first_seen_commit: 'f1e2d3c4',
              first_seen_at: new Date().toISOString(),
              last_seen_at: new Date().toISOString(),
              state: 'open'
            }
          ],
          total_count: 1,
          page: 1,
          per_page: 20
        })
      });
    });

    // 7. Mock Finding Fix and Fix PR
    await page.route(`/api/repos/${repoId}/findings/${findingId}/fix`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          fix_attempt: {
            id: 'fix-att-golden-1',
            finding_id: findingId,
            repo_id: repoId,
            status: 'verified',
            provider: 'gemini',
            model: 'gemini-1.5-flash',
            target_file: 'src/webhook.py',
            start_line: 30,
            end_line: 35,
            diff: '--- src/webhook.py\n+++ src/webhook.py\n@@ -32,1 +32,1 @@\n-subprocess.run(f"verify {token}", shell=True)\n+subprocess.run(["verify", token], shell=False)',
            explanation: 'Disabled shell=True and passed arguments as a list.',
            verification_json: {
              syntax_valid: true,
              issue_resolved: true,
              zero_new_regressions: true
            },
            created_at: new Date().toISOString()
          }
        })
      });
    });

    await page.route(`/api/repos/${repoId}/findings/${findingId}/fix/pr`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pr_number: 43,
          pr_url: 'https://github.com/vanguard-team/production-api/pull/43',
          branch_name: 'cv/fix-B602-f1e2d3c4'
        })
      });
    });
  });

  test('Step 1: Sign in and landing experience', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=Sign in to CodeVanguard')).toBeVisible();
    await expect(page.locator('text=Continue with GitHub')).toBeVisible();
    await expect(page.locator('text=Your source code is never stored.')).toBeVisible();
  });

  test('Step 2: Connect and view installed repository', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('text=Repositories')).toBeVisible();
    await expect(page.locator('text=vanguard-team/production-api')).toBeVisible();
  });

  test('Step 3: Repository overview, scan baseline, and score trend', async ({ page }) => {
    await page.goto(`/repos/${repoId}`);
    await expect(page.locator('text=vanguard-team/production-api')).toBeVisible();
    await expect(page.locator('text=Scan now')).toBeVisible();
    await expect(page.locator('text=Pull requests')).toBeVisible();
    await expect(page.locator('text=Add payment webhook processor')).toBeVisible();
    await expect(page.locator('text=BLOCK')).toBeVisible();
  });

  test('Step 4: Pull Request detail review with deterministic facts', async ({ page }) => {
    await page.goto(`/repos/${repoId}/pulls/${prNumber}`);
    await expect(page.locator('text=Pull Request #42')).toBeVisible();
    await expect(page.locator('text=Add payment webhook processor')).toBeVisible();
    await expect(page.locator('text=BLOCK')).toBeVisible();
    await expect(page.locator('text=auth')).toBeVisible();
    await expect(page.locator('text=subprocess/exec')).toBeVisible();
    await expect(page.locator('text=Subprocess call with shell=True identified')).toBeVisible();
  });

  test('Step 5: Findings drawer, verified fix inspection, and open PR', async ({ page }) => {
    await page.goto(`/repos/${repoId}/findings`);
    await expect(page.locator('text=Subprocess execution with shell=True')).toBeVisible();
    
    // Open finding side drawer
    await page.click('text=Subprocess execution with shell=True');
    await expect(page.locator('text=Finding Details')).toBeVisible();
    await expect(page.locator('text=Automated Verified Patch')).toBeVisible();
    await expect(page.locator('text=VERIFIED')).toBeVisible();
    
    // Click Open Fix Pull Request
    const openPrBtn = page.locator('button:has-text("Open Fix Pull Request")');
    await expect(openPrBtn).toBeVisible();
    await openPrBtn.click();
    
    // Check confirmation of created PR
    await expect(page.locator('text=Pull Request #43 Opened')).toBeVisible();
  });
});
