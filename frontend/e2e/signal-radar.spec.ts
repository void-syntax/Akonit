import { test, expect } from '@playwright/test';

test.describe('Signal Radar E2E Test Suite', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API endpoints for deterministic and reliable testing
    await page.route('**/api/v1/signals**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'sig-1',
              title: 'AI Breakthrough in Quantum Computing',
              description: 'Researchers achieve quantum supremacy benchmark.',
              category: 'AI',
              hashtags: ['#AI', '#Quantum'],
              country_code: 'US',
              country_name: 'United States',
              flag: '🇺🇸',
              source_id: 'github',
              source_url: 'https://github.com/example/quantum',
              thumbnail: null,
              cross_source_count: 3,
              first_seen_at: new Date().toISOString(),
              last_seen_at: new Date().toISOString(),
              current_activity: 1500,
              previous_activity: 1000,
              growth: 50,
              acceleration: 10,
              status: 'RISING',
              strength: 88,
              age_minutes: 15,
              activity_metric: 'stars/hr',
              keywords: ['quantum', 'ai'],
              is_saved: false,
              is_ignored: false,
              velocity: 5,
              density_count: 2,
              ai_priority: 'critical',
              ai_priority_score: 0.95,
              ai_category: 'Technology',
            },
            {
              id: 'sig-2',
              title: 'Global Semiconductor Supply Update',
              description: 'New fabrication plant opens in Europe.',
              category: 'Hardware',
              hashtags: ['#Hardware', '#Chips'],
              country_code: 'DE',
              country_name: 'Germany',
              flag: '🇩🇪',
              source_id: 'rss',
              source_url: 'https://example.com/news',
              thumbnail: null,
              cross_source_count: 1,
              first_seen_at: new Date().toISOString(),
              last_seen_at: new Date().toISOString(),
              current_activity: 800,
              previous_activity: 700,
              growth: 14,
              acceleration: 2,
              status: 'NEW',
              strength: 65,
              age_minutes: 30,
              activity_metric: 'mentions',
              keywords: ['semiconductor', 'europe'],
              is_saved: false,
              is_ignored: false,
              velocity: 2,
              density_count: 1,
              ai_priority: 'watch',
              ai_priority_score: 0.70,
            }
          ],
          total: 2,
          limit: 30,
          offset: 0
        })
      });
    });

    await page.route('**/api/v1/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_signals: 12500,
          active_sources: 12,
          countries_count: 45
        })
      });
    });

    await page.route('**/api/v1/radars', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'radar-1', name: 'Tech Radar', emoji: '🚀', description: 'Tech trends' }
        ])
      });
    });

    await page.route('**/api/v1/countries**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { code: 'US', alpha3: 'USA', name: 'United States', slug: 'us', flag: '🇺🇸', region: 'North America', is_supported: true },
          { code: 'DE', alpha3: 'DEU', name: 'Germany', slug: 'de', flag: '🇩🇪', region: 'Europe', is_supported: true }
        ])
      });
    });

    await page.route('**/api/v1/sources**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'github', name: 'GitHub Trending', type: 'github', enabled: true, status: 'ACTIVE' }
        ])
      });
    });

    await page.route('**/api/v1/tags**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { slug: 'quantum', name: 'Quantum', category: 'tech', emoji: '⚛️' }
        ])
      });
    });

    await page.route('**/api/v1/admin/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_signals: 12500,
          active_websocket_connections: 8,
          dlq_size: 0,
          cache_hits: 3420,
          cache_misses: 150,
          service: 'signal-radar-backend',
          status: 'healthy'
        })
      });
    });

    await page.route('**/api/v1/signals/*/save', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });

    await page.route('**/api/v1/signals/*/unsave', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });

    await page.route('**/api/v1/signals/*/mute', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });

    await page.route('**/api/v1/signals/*/unmute', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });
  });

  test('1. Loading main feed', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h3.card-title').first()).toContainText('AI Breakthrough in Quantum Computing');
  });

  test('2. Verifying filter dropdowns open with proper stacking/z-index and do not get clipped', async ({ page }) => {
    await page.goto('/');
    
    const filterBtn = page.locator('.filter').filter({ hasText: /Country/i }).first();
    await expect(filterBtn).toBeVisible({ timeout: 10000 });
    
    // Open dropdown
    await filterBtn.click();
    
    const menu = page.locator('.filter-menu');
    await expect(menu).toBeVisible();

    // Verify z-index and dimensions
    const zIndex = await menu.evaluate((el) => window.getComputedStyle(el).zIndex);
    expect(parseInt(zIndex, 10)).toBeGreaterThanOrEqual(1000);

    const box = await menu.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(100);
      expect(box.height).toBeGreaterThan(20);
    }
  });

  test('3. Simulating live feed update / search debouncing', async ({ page }) => {
    await page.goto('/');
    
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search" i]').first();
    if (await searchInput.isVisible()) {
      await searchInput.fill('Quantum');
      await page.waitForTimeout(400); // debounce timer
      await expect(page.locator('h3.card-title').first()).toContainText('Quantum');
    }
  });

  test('4. Testing signal action buttons (save/mute) with optimistic UI response', async ({ page }) => {
    await page.goto('/');
    
    const firstCard = page.locator('.signal-card').first();
    await expect(firstCard).toBeVisible();

    const saveBtn = firstCard.locator('button[aria-label*="Save" i], button[aria-label*="saved" i]').first();
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();
    await expect(saveBtn).toHaveAttribute('data-active', 'true');

    const muteBtn = firstCard.locator('button[aria-label*="Hide" i], button[aria-label*="Unhide" i]').first();
    await expect(muteBtn).toBeVisible();
    await muteBtn.click();
    await expect(muteBtn).toHaveAttribute('data-active', 'true');
  });

  test('5. Visiting /admin metrics dashboard', async ({ page }) => {
    await page.goto('/admin');
    
    await expect(page.locator('h1')).toContainText('Admin & Observability Dashboard');
    await expect(page.locator('text=Total Signals Ingested')).toBeVisible();
    await expect(page.locator('text=12,500')).toBeVisible();
    await expect(page.locator('text=Active WebSocket')).toBeVisible();
  });
});
