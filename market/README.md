# dsh-greatwall-agent — market artifacts

This directory is the **plugin-market index** for `dsh-greatwall-agent` plus its icon.
It is served as static files; nothing here is part of the npm tarball (`package.json`
`files` does not list `market/`).

| Path | Served as |
| --- | --- |
| `market/index.json` | the index source users add in DSH |
| `market/icons/dsh-greatwall-agent.svg` | the card icon (copy of the package `icon.svg`) |

---

## The honest picture: DSH has no central market

DeepSeek Harness ships **no official plugin market and no default index source**. The
official guide is explicit — *"DSH ships no index source"* — and describes publishing as
"write or generate an index file and serve it, together with its icon files, from any
static host".

Sources (verified 2026-11-07 against the running DSH `0.2.2-rc.1`):

- Guide: <https://deepseek-harness.github.io/deepseek-harness/en/guide/plugin-market.md>
- Pinned format note (the executable rule set for `0.2.2-rc.1`):
  <https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.1/.agents/notes/implemented/feature/2026-10-02-plugin-market-index-format.md>

So "publishing to the DSH plugin market" means one of the two channels below. This
package uses **both**.

---

## Channel A — Open Plugin Market (community, recommended for reach)

The community project **开放插件市场 / Open Plugin Market** is a third-party index with
roughly a thousand listed plugins. It is **not affiliated with DeepSeek** and is
GPL-3.0-licensed; the plugin keeps its own MIT license.

| | |
| --- | --- |
| Site | <https://dshopen.org/> · <https://dshopen.org/zh/> |
| Index source to add in DSH | `https://dshopen.org/index.json` |
| Index repository | <https://github.com/polang233/dsh-plugin-index> |
| Submit a plugin | <https://github.com/polang233/dsh-plugin-index/issues/new?template=plugin-add.yml> |

The live index is `format: 1` (1,055 plugins, ~1.6 MB at the time of writing), so a
`dsh-greatwall-agent` listing appears in Discover alongside any other source.

