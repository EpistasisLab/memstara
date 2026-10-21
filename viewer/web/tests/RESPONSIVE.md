# Responsive UI regression tests

From `viewer/web`:

```sh
npm ci
npx playwright install --with-deps chromium firefox webkit
npm run build
npm run test:responsive
```

The suite starts isolated fixture servers on ports 4175 and 4177. Stop other test
servers using those ports first. Synthetic records replace API responses; these
tests do not start experiments, invoke models, or read production histories.

| Coverage | Method |
| --- | --- |
| Setup, skill instructions, editor | 360–1920px widths, short screens, wheel, keyboard, retained selections |
| Telemetry and reports | 50 loops, long notices/prose, wide tables, pagination |
| Agent outputs and logs | 80 outputs, filtering, keyboard navigation, automatic follow and deliberate scroll-away |
| Workspace and history | Navigation, popovers, 30 pipelines, reachable execution controls |
| Chromium, Firefox, WebKit | Actual engine rendering, not user-agent substitution |
| 125%, 150%, 200% zoom | Chromium `chrome.tabs.setZoom`, verified with getZoom and devicePixelRatio; not CSS zoom or viewport-only simulation |
| Touch | Chromium/WebKit touch selection and rotation; Chromium protocol swipe |

The floor-plan minimum-canvas-height matrix runs at normal zoom; the workspace,
setup, telemetry, reports and output/log suites also run with browser zoom.
Firefox touch emulation and browser-zoom automation outside Chromium are not part
of this harness. WebKit results do not certify the installed Safari application.
Physical trackpad, touch-screen and assistive-technology checks require devices
and human interaction; emulation is not reported as physical-device verification.

CI runs this suite in `responsive-ui`, preserving its HTML report. Local HTML
results are written to `responsive-report/`. Each test attachment records the
viewport checks and failure output. To run one group:

```sh
npm run test:responsive -- --project=webkit --grep responsive-reading
npm run test:responsive -- --project=chromium-200 --grep responsive-history
```
