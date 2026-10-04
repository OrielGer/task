import { test } from "node:test";
import assert from "node:assert/strict";
import { redactText, sanitizeUrl, REDACTED } from "../src/redaction";

test("sanitizeUrl strips sensitive query values but keeps keys and safe params", () => {
  const out = sanitizeUrl(
    "https://example.com/p?token=abc123&q=marketing&access_token=XYZ&page=2&api_key=secretkey"
  );
  assert.ok(out.includes("q=marketing"));
  assert.ok(out.includes("page=2"));
  assert.ok(!out.includes("abc123"));
  assert.ok(!out.includes("XYZ"));
  assert.ok(!out.includes("secretkey"));
  assert.ok(out.includes("token=" + encodeURIComponent(REDACTED)) || out.includes("token=%5BREDACTED%5D"));
});

test("sanitizeUrl removes embedded credentials (userinfo)", () => {
  const out = sanitizeUrl("https://user:pass@example.com/path");
  assert.ok(!out.includes("user:pass"));
  assert.ok(out.includes("example.com/path"));
});

test("redactText masks Authorization headers and bearer tokens", () => {
  assert.equal(redactText("Authorization: Bearer abcdef123456"), "Authorization: " + REDACTED);
  assert.ok(redactText("here is Bearer sometokenvalue123").includes(REDACTED));
});

test("redactText masks JWTs", () => {
  const jwt = "eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSM";
  assert.ok(redactText(`token=${jwt}`).includes(REDACTED));
});

test("redactText masks key:value secrets", () => {
  assert.ok(redactText('password: hunter2secret').includes(REDACTED));
  assert.ok(redactText('api_key = ABCD1234EFGH').includes(REDACTED));
  assert.ok(!redactText('password: hunter2secret').includes("hunter2secret"));
});

test("redactText masks provider API keys and PEM private keys", () => {
  assert.ok(redactText("sk-ABCDEFGHIJKLMNOPQRST1234").includes(REDACTED));
  assert.ok(redactText("AKIAIOSFODNN7EXAMPLE").includes(REDACTED));
  const pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOg==\n-----END RSA PRIVATE KEY-----";
  assert.equal(redactText(pem), REDACTED);
});

test("redactText masks Luhn-valid credit card numbers", () => {
  assert.ok(redactText("card 4242 4242 4242 4242 on file").includes(REDACTED));
  assert.ok(!redactText("card 4242 4242 4242 4242 on file").includes("4242 4242 4242 4242"));
});

test("business text without secrets is preserved", () => {
  const text = "Turn qualified leads into customers with AI-powered automation.";
  assert.equal(redactText(text), text);
});

test("redaction is idempotent", () => {
  const text = "Authorization: Bearer abc123 and api_key=XYZ987LONGKEY";
  assert.equal(redactText(redactText(text)), redactText(text));
});