Submission is **one GitHub issue** (`[plugin-add] …`) reviewed by hand. Per
[`.github/CONTRIBUTING.md`](https://github.com/polang233/dsh-plugin-index/blob/main/.github/CONTRIBUTING.md)
a listing needs:

- a public npm release (or a pinned full 40-character commit);
- `dsh.bundle.patch` declared in `package.json`, **with the patch file inside the published package**;
- a public source repository and a clear license — the `license` field *and* a `LICENSE` file;
- a clear purpose (maintainers write the Chinese and English descriptions);
- compatibility declared in `engines.dsh` (or DSH-related `peerDependencies`).

`dsh-greatwall-agent` satisfies all of these: npm `dsh-greatwall-agent`, MIT + `LICENSE`,
`dsh.bundle.patch: ./cordis.patch.yml` shipped in the tarball,
`engines.dsh: ">=0.2.2-rc.1 <0.3.0-0"`. Listed plugins follow npm's `latest` tag, and
**each new release needs a re-review** — reply in the same issue instead of opening a new one.
Unanswered issues are closed after 7 days.

The exact submit command and the ready-to-paste body live in [`../RELEASE.md`](../RELEASE.md)
step 6 and [`../.release/issue-body.md`](../.release/issue-body.md).

## Channel B — this self-hosted index (zero intermediaries)

The index in this directory is a complete `format: 1` market with one plugin and one
version. Adding it needs no review, no third party, and no account:

| | |
| --- | --- |
| **Primary URL (GitHub Pages)** | `https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json` |
| Fallback (raw file) | `https://raw.githubusercontent.com/Qingzhu093/dsh-greatwall-agent/main/market/index.json` |

Use the **Pages** URL: it is a real static host, serves `application/json` with a 2xx and
no redirects, and the guide names GitHub Pages as a supported host. The `raw.githubusercontent.com`
URL works too (`text/plain`, `access-control-allow-origin: *`, ~5 minute cache) and is handy
for verifying a push immediately, but it is rate-limited and not a documented market host —
do not print it in user-facing copy.

Prefer Pages over a self-run server: the plugin installer fetches the index and then the
npm tarball. Serving the index over plain `http:` lets anyone on the network path change
it — and with it the install specs. Use `https:`.

### Adding this index in DSH (exact steps)

1. **Plugins** → **More** (beside *Experimental plugins*) → switch on **Custom plugin markets**.
   A **Discover** tab appears next to *Installed*.
2. **Discover** → **Add index source** → paste the index URL.
   The URL must use `http:`/`https:` and must not contain a user name, a password, or a `#` fragment.
3. Search for `greatwall` → open the **Great Wall Agent V4.2** card → **Install** →
   confirm `dsh-greatwall-agent@4.2.0`.
4. If the source is rejected, **Manage index sources…** shows the reader's error and the
   JSON path of the offending value. Run `node .release/verify-index.mjs --strict` locally first.

Each index source belongs to the current DSH profile, so every teammate/profile must add it once.

---

## The `__PUBLISH_TIMESTAMP__` placeholder

The index is committed **before** the npm release exists, but a version's
`publishTimestamp` must be an integer Unix timestamp in `[0, 10^11)` (GitHub Pages cannot be
made to substitute anything). So the committed index carries the literal token
`"__PUBLISH_TIMESTAMP__"` and the **Lead substitutes real Unix seconds right after
`npm publish`** — that substitution is a release-time step, never a manual guess:

```powershell
node .release/finalize-index.mjs          # dry run: reads the real time from the npm registry
node .release/finalize-index.mjs --write  # substitute it into market/index.json
node .release/verify-index.mjs --strict   # must pass before the final push
```

`verify-index.mjs` accepts the placeholder in its default mode (with a warning) so the
committed file is always checkable; `--strict` — the publish gate — rejects it.

**Never enable Pages or tell a user to add the URL while the placeholder is still in the
index: the reader rejects the whole index on that field, so the source shows an error
instead of a plugin card.**

---

## What the reader checks (rules this index obeys)

From the pinned format note; violations reject the **entire** index, not just one entry.

| Rule | Where it lands here |
| --- | --- |
| `format` is the integer `1` | `"format": 1` |
| root `title` required `LocalizedText` | `{ "en": …, "zh": … }` |
| `LocalizedText` objects must contain `en`; keys are lowercase language ids; no whitespace-only string | both languages present |
| plugin `name` is a valid npm package name, unique in the index | `dsh-greatwall-agent` |
| each version needs exact SemVer `version`, integer `publishTimestamp`, `source` | `4.2.0` |
| `engines` **and** `engines.dsh` are required | `">=0.2.2-rc.1 <0.3.0-0"`, copied unchanged from `package.json` |
| `engines.dsh` is evaluated with `includePrerelease: true` against the running DSH | `0.2.2-rc.1` satisfies it (checked by `verify-index.mjs`) |
| icon: inline `data:` (≤ 32 KiB) or a URL that resolves to `https:` or the index origin | `icons/dsh-greatwall-agent.svg`, relative → same origin |
| `repository.url` is a web page URL, no credentials/query/fragment; `directory` optional | `https://github.com/Qingzhu093/dsh-greatwall-agent` |
| unknown members are ignored | extra `metadata.keywords` is safe |
| a `dist-tags` target must be an exact listed version | `"latest": "4.2.0"` |
| index: UTF-8 JSON, 2xx, no redirects, ≤ 128 MiB | Pages serves it directly |

**Divergence worth knowing:** the guide calls `engines.dsh` optional ("absent means any"),
while the pinned note makes `engines` + `engines.dsh` **required** and says the reader
rejects a version without one. This index always declares it, which satisfies both.

Not used here, but supported if the market grows: `metadata.categories` / `labels` /
`sortKeys` declarations (a reference to an undeclared id is rejected), a `data:` inline icon,
git `source` entries, and multiple versions per plugin (newest first is conventional but
order does not select the install version — `dist-tags` and the recommended-version rule do).

---

## Maintaining this index

1. Bump `package.json` `version`; keep `engines.dsh` in the index identical to the manifest.
2. Add the new version object to `plugins[0].versions` (keep `4.2.0` for older releases) and
   point `dist-tags.latest` at the new version.
3. `node .release/verify-index.mjs` in default mode still passes with the placeholder.
4. Publish, then `node .release/finalize-index.mjs --write` and `node .release/verify-index.mjs --strict`.
5. Push; wait for the Pages build; re-check the live URL (see `RELEASE.md` step 7).
6. New release ⇒ reply in the Open Plugin Market issue for a re-review.

Keep `market/icons/dsh-greatwall-agent.svg` byte-identical to `../icon.svg`
(and `../greatwall-agent/assets/logo.svg`); re-copy it if the logo changes.
