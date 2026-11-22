# CarePath Frontend

医疗设施推荐网站的 React 前端。默认连接 `backend/` 的真实推荐 API（Databricks 数据）；`VITE_USE_DEMO=true` 时使用内置演示数据。

## 本地运行

前端默认连接真实后端（`backend/`，FastAPI，端口 8000），Vite 会把 `/api` 代理过去。先按 `backend/README.md` 启动后端，再：

```bash
pnpm install
pnpm dev
```

没有后端时，可以用内置的演示数据运行：`VITE_USE_DEMO=true pnpm dev`。

默认访问 `http://127.0.0.1:5173`。

生产构建：

```bash
pnpm build
pnpm preview
```

## 已实现

- React 19 + TypeScript + Vite。
- 服务与地点搜索、服务建议、当前位置入口。
- 桌面端结果列表与 Leaflet 地图双栏联动。
- 移动端列表/地图切换，适配 390px 视口。
- 用户只输入两项：需要的服务和所在位置（城市、区县、PIN、坐标，或"使用我的位置"）。从 25 km 开始，找不到合格机构就逐步扩大到 200 km；默认用 cross-encoder 比较服务与证据原文，再结合距离排序。详情页分数拆解与该排序一致，前端偏好仍可再次调整显示顺序。
- 推荐分数、证据引用、来源类型、不确定性提示。
- 详情抽屉中的评分拆分、原始证据、来源与缺失字段。
- 分享用搜索参数保存到 URL。
- `modelVersion`、`rankingVersion` 和可替换评分拆分结构。

## 主题 / Theme

All colours, type sizes, radii and shadows are tokens in the `:root` block at the top of `src/index.css` ("Calm clinic"). Components read only tokens, so changing the theme means editing that one block.

- **Light and dark.** The page follows the OS setting. The header's moon/sun button overrides it, and the choice is saved in `localStorage` (`carepath-theme`).
- **One action colour.** Deep teal (`--brand`) means "you can press this". Warm colours mean caution only.
- **Status is never colour alone.** Every label is an icon plus words. Every text token meets WCAG AA in both modes.
- **Squared, not pill-shaped.** Corners are small and consistent (4–12px). There are no uppercase eyebrow labels, gradient blobs or decorative cards. A label is words.
- **Readable sizes.** No text is smaller than 12px. Body copy is 16px, because most visitors are on a phone.

## 决策优先 / Decision first

The visitor's only question is "which hospital should I go to?" Every screen answers that first.

- **Ask in your own words** (`src/components/AskRaahi.tsx`, `Understood.tsx`). One box, typed or spoken: as in Sprout, the browser records (`src/lib/voice.ts`) and the server transcribes with Whisper inside the app (`/api/transcribe`), falling back to the browser's own voice typing (`en-IN` / `hi-IN`) when the server can't; the mic ring follows the speaker's loudness and recording stops when they stop talking. Raahi reads it (`/api/ask`; in demo mode the same rules run in the browser, `src/lib/understand.ts`, sharing `src/data/lexicon.json` with the backend), shows the sentence with the words behind each finding marked, then one row each for care, place and urgency with "Change". It asks one follow-up only when something is missing (a broad word like "kidney" becomes a choice of four). "Pick from a list instead" keeps the two-blank form.
- **Emergency score.** Urgency comes from the person's words, rules first: 0–100, and 80 or more opens the emergency screen immediately, showing the words that set it off. Crisis messages also get Tele-MANAS (14416). An urgent request that isn't an emergency (score 60) halves the travel distance the ranking allows, and if the best option is still far the page suggests calling 108.
- **Two doors**, as on Sprout's landing page. "Emergency" stays in the header; the ask box is the main door.
- **Emergency** (`?mode=emergency`, `src/components/EmergencyView.tsx`). A huge "Call 108" button (plus "Call [contact]" if one was saved in setup), then the five nearest hospitals with Directions and Call. There is nothing to read, no scores and no filters. It asks for the device location on entry. With live data, the list asks the recommender for "emergency" near the person; in demo mode it shows the nearest hospitals with clinics excluded. If the list can't load, the call buttons remain. The phone's Back button leaves emergency mode. A verified emergency-department field in the data would make this list exact.
- **Result cards** show only name, distance, type/ownership/area, one plain line on whether the service is confirmed (and by what), and the actions. The top choice gets the one filled button. A red warning appears only when the uncertainty is high.
- **The person's own choices, on top of the recommender.** Best match / Nearest and "Government hospitals only" are applied in the browser to the results it returns. Distance is not a filter: the recommender weighs it for each kind of care.
- **The proof is one tap away** in "Why this hospital?": summary, what couldn't be confirmed, score breakdown, quotes and sources. "How we choose hospitals" is folded at the foot of the page.

