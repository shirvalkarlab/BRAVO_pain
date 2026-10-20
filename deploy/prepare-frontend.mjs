// The Django-served page and Caddy assets must identify the same accepted build.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
const revision = process.env.REACT_APP_BUILD_REVISION;
if (!revision || !/^[a-f0-9]{40}$/.test(revision)) {
  throw new Error("A full accepted Git commit is required for a deployable build");
}
let html = readFileSync("build/index.html", "utf8");
const assets = {};
for (const match of html.matchAll(/(?:src|href)="(\/static\/[^\"]+)"/g)) {
  const path = match[1];
  assets[path] = createHash("sha256").update(readFileSync(`build${path}`)).digest("hex");
}
html = html.replace("</head>", `<meta name="bravo-build-revision" content="${revision}"></head>`);
html = html.replace(/<body([^>]*)>/, "<body$1>{% csrf_token %}");
writeFileSync("build/index.html", html);
writeFileSync("build/static/build-identity.json", JSON.stringify({ revision, assets }));
