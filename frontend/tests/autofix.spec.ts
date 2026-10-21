import { test, expect } from '@playwright/test';

test.describe('Automated Verified Auto-Fix Flow', () => {
  const repoId = 'repo-fix-999';
  const findingId = 'finding-sqli-01';

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
              full_name: 'octocat/payment-service',
              default_branch: 'main',
              scan_enabled: true,
              autofix_enabled: true
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
            full_name: 'octocat/payment-service',
            default_branch: 'main',
            scan_enabled: true,
            autofix_enabled: true,
            autofix_daily_quota: 20
          },
          installation: {
            id: 'inst-1',
            account_login: 'octocat'
          },
          scans: []
        })
      });
    });

    // 4. Mock quota endpoint
    await page.route(`/api/repos/${repoId}/autofix/quota`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          autofix_enabled: true,
          daily_quota: 20,
          used_today: 2,
          remaining: 18
        })
      });
    });

    // 5. Mock findings endpoint
    await page.route(`/api/repos/${repoId}/findings*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_count: 1,
          page: 1,
          per_page: 15,
          findings: [
            {
              id: findingId,
              repo_id: repoId,
              fingerprint: 'fp_sqli_777',
              rule_id: 'B608:hardcoded_sql_expressions',
              severity: 'critical',
              title: 'Hardcoded SQL injection vulnerability in execute()',
              filepath: 'app/db/users.py',
              line_number: 14,
              first_seen_commit: 'abcdef1234567890',
              first_seen_at: new Date().toISOString(),
              last_seen_at: new Date().toISOString(),
              state: 'open',
              code_snippet: 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")',
              fix_description: 'Use parameterized queries instead of string formatting.'
            }
          ]
        })
      });
    });

    // 6. Mock initial latest fix check (returns null initially)
    await page.route(`/api/repos/${repoId}/findings/${findingId}/fix`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ fix_attempt: null })
        });
      } else if (route.request().method() === 'POST') {
        // Mock generating fix response
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            fix_attempt: {
              id: 'attempt-101',
              finding_id: findingId,
              repo_id: repoId,
              status: 'verified',
              provider: 'gemini',
              model: 'gemini-2.5-flash',
              target_file: 'app/db/users.py',
              target_function: 'get_user_by_id',
              start_line: 12,
              end_line: 16,
              diff: '@@ -12,5 +12,5 @@\n def get_user_by_id(conn, uid):\n     cursor = conn.cursor()\n-    cursor.execute(f"SELECT * FROM users WHERE id = {uid}")\n+    cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))\n     return cursor.fetchone()',
              patch_code: 'def get_user_by_id(conn, uid):\n    cursor = conn.cursor()\n    cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))\n    return cursor.fetchone()',
              explanation: 'Replaced insecure f-string format with parameterized SQL query placeholder.',
              verification_json: {
                is_verified: true,
                scanners_run: ['bandit', 'semgrep'],
                syntax_valid: true,
                original_fingerprint_resolved: true,
                new_findings_count: 0
              },
              created_at: new Date().toISOString()
            }
          })
        });
      }
    });

    // 7. Mock create PR endpoint
    await page.route(`/api/repos/${repoId}/findings/${findingId}/fix/pr`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pr_number: 44,
          pr_url: 'https://github.com/octocat/payment-service/pull/44',
          branch_name: 'cv/fix-hardcoded_sql_expres-fp_sqli_'
        })
      });
    });
  });

  test('generates, verifies, and creates PR from the findings details drawer', async ({ page }) => {
    // Navigate to findings page
    await page.goto(`/repos/${repoId}/findings`);

    // Verify finding row is rendered
    await expect(page.locator('text=Hardcoded SQL injection vulnerability in execute()')).toBeVisible();

    // Click finding row to open drawer
    await page.locator('text=Hardcoded SQL injection vulnerability in execute()').click();

    // Check Auto-Fix section is present
    await expect(page.locator('text=Automated Verified Fix')).toBeVisible();
    await expect(page.locator('text=Generate verified fix')).toBeVisible();

    // Click "Generate verified fix"
    await page.locator('button:has-text("Generate verified fix")').click();

    // Verify verified status chip and verification badges
    await expect(page.locator('text=VERIFIED')).toBeVisible();
    await expect(page.locator('text=✓ Syntax Valid')).toBeVisible();
    await expect(page.locator('text=✓ Issue Resolved')).toBeVisible();
    await expect(page.locator('text=✓ Zero Regressions')).toBeVisible();

    // Verify CodeDiff is rendered with diff lines
    await expect(page.locator('text=cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))')).toBeVisible();
    await expect(page.locator('button:has-text("Open Fix PR")')).toBeVisible();

    // Click "Open Fix PR"
    await page.locator('button:has-text("Open Fix PR")').click();

    // Verify PR created status and GitHub link
    await expect(page.locator('text=PR OPENED')).toBeVisible();
    await expect(page.locator('text=Pull Request #44 created')).toBeVisible();
    await expect(page.locator('a:has-text("View on GitHub")')).toBeVisible();
  });

  test('displays auto-fix configuration toggle and disclosure on settings page', async ({ page }) => {
    await page.goto(`/repos/${repoId}/settings`);

    // Check for Auto-Fix section
    await expect(page.locator('text=Automated Verified Fixes (Auto-Fix)')).toBeVisible();
    await expect(page.locator('text=Auto-Fix Permissions & Privacy Disclosure')).toBeVisible();
    await expect(page.locator('text=Contents: write')).toBeVisible();
  });
});