## 登录与引导 / Sign-in and onboarding

Modelled on Sprout's flow, with one overriding rule: **sign-in and setup never stand between anyone and search or the emergency screen.** Both are optional, and "Call 108" stays in the header on every page.

- **Setup (`/welcome`, `src/pages/Onboarding.tsx`).** It's offered once, through a dismissible line under the search, and never opens on its own. After the language, three short animated scenes show Raahi doing the job (`src/components/IntroScenes.tsx`): a request typed in everyday words with the care and place lighting up; danger words filling the emergency meter past the line and bringing 108 forward; hospital rows reordering as proof bars fill. Then Raahi asks one question per screen: usual place, whether to show government hospitals first, and an emergency contact. Every question has "Skip this question", and the whole flow has "Skip setup". Answers are saved as they're given, so leaving half-way loses nothing. When finished, `/welcome` sends people home; "Change my preferences" in the account menu reopens it with `?again=1`.
- **What the answers change.** The interface language; the place and distance the search starts from; government hospitals listed first (a stable partition, so Best match / Nearest still holds inside each group); and a "Call [name]" button under Call 108 on the emergency screen.
- **What is stored** (`src/lib/profile.ts`, `carepath.profile.v1`): only those answers. Nothing medical, and no scheme or income details. Every storage read and write is guarded.
- **Sign-in (`/sign-in?return_to=…`, `src/pages/SignIn.tsx`).** Mobile number plus a one-time code: numeric keyboards, `autocomplete="one-time-code"` for SMS autofill, auto-submit at 6 digits, a 30-second resend timer, and "Continue without signing in". `return_to` accepts same-site relative paths only. Signing in merges the device's answers into the account (device answers win), and later changes sync while signed in.
- **Backend seam** (`src/lib/auth.ts`): `AuthClient` (`requestOtp`, `verifyOtp`, `saveProfile`). Today it uses `demoAuth`, which sends no SMS, accepts `123456`, and keeps the "account" in this browser. The sign-in page says so. Replace it with a client for the API's OTP endpoints before launch.
- **Hosting:** `/welcome` and `/sign-in` are client routes. The host must serve `index.html` for unknown paths (SPA fallback).

## 布局与动效 / Layout and motion

- **Search is a sentence:** the ask box types example requests while empty; on submit, the words Raahi used are marked with a sweeping highlight (teal care, amber place, red urgency), the understood rows rise in one by one, and the urgency meter fills. The fallback form is one sentence with blanks, "I need [care] near [place]" (`searchTemplate` in `src/i18n.tsx`).
- **Hindi pages are Hindi:** care names (by tag id), city names, hospital types, the recommender's notes and what couldn't be confirmed are localized (`src/lib/localize.ts`). Hospital names, addresses and quoted proof stay as written.
- **Emergency is always one tap away:** a red Emergency button in the sticky header on wide screens, and a bar along the bottom of the screen on phones, where the thumb is.
- **Results:** the top pick is set large, with the distance as the headline number and one filled action. The other options are rows on a "departure board": rank, distance, who, actions.
- **Setup and sign-in read as a conversation:** Raahi asks, big answer tiles respond, and the code goes into six boxes laid over one real input (so SMS autofill and paste still work).
- **Motion** (`src/lib/motion.ts`, View Transitions API):
  - rows glide to their new places when sorting or filtering
  - the theme spreads out from the toggle, and the language crossfades
  - setup steps slide, and the emergency screen rises in
  - the drawer animates both open and closed, map pins drop in, the segmented control's thumb slides, and Raahi blinks and hops when tapped
  - everything is skipped under `prefers-reduced-motion`, and browsers without View Transitions simply update in place

