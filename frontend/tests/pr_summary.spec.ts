import { test, expect } from '@playwright/test';

test.describe('Pull Request Security Summary and Reviewer Needs', () => {
  const repoId = 'repo-alpha-101';
  const prNumber = '42';

  test.beforeEach(async ({ page }) => {
    // Mock the session authentication
    await page.route('/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 1,
            username: 'octocat',
            github_login: 'octocat',
            role: 'user'
          }
        })
      });
    });

    // Mock repositories list for RepoSwitcher
    await page.route('/api/repos', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          repositories: [
            {
              id: repoId,
              full_name: 'octocat/codevanguard',
              default_branch: 'main',
              scan_enabled: true
            }
          ]
        })
      });
    });

    // Mock PR detail and deterministic summary
    await page.route(`/api/repos/${repoId}/pulls/${prNumber}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pr_number: 42,
          repo: {
            id: repoId,
            full_name: 'octocat/codevanguard',
            default_branch: 'main',
            scan_enabled: true
          },
          latest_scan: {
            id: 'scan_pr42_head',
            status: 'completed',
            branch: 'feature-secure-auth',
            timestamp: new Date().toISOString(),
            fixed_findings_count: 1,
            total_issues: 2
          },
          new_issues: [
            {
              id: 1,
              rule_id: 'B608:hardcoded_sql_expression',
              severity: 'critical',
              message: 'Possible SQL injection in query builder',
              filepath: 'app/database/query.py',
              line_number: 45,
              scanner: 'bandit',
              fix_title: 'Use Parameterized Query',
              fix_before: 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
              fix_after: 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))'
            },
            {
              id: 2,
              rule_id: 'generic_secret_token',
              severity: 'high',
              message: 'Stripe API key hardcoded',
              filepath: 'app/billing/config.py',
              line_number: 12,
              scanner: 'semgrep',
              fix_title: 'Rotate Stripe API Key',
              fix_before: 'STRIPE_KEY = "sk_live_1234567890"',
              fix_after: 'STRIPE_KEY = os.environ.get("STRIPE_KEY")'
            }
          ],
          existing_issues_count: 5,
          timeline: [
            {
              id: 'scan_pr42_head',
              commit_sha: 'a1b2c3d4e5f6',
              timestamp: new Date().toISOString(),
              verdict: 'BLOCK'
            }
          ],
          summary: {
            id: 'sum_42_1',
            repo_id: repoId,
            pr_number: 42,
            head_sha: 'a1b2c3d4e5f6',
            narrative: 'Pull request #42 introduces 2 new finding(s) including 1 Critical and 1 High severity issue(s). Remediation is required prior to merge.',
            narrative_source: 'template',
            facts: {
              version: 1,
              pr: {
                number: 42,
                title: 'Add billing webhooks',
                author: 'octocat',
                head_sha: 'a1b2c3d4e5f6',
                base_sha: '000000000000',
                files_changed: 2,
                additions: 45,
                deletions: 12
              },
              categories_touched: ['db', 'config/secrets'],
              findings: {
                new: [],
                fixed: [],
                existing_touched: [],
                hidden_existing_count: 5
              },
              dependency_changes: [],
              delta_since_previous_push: {
                new_count: 2,
                fixed_count: 1,
                delta_new: 1,
                delta_fixed: 0,
                previous_head_sha: '998877665544'
              },
              verdict: 'block',
              reasons: ['2 new finding(s) meet or exceed the repository block threshold.'],
              actions: [
                {
                  priority: 1,
                  category: 'critical_finding',
                  title: '[CRITICAL] Remediate B608 in app/database/query.py:45',
                  description: 'Possible SQL injection in query builder',
                  file: 'app/database/query.py',
                  line: 45
                },
                {
                  priority: 2,
                  category: 'secrets_rotation',
                  title: 'Secrets: Rotate leaked secret in app/billing/config.py:12',
                  description: 'Immediately revoke the exposed secret and rotate credentials.',
                  file: 'app/billing/config.py',
                  line: 12
                }
              ],
              omitted_actions_count: 0
            }
          }
        })
      });
    });
  });

  test('renders StatusCard banner, narrative, needs before merge checklist, and delta strip', async ({ page }) => {
    await page.goto(`/repos/${repoId}/pulls/${prNumber}`);

    // 1. Verify StatusCard verdict banner
    await expect(page.getByText('NEEDS ATTENTION')).toBeVisible();
    await expect(page.getByText('2 issues to fix first')).toBeVisible();

    // 2. Verify Reviewer Executive Summary
    await expect(page.getByText('Reviewer Executive Summary')).toBeVisible();
    await expect(page.getByText(/Pull request #42 introduces 2 new finding/)).toBeVisible();

    // 3. Verify Delta & Scope Strip
    await expect(page.getByText('+2 new')).toBeVisible();
    await expect(page.getByText('-1 fixed')).toBeVisible();
    await expect(page.getByText('5 baseline')).toBeVisible();
    await expect(page.getByText('db')).toBeVisible();
    await expect(page.getByText('config/secrets')).toBeVisible();

    // 4. Verify Needs Before Merge checklist
    await expect(page.getByRole('heading', { name: 'Needs Before Merge' })).toBeVisible();
    await expect(page.getByText('[CRITICAL] Remediate B608 in app/database/query.py:45')).toBeVisible();
    await expect(page.getByText('Secrets: Rotate leaked secret in app/billing/config.py:12')).toBeVisible();

    // 5. Test interactive checklist toggle
    const firstChecklistCard = page.locator('text=[CRITICAL] Remediate B608 in app/database/query.py:45').locator('..');
    await firstChecklistCard.click();

    // 6. Verify New Findings section
    await expect(page.getByRole('heading', { name: 'New Findings in this PR' })).toBeVisible();
    await expect(page.getByText('Use Parameterized Query')).toBeVisible();
    await expect(page.getByText('Rotate Stripe API Key')).toBeVisible();

    // 7. Verify Push Timeline
    await expect(page.getByRole('heading', { name: 'Push-by-Push Timeline' })).toBeVisible();
    await expect(page.getByText('a1b2c3d')).toBeVisible();
  });
});
