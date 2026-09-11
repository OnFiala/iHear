import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

// Inspect Git's staged candidate, never print a matching credential value.
const files = execFileSync("git", ["ls-files", "-z"], { encoding: "utf8" })
  .split("\0")
  .filter(Boolean);
let runtimeSecrets = [];
try {
  runtimeSecrets = readFileSync(".env.local", "utf8")
    .split("\n")
    .filter((line) =>
      /^(OPENAI_API_KEY|SUPABASE_SERVICE_ROLE_KEY|IHEAR_RATE_LIMIT_SALT)=/.test(
        line,
      ),
    )
    .map((line) => line.slice(line.indexOf("=") + 1))
    .filter((value) => value.length >= 24);
} catch {
  // A clean checkout has no local credentials to compare.
}
const findings = [];
for (const file of files) {
  if (
    /^(\.local|artifacts|test-results|playwright-report|node_modules)\//.test(
      file,
    ) ||
    /(?:^|\/)\.env(?!\.example$)/.test(file) ||
    /\.(?:wav|pcm|y4m|onnx|tflite|h5|pt|sqlite3?|pdf)$/i.test(file)
  ) {
    findings.push(`${file}: runtime or private artifact path`);
  }
  const content = execFileSync("git", ["show", `:${file}`], {
    maxBuffer: 20_000_000,
  }).toString("utf8");
  if (runtimeSecrets.some((secret) => content.includes(secret)))
    findings.push(`${file}: matches a local runtime secret`);
  if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(content))
    findings.push(`${file}: private key material`);
  if (/\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b/.test(content))
    findings.push(`${file}: possible API credential`);
}
if (findings.length) {
  console.error(findings.join("\n"));
  process.exitCode = 1;
} else {
  console.log(
    `Checked ${files.length} staged/tracked paths: no raw recordings, runtime artifacts or detected credentials.`,
  );
}