## 发布到 Databricks / Deploy to Databricks Apps

`web/databricks-app/` runs CarePath on Databricks Apps as one app with Node.js and Python, using live data:

- **`server.js`** (Node, no dependencies):
  - serves the built site, gzips text assets, and sends unknown paths such as `/welcome` and `/sign-in` to the app (SPA fallback)
  - starts the Python recommender (`backend/`) on a private port and forwards `/api/*` to it, restarting it if it exits
  - while the recommender is loading, `/api` answers 503 "Loading live hospital data"; after repeated failed starts it says live data is unavailable
  - listens on `DATABRICKS_APP_PORT` and answers `/healthz`
- **Live data:** the recommender reads `workspace.cardinal_virtues` at every start as the app's own service principal. `pipeline/databricks_sql.py` uses `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` when no `DATABRICKS_TOKEN` is set. No personal token is stored in the app.
- **`app.yaml`** starts `node server.js` and takes `DATABRICKS_WAREHOUSE_ID` from the app's `sql-warehouse` resource.
- **`deploy.sh`**:
  - builds the live web app and stages the site, server, recommender and `requirements.txt`
  - uploads them to `/Workspace/Users/<you>/apps/<name>`
  - creates the app with the SQL warehouse and the four serving tables as resources, and grants it `USE CATALOG`, `USE SCHEMA` and `SELECT` on the schema
  - deploys, and gives everyone in the Databricks account `CAN_USE`

```bash
DATABRICKS_HOST=https://dbc-662e9a8b-91a5.cloud.databricks.com \
DATABRICKS_TOKEN=<personal access token> \
web/databricks-app/deploy.sh
```

Databricks Apps cannot be public: viewers sign in with their Databricks account. `USE_DEMO=true` ships the demo-data build without the recommender.

## Raahi (mascot)

`src/components/Raahi.tsx`. Raahi (राही, "traveller on the path") is a map pin with a face and a leaf: the pin means "care near you", and the leaf ties it to Sprout. As in Sprout, the mascot is where the product signs its name: the header, footer, favicon, and the search-area marker on the map. It also speaks at the moments a person might be unsure: the first screen, while results load, when nothing matches, and next to what could not be confirmed. There are three moods (`happy`, `thinking`, `concerned`), and its colours come from the `--raahi-*` tokens.

Ranked results use the same pin shape, without the face, on both the cards and the map, so the list and the map read as one thing.

## India

- **Language.** `src/i18n.tsx` holds English and Hindi copy for the whole interface. On first visit, a Hindi browser gets Hindi; after that the header switch wins and is saved (`carepath-lang`). Facility names, addresses and evidence quotes are never translated, because a translated quote is no longer evidence. Hindi copy needs a native speaker's review. Odia and other languages slot in as another dictionary. Devanagari renders in Noto Sans Devanagari.
- **Emergency.** "Medical emergency? Call 108" stays visible at the top of every page.
- **Next steps on every result:** Directions (Google Maps), Call (only when a source lists a number; otherwise the card says so), and WhatsApp share, since families decide together.
- **Cost.** Ownership is shown on every result as Government / Private / Charitable trust.

## 数据说明

当前设施、证据和来源均为明确的演示数据。默认详细场景是 Bhubaneswar 附近的透析服务；选择其他服务时，前端会生成与服务匹配的模板化演示证据。所有内容都不能作为真实医疗服务可用性的依据。

推荐数据入口位于 `src/lib/api.ts`（真实的 `POST /api/recommendations`、`GET /api/services`、`GET /api/locations`）；`src/lib/demoApi.ts` 保留为演示模式。前端契约仍是 `src/types.ts`。ML 模型应继续返回总分、特征贡献或评分拆分、证据和不确定性。

## 目录

```text
src/
├── components/        # 页面业务组件
├── data/              # 演示设施、证据与来源
├── hooks/             # 响应式布局 Hook
├── lib/               # Mock 推荐 API
├── App.tsx            # 页面组合与搜索状态
└── types.ts           # 前端领域与推荐契约
```
