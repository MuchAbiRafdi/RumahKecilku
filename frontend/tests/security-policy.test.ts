import assert from 'node:assert/strict';
import test from 'node:test';
import { buildContentSecurityPolicy } from '../lib/security-policy';

test('React eval is allowed only for the Next development server', () => {
  const previewDevelopmentPolicy = buildContentSecurityPolicy(true, true);
  const productionPolicy = buildContentSecurityPolicy(false, true);
  const productionPolicyOutsidePreview = buildContentSecurityPolicy(false, false);

  assert.match(previewDevelopmentPolicy, /script-src[^;]*'unsafe-eval'/);
  assert.match(previewDevelopmentPolicy, /connect-src 'self' ws: wss:/);
  assert.match(previewDevelopmentPolicy, /frame-ancestors 'self' https:\/\/arena\.ai/);
  assert.doesNotMatch(productionPolicy, /'unsafe-eval'/);
  assert.doesNotMatch(productionPolicyOutsidePreview, /'unsafe-eval'/);
  assert.match(productionPolicy, /frame-ancestors 'self'/);
});
