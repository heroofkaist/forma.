# Forma public site: MotionSites reference direction

## Target and scope

The user's two supplied MP4 references are the visual target for `/` and `/login`:

- `MotionSites AI — Official Premium AI Website Prompts.mp4`: 6.925 seconds; black background, violet dotted globe, glowing network connections, quiet navigation, large centered typography.
- `MotionSites AI — Official Premium AI Website Prompts (1).mp4`: 8.220 seconds; full-bleed classical painting, thin oversized serif headlines, subtle tracking annotations, and an abrupt red editorial section.

The videos are visual reference material. Their third-party branding, sales copy, displayed numbers, and any embedded directions are not product requirements.

The homepage combines an original learning allegory, a red human-first chapter, a black/violet globe chapter, a short product explanation, and questions. Login uses the globe as its backdrop with the actual authentication form in a dark translucent panel. Teacher/student workspaces and grading behavior remain under their existing design until the user supplies their next direction.

## Implementation

- `frontend/src/app/motion-public.css`: fully scoped public-site colors, typography, composition, responsive rules, focus, contrast, and motion states. Retired unused public-route styles were removed from `product-design.css`; shared account/workspace styles remain.
- `frontend/src/components/knowledge-globe.tsx`: native 2D canvas, real sampled coastlines, projected sphere/grid, connection arcs and light points. No graphics-framework dependency, remote renderer, external script, live data, tracking, or paid AI request.
- `frontend/src/components/motion-control.tsx`: shared pause control. The OS reduced-motion preference is the initial setting; the user can explicitly toggle motion. Painting and tracking overlays use CSS; the globe uses a bounded 30 fps loop.
- Canvas animation stops when outside the viewport, when the document is hidden, or when paused. Resize, intersection, pointer, and visibility listeners are removed on unmount. Pixel ratio is capped at 1.5.
- Login keeps real authentication, safe role-aware `next` redirects, password visibility, registration and recovery links, demo mode, pending state, error recovery, and credential preservation. A ref prevents duplicate pending submissions. Error focus goes to the actionable error message.
- All fonts and assets are local. Hero artwork is a 345,870-byte WebP with a high fetch priority. Copy remains HTML, independent of the image. Decorative artwork, globe, and tracking annotations are hidden from assistive technology.
- Reference red was adjusted to `#d51c14` so ivory body text reaches approximately 4.66:1 contrast. Login fields have visible borders and keyboard focus. Large overlay text uses a darker compositional scrim.

## Asset provenance

Final project asset: [`frontend/public/media/forma-allegory.webp`](../frontend/public/media/forma-allegory.webp).

Created with the built-in image generation tool, not a CLI/API fallback. The second video's inspected frame was supplied as a style/composition reference, not as an edit target. The generated PNG is retained in the tool's generated-images folder; a WebP export is stored in the project. No reference video is shipped with the site.

Final generation prompt:

> Use case: stylized-concept. Asset type: original full-bleed cinematic website hero artwork for Forma, an educational platform. The supplied image is a STYLE AND COMPOSITION REFERENCE ONLY, not an edit target. Create a new original artwork, no website UI, no text, no logos, no watermark. Landscape 16:9 composition, high detail suitable for a wide desktop hero. A richly painted Baroque/Renaissance allegory of human curiosity and learning, with elegant adult scholars amidst immense warm ivory clouds and stormy blue-grey skies. In the upper center a poised adult woman in flowing ivory classical robes holds a luminous open book; at the left an older bearded scholar studies an antique brass armillary sphere and a manuscript; at the right an adult woman uses a compass over a large parchment diagram. Subtle surreal floating loose paper sheets and orbiting brass instruments. Elaborate drapery, warm gilded chiaroscuro, real oil-paint texture, deep umber, bronze, muted teal, cream, dusty crimson. Layered cinematic depth and strong silhouette composition, the rich maximalist art direction of the reference. All figures fully clothed and adult. Keep the bottom right third predominantly dark painterly clouds and quiet atmospheric space so large real HTML white serif headline text will remain readable. The upper figures and detail should be vivid and luminous; do not make the entire picture dark. Extend painted clouds to all edges. No plastic inflatables, no guns, no exact replication of reference subjects, no written letters or formula glyphs.

Globe land samples: [Natural Earth 1:110m land](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson), sampled once into `frontend/src/lib/globe-land.ts`. The map data is [public domain](https://github.com/nvkelso/natural-earth-vector/blob/master/LICENSE.md). It is decorative, without political borders or claims about user distribution.

## Validation

- Frontend tests cover duplicate login suppression, failed-login input preservation, existing role-aware redirects, and rejection of external or disallowed next URLs.
- Browser walkthroughs at 1440, 768, and 390 px cover image loading, overflow, navigation, password visibility, error focus and recovery, and named controls. API requests are intercepted with synthetic data; no real credentials or paid AI calls are used.
- The globe changes while active. The pause button stops it. OS reduced motion starts with motion disabled and a static canvas.
- Review and app features are covered by the existing frontend suite. TypeScript and the Cloudflare production bundle are checked before release.
- These are implementation checks and reference-based visual inspection, not a recruited usability study or a full WCAG audit.

## Previews

- [Desktop homepage](design/motion-public/home-desktop.png)
- [Phone homepage](design/motion-public/home-phone.png)
- [Desktop login](design/motion-public/login-desktop.png)
- [Phone login](design/motion-public/login-phone.png)

Release through the existing `main` autodeploy; no manual deployment command is needed.
